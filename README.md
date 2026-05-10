# Canteen Management System

食堂食材进货自动录入系统的第一阶段实现：跨 Windows / Linux / Jetson 的双路视频采集、实时预览、状态监控和“开始录入”批次抓拍接口。

## 当前能力

- 两路摄像头统一走 `BaseCamera` 抽象：
  - `start()`
  - `stop()`
  - `get_latest_frame()`
  - `reconnect()`
  - `capture_snapshot()`
- 使用 FFmpeg 子进程读取 RTSP、Windows dshow、Linux/Jetson v4l2 或测试源。
- 每路摄像头独立采集线程，只保留最新帧，不堆积队列。
- 任意一路摄像头异常时仅该路标记离线并自动重连，Flask 主进程和另一路视频不退出。
- Flask API 提供：
  - `GET /api/cameras/status`
  - `GET /api/cameras/<camera_id>/stream`
  - `POST /api/capture/start`
  - `GET /api/capture/<batch_id>`
- Vue 前端固定显示左右两块黑色视频区域，右上角显示在线/离线。
- “开始录入”会同时抓取左右两路最新画面，写入 `data/captures/<batch_id>/`，再交给后台检测调度线程调用 YOLO/OCR 服务占位接口。

## 项目结构

```text
.
├── app.py
├── api/
│   └── frame_api.py
├── camera/
│   ├── base.py
│   ├── buffer.py
│   ├── ffmpeg_camera.py
│   ├── gstreamer_camera.py
│   ├── manager.py
│   └── opencv_camera.py
├── config/
│   └── camera.yaml
├── frontend/
│   ├── index.html
│   ├── package.json
│   └── src/
├── services/
│   ├── capture_service.py
│   └── detection_service.py
└── tests/
```

## 后端启动

安装 FFmpeg 后运行：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

默认 `config/camera.yaml` 使用 FFmpeg 测试源，不接真实摄像头也能看到两路画面。

## 前端启动

开发模式：

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

如果前端和后端端口不同，可设置：

```bash
VITE_API_BASE=http://localhost:5000 npm --prefix frontend run dev
```

构建后由 Flask 托管：

```bash
npm --prefix frontend run build
python app.py
```

## 摄像头配置示例

RTSP：

```yaml
- id: entrance
  name: 进货区摄像头
  source_type: rtsp
  source: rtsp://user:password@192.168.1.10:554/stream1
```

Windows USB 摄像头：

```yaml
- id: entrance
  name: 进货区摄像头
  source_type: device
  input_format: dshow
  source: video=USB Camera
```

Jetson / Linux USB 摄像头：

```yaml
- id: entrance
  name: 进货区摄像头
  source_type: device
  input_format: v4l2
  source: /dev/video0
```

## 后续接入 YOLO/OCR

`services/detection_service.py` 中预留了模型接口：

- `detect_products(image_paths)`
- `recognize_weight(image_path)`

当前返回 `model_not_configured` / `ocr_not_configured`，后续可在这里加载 YOLO、TensorRT/ONNX Runtime 或 OCR 模型。`POST /api/capture/start` 的返回批次会在后台线程完成后更新为：

```json
{
  "batch_id": "...",
  "time": 1710000000.0,
  "recorder": "web",
  "trigger_type": "manual",
  "products": [],
  "weight": {
    "weight": null,
    "unit": "kg"
  },
  "frames": {
    "entrance": "data/captures/<batch_id>/entrance.jpg",
    "scale": "data/captures/<batch_id>/scale.jpg"
  }
}
```
