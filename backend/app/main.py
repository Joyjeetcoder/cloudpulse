import asyncio
import hashlib
import hmac
import json
import logging
import re
import secrets
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .db import Store
from .github import GitHub
from .logs import redact
from .schemas import ImportRun, ServiceError
from .worker import Worker


def signature_valid(body: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return secrets.compare_digest(expected.encode(), signature.encode())


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    store = Store(settings.data_dir)
    worker = Worker(settings, store)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # HTTP clients must not print URLs containing provider data or credentials.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    @asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(store.initialize)
        task = asyncio.create_task(worker.run(), name="cloudpulse-worker")
        app.state.worker_task = task
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="CloudPulse", version="1.0.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    async def authorized(authorization: str = Header(default="")):
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(token.encode(), settings.dashboard_token.get_secret_value().encode()):
            raise HTTPException(401, "Enter the dashboard access token.", headers={"WWW-Authenticate": "Bearer"})

    @app.get("/healthz")
    async def health():
        task = getattr(app.state, "worker_task", None)
        if task is None or task.done():
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ok"}

    @app.post("/webhook/github")
    async def webhook(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1_000_000:
                raise HTTPException(413, "Webhook payload too large.")
        signature = request.headers.get("x-hub-signature-256", "")
        if not signature_valid(bytes(body), signature, settings.github_webhook_secret.get_secret_value()):
            raise HTTPException(401, "Invalid webhook signature.")
        event = request.headers.get("x-github-event", "")
        if event == "ping":
            return {"status": "pong"}
        if event != "workflow_run":
            return {"status": "ignored", "reason": "Only workflow_run is supported."}
        try:
            payload = json.loads(body)
            if payload.get("action") != "completed":
                return {"status": "ignored", "reason": "Only completed runs are processed."}
            repository = payload["repository"]["full_name"].lower()
            if repository not in settings.repositories_set:
                raise HTTPException(403, "Repository is not configured in GITHUB_REPOSITORIES.")
            run = payload["workflow_run"]
            if run.get("status") != "completed" or int(run["id"]) <= 0 or int(run.get("run_attempt", 1)) <= 0:
                raise ValueError("Invalid run")
            # Initial fields are also redacted before persistence.
            run = dict(run, name=redact(str(run.get("name") or "Workflow"), settings.known_secrets),
                       head_branch=redact(str(run.get("head_branch") or ""), settings.known_secrets))
            delivery = request.headers.get("x-github-delivery", "")
            if not re.fullmatch(r"[A-Za-z0-9-]{1,100}", delivery):
                raise ValueError("Missing delivery id")
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise HTTPException(400, "Invalid workflow_run payload or delivery ID.") from exc
        record_id, inserted = await asyncio.to_thread(store.enqueue, repository, run, delivery)
        worker.wake.set()
        return JSONResponse({"status": "queued" if inserted else "duplicate", "id": record_id}, status_code=202)

    @app.get("/api/config", dependencies=[Depends(authorized)])
    async def config():
        return {"repositories": sorted(settings.repositories_set), "model": settings.gemini_model,
                "gemini_configured": bool(settings.gemini_api_key.get_secret_value()),
                "github_configured": bool(settings.github_token.get_secret_value())}

    @app.get("/api/stats", dependencies=[Depends(authorized)])
    async def stats():
        return await asyncio.to_thread(store.stats)

    @app.get("/api/runs", dependencies=[Depends(authorized)])
    async def runs(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), conclusion: str | None = None):
        return await asyncio.to_thread(store.list, limit, offset, conclusion)

    @app.get("/api/runs/{record_id}", dependencies=[Depends(authorized)])
    async def run_detail(record_id: int):
        item = await asyncio.to_thread(store.get, record_id)
        if item is None:
            raise HTTPException(404, "Run not found.")
        return item

    @app.post("/api/runs/{record_id}/retry", dependencies=[Depends(authorized)])
    async def retry(record_id: int):
        item = await asyncio.to_thread(store.get, record_id)
        if item is None:
            raise HTTPException(404, "Run not found.")
        if not await asyncio.to_thread(store.retry, record_id):
            raise HTTPException(409, "This run is already queued, processing, or needs no analysis.")
        worker.wake.set()
        return {"status": "queued"}

    @app.post("/api/import", dependencies=[Depends(authorized)])
    async def import_run(data: ImportRun):
        repository = data.repository.lower()
        if repository not in settings.repositories_set:
            raise HTTPException(403, "Repository is not configured.")
        try:
            run = await GitHub(settings).run(repository, data.run_id)
        except ServiceError as exc:
            raise HTTPException(502, str(exc)) from exc
        if run.get("status") != "completed":
            raise HTTPException(409, "Wait until the GitHub workflow completes.")
        run = dict(run, name=redact(str(run.get("name") or "Workflow"), settings.known_secrets),
                   head_branch=redact(str(run.get("head_branch") or ""), settings.known_secrets))
        record_id, inserted = await asyncio.to_thread(store.enqueue, repository, run)
        worker.wake.set()
        return {"id": record_id, "status": "queued" if inserted else "already_exists"}

    frontend = settings.frontend_dir.resolve()
    if (frontend / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon():
        path = frontend / "favicon.svg"
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get("/", include_in_schema=False)
    async def index():
        path = frontend / "index.html"
        if not path.is_file():
            return JSONResponse({"message": "Backend ready. Build the frontend or use its Vite development server."})
        return FileResponse(path)

    return app
