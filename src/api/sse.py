import sys
import asyncio
from typing import Dict, List

# Global dictionaries to track active SSE streams and final job deliverables
job_streams: Dict[str, List[asyncio.Queue]] = {}
job_results: Dict[str, dict] = {}

def _get_event_loop() -> asyncio.AbstractEventLoop:
    """Try to get the running event loop, or None."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None

class SSELogger:
    """
    A file-like object that intercepts sys.stdout.write() calls from a
    synchronous background thread. It routes text to asyncio Queues via
    loop.call_soon_threadsafe() to avoid corrupting the event loop.
    """
    def __init__(self, job_id: str, loop: asyncio.AbstractEventLoop = None):
        self.job_id = job_id
        self.loop = loop
        if job_id not in job_streams:
            job_streams[job_id] = []

    def write(self, text: str):
        if not text.strip() and text != '\n':
            return
        
        # Mirror back to terminal so developers can monitor locally
        sys.__stdout__.write(text)
        sys.__stdout__.flush()
        
        # Post to all active subscribers (thread-safe)
        if self.job_id in job_streams:
            for q in job_streams[self.job_id]:
                if self.loop and self.loop.is_running():
                    self.loop.call_soon_threadsafe(q.put_nowait, text)
                else:
                    try:
                        q.put_nowait(text)
                    except asyncio.QueueFull:
                        pass

    def flush(self):
        sys.__stdout__.flush()

