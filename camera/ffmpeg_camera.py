"""FFmpeg-backed camera implementation.

The camera process outputs JPEG frames to stdout. The capture thread parses the
MJPEG byte stream and keeps only the newest frame, so one blocked or failed
camera cannot stop the rest of the application.
"""

from __future__ import annotations

import logging
import platform
import re
import subprocess
import threading
import time
from typing import Optional

from camera.base import BaseCamera, CameraConfig, CameraStatus
from camera.buffer import FrameSnapshot, LatestFrameBuffer

LOGGER = logging.getLogger(__name__)

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


class FFmpegCamera(BaseCamera):
    def __init__(self, config: CameraConfig) -> None:
        super().__init__(config)
        self._buffer = LatestFrameBuffer(config.camera_id)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen[bytes]] = None
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
        self._terminate_process()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        with self._state_lock:
            self._online = False

    def reconnect(self) -> None:
        self._terminate_process()

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
                self._run_ffmpeg_until_failure()
            except Exception as exc:  # noqa: BLE001 - camera loops must survive.
                if self._stop_event.is_set():
                    break
                self._mark_offline(str(exc))
                LOGGER.warning("Camera %s capture failed: %s", self.config.camera_id, exc)
                LOGGER.debug("Camera %s capture traceback", self.config.camera_id, exc_info=True)
            finally:
                self._terminate_process()

            if not self._stop_event.wait(self.config.reconnect_interval_sec):
                LOGGER.info("Reconnecting camera %s", self.config.camera_id)

    def _run_ffmpeg_until_failure(self) -> None:
        command = self._build_command()
        LOGGER.info("Starting camera %s with %s", self.config.camera_id, self._backend_name())
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert self._process.stdout is not None
        pending = bytearray()

        while not self._stop_event.is_set():
            chunk = self._process.stdout.read(8192)
            if not chunk:
                stderr = self._read_stderr()
                message = stderr or f"FFmpeg exited with code {self._process.poll()}"
                raise RuntimeError(message)

            pending.extend(chunk)
            for frame in self._extract_jpeg_frames(pending):
                self._buffer.put(frame)
                self._mark_online()

    def _build_command(self) -> list[str]:
        cfg = self.config
        command = [cfg.ffmpeg_path, "-hide_banner", "-loglevel", "error"]

        input_format, source = self._resolve_input()

        if cfg.source_type == "rtsp":
            command.extend(["-rtsp_transport", cfg.rtsp_transport])

        if input_format:
            command.extend(["-f", input_format])

        command.extend(cfg.extra_input_args)
        command.extend(["-i", source])

        video_filter = f"fps={cfg.fps},scale={cfg.width}:{cfg.height}"
        command.extend(
            [
                "-an",
                "-vf",
                video_filter,
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "-q:v",
                "5",
            ]
        )
        command.extend(cfg.extra_output_args)
        command.append("pipe:1")
        return command

    def _backend_name(self) -> str:
        return "FFmpeg"

    def _resolve_input(self) -> tuple[Optional[str], str]:
        cfg = self.config
        if cfg.source_type in {"webcam", "local"}:
            return self._resolve_local_webcam()
        return cfg.input_format, cfg.source

    def _resolve_local_webcam(self) -> tuple[str, str]:
        cfg = self.config
        system_name = platform.system().lower()
        requested_source = cfg.source.strip()
        auto_source = requested_source in {"", "auto", "default"}

        if system_name == "windows":
            source = self._detect_windows_dshow_source() if auto_source else requested_source
            if not source.startswith("video="):
                source = f"video={source}"
            return "dshow", source

        if system_name == "darwin":
            return "avfoundation", "0" if auto_source else requested_source

        return "v4l2", "/dev/video0" if auto_source else requested_source

    def _detect_windows_dshow_source(self) -> str:
        command = [
            self.config.ffmpeg_path,
            "-hide_banner",
            "-list_devices",
            "true",
            "-f",
            "dshow",
            "-i",
            "dummy",
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        output = "\n".join([completed.stdout, completed.stderr])
        in_video_section = False
        for line in output.splitlines():
            if "DirectShow video devices" in line:
                in_video_section = True
                continue
            if "DirectShow audio devices" in line:
                in_video_section = False
            if not in_video_section:
                continue
            match = re.search(r'"([^"]+)"', line)
            if match and not match.group(1).startswith("@"):
                return f"video={match.group(1)}"
        raise RuntimeError("No DirectShow video device detected")

    @staticmethod
    def _extract_jpeg_frames(pending: bytearray) -> list[bytes]:
        frames: list[bytes] = []
        while True:
            start = pending.find(JPEG_SOI)
            if start < 0:
                pending.clear()
                break
            end = pending.find(JPEG_EOI, start + len(JPEG_SOI))
            if end < 0:
                if start > 0:
                    del pending[:start]
                break
            end += len(JPEG_EOI)
            frames.append(bytes(pending[start:end]))
            del pending[:end]
        return frames

    def _read_stderr(self) -> str:
        if not self._process or not self._process.stderr:
            return ""
        try:
            return self._process.stderr.read(4096).decode("utf-8", errors="ignore").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _terminate_process(self) -> None:
        process = self._process
        self._process = None
        if not process:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
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
        LOGGER.warning("Camera %s offline: %s", self.config.camera_id, error)
