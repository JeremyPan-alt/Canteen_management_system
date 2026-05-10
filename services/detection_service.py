"""Model service contracts for YOLO and OCR integration.

The first milestone wires the video path and API contract. These methods are
placeholders that can later load TensorRT/ONNX/PyTorch YOLO models and an OCR
engine without changing the camera or frontend flow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class DetectionService:
    def detect_products(self, image_paths: list[Path]) -> list[dict[str, Any]]:
        return [
            {
                "image_path": str(path),
                "products": [],
                "status": "model_not_configured",
            }
            for path in image_paths
        ]

    def recognize_weight(self, image_path: Path | None) -> dict[str, Any]:
        if image_path is None:
            return {"weight": None, "unit": "kg", "status": "no_scale_frame"}
        return {
            "image_path": str(image_path),
            "weight": None,
            "unit": "kg",
            "status": "ocr_not_configured",
        }
