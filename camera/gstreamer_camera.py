"""Compatibility module for future Jetson GStreamer-specific capture.

Jetson deployments can already use FFmpeg with RTSP or V4L2 inputs. If later
hardware requires a dedicated GStreamer pipeline, it can implement the same
BaseCamera interface here without changing services or APIs.
"""

from camera.ffmpeg_camera import FFmpegCamera as GStreamerCamera

__all__ = ["GStreamerCamera"]
