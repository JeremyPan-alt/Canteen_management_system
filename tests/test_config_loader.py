from pathlib import Path

from config_loader import load_camera_configs


def test_load_camera_configs_merges_defaults(tmp_path: Path):
    config = tmp_path / "camera.yaml"
    config.write_text(
        """
defaults:
  ffmpeg_path: ffmpeg
  width: 320
  height: 240
cameras:
  - id: entrance
    name: Entrance
    source: rtsp://example/stream
    source_type: rtsp
""",
        encoding="utf-8",
    )

    cameras = load_camera_configs(config)

    assert len(cameras) == 1
    assert cameras[0].camera_id == "entrance"
    assert cameras[0].width == 320
    assert cameras[0].source == "rtsp://example/stream"
