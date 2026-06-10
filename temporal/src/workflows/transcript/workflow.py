from __future__ import annotations
import asyncio
import logging
from datetime import timedelta
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from ...activities.transcript import (
        split_transcript,
        update_job_status,
    )
    from .topic_workflow import TopicTicketsWorkflow

logger = logging.getLogger(__name__)

_OPTS = {"start_to_close_timeout": timedelta(minutes=5)}


@workflow.defn
class TranscriptToTicketsWorkflow:
    @workflow.run
    async def run(self, job_id: str, team_id: str, transcript: str) -> dict:
        try:
            await workflow.execute_activity(update_job_status, args=[job_id, "processing"], **_OPTS)

            sections = await workflow.execute_activity(split_transcript, args=[transcript], **_OPTS)

            child_handles = []
            for i, section in enumerate(sections):
                handle = await workflow.start_child_workflow(
                    TopicTicketsWorkflow.run,
                    args=[job_id, team_id, section["text"], section["topic"]],
                    id=f"transcript-{job_id}-topic-{i}",
                )
                child_handles.append(handle)

            results = await asyncio.gather(*child_handles)
            total_tickets = sum(r.get("ticket_count", 0) for r in results)

            await workflow.execute_activity(update_job_status, args=[job_id, "complete"], **_OPTS)
            workflow.logger.info(
                f"Completed job {job_id}: {len(sections)} section(s), {total_tickets} tickets total"
            )
            return {"job_id": job_id, "section_count": len(sections), "ticket_count": total_tickets}

        except Exception as exc:
            await workflow.execute_activity(
                update_job_status, args=[job_id, "error", str(exc)], **_OPTS
            )
            raise
