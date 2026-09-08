"""Bounded ASGI drain plus a process deadline for stuck synchronous SDK calls."""

import os
import threading
import uvicorn


class BoundedServer(uvicorn.Server):
    def __init__(self, config, *, hard_shutdown_seconds=9):
        super().__init__(config)
        self.hard_shutdown_seconds = hard_shutdown_seconds
        self.shutdown_timer = None

    def handle_exit(self, sig, frame):
        if self.shutdown_timer is None:
            # Uvicorn cancellation cannot kill Python threads blocked in an SDK.
            # A daemon watchdog bounds process lifetime without replaying requests.
            self.shutdown_timer = threading.Timer(
                self.hard_shutdown_seconds, os._exit, args=(0,)
            )
            self.shutdown_timer.daemon = True
            self.shutdown_timer.start()
        super().handle_exit(sig, frame)


def serve(app, *, host, port):
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        access_log=False,
        proxy_headers=False,
        timeout_graceful_shutdown=8,
        timeout_keep_alive=5,
        limit_concurrency=64,
    )
    BoundedServer(config).run()
