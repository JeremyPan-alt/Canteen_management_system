"""Flask API for camera preview, status, and capture triggers."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Iterator

from flask import Blueprint, Response, current_app, jsonify, request

frame_api = Blueprint("frame_api", __name__, url_prefix="/api")


def _camera_manager():
    return current_app.config["camera_manager"]


def _capture_service():
    return current_app.config["capture_service"]


@frame_api.get("/health")
def health() -> Response:
    return jsonify({"status": "ok"})


@frame_api.get("/cameras/status")
def camera_status() -> Response:
    return jsonify({"cameras": _camera_manager().statuses()})


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
    batch = _capture_service().submit_capture(
        trigger_type=trigger_type,
        recorder=recorder,
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
