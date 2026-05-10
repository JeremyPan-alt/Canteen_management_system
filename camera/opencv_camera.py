"""OpenCV-backed local webcam implementation.

Windows laptop webcams are often more reliable through OpenCV's DirectShow
backend than through FFmpeg device-name probing. This class keeps the same
BaseCamera contract and feeds JPEG bytes into the shared latest-frame buffer.
"""

from __future__ import annotations

import logging
import platform
import threading
import time
from typing import Optional

from camera.base import BaseCamera, CameraConfig, CameraStatus
from camera.buffer import FrameSnapshot, LatestFrameBuffer

LOGGER = logging.getLogger(__name__)


class OpenCVCamera(BaseCamera):
    def __init__(self, config: CameraConfig) -> None:
        super().__init__(config)
        self._buffer = LatestFrameBuffer(config.camera_id)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._capture = None
        self._state_lock = threading.Lock()
        self._online = False
        self._last_error: Optional[str] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name=f"camera-{self.config.camera_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._release_capture()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        with self._state_lock:
            self._online = False

    def reconnect(self) -> None:
        self._release_capture()

    def get_latest_frame(self) -> Optional[FrameSnapshot]:
        return self._buffer.get_latest()

    def capture_snapshot(self) -> Optional[FrameSnapshot]:
        return self.get_latest_frame()

    def get_status(self) -> CameraStatus:
        latest = self.get_latest_frame()
        with self._state_lock:
            online = self._online
            last_error = self._last_error
        return CameraStatus(
            camera_id=self.config.camera_id,
            name=self.config.name,
            source_type=self.config.source_type,
            source_label=self.config.display_source(),
            online=online,
            running=bool(self._thread and self._thread.is_alive()),
            last_frame_at=latest.timestamp if latest else None,
            last_error=last_error,
        )

    def _capture_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._run_opencv_until_failure()
            except Exception as exc:  # noqa: BLE001 - camera loops must survive.
                self._mark_offline(str(exc))
                LOGGER.exception("OpenCV camera %s capture failed", self.config.camera_id)
            finally:
                self._release_capture()

            if not self._stop_event.wait(self.config.reconnect_interval_sec):
                LOGGER.info("Reconnecting OpenCV camera %s", self.config.camera_id)

    def _run_opencv_until_failure(self) -> None:
        cv2 = self._import_cv2()
        source = self._resolve_source()
        api_preference = self._api_preference(cv2)
        LOGGER.info(
            "Starting camera %s with OpenCV source %s",
            self.config.camera_id,
            source,
        )

        capture = cv2.VideoCapture(source, api_preference)
        self._capture = capture
        if not capture.isOpened():
            raise RuntimeError(f"OpenCV could not open webcam source: {source}")

        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        capture.set(cv2.CAP_PROP_FPS, self.config.fps)

        frame_interval = 1.0 / max(self.config.fps, 1)
        while not self._stop_event.is_set():
            ok, frame = capture.read()
            if not ok or frame is None:
                raise RuntimeError(f"OpenCV failed to read frame from webcam source: {source}")

            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                raise RuntimeError("OpenCV failed to encode webcam frame as JPEG")

            self._buffer.put(encoded.tobytes())
            self._mark_online()
            self._stop_event.wait(frame_interval)

    def _resolve_source(self) -> int | str:
        source = self.config.source.strip()
        if source in {"", "auto", "default"}:
            return 0
        if source.isdigit():
            return int(source)
        return source

    @staticmethod
    def _api_preference(cv2) -> int:
        system_name = platform.system().lower()
        if system_name == "windows":
            return cv2.CAP_DSHOW
        if system_name == "linux":
            return cv2.CAP_V4L2
        return cv2.CAP_ANY

    @staticmethod
    def _import_cv2():
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV is required for local webcam capture. Install dependencies with "
                "`pip install -r requirements.txt`."
            ) from exc
        return cv2

    def _release_capture(self) -> None:
        capture = self._capture
        self._capture = None
        if capture is not None:
            try:
                capture.release()
            except Exception:  # noqa: BLE001
                LOGGER.exception("Failed to release OpenCV camera %s", self.config.camera_id)
        with self._state_lock:
            self._online = False

    def _mark_online(self) -> None:
        with self._state_lock:
            self._online = True
            self._last_error = None

    def _mark_offline(self, error: str) -> None:
        with self._state_lock:
            self._online = False
            self._last_error = error[:500]
        LOGGER.warning("OpenCV camera %s offline: %s", self.config.camera_id, error)

__all__ = ["OpenCVCamera"]
