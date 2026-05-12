"""Camera manager for multi-camera lifecycle and snapshots."""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict
from typing import Iterable, Optional

from camera.base import BaseCamera, CameraConfig
from camera.buffer import FrameSnapshot
from camera.ffmpeg_camera import FFmpegCamera
from camera.gstreamer_camera import GStreamerCamera
from camera.opencv_camera import OpenCVCamera

LOGGER = logging.getLogger(__name__)


class CameraManager:
    def __init__(self, cameras: Iterable[BaseCamera]) -> None:
        self._cameras = {camera.config.camera_id: camera for camera in cameras}
        self._lock = threading.RLock()

    @classmethod
    def from_configs(cls, configs: Iterable[CameraConfig]) -> "CameraManager":
        return cls(cls._create_camera(config) for config in configs)

    @staticmethod
    def _create_camera(config: CameraConfig) -> BaseCamera:
        if config.source_type in {"csi", "gstreamer"}:
            return GStreamerCamera(config)
        if config.source_type in {"webcam", "local"}:
            return OpenCVCamera(config)
        return FFmpegCamera(config)

    def start_all(self) -> None:
        with self._lock:
            cameras = list(self._cameras.values())
        for camera in cameras:
            try:
                camera.start()
            except Exception:  # noqa: BLE001
                LOGGER.exception("Failed to start camera %s", camera.config.camera_id)

    def stop_all(self) -> None:
        with self._lock:
            cameras = list(self._cameras.values())
        for camera in cameras:
            try:
                camera.stop()
            except Exception:  # noqa: BLE001
                LOGGER.exception("Failed to stop camera %s", camera.config.camera_id)

    def get(self, camera_id: str) -> Optional[BaseCamera]:
        with self._lock:
            return self._cameras.get(camera_id)

    def get_config(self, camera_id: str) -> Optional[CameraConfig]:
        camera = self.get(camera_id)
        return camera.config if camera else None

    def update_camera_source(
        self,
        camera_id: str,
        *,
        source_type: str,
        source: str,
        source_label: Optional[str] = None,
    ) -> dict[str, object]:
        """Replace a camera with a new source and start it immediately."""

        with self._lock:
            old_camera = self._cameras.get(camera_id)
            if old_camera is None:
                raise KeyError(f"Unknown camera: {camera_id}")

            old_config = old_camera.config
            new_config = CameraConfig(
                camera_id=old_config.camera_id,
                name=old_config.name,
                source=source,
                source_type=source_type,
                source_label=source_label,
                width=old_config.width,
                height=old_config.height,
                fps=old_config.fps,
                reconnect_interval_sec=old_config.reconnect_interval_sec,
                ffmpeg_path=old_config.ffmpeg_path,
                gstreamer_path=old_config.gstreamer_path,
                rtsp_transport=old_config.rtsp_transport,
                input_format=None,
                gstreamer_pipeline=None,
                extra_input_args=(),
                extra_output_args=(),
            )
            new_camera = self._create_camera(new_config)
            self._cameras[camera_id] = new_camera

        old_camera.stop()
        new_camera.start()
        return asdict(new_camera.get_status())

    def get_latest_frame(self, camera_id: str) -> Optional[FrameSnapshot]:
        camera = self.get(camera_id)
        return camera.get_latest_frame() if camera else None

    def capture_snapshot(self, camera_id: str) -> Optional[FrameSnapshot]:
        camera = self.get(camera_id)
        return camera.capture_snapshot() if camera else None

    def capture_all(self) -> dict[str, Optional[FrameSnapshot]]:
        with self._lock:
            cameras = dict(self._cameras)
        return {camera_id: camera.capture_snapshot() for camera_id, camera in cameras.items()}

    def statuses(self) -> list[dict[str, object]]:
        with self._lock:
            cameras = list(self._cameras.values())
        return [asdict(camera.get_status()) for camera in cameras]

    def camera_ids(self) -> list[str]:
        with self._lock:
            return list(self._cameras.keys())
