"""Discover selectable video sources for the frontend."""

from __future__ import annotations

import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class VideoSourceOption:
    id: str
    label: str
    source_type: str
    source: str
    source_label: str
    available: bool = True
    description: Optional[str] = None


def discover_video_sources(max_index: int = 6) -> list[VideoSourceOption]:
    """Return local camera choices plus an RTSP placeholder option."""

    options = _discover_local_webcams(max_index=max_index)
    if not options:
        options.append(
            VideoSourceOption(
                id="webcam-0",
                label="电脑摄像头 0",
                source_type="webcam",
                source="0",
                source_label="电脑摄像头",
                available=False,
                description="未确认可用；可尝试选择后检查系统摄像头权限",
            )
        )

    options.append(
        VideoSourceOption(
            id="rtsp",
            label="RTSP 视频流",
            source_type="rtsp",
            source="",
            source_label="RTSP",
            available=True,
            description="选择后输入 rtsp:// 开头的视频流地址",
        )
    )
    return options


def _discover_local_webcams(max_index: int) -> list[VideoSourceOption]:
    cv2 = _try_import_cv2()
    if cv2 is None:
        return []

    api_preference = _api_preference(cv2)
    options: list[VideoSourceOption] = []
    for index in range(max_index):
        capture = cv2.VideoCapture(index, api_preference)
        try:
            if not capture.isOpened():
                continue
            ok, _ = capture.read()
            if not ok:
                continue
            options.append(
                VideoSourceOption(
                    id=f"webcam-{index}",
                    label=_camera_label(index),
                    source_type="webcam",
                    source=str(index),
                    source_label="电脑摄像头",
                    description=_camera_description(index),
                )
            )
        finally:
            capture.release()
    return options


def _camera_label(index: int) -> str:
    device_path = Path(f"/dev/video{index}")
    if platform.system().lower() == "linux" and device_path.exists():
        return f"电脑摄像头 {index} ({device_path})"
    return f"电脑摄像头 {index}"


def _camera_description(index: int) -> str:
    system_name = platform.system().lower()
    if system_name == "windows":
        return f"OpenCV DirectShow 摄像头索引 {index}"
    if system_name == "linux":
        return f"OpenCV V4L2 摄像头索引 {index}"
    return f"OpenCV 摄像头索引 {index}"


def _api_preference(cv2) -> int:
    system_name = platform.system().lower()
    if system_name == "windows":
        return cv2.CAP_DSHOW
    if system_name == "linux":
        return cv2.CAP_V4L2
    return cv2.CAP_ANY


def _try_import_cv2():
    try:
        import cv2  # type: ignore
    except ImportError:
        return None
    return cv2


def serialize_options(options: list[VideoSourceOption]) -> list[dict[str, object]]:
    return [asdict(option) for option in options]
