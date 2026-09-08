"""Local only Temporal failure experiment; no specimen/model/cloud operations."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.worker import Worker, UnsandboxedWorkflowRunner

ROOT = Path(__file__).parent
ADDRESS = '127.0.0.1:17333'

@activity.defn
async def local_effect(mode: str) -> str:
    state = ROOT / (mode + '.sqlite3')
    with sqlite3.connect(state) as db:
        db.execute('CREATE TABLE IF NOT EXISTS intent (id INTEGER PRIMARY KEY)')
        db.execute('CREATE TABLE IF NOT EXISTS effects (id INTEGER PRIMARY KEY)')
        seen = db.execute('SELECT COUNT(*) FROM intent').fetchone()[0]
        if mode == 'guarded' and seen:
            return 'blocked:external_outcome_unknown'
        db.execute('INSERT OR IGNORE INTO intent VALUES (1)')
        db.execute('INSERT INTO effects DEFAULT VALUES')
        count = db.execute('SELECT COUNT(*) FROM effects').fetchone()[0]
    (ROOT / (mode + '.entered')).write_text(str(count))
    if count == 1:
        await asyncio.sleep(120)  # Parent kills this process, never graceful cleanup.
    return 'completed'

@workflow.defn
class Probe:
    @workflow.run
    async def run(self, mode: str) -> str:
        return await workflow.execute_activity(
            local_effect, mode, start_to_close_timeout=timedelta(seconds=4),
            retry_policy=RetryPolicy(maximum_attempts=2, initial_interval=timedelta(seconds=1)),
        )

async def work():
    client = await Client.connect(ADDRESS)
    async with Worker(client, task_queue='comparison', workflows=[Probe],
                      activities=[local_effect], workflow_runner=UnsandboxedWorkflowRunner()):
        await asyncio.Event().wait()

async def wait_server():
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            return await Client.connect(ADDRESS)
        except Exception:
            await asyncio.sleep(0.2)
    raise RuntimeError('Server unavailable')

def server():
    return subprocess.Popen([str(ROOT / 'temporal'), 'server', 'start-dev', '--headless',
        '--ip', '127.0.0.1', '--port', '17333', '--http-port', '17334',
        '--metrics-port', '17335', '--db-filename', str(ROOT / 'server.sqlite3')],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def start_worker():
    return subprocess.Popen([sys.executable, str(Path(__file__)), 'worker'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

async def main():
    # Refuse to disturb any existing listeners.
    for port in (17333, 17334, 17335):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', port))
    service = worker = None
    rows = []
    try:
        service = server()
        client = await wait_server()
        for mode in ('unguarded', 'guarded'):
            worker = start_worker()
            handle = await client.start_workflow(Probe.run, mode, id='comparison-' + mode,
                                                task_queue='comparison')
            deadline = time.monotonic() + 20
            while not (ROOT / (mode + '.entered')).exists():
                assert time.monotonic() < deadline, 'Activity did not enter'
                await asyncio.sleep(0.05)
            worker.kill()
            worker.wait(timeout=5)
            worker = None
            # Abrupt engine restart too, with persisted event history.
            service.kill()
            service.wait(timeout=5)
            service = server()
            client = await wait_server()
            worker = start_worker()
            result = await asyncio.wait_for(
                client.get_workflow_handle('comparison-' + mode).result(), timeout=40)
            worker.terminate()
            worker.wait(timeout=10)
            worker = None
            with sqlite3.connect(ROOT / (mode + '.sqlite3')) as db:
                effects = db.execute('SELECT COUNT(*) FROM effects').fetchone()[0]
            history = await client.get_workflow_handle('comparison-' + mode).fetch_history()
            (ROOT / (mode + '.history.json')).write_text(history.to_json())
            rows.append({'mode': mode, 'worker_killed': True, 'server_killed': True,
                         'result': result, 'effects': effects, 'history_events': len(history.events)})
        assert rows[0]['effects'] == 2 and rows[0]['result'] == 'completed', rows
        assert rows[1]['effects'] == 1 and rows[1]['result'] == 'blocked:external_outcome_unknown', rows
        print(json.dumps(rows, indent=2))
        (ROOT / 'result.json').write_text(json.dumps(rows, indent=2) + '\n')
    finally:
        for process in (worker, service):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

if __name__ == '__main__':
    asyncio.run(work() if len(sys.argv) > 1 else main())
