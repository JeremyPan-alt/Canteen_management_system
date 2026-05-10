"""Application configuration loading."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from camera.base import CameraConfig


def load_camera_configs(path: str | os.PathLike[str]) -> list[CameraConfig]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file:
        raw: dict[str, Any] = yaml.safe_load(file) or {}

    defaults = raw.get("defaults", {})
    cameras = raw.get("cameras", [])
    result: list[CameraConfig] = []
    for item in cameras:
        merged = {**defaults, **item}
        merged["camera_id"] = str(merged.pop("id"))
        merged["source"] = str(merged["source"])
        merged["extra_input_args"] = tuple(merged.get("extra_input_args") or ())
        merged["extra_output_args"] = tuple(merged.get("extra_output_args") or ())
        result.append(CameraConfig(**merged))
    return result
