from camera.buffer import LatestFrameBuffer
from camera.ffmpeg_camera import FFmpegCamera


def test_latest_frame_buffer_keeps_only_newest_frame():
    buffer = LatestFrameBuffer("entrance")

    first = buffer.put(b"first")
    second = buffer.put(b"second")

    latest = buffer.get_latest()
    assert latest == second
    assert latest != first
    assert latest.data == b"second"


def test_extract_jpeg_frames_keeps_partial_frame_pending():
    frame = b"\xff\xd8image-data\xff\xd9"
    partial = b"\xff\xd8partial"
    pending = bytearray(b"noise" + frame + partial)

    frames = FFmpegCamera._extract_jpeg_frames(pending)

    assert frames == [frame]
    assert pending == bytearray(partial)
