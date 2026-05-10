"""GStreamer-backed camera implementation for Jetson CSI cameras."""

from __future__ import annotations

import shlex

from camera.ffmpeg_camera import FFmpegCamera


class GStreamerCamera(FFmpegCamera):
    """Read JPEG frames from a GStreamer pipeline on stdout."""

    def _backend_name(self) -> str:
        return "GStreamer"

    def _build_command(self) -> list[str]:
        cfg = self.config
        if cfg.gstreamer_pipeline:
            pipeline = shlex.split(cfg.gstreamer_pipeline)
        else:
            sensor_id = cfg.source.strip() or "0"
            pipeline = [
                "nvarguscamerasrc",
                f"sensor-id={sensor_id}",
                "!",
                f"video/x-raw(memory:NVMM),width={cfg.width},height={cfg.height},framerate={cfg.fps}/1",
                "!",
                "nvvidconv",
                "!",
                "video/x-raw,format=I420",
                "!",
                "jpegenc",
            ]

        if "fdsink" not in pipeline:
            pipeline.extend(["!", "fdsink", "fd=1"])

        return [cfg.gstreamer_path, "-q", *pipeline]

__all__ = ["GStreamerCamera"]
