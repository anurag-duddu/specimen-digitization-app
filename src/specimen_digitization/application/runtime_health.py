"""Read-only dependency readiness, cached and serialized to bound probe traffic."""

import threading
import time
from fastapi.responses import JSONResponse


class DependencyReadiness:
    def __init__(self, probe, ttl=15):
        self.probe, self.ttl = probe, ttl
        self.lock = threading.Lock()
        self.checked_at = None
        self.ready = False

    def __call__(self):
        if not self.lock.acquire(blocking=False):
            # Never occupy the shared request pool waiting behind cloud I/O.
            # An in-progress refresh is conservatively not ready.
            return False
        try:
            if (
                self.checked_at is None
                or time.monotonic() - self.checked_at >= self.ttl
            ):
                try:
                    self.ready = self.probe() is True
                except Exception:
                    self.ready = False
                self.checked_at = time.monotonic()
            return self.ready
        finally:
            self.lock.release()


def cloud_probe(repository, blobs, config):
    def probe():
        # Named read-only query plus generation-pinned object metadata; never
        # read image bytes or request bucket-level IAM for a health probe.
        response = repository.session.post(
            repository.url + ":impersonateQuery",
            json={"operationName": "Readiness", "variables": {}},
            timeout=3,
        )
        if response.status_code != 200:
            return False
        body = response.json()
        if body.get("errors") or "data" not in body:
            return False
        blob = blobs.bucket.blob(
            config.readiness_object, generation=config.readiness_generation
        )
        blob.reload(
            timeout=3, retry=None, if_generation_match=config.readiness_generation
        )
        return True

    return probe


def install_health(app, *, mode, provenance, readiness):
    @app.get("/health/live", include_in_schema=False)
    async def live():
        return JSONResponse({"status": "live"}, headers={"Cache-Control": "no-store"})

    @app.get("/health/ready", include_in_schema=False)
    def ready():
        available = readiness()
        return JSONResponse(
            {
                "status": "ready" if available else "not_ready",
                "mode": mode,
                "scope": "sql_query_and_object_metadata"
                if mode == "production"
                else "local_fixture",
            },
            status_code=200 if available else 503,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/version", include_in_schema=False)
    async def version():
        return JSONResponse(
            dict(provenance, mode=mode), headers={"Cache-Control": "no-store"}
        )
