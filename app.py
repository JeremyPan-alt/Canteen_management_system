"""Flask application entry point for the canteen capture system."""

from __future__ import annotations

import atexit
import logging
import os
from pathlib import Path

from flask import Flask, send_from_directory
from flask_cors import CORS

from api import frame_api
from camera.manager import CameraManager
from config_loader import load_camera_configs
from services import CaptureService, DatabaseService, DetectionService


def create_app() -> Flask:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    app = Flask(__name__, static_folder="frontend/dist", static_url_path="")
    CORS(app)

    config_path = os.getenv("CAMERA_CONFIG", "config/camera.yaml")
    camera_manager = CameraManager.from_configs(load_camera_configs(config_path))
    detection_service = DetectionService()
    capture_service = CaptureService(
        camera_manager=camera_manager,
        detection_service=detection_service,
        storage_dir=os.getenv("CAPTURE_STORAGE_DIR", "data/captures"),
    )
    database_service = DatabaseService(os.getenv("SQLITE_DB_PATH", "data/intake_records.sqlite3"))

    app.config["camera_manager"] = camera_manager
    app.config["capture_service"] = capture_service
    app.config["detection_service"] = detection_service
    app.config["database_service"] = database_service
    app.register_blueprint(frame_api)

    camera_manager.start_all()
    capture_service.start()

    def shutdown() -> None:
        capture_service.stop()
        camera_manager.stop_all()

    atexit.register(shutdown)

    @app.get("/")
    def index():
        dist = Path(app.static_folder or "")
        index_path = dist / "index.html"
        if index_path.exists():
            return send_from_directory(dist, "index.html")
        return {
            "status": "backend_running",
            "message": "Build frontend with `npm --prefix frontend run build` to serve the UI.",
        }

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        threaded=True,
    )
