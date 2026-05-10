"""Compatibility module for the planned camera package layout.

The current implementation standardizes live capture through FFmpeg so RTSP,
Windows, Linux, and Jetson sources share one path. This alias keeps imports
stable if later code asks for an OpenCV-style camera class.
"""

from camera.ffmpeg_camera import FFmpegCamera as OpenCVCamera

__all__ = ["OpenCVCamera"]
