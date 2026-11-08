"""Guard graceful indexing shutdown against completed-task callback starvation."""
import importlib
import os
from pathlib import Path
import subprocess
import sys
import textwrap


# Bound a Python 3.12 task-callback ordering regression in a separate process.
def test_drain_returns_when_completed_tasks_still_await_discard_callbacks():
    probe = textwrap.dedent('''\
        """Isolate the retained-completed-task state without real indexing or services."""
        import asyncio
        import faulthandler
        from tribal_kb.service import KnowledgeBaseService

        # Reproduce the callback ordering observed during real indexing shutdown.
        async def main():
            service = object.__new__(KnowledgeBaseService)
            service._index_tasks = set()
            task = asyncio.create_task(asyncio.sleep(0))
            service._index_tasks.add(task)
            task.add_done_callback(service._index_tasks.discard)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert task.done(), "Probe must reach a completed task"
            assert task in service._index_tasks, "Probe must run before discard callback"
            print("completed task still retained", flush=True)
            faulthandler.dump_traceback_later(2, exit=True)
            await service.drain_indexing()
            faulthandler.cancel_dump_traceback_later()
            print("drain returned", flush=True)

        asyncio.run(main())
    ''')
    source_root = Path(importlib.import_module("tribal_kb.service").__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(source_root) + os.pathsep + environment.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True,
        env=environment, timeout=5,
    )
    assert "completed task still retained" in completed.stdout, completed.stdout + completed.stderr
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "drain returned" in completed.stdout
