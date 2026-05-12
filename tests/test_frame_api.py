from flask import Flask

from api.frame_api import frame_api
from camera.buffer import FrameSnapshot


class FakeCamera:
    pass


class FakeCameraManager:
    def __init__(self):
        self.snapshot = FrameSnapshot(
            camera_id="entrance",
            data=b"jpeg-data",
            content_type="image/jpeg",
            timestamp=1.0,
        )

    def get(self, camera_id):
        return FakeCamera() if camera_id == "entrance" else None

    def get_latest_frame(self, camera_id):
        return self.snapshot


def test_mjpeg_stream_does_not_require_app_context_during_iteration():
    app = Flask(__name__)
    app.config["camera_manager"] = FakeCameraManager()
    app.register_blueprint(frame_api)

    with app.test_request_context("/api/cameras/entrance/stream"):
        response = app.view_functions["frame_api.camera_stream"]("entrance")

    chunk = next(response.response)

    assert b"--frame" in chunk
    assert b"Content-Type: image/jpeg" in chunk
    assert b"jpeg-data" in chunk
