"""Flask API for camera preview, status, and capture triggers."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Iterator

from flask import Blueprint, Response, current_app, jsonify, request

from camera.source_discovery import VideoSourceOption, discover_video_sources, serialize_options

frame_api = Blueprint("frame_api", __name__, url_prefix="/api")


def _camera_manager():
    return current_app.config["camera_manager"]


def _capture_service():
    return current_app.config["capture_service"]


def _detection_service():
    return current_app.config["detection_service"]


def _database_service():
    return current_app.config["database_service"]


@frame_api.get("/health")
def health() -> Response:
    return jsonify({"status": "ok"})


@frame_api.get("/models")
def models() -> Response:
    return jsonify(_detection_service().available_models())


@frame_api.get("/cameras/status")
def camera_status() -> Response:
    return jsonify({"cameras": _camera_manager().statuses()})


@frame_api.get("/video-sources")
def video_sources() -> Response:
    camera_id = request.args.get("camera_id") or "entrance"
    camera_manager = _camera_manager()
    options = discover_video_sources(active_webcam_sources=camera_manager.active_webcam_sources())
    current_config = camera_manager.get_config(camera_id)
    if current_config is not None and current_config.source_type == "webcam":
        current_source = current_config.source if current_config.source else "auto"
        if current_source in {"auto", "default"}:
            current_source = "0"
        if all(option.source != current_source for option in options if option.source_type == "webcam"):
            options.insert(
                0,
                VideoSourceOption(
                    id=f"webcam-{current_source}",
                    label=f"当前电脑摄像头 {current_source}",
                    source_type="webcam",
                    source=current_source,
                    source_label="电脑摄像头",
                    available=True,
                    description="当前正在使用的本机摄像头",
                ),
            )
    return jsonify({"sources": serialize_options(options)})


@frame_api.post("/cameras/<camera_id>/source")
def update_camera_source(camera_id: str) -> Response:
    payload = request.get_json(silent=True) or {}
    source_type = str(payload.get("source_type") or "").strip()
    source = str(payload.get("source") or "").strip()

    if source_type not in {"webcam", "rtsp"}:
        return jsonify({"error": "source_type must be one of: webcam, rtsp"}), 400
    if source_type == "rtsp" and not source.lower().startswith("rtsp://"):
        return jsonify({"error": "RTSP source must start with rtsp://"}), 400
    if source_type == "webcam" and not source:
        source = "0"

    source_label = str(payload.get("source_label") or "").strip() or None
    status = _camera_manager().update_camera_source(
        camera_id,
        source_type=source_type,
        source=source,
        source_label=source_label,
    )
    return jsonify({"camera": status})


@frame_api.get("/cameras/<camera_id>/stream")
def camera_stream(camera_id: str) -> Response:
    camera_manager = _camera_manager()
    camera = camera_manager.get(camera_id)
    if camera is None:
        return jsonify({"error": f"Unknown camera: {camera_id}"}), 404

    return Response(
        _mjpeg_frames(camera_manager, camera_id),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@frame_api.post("/capture/start")
def start_capture() -> Response:
    payload = request.get_json(silent=True) or {}
    recorder = str(payload.get("recorder") or "anonymous")
    trigger_type = str(payload.get("trigger_type") or "manual")
    detection_model = str(payload.get("detection_model") or "yolov11")
    ocr_model = str(payload.get("ocr_model") or "paddleocr")
    batch = _capture_service().submit_capture(
        trigger_type=trigger_type,
        recorder=recorder,
        detection_model=detection_model,
        ocr_model=ocr_model,
    )
    return jsonify({"batch": asdict(batch)}), 202


@frame_api.get("/capture/<batch_id>")
def get_capture(batch_id: str) -> Response:
    batch = _capture_service().get_batch(batch_id)
    if batch is None:
        return jsonify({"error": f"Unknown batch: {batch_id}"}), 404
    return jsonify({"batch": asdict(batch)})


@frame_api.get("/capture")
def list_captures() -> Response:
    batches = _capture_service().list_batches()
    batches.sort(key=lambda item: item.created_at, reverse=True)
    return jsonify({"batches": [asdict(batch) for batch in batches]})


@frame_api.post("/records/local")
def create_local_record() -> Response:
    payload = request.get_json(silent=True) or {}
    record = _database_service().insert_local_record(payload)
    return jsonify({"record": record}), 201


@frame_api.get("/records/local/session")
def local_session_records() -> Response:
    pending_only = request.args.get("pending_only", "1") != "0"
    records = _database_service().list_session_records(pending_only=pending_only)
    message = "" if records else "数据已入库，本地数据库暂无待上传数据"
    return jsonify({"records": records, "message": message})


@frame_api.delete("/records/local/cache")
def clear_local_cache() -> Response:
    return jsonify(_database_service().clear_local_cache())


@frame_api.post("/records/upload-mysql")
def upload_mysql_records() -> Response:
    try:
        result = _database_service().upload_session_pending_to_mysql()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@frame_api.get("/records/mysql")
def mysql_records() -> Response:
    intake_date = request.args.get("date") or time.strftime("%Y-%m-%d")
    return jsonify(_database_service().list_mysql_records(intake_date))


def _mjpeg_frames(camera_manager, camera_id: str) -> Iterator[bytes]:
    last_timestamp = 0.0
    while True:
        snapshot = camera_manager.get_latest_frame(camera_id)
        if snapshot is None or snapshot.timestamp == last_timestamp:
            time.sleep(0.05)
            continue
        last_timestamp = snapshot.timestamp
        yield (
            b"--frame\r\n"
            + f"Content-Type: {snapshot.content_type}\r\n".encode("ascii")
            + f"Content-Length: {len(snapshot.data)}\r\n\r\n".encode("ascii")
            + snapshot.data
            + b"\r\n"
        )
