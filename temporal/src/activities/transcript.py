from __future__ import annotations
import logging
from temporalio import activity
from supabase import create_client
from ..config import settings

logger = logging.getLogger(__name__)


def _supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@activity.defn
def split_transcript(transcript: str) -> list[dict]:
    """Return [{topic, text}] sections. Falls back to one section if no clear divisions."""
    if not settings.azure_ai_endpoint or not settings.azure_ai_key:
        return [{"topic": "General", "text": transcript}]

    import json
    from openai import OpenAI

    client = OpenAI(base_url=settings.azure_ai_endpoint, api_key=settings.azure_ai_key)

    system_prompt = (
        "You are a meeting transcript analyzer. Determine whether a transcript covers multiple "
        "distinct topics, projects, or agenda items. If it does, split it into sections. "
        "Return a JSON object with a 'sections' array where each element has: "
        "'topic' (short descriptive name, max 5 words) and "
        "'text' (the relevant portion of the transcript for that section). "
        "If the transcript is about a single topic or cannot be meaningfully divided, "
        "return a single-element array with topic='General' and the full transcript as text. "
        "Never omit transcript content — every sentence must appear in exactly one section."
    )

    response = client.chat.completions.create(
        model=settings.azure_ai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    result = json.loads(response.choices[0].message.content)
    sections = result.get("sections", [])
    if not sections:
        sections = [{"topic": "General", "text": transcript}]
    logger.info(f"Transcript split into {len(sections)} section(s): {[s['topic'] for s in sections]}")
    return sections


@activity.defn
def fetch_team_members(team_id: str) -> list[dict]:
    sb = _supabase()
    res = sb.table("team_members").select("id, name, role").eq("team_id", team_id).execute()
    return res.data


@activity.defn
def extract_structured_tasks(transcript: str, team_members: list[dict]) -> dict:
    """
    Decides whether the transcript describes sequential tasks (workflow) or
    independent tasks (tickets), then extracts accordingly.
    Returns {type, task_flows, tickets}.
    """
    if not settings.azure_ai_endpoint or not settings.azure_ai_key:
        return {"type": "tickets", "task_flows": [], "tickets": _stub_tickets(team_members)}

    import json
    from openai import OpenAI

    client = OpenAI(base_url=settings.azure_ai_endpoint, api_key=settings.azure_ai_key)

    member_names = ", ".join(m["name"] for m in team_members) if team_members else "none listed"

    system_prompt = (
        "You are a project management assistant. Analyze the meeting transcript and decide:\n\n"
        "WORKFLOW — choose this when tasks have a clear sequential dependency: one must finish "
        "before the next can start (e.g. 'first do X, then Y', 'after X is done start Y', 'X blocks Y').\n\n"
        "TICKETS — choose this when tasks are independent and can be done in any order or in parallel.\n\n"
        "Return a JSON object:\n"
        "{\n"
        '  "type": "workflow" or "tickets",\n'
        '  "task_flows": [   // populate only when type=workflow\n'
        '    {\n'
        '      "title": "short descriptive name for the flow",\n'
        '      "steps": [\n'
        '        {"title": "...", "description": "1-2 sentences", '
        '"assignee_name": "exact name or null", "due_date": "YYYY-MM-DD or null", "step_order": 1},\n'
        '        ...\n'
        '      ]\n'
        '    }\n'
        '  ],\n'
        '  "tickets": [   // populate only when type=tickets\n'
        '    {"title": "...", "description": "1-2 sentences", '
        '"assignee_name": "exact name or null", "due_date": "YYYY-MM-DD or null"}\n'
        '  ]\n'
        "}\n\n"
        f"Team members: {member_names}\n"
        "Only include concrete action items. If type=workflow, tickets must be []. "
        "If type=tickets, task_flows must be []."
    )

    response = client.chat.completions.create(
        model=settings.azure_ai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    result = json.loads(response.choices[0].message.content)
    result.setdefault("type", "tickets")
    result.setdefault("task_flows", [])
    result.setdefault("tickets", [])
    logger.info(
        f"extract_structured_tasks → type={result['type']}, "
        f"flows={len(result['task_flows'])}, tickets={len(result['tickets'])}"
    )
    return result


@activity.defn
def save_task_flows(
    flows: list[dict],
    transcript_job_id: str,
    team_id: str,
    team_members: list[dict],
    topic: str | None = None,
) -> list[str]:
    if not flows:
        return []

    sb = _supabase()
    member_map = {m["name"].lower(): m["id"] for m in team_members}
    flow_ids = []

    for flow in flows:
        flow_res = sb.table("task_flows").insert({
            "transcript_job_id": transcript_job_id,
            "team_id": team_id,
            "title": flow.get("title", "Task Flow"),
            "topic": topic,
        }).execute()
        flow_id = flow_res.data[0]["id"]
        flow_ids.append(flow_id)

        step_rows = []
        for step in flow.get("steps", []):
            assignee_name = step.get("assignee_name")
            assignee_id = member_map.get(assignee_name.lower()) if assignee_name else None
            step_rows.append({
                "task_flow_id": flow_id,
                "title": step.get("title", "Step"),
                "description": step.get("description"),
                "step_order": step.get("step_order", 1),
                "assignee_id": assignee_id,
                "assignee_name": assignee_name,
                "due_date": step.get("due_date"),
            })

        if step_rows:
            sb.table("task_flow_steps").insert(step_rows).execute()

    return flow_ids


@activity.defn
def call_ai_for_tickets(transcript: str, team_members: list[dict]) -> list[dict]:
    if not settings.azure_ai_endpoint or not settings.azure_ai_key:
        logger.warning("Azure AI Foundry not configured — returning stub tickets")
        return _stub_tickets(team_members)

    import json
    from openai import OpenAI

    client = OpenAI(
        base_url=settings.azure_ai_endpoint,
        api_key=settings.azure_ai_key,
    )

    member_names = ", ".join(m["name"] for m in team_members) if team_members else "none listed"

    system_prompt = (
        "You are a project management assistant. Extract action items and tickets from a meeting transcript. "
        "Return a JSON object with a 'tickets' array. Each ticket must have: "
        "'title' (short, imperative phrase), "
        "'description' (1-2 sentences explaining the task), "
        "'assignee_name' (exact name from the team list below, or null if unclear), "
        "'due_date' (ISO date YYYY-MM-DD if a deadline was mentioned, otherwise null). "
        "Only include concrete action items — not discussion points or decisions without next steps."
    )

    user_prompt = (
        f"Team members: {member_names}\n\n"
        f"Meeting transcript:\n{transcript}"
    )

    response = client.chat.completions.create(
        model=settings.azure_ai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    result = json.loads(response.choices[0].message.content)
    tickets = result.get("tickets", [])
    logger.info(f"Azure OpenAI extracted {len(tickets)} tickets")
    return tickets


@activity.defn
def save_tickets(
    tickets: list[dict],
    transcript_job_id: str,
    team_id: str,
    team_members: list[dict],
    topic: str | None = None,
) -> list[str]:
    if not tickets:
        return []

    sb = _supabase()
    member_map = {m["name"].lower(): m["id"] for m in team_members}

    rows = []
    for t in tickets:
        assignee_name = t.get("assignee_name")
        assignee_id = member_map.get(assignee_name.lower()) if assignee_name else None
        rows.append({
            "transcript_job_id": transcript_job_id,
            "team_id": team_id,
            "title": t.get("title", "Untitled ticket"),
            "description": t.get("description"),
            "assignee_id": assignee_id,
            "assignee_name": assignee_name,
            "due_date": t.get("due_date"),
            "topic": topic,
        })

    res = sb.table("tickets").insert(rows).execute()
    return [r["id"] for r in res.data]


@activity.defn
def update_job_status(job_id: str, status: str, error_msg: str | None = None) -> None:
    sb = _supabase()
    data: dict = {"status": status}
    if error_msg:
        data["error_msg"] = error_msg
    sb.table("transcript_jobs").update(data).eq("id", job_id).execute()


def _stub_tickets(team_members: list[dict]) -> list[dict]:
    first = team_members[0]["name"] if team_members else None
    return [
        {
            "title": "Follow up on action items from meeting",
            "description": "Review the discussed items and assign owners. (Stub — connect Azure AI to extract real tickets.)",
            "assignee_name": first,
            "due_date": None,
        }
    ]
