from unittest.mock import patch

from flask import Flask

from api.frame_api import frame_api
from camera.base import CameraConfig
from camera.buffer import FrameSnapshot
from camera.source_discovery import VideoSourceOption


class FakeCamera:
    pass


class FakeCameraManager:
    def __init__(self):
        self.config = CameraConfig(
            camera_id="entrance",
            name="进货区实时画面",
            source_type="webcam",
            source="0",
        )
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

    def get_config(self, camera_id):
        return self.config if camera_id == "entrance" else None

    def active_webcam_sources(self):
        return ["0"]

    def update_camera_source(self, camera_id, *, source_type, source, source_label=None):
        return {
            "camera_id": camera_id,
            "name": "进货区实时画面",
            "source_type": source_type,
            "source_label": source_label or "电脑摄像头",
            "online": False,
            "running": True,
            "last_frame_at": None,
            "last_error": None,
        }


class FakeDetectionService:
    def available_models(self):
        return {
            "detection_models": [{"id": "yolov11", "name": "YOLOv11"}],
            "ocr_models": [{"id": "paddleocr", "name": "PaddleOCR"}],
        }


class FakeDatabaseService:
    def __init__(self):
        self.records = []

    def insert_local_record(self, payload):
        record = {"id": 1, **payload}
        self.records.append(record)
        return record

    def list_session_records(self, pending_only=True):
        return self.records

    def upload_session_pending_to_mysql(self):
        self.records = []
        return {"uploaded": 1, "message": "数据已入库，本地数据库暂无待上传数据"}

    def clear_local_cache(self):
        deleted = len(self.records)
        self.records = []
        return {"deleted": deleted, "message": "本地数据库缓存已清除"}

    def list_mysql_records(self, intake_date):
        return {"configured": True, "records": []}


def make_app():
    app = Flask(__name__)
    app.config["camera_manager"] = FakeCameraManager()
    app.config["detection_service"] = FakeDetectionService()
    app.config["database_service"] = FakeDatabaseService()
    app.register_blueprint(frame_api)
    return app

    def update_camera_source(self, camera_id, *, source_type, source, source_label=None):
        self.config = CameraConfig(
            camera_id=camera_id,
            name="进货区实时画面",
            source_type=source_type,
            source=source,
            source_label=source_label,
        )
        return {
            "camera_id": camera_id,
            "name": "进货区实时画面",
            "source_type": source_type,
            "source_label": self.config.display_source(),
            "online": False,
            "running": True,
            "last_frame_at": None,
            "last_error": None,
        }


def test_mjpeg_stream_does_not_require_app_context_during_iteration():
    app = make_app()

    with app.test_request_context("/api/cameras/entrance/stream"):
        response = app.view_functions["frame_api.camera_stream"]("entrance")

    chunk = next(response.response)

    assert b"--frame" in chunk
    assert b"Content-Type: image/jpeg" in chunk
    assert b"jpeg-data" in chunk


def test_video_sources_returns_discovered_webcams_and_rtsp_option():
    app = make_app()

    with patch(
        "api.frame_api.discover_video_sources",
        return_value=[
            VideoSourceOption(
                id="webcam-0",
                label="电脑摄像头 0",
                source_type="webcam",
                source="0",
                source_label="电脑摄像头",
            ),
            VideoSourceOption(
                id="rtsp",
                label="RTSP 视频流",
                source_type="rtsp",
                source="",
                source_label="RTSP",
            ),
        ],
    ):
        response = app.test_client().get("/api/video-sources?camera_id=entrance")

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["sources"][0]["source_type"] == "webcam"
    assert payload["sources"][1]["source_type"] == "rtsp"


def test_update_camera_source_rejects_invalid_rtsp_url():
    app = make_app()

    response = app.test_client().post(
        "/api/cameras/entrance/source",
        json={"source_type": "rtsp", "source": "http://example.com/stream"},
    )

    assert response.status_code == 400


def test_update_camera_source_accepts_webcam_index():
    app = make_app()

    response = app.test_client().post(
        "/api/cameras/entrance/source",
        json={"source_type": "webcam", "source": "1", "source_label": "电脑摄像头"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["camera"]["source_type"] == "webcam"


def test_models_endpoint_returns_model_options():
    response = make_app().test_client().get("/api/models")

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["detection_models"][0]["id"] == "yolov11"


def test_local_record_endpoint_saves_confirmed_record():
    response = make_app().test_client().post(
        "/api/records/local",
        json={"product_name": "土豆", "weight": 2.5},
    )

    payload = response.get_json()
    assert response.status_code == 201
    assert payload["record"]["product_name"] == "土豆"


def test_clear_local_cache_endpoint_deletes_records():
    app = make_app()
    client = app.test_client()
    client.post("/api/records/local", json={"product_name": "土豆", "weight": 2.5})

    response = client.delete("/api/records/local/cache")

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["deleted"] == 1
