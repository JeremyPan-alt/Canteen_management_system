"""Batch capture and detection scheduling service."""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from camera.buffer import FrameSnapshot
from camera.manager import CameraManager
from services.detection_service import DetectionService

LOGGER = logging.getLogger(__name__)


@dataclass
class CaptureBatch:
    batch_id: str
    created_at: float
    trigger_type: str
    recorder: str
    detection_model: str
    ocr_model: str
    status: str
    frames: dict[str, Optional[str]]
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    progress_logs: list[dict[str, Any]] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class CaptureJob:
    batch_id: str


class CaptureService:
    def __init__(
        self,
        camera_manager: CameraManager,
        detection_service: DetectionService,
        storage_dir: str | Path = "data/captures",
    ) -> None:
        self._camera_manager = camera_manager
        self._detection_service = detection_service
        self._storage_dir = Path(storage_dir)
        self._jobs: queue.Queue[CaptureJob] = queue.Queue(maxsize=100)
        self._batches: dict[str, CaptureBatch] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="detection-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def submit_capture(
        self,
        trigger_type: str = "manual",
        recorder: str = "anonymous",
        detection_model: str = "yolov11",
        ocr_model: str = "paddleocr",
    ) -> CaptureBatch:
        batch_id = uuid.uuid4().hex
        batch_dir = self._storage_dir / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)

        snapshots = self._camera_manager.capture_all()
        frames = {
            camera_id: self._write_snapshot(batch_dir, camera_id, snapshot)
            for camera_id, snapshot in snapshots.items()
        }

        batch = CaptureBatch(
            batch_id=batch_id,
            created_at=time.time(),
            trigger_type=trigger_type,
            recorder=recorder,
            detection_model=detection_model,
            ocr_model=ocr_model,
            status="queued",
            frames=frames,
        )
        with self._lock:
            self._batches[batch_id] = batch
        self._append_progress(batch_id, "已抓取当前左右两路画面，检测任务已进入队列")

        try:
            self._jobs.put_nowait(CaptureJob(batch_id=batch_id))
        except queue.Full as exc:
            self._update_batch(batch_id, status="failed", error="Detection queue is full")
            raise RuntimeError("Detection queue is full") from exc

        return self.get_batch(batch_id) or batch

    def get_batch(self, batch_id: str) -> Optional[CaptureBatch]:
        with self._lock:
            batch = self._batches.get(batch_id)
            if not batch:
                return None
            return CaptureBatch(**asdict(batch))

    def list_batches(self) -> list[CaptureBatch]:
        with self._lock:
            return [CaptureBatch(**asdict(batch)) for batch in self._batches.values()]

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._process_job(job)
            except Exception as exc:  # noqa: BLE001 - scheduler must stay alive.
                LOGGER.exception("Capture batch %s failed", job.batch_id)
                self._update_batch(job.batch_id, status="failed", error=str(exc))
            finally:
                self._jobs.task_done()

    def _process_job(self, job: CaptureJob) -> None:
        batch = self.get_batch(job.batch_id)
        if not batch:
            return
        self._update_batch(job.batch_id, status="processing")
        self._append_progress(job.batch_id, "检测调度线程已开始处理")

        entrance_path = self._path_or_none(batch.frames.get("entrance"))
        scale_path = self._path_or_none(batch.frames.get("scale"))
        product_images = [path for path in [entrance_path] if path is not None]
        for message in self._detection_service.runtime_diagnostics():
            self._append_progress(job.batch_id, message)
        self._append_progress(job.batch_id, f"进货区图片数量：{len(product_images)}，秤面图片：{'已获取' if scale_path else '未获取'}")

        result = {
            "batch_id": batch.batch_id,
            "time": batch.created_at,
            "recorder": batch.recorder,
            "trigger_type": batch.trigger_type,
            "detection_model": batch.detection_model,
            "ocr_model": batch.ocr_model,
            "products": self._detection_service.detect_products(
                product_images,
                batch.detection_model,
                progress=lambda message: self._append_progress(job.batch_id, message),
            ),
            "weight": self._detection_service.recognize_weight(
                scale_path,
                batch.ocr_model,
                progress=lambda message: self._append_progress(job.batch_id, message),
            ),
            "frames": batch.frames,
        }
        self._append_progress(job.batch_id, "检测和 OCR 处理完成，正在生成待确认结果")
        result["suggested_record"] = self._detection_service.build_suggested_record(
            products=result["products"],
            weight=result["weight"],
        )

        result_path = self._storage_dir / batch.batch_id / "result.json"
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result["result_path"] = str(result_path)
        self._append_progress(job.batch_id, "结果文件已保存，等待录入人员确认")
        self._update_batch(job.batch_id, status="completed", result=result, error=None)

    def _write_snapshot(
        self,
        batch_dir: Path,
        camera_id: str,
        snapshot: Optional[FrameSnapshot],
    ) -> Optional[str]:
        if snapshot is None:
            return None
        path = batch_dir / f"{camera_id}.jpg"
        path.write_bytes(snapshot.data)
        return str(path)

    def _path_or_none(self, value: Optional[str]) -> Optional[Path]:
        return Path(value) if value else None

    def _update_batch(
        self,
        batch_id: str,
        *,
        status: str,
        result: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        with self._lock:
            batch = self._batches.get(batch_id)
            if not batch:
                return
            batch.status = status
            batch.updated_at = time.time()
            if result is not None:
                batch.result = result
            batch.error = error

    def _append_progress(self, batch_id: str, message: str) -> None:
        with self._lock:
            batch = self._batches.get(batch_id)
            if not batch:
                return
            batch.progress_logs.append(
                {
                    "time": time.strftime("%H:%M:%S"),
                    "message": message,
                }
            )
            batch.updated_at = time.time()
