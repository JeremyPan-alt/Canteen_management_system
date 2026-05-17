"""Model service contracts for YOLO and OCR integration."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

ProgressCallback = Optional[Callable[[str], None]]


class DetectionService:
    def runtime_diagnostics(self) -> list[str]:
        messages = ["开始读取推理设备信息"]
        try:
            import torch  # type: ignore
        except ImportError:
            messages.append("未安装 PyTorch，YOLO 将使用未配置/占位流程")
            return messages

        if torch.cuda.is_available():
            device_count = torch.cuda.device_count()
            devices = [torch.cuda.get_device_name(index) for index in range(device_count)]
            messages.append(f"CUDA 可用，检测到 {device_count} 个设备：{', '.join(devices)}")
        else:
            messages.append("CUDA 不可用，将使用 CPU 或占位流程")
        return messages

    def available_models(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "detection_models": [
                {
                    "id": "yolov11",
                    "name": "YOLOv11",
                    "description": "使用 ultralytics YOLO 接口加载 YOLOv11 权重",
                    "available": bool(os.getenv("YOLO_MODEL_PATH")),
                }
            ],
            "ocr_models": [
                {
                    "id": "paddleocr",
                    "name": "PaddleOCR",
                    "description": "使用 PaddleOCR 识别秤面数字",
                    "available": self._paddleocr_available(),
                }
            ],
        }

    def detect_products(
        self,
        image_paths: list[Path],
        model_id: str = "yolov11",
        progress: ProgressCallback = None,
    ) -> list[dict[str, Any]]:
        self._progress(progress, f"准备加载目标检测模型：{model_id}")
        if model_id == "yolov11" and os.getenv("YOLO_MODEL_PATH"):
            return self._detect_with_yolo(image_paths, progress)
        self._progress(progress, "YOLO 权重未配置，返回可人工编辑的空检测结果")
        return [
            {
                "image_path": str(path),
                "products": [],
                "status": f"{model_id}_model_not_configured",
            }
            for path in image_paths
        ]

    def recognize_weight(
        self,
        image_path: Path | None,
        model_id: str = "paddleocr",
        progress: ProgressCallback = None,
    ) -> dict[str, Any]:
        self._progress(progress, f"准备加载 OCR 模型：{model_id}")
        if image_path is None:
            self._progress(progress, "未获取到秤面图片，OCR 跳过")
            return {"weight": None, "unit": "kg", "status": "no_scale_frame"}
        if model_id == "paddleocr" and self._paddleocr_available():
            return self._recognize_with_paddleocr(image_path, progress)
        self._progress(progress, "PaddleOCR 未安装或未配置，返回可人工编辑的空重量结果")
        return {
            "image_path": str(image_path),
            "weight": None,
            "unit": "kg",
            "status": f"{model_id}_not_configured",
        }

    def build_suggested_record(
        self,
        *,
        products: list[dict[str, Any]],
        weight: dict[str, Any],
    ) -> dict[str, Any]:
        product_name = ""
        confidence = None
        for image_result in products:
            detected = image_result.get("products") or []
            if detected:
                first = detected[0]
                product_name = str(first.get("name") or "")
                confidence = first.get("confidence")
                break
        return {
            "product_name": product_name,
            "weight": weight.get("weight"),
            "unit": weight.get("unit") or "kg",
            "confidence": confidence,
            "notes": "",
        }

    def _detect_with_yolo(self, image_paths: list[Path], progress: ProgressCallback = None) -> list[dict[str, Any]]:
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError:
            self._progress(progress, "未安装 ultralytics，无法加载 YOLOv11")
            return [
                {
                    "image_path": str(path),
                    "products": [],
                    "status": "ultralytics_not_installed",
                }
                for path in image_paths
            ]

        self._progress(progress, f"正在加载 YOLO 权重：{os.environ['YOLO_MODEL_PATH']}")
        model = YOLO(os.environ["YOLO_MODEL_PATH"])
        self._progress(progress, f"YOLO 模型加载完成，开始检测 {len(image_paths)} 张图片")
        results = []
        for path in image_paths:
            image_products = []
            for prediction in model.predict(str(path), verbose=False):
                names = prediction.names
                for box in prediction.boxes:
                    class_id = int(box.cls[0])
                    image_products.append(
                        {
                            "name": str(names.get(class_id, class_id)),
                            "confidence": float(box.conf[0]),
                            "bbox": [float(value) for value in box.xyxy[0].tolist()],
                        }
                    )
            results.append({"image_path": str(path), "products": image_products, "status": "ok"})
            self._progress(progress, f"目标检测完成：{path.name}，识别到 {len(image_products)} 个目标")
        return results

    def _recognize_with_paddleocr(self, image_path: Path, progress: ProgressCallback = None) -> dict[str, Any]:
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError:
            self._progress(progress, "未安装 paddleocr，无法加载 PaddleOCR")
            return {
                "image_path": str(image_path),
                "weight": None,
                "unit": "kg",
                "status": "paddleocr_not_installed",
            }

        self._progress(progress, "正在初始化 PaddleOCR")
        ocr = PaddleOCR(use_angle_cls=True, lang="en")
        self._progress(progress, f"开始 OCR 识别：{image_path.name}")
        result = ocr.ocr(str(image_path), cls=True)
        texts = []
        for line_group in result or []:
            for line in line_group or []:
                if len(line) >= 2:
                    texts.append(str(line[1][0]))
        joined = " ".join(texts)
        match = re.search(r"(\d+(?:\.\d+)?)", joined)
        return {
            "image_path": str(image_path),
            "weight": float(match.group(1)) if match else None,
            "unit": "kg",
            "raw_text": joined,
            "status": "ok" if match else "no_number_detected",
        }

    @staticmethod
    def _progress(progress: ProgressCallback, message: str) -> None:
        if progress:
            progress(message)

    @staticmethod
    def _paddleocr_available() -> bool:
        try:
            import paddleocr  # noqa: F401
        except ImportError:
            return False
        return True
