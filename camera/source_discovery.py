"""Discover selectable video sources for the frontend."""

from __future__ import annotations

import platform
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class VideoSourceOption:
    id: str
    label: str
    source_type: str
    source: str
    source_label: str
    available: bool = True
    description: Optional[str] = None


_CACHE_TTL_SEC = 30.0
_cached_at = 0.0
_cached_options: list[VideoSourceOption] = []


def discover_video_sources(
    max_index: int = 6,
    active_webcam_sources: Optional[Iterable[str]] = None,
) -> list[VideoSourceOption]:
    """Return local camera choices plus an RTSP placeholder option."""

    active_options = _active_webcam_options(active_webcam_sources or [])
    # Probing webcams can interrupt an active Windows camera. If a local camera
    # is already streaming, expose that known-good source and defer deeper scans.
    options = active_options or _cached_or_discover_local_webcams(max_index=max_index)
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


def _active_webcam_options(active_webcam_sources: Iterable[str]) -> list[VideoSourceOption]:
    options = []
    for source in _unique_sources(active_webcam_sources):
        index = _normalize_webcam_source(source)
        options.append(
            VideoSourceOption(
                id=f"webcam-{index}",
                label=f"电脑摄像头 {index}",
                source_type="webcam",
                source=index,
                source_label="电脑摄像头",
                description="当前已连接并正在使用的本机摄像头",
            )
        )
    return options


def _cached_or_discover_local_webcams(max_index: int) -> list[VideoSourceOption]:
    global _cached_at, _cached_options
    now = time.monotonic()
    if _cached_options and now - _cached_at < _CACHE_TTL_SEC:
        return list(_cached_options)

    _cached_options = _discover_local_webcams(max_index=max_index)
    _cached_at = now
    return list(_cached_options)


def _discover_local_webcams(max_index: int) -> list[VideoSourceOption]:
    cv2 = _try_import_cv2()
    if cv2 is None:
        return []

    windows_names = _windows_camera_device_names()
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
            label = windows_names[len(options)] if len(options) < len(windows_names) else _camera_label(index)
            options.append(
                VideoSourceOption(
                    id=f"webcam-{index}",
                    label=label,
                    source_type="webcam",
                    source=str(index),
                    source_label="电脑摄像头",
                    description=_camera_description(index),
                )
            )
        finally:
            capture.release()

    if windows_names and len(options) > len(windows_names):
        options = options[: len(windows_names)]
    return _dedupe_options(options)


def _dedupe_options(options: list[VideoSourceOption]) -> list[VideoSourceOption]:
    seen: set[str] = set()
    result: list[VideoSourceOption] = []
    for option in options:
        key = option.label.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(option)
    return result


def _unique_sources(sources: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for source in sources:
        normalized = _normalize_webcam_source(source)
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _normalize_webcam_source(source: str) -> str:
    source = str(source or "").strip()
    if source in {"", "auto", "default"}:
        return "0"
    return source


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


def _windows_camera_device_names() -> list[str]:
    if platform.system().lower() != "windows":
        return []

    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "Get-CimInstance Win32_PnPEntity | "
            "Where-Object { $_.PNPClass -in @('Camera','Image') } | "
            "Select-Object -ExpandProperty Name"
        ),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return []

    names = []
    for line in completed.stdout.splitlines():
        name = line.strip()
        if name and name not in names:
            names.append(name)
    return names


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
