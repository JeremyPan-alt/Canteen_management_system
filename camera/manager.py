"""Camera manager for multi-camera lifecycle and snapshots."""

from __future__ import annotations

import logging
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
        for camera in self._cameras.values():
            try:
                camera.start()
            except Exception:  # noqa: BLE001
                LOGGER.exception("Failed to start camera %s", camera.config.camera_id)

    def stop_all(self) -> None:
        for camera in self._cameras.values():
            try:
                camera.stop()
            except Exception:  # noqa: BLE001
                LOGGER.exception("Failed to stop camera %s", camera.config.camera_id)

    def get(self, camera_id: str) -> Optional[BaseCamera]:
        return self._cameras.get(camera_id)

    def get_latest_frame(self, camera_id: str) -> Optional[FrameSnapshot]:
        camera = self.get(camera_id)
        return camera.get_latest_frame() if camera else None

    def capture_snapshot(self, camera_id: str) -> Optional[FrameSnapshot]:
        camera = self.get(camera_id)
        return camera.capture_snapshot() if camera else None

    def capture_all(self) -> dict[str, Optional[FrameSnapshot]]:
        return {
            camera_id: camera.capture_snapshot()
            for camera_id, camera in self._cameras.items()
        }

    def statuses(self) -> list[dict[str, object]]:
        return [asdict(camera.get_status()) for camera in self._cameras.values()]

    def camera_ids(self) -> list[str]:
        return list(self._cameras.keys())
