"""A camera view that reuses another camera's latest frames."""

from __future__ import annotations

from dataclasses import asdict
from typing import Callable, Optional

from camera.base import BaseCamera, CameraConfig, CameraStatus
from camera.buffer import FrameSnapshot


class SharedCamera(BaseCamera):
    """Expose one physical camera in multiple UI panels without reopening it."""

    def __init__(self, config: CameraConfig, provider_id: str, provider_getter: Callable[[str], Optional[BaseCamera]]) -> None:
        super().__init__(config)
        self.provider_id = provider_id
        self._provider_getter = provider_getter

    def start(self) -> None:
        provider = self._provider()
        if provider:
            provider.start()

    def stop(self) -> None:
        # The owner camera controls the physical device lifecycle.
        return None

    def reconnect(self) -> None:
        provider = self._provider()
        if provider:
            provider.reconnect()

    def get_latest_frame(self) -> Optional[FrameSnapshot]:
        provider = self._provider()
        return provider.get_latest_frame() if provider else None

    def capture_snapshot(self) -> Optional[FrameSnapshot]:
        return self.get_latest_frame()

    def get_status(self) -> CameraStatus:
        provider = self._provider()
        if provider is None:
            return CameraStatus(
                camera_id=self.config.camera_id,
                name=self.config.name,
                source_type=self.config.source_type,
                source_label=self.config.display_source(),
                online=False,
                running=False,
                last_frame_at=None,
                last_error=f"共享摄像头来源 {self.provider_id} 不可用",
            )

        status = asdict(provider.get_status())
        return CameraStatus(
            camera_id=self.config.camera_id,
            name=self.config.name,
            source_type=self.config.source_type,
            source_label=self.config.display_source(),
            online=bool(status["online"]),
            running=bool(status["running"]),
            last_frame_at=status["last_frame_at"],
            last_error=status["last_error"],
        )

    def _provider(self) -> Optional[BaseCamera]:
        provider = self._provider_getter(self.provider_id)
        if provider is self:
            return None
        return provider
