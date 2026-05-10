"""Camera abstraction shared by Windows, Linux, and Jetson deployments."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from camera.buffer import FrameSnapshot


@dataclass(frozen=True)
class CameraConfig:
    camera_id: str
    name: str
    source: str
    source_type: str = "rtsp"
    width: int = 640
    height: int = 480
    fps: int = 15
    reconnect_interval_sec: float = 3.0
    ffmpeg_path: str = "ffmpeg"
    rtsp_transport: str = "tcp"
    input_format: Optional[str] = None
    extra_input_args: tuple[str, ...] = ()
    extra_output_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class CameraStatus:
    camera_id: str
    name: str
    online: bool
    running: bool
    last_frame_at: Optional[float]
    last_error: Optional[str]


class BaseCamera(ABC):
    """Uniform camera interface used by APIs and services."""

    def __init__(self, config: CameraConfig) -> None:
        self.config = config

    @abstractmethod
    def start(self) -> None:
        """Start camera capture."""

    @abstractmethod
    def stop(self) -> None:
        """Stop camera capture and release resources."""

    @abstractmethod
    def reconnect(self) -> None:
        """Reconnect the underlying source."""

    @abstractmethod
    def get_latest_frame(self) -> Optional[FrameSnapshot]:
        """Return the freshest frame, if one exists."""

    @abstractmethod
    def capture_snapshot(self) -> Optional[FrameSnapshot]:
        """Capture the freshest frame for downstream recognition."""

    @abstractmethod
    def get_status(self) -> CameraStatus:
        """Return health and stream state."""
