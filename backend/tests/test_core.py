"""Checks for CI/user execution. These were supplied, not executed during delivery."""
import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Store
from app.logs import redact, excerpt_for_job, validate_evidence
from app.main import create_app, signature_valid


def config(tmp_path):
    return Settings(_env_file=None, data_dir=tmp_path, frontend_dir=tmp_path / "static",
                    github_webhook_secret="w" * 40, dashboard_token="d" * 40,
                    github_repositories="owner/demo")


def sample_run(attempt=1):
    return {"id": 1234, "run_attempt": attempt, "run_number": 7, "name": "Demo CI",
            "status": "completed", "conclusion": "failure", "head_sha": "a" * 40,
            "head_branch": "main", "created_at": "2026-10-17T10:00:00Z"}


def test_signature_rejects_changed_payload():
    body = b'{"action":"completed"}'
    signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert signature_valid(body, signature, "secret")
    assert not signature_valid(body + b" ", signature, "secret")
    assert not signature_valid(body, "", "secret")


def test_database_duplicates_and_reruns(tmp_path):
    store = Store(tmp_path)
    store.initialize()
    first, inserted = store.enqueue("owner/demo", sample_run(), "delivery-1")
    assert inserted
    second, inserted = store.enqueue("owner/demo", sample_run(), "delivery-2")
    assert second == first and not inserted
    third, inserted = store.enqueue("owner/demo", sample_run(2), "delivery-3")
    assert inserted and third != first
    assert store.list()["total"] == 2


def test_interrupted_queue_recovers_and_retry_respects_time(tmp_path):
    store = Store(tmp_path)
    store.initialize()
    record_id, _ = store.enqueue("owner/demo", sample_run())
    item = store.claim()
    assert item["id"] == record_id and item["attempts"] == 1
    assert store.claim() is None
    store.initialize()
    assert store.claim()["id"] == record_id
    store.update(record_id, state="pending", next_attempt_at=time.time() + 60)
    assert store.claim() is None


def test_evidence_cannot_reference_invented_lines():
    excerpt = [{"id": "job1:L4", "text": "ModuleNotFoundError: example", "line": 4, "job_id": 1, "job_name": "test"}]
    analysis = {"category": "Dependency error", "root_cause": "A dependency is missing.",
                "evidence_ids": ["job1:L999"], "suggested_fix": "Install example.",
                "uncertainty": "low", "insufficient_evidence": False}
    result, state = validate_evidence(analysis, excerpt)
    assert state == "inconclusive"
    assert result["category"] == "Unknown" and result["evidence"] == []
    analysis["evidence_ids"] = ["job1:L4"]
    result, state = validate_evidence(analysis, excerpt)
    assert state == "completed" and result["evidence"][0]["text"] == excerpt[0]["text"]


def test_redaction_and_excerpt_line_numbers():
    secret = "a-long-example-private-key-0123456789"
    text = "setup\n2026-10-17T10:00:00.123Z ERROR token=" + secret + "\npassword=hunter2\nfinished"
    clean = redact(text, [secret])
    assert secret not in clean and "hunter2" not in clean
    excerpt = excerpt_for_job(clean, {"id": 88, "name": "test"}, 2000)
    assert any(line["id"] == "job88:L2" and line["text"].startswith("ERROR") for line in excerpt)


def test_webhook_and_dashboard_authentication(tmp_path):
    # No workflow is queued in this test, so the idle worker makes no provider calls.
    app = create_app(config(tmp_path))
    app.state.store.initialize()
    with TestClient(app, raise_server_exceptions=True) as client:
        assert client.get("/api/runs").status_code == 401
        assert client.post("/webhook/github", json={}).status_code == 401
        body = b'{}'
        signature = "sha256=" + hmac.new(b"w" * 40, body, hashlib.sha256).hexdigest()
        response = client.post("/webhook/github", content=body, headers={
            "X-Hub-Signature-256": signature, "X-GitHub-Event": "ping"})
        assert response.json() == {"status": "pong"}
        assert client.get("/api/runs", headers={"Authorization": "Bearer " + "d" * 40}).status_code == 200


def test_signed_unconfigured_repository_rejected(tmp_path):
    app = create_app(config(tmp_path))
    body = json.dumps({"action": "completed", "repository": {"full_name": "other/repo"}, "workflow_run": sample_run()}).encode()
    signature = "sha256=" + hmac.new(b"w" * 40, body, hashlib.sha256).hexdigest()
    with TestClient(app) as client:
        response = client.post("/webhook/github", content=body, headers={
            "X-Hub-Signature-256": signature, "X-GitHub-Event": "workflow_run", "X-GitHub-Delivery": "test-1"})
        assert response.status_code == 403
