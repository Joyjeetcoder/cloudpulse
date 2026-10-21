import asyncio
import json
import logging
import time
from datetime import datetime

from .config import Settings
from .db import Store
from .github import GitHub
from .gemini import analyze
from .logs import redact, excerpt_for_job, validate_evidence
from .schemas import ServiceError

logger = logging.getLogger("cloudpulse")
FAILED = {"failure", "timed_out", "startup_failure"}


def duration(jobs: list[dict]):
    try:
        starts = [datetime.fromisoformat(j["started_at"].replace("Z", "+00:00")) for j in jobs if j.get("started_at")]
        ends = [datetime.fromisoformat(j["completed_at"].replace("Z", "+00:00")) for j in jobs if j.get("completed_at")]
        return max(0, (max(ends) - min(starts)).total_seconds()) if starts and ends else None
    except (ValueError, TypeError):
        return None


class Worker:
    def __init__(self, settings: Settings, store: Store):
        self.settings, self.store = settings, store
        self.github = GitHub(settings)
        self.wake = asyncio.Event()

    async def run(self):
        while True:
            self.wake.clear()
            item = await asyncio.to_thread(self.store.claim)
            if item is None:
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=2)
                except asyncio.TimeoutError:
                    pass
                continue
            try:
                await self.process(item)
            except asyncio.CancelledError:
                raise
            except ServiceError as exc:
                retry = exc.retryable and item["attempts"] < self.settings.max_analysis_attempts
                await asyncio.to_thread(self.store.update, item["id"], state="pending" if retry else "error",
                                        error=str(exc), next_attempt_at=time.time() + 30 * 2**(item["attempts"] - 1))
                logger.warning("Run %s analysis delayed/failed; retry=%s", item["id"], retry)
            except Exception as exc:
                # Never log arbitrary provider bodies, log contents, or secret-bearing exception strings.
                await asyncio.to_thread(self.store.update, item["id"], state="error",
                                        error="An internal processing error occurred. Check the server logs for its error type.")
                logger.error("Run %s internal error type=%s", item["id"], type(exc).__name__)

    async def process(self, item: dict):
        settings = self.settings
        run = await self.github.run(item["repository"], item["run_id"], item["run_attempt"])
        if run.get("status") != "completed":
            raise ServiceError("This workflow attempt is not completed yet.", True)
        if int(run.get("run_attempt", 1)) != item["run_attempt"]:
            raise ServiceError("GitHub returned a different workflow attempt; import the correct attempt again.")
        jobs = await self.github.jobs(item["repository"], item["run_id"], item["run_attempt"])
        safe_jobs = [{"id": j["id"], "name": redact(str(j.get("name", ""))[:200], settings.known_secrets),
                      "conclusion": j.get("conclusion"),
                      "failed_steps": [redact(str(s.get("name", ""))[:200], settings.known_secrets)
                                       for s in j.get("steps", []) if s.get("conclusion") in FAILED]}
                     for j in jobs]
        conclusion = str(run.get("conclusion") or "unknown")
        await asyncio.to_thread(self.store.update, item["id"], conclusion=conclusion,
                                duration_seconds=duration(jobs), jobs_json=json.dumps(safe_jobs),
                                workflow_name=redact(str(run.get("name") or "Workflow")[:200], settings.known_secrets),
                                branch=redact(str(run.get("head_branch") or "")[:200], settings.known_secrets),
                                commit_sha=str(run.get("head_sha") or "")[:64], created_at=run.get("run_started_at") or run.get("created_at"),
                                completed_at=run.get("updated_at"), error=None)
        if conclusion not in FAILED:
            await asyncio.to_thread(self.store.update, item["id"], state="not_required", analysis_json=None,
                                    excerpt_json=None, model=None, usage_json=None)
            return

        failed_jobs = [j for j in jobs if j.get("conclusion") in FAILED]
        notes = []
        if len(failed_jobs) > settings.max_failed_jobs:
            notes.append(f"Only the first {settings.max_failed_jobs} failed jobs were analyzed.")
        failed_jobs = failed_jobs[:settings.max_failed_jobs]
        excerpt = []
        log_dir = settings.data_dir / "logs" / str(item["id"])
        await asyncio.to_thread(log_dir.mkdir, parents=True, exist_ok=True)
        budget = settings.max_excerpt_chars // max(1, len(failed_jobs))
        for job in failed_jobs:
            text, truncated = await self.github.job_log(item["repository"], int(job["id"]))
            text = redact(text, settings.known_secrets)
            await asyncio.to_thread((log_dir / f"{int(job['id'])}.log").write_text, text, encoding="utf-8")
            safe_job = dict(job, name=redact(str(job.get("name", "Job")), settings.known_secrets))
            excerpt.extend(excerpt_for_job(text, safe_job, budget))
            if truncated:
                notes.append(f"Job {job['id']} log exceeded the download limit; its ending may be missing.")
        await asyncio.to_thread(self.store.update, item["id"], excerpt_json=json.dumps(excerpt),
                                log_note=" ".join(notes) or None)
        if not excerpt:
            result = {"category": "Unknown", "root_cause": "No usable failed-job log excerpt was available.",
                      "suggested_fix": "Open the workflow on GitHub to inspect startup or workflow configuration errors.",
                      "evidence_ids": [], "evidence": [], "uncertainty": "high", "insufficient_evidence": True,
                      "evidence_check": "No evidence to check."}
            await asyncio.to_thread(self.store.update, item["id"], state="inconclusive",
                                    analysis_json=json.dumps(result), model=None, usage_json=None)
            return
        metadata = {"repository": item["repository"], "conclusion": conclusion,
                    "jobs": [j for j in safe_jobs if j["conclusion"] in FAILED][:settings.max_failed_jobs]}
        raw, usage = await analyze(settings, metadata, excerpt)
        result, state = validate_evidence(raw, excerpt)
        for key in ("root_cause", "suggested_fix"):
            result[key] = redact(result[key], settings.known_secrets)
        await asyncio.to_thread(self.store.update, item["id"], state=state, analysis_json=json.dumps(result),
                                model=settings.gemini_model, usage_json=json.dumps(usage), error=None)
        logger.info("Run %s analysis %s", item["id"], state)
