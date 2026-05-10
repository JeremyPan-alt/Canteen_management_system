"""Thread-safe latest-frame cache for real-time camera streams."""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FrameSnapshot:
    camera_id: str
    data: bytes
    content_type: str
    timestamp: float


class LatestFrameBuffer:
    """A max-size-one frame buffer.

    Real-time preview and recognition should use the freshest frame only. This
    wrapper keeps queue semantics for the requested cache strategy while
    replacing stale data instead of letting frames pile up.
    """

    def __init__(self, camera_id: str) -> None:
        self.camera_id = camera_id
        self._queue: queue.Queue[FrameSnapshot] = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._latest: Optional[FrameSnapshot] = None

    def put(self, data: bytes, content_type: str = "image/jpeg") -> FrameSnapshot:
        snapshot = FrameSnapshot(
            camera_id=self.camera_id,
            data=data,
            content_type=content_type,
            timestamp=time.time(),
        )
        with self._lock:
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
            self._queue.put_nowait(snapshot)
            self._latest = snapshot
        return snapshot

    def get_latest(self) -> Optional[FrameSnapshot]:
        with self._lock:
            return self._latest

    def clear(self) -> None:
        with self._lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            self._latest = None
