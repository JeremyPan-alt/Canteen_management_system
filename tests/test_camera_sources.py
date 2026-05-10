from unittest.mock import patch

from camera.base import CameraConfig
from camera.ffmpeg_camera import FFmpegCamera
from camera.gstreamer_camera import GStreamerCamera
from camera.manager import CameraManager
from camera.opencv_camera import OpenCVCamera


def test_webcam_auto_uses_first_windows_dshow_device():
    camera = FFmpegCamera(
        CameraConfig(
            camera_id="entrance",
            name="进货区实时画面",
            source_type="webcam",
            source="auto",
        )
    )

    with patch("camera.ffmpeg_camera.platform.system", return_value="Windows"):
        with patch.object(camera, "_detect_windows_dshow_source", return_value="video=Integrated Camera"):
            input_format, source = camera._resolve_input()

    assert input_format == "dshow"
    assert source == "video=Integrated Camera"


def test_manager_uses_gstreamer_for_csi_camera():
    manager = CameraManager.from_configs(
        [
            CameraConfig(
                camera_id="entrance",
                name="进货区实时画面",
                source_type="csi",
                source="0",
            )
        ]
    )

    assert isinstance(manager.get("entrance"), GStreamerCamera)


def test_manager_uses_opencv_for_local_webcam():
    manager = CameraManager.from_configs(
        [
            CameraConfig(
                camera_id="entrance",
                name="进货区实时画面",
                source_type="webcam",
                source="auto",
            )
        ]
    )

    assert isinstance(manager.get("entrance"), OpenCVCamera)


def test_opencv_webcam_auto_maps_to_camera_index_zero():
    camera = OpenCVCamera(
        CameraConfig(
            camera_id="entrance",
            name="进货区实时画面",
            source_type="webcam",
            source="auto",
        )
    )

    assert camera._resolve_source() == 0


def test_gstreamer_csi_command_outputs_jpeg_to_stdout():
    camera = GStreamerCamera(
        CameraConfig(
            camera_id="entrance",
            name="进货区实时画面",
            source_type="csi",
            source="0",
            width=640,
            height=480,
            fps=15,
        )
    )

    command = camera._build_command()

    assert command[:2] == ["gst-launch-1.0", "-q"]
    assert "nvarguscamerasrc" in command
    assert "jpegenc" in command
    assert command[-2:] == ["fdsink", "fd=1"]


def test_source_label_defaults_to_human_readable_name():
    assert CameraConfig("a", "A", source_type="webcam").display_source() == "电脑摄像头"
    assert CameraConfig("b", "B", source_type="csi").display_source() == "CSI"
    assert CameraConfig("c", "C", source_type="rtsp").display_source() == "RTSP"
