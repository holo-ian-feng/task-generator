from __future__ import annotations
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from temporalio.client import Client
from temporalio.worker import Worker

from .config import settings
from .activities.transcript import (
    split_transcript,
    fetch_team_members,
    extract_structured_tasks,
    call_ai_for_tickets,
    save_tickets,
    save_task_flows,
    update_job_status,
)
from .workflows.transcript.workflow import TranscriptToTicketsWorkflow
from .workflows.transcript.topic_workflow import TopicTicketsWorkflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

POLL_INTERVAL = 10  # seconds


async def poll_pending_jobs(client: Client) -> None:
    from supabase import create_client
    sb = create_client(settings.supabase_url, settings.supabase_service_role_key)

    while True:
        try:
            res = (
                sb.table("transcript_jobs")
                .select("id, team_id, transcript")
                .eq("status", "pending")
                .execute()
            )
            for job in res.data:
                sb.table("transcript_jobs").update({"status": "processing"}).eq("id", job["id"]).execute()
                await client.start_workflow(
                    TranscriptToTicketsWorkflow.run,
                    args=[job["id"], job["team_id"], job["transcript"]],
                    id=f"transcript-{job['id']}",
                    task_queue=settings.temporal_task_queue,
                )
                logger.info(f"Started workflow for transcript job {job['id']}")
        except Exception as exc:
            logger.error(f"Poller error: {exc}")

        await asyncio.sleep(POLL_INTERVAL)


async def main() -> None:
    logger.info(f"Connecting to Temporal at {settings.temporal_address}")
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)

    activity_executor = ThreadPoolExecutor(max_workers=20)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[TranscriptToTicketsWorkflow, TopicTicketsWorkflow],
        activities=[split_transcript, fetch_team_members, extract_structured_tasks, call_ai_for_tickets, save_tickets, save_task_flows, update_job_status],
        activity_executor=activity_executor,
    )

    logger.info(f"Worker started on task queue '{settings.temporal_task_queue}'")
    await asyncio.gather(worker.run(), poll_pending_jobs(client))


if __name__ == "__main__":
    asyncio.run(main())
