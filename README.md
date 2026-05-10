# Canteen Management System

食堂食材进货自动录入系统的第一阶段实现：跨 Windows / Linux / Jetson 的双路视频采集、实时预览、状态监控和“开始录入”批次抓拍接口。

## 当前能力

- 两路摄像头统一走 `BaseCamera` 抽象：
  - `start()`
  - `stop()`
  - `get_latest_frame()`
  - `reconnect()`
  - `capture_snapshot()`
- 使用 FFmpeg 子进程读取 RTSP、Windows dshow、Linux v4l2、本机摄像头或测试源。
- Jetson CSI 摄像头使用 GStreamer (`gst-launch-1.0`) 管线读取。
- 每路摄像头独立采集线程，只保留最新帧，不堆积队列。
- 任意一路摄像头异常时仅该路标记离线并自动重连，Flask 主进程和另一路视频不退出。
- Flask API 提供：
  - `GET /api/cameras/status`
  - `GET /api/cameras/<camera_id>/stream`
  - `POST /api/capture/start`
  - `GET /api/capture/<batch_id>`
- Vue 前端固定显示左右两块黑色视频区域，离线时居中显示“视频流读取异常请检查”，并用红绿小点显示在线/离线和视频来源。
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
│   ├── camera.demo.yaml
│   ├── camera.jetson.yaml
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

默认 `config/camera.yaml` 面向 Windows/普通电脑测试：

- 左侧 `entrance` 会尝试调用第一路本机摄像头。
- 右侧 `scale` 默认是待替换的 RTSP 地址。如果没有真实秤摄像头，前端会显示“视频流读取异常请检查”，程序不会退出。

无真实摄像头时，可用测试源配置启动：

```bash
CAMERA_CONFIG=config/camera.demo.yaml python app.py
```

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
  name: 进货区实时画面
  source_type: rtsp
  source_label: RTSP
  source: rtsp://user:password@192.168.1.10:554/stream1
```

Windows 笔记本/USB 摄像头：

```yaml
- id: entrance
  name: 进货区实时画面
  source_type: webcam
  source_label: 电脑摄像头
  # auto 会枚举并使用第一路 DirectShow 视频设备。
  source: auto
```

如果要指定 Windows 设备名：

```yaml
- id: entrance
  name: 进货区实时画面
  source_type: webcam
  source_label: 电脑摄像头
  source: video=Integrated Camera
```

Jetson CSI 摄像头：

```yaml
- id: entrance
  name: 进货区实时画面
  source_type: csi
  source_label: CSI
  # nvarguscamerasrc sensor-id
  source: "0"
```

Jetson 使用示例配置：

```bash
CAMERA_CONFIG=config/camera.jetson.yaml python app.py
```

Linux USB 摄像头：

```yaml
- id: entrance
  name: 进货区实时画面
  source_type: device
  source_label: 电脑摄像头
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
