from __future__ import annotations
import logging
from datetime import timedelta
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ...activities.transcript import (
        fetch_team_members,
        extract_structured_tasks,
        save_tickets,
        save_task_flows,
    )

logger = logging.getLogger(__name__)

_OPTS = {"start_to_close_timeout": timedelta(minutes=5)}


@workflow.defn
class TopicTicketsWorkflow:
    @workflow.run
    async def run(self, job_id: str, team_id: str, transcript: str, topic: str) -> dict:
        members = await workflow.execute_activity(fetch_team_members, args=[team_id], **_OPTS)
        result = await workflow.execute_activity(
            extract_structured_tasks, args=[transcript, members], **_OPTS
        )

        if result.get("type") == "workflow":
            flow_ids = await workflow.execute_activity(
                save_task_flows,
                args=[result.get("task_flows", []), job_id, team_id, members, topic],
                **_OPTS,
            )
            workflow.logger.info(f"Topic '{topic}': {len(flow_ids)} task flow(s) created")
            return {"topic": topic, "type": "workflow", "count": len(flow_ids)}
        else:
            ticket_ids = await workflow.execute_activity(
                save_tickets,
                args=[result.get("tickets", []), job_id, team_id, members, topic],
                **_OPTS,
            )
            workflow.logger.info(f"Topic '{topic}': {len(ticket_ids)} ticket(s) created")
            return {"topic": topic, "type": "tickets", "count": len(ticket_ids)}
