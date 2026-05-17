# Canteen Management System

食堂食材进货自动录入系统：跨 Windows / Linux / Jetson 的双路视频采集、实时预览、YOLO/OCR 检测确认、本地 SQLite 暂存和 MySQL 入库。

## 当前能力

- 两路摄像头统一走 `BaseCamera` 抽象：
  - `start()`
  - `stop()`
  - `get_latest_frame()`
  - `reconnect()`
  - `capture_snapshot()`
- 使用 FFmpeg 子进程读取 RTSP、Linux v4l2 或测试源。
- Windows/普通电脑本机摄像头使用 OpenCV 读取，避免 FFmpeg DirectShow 设备名匹配失败。
- Jetson CSI 摄像头使用 GStreamer (`gst-launch-1.0`) 管线读取。
- 每路摄像头独立采集线程，只保留最新帧，不堆积队列。
- 任意一路摄像头异常时仅该路标记离线并自动重连，Flask 主进程和另一路视频不退出。
- Flask API 提供：
  - `GET /api/models`
  - `GET /api/cameras/status`
  - `GET /api/cameras/<camera_id>/stream`
  - `GET /api/video-sources?camera_id=entrance`
  - `POST /api/cameras/<camera_id>/source`
  - `POST /api/capture/start`
  - `GET /api/capture/<batch_id>`
  - `POST /api/records/local`
  - `DELETE /api/records/local/cache`
  - `POST /api/records/upload-mysql`
  - `GET /api/records/mysql?date=YYYY-MM-DD`
  - `PUT /api/records/mysql/<record_id>`
- Vue 前端固定显示左右两块黑色视频区域，离线时居中显示“视频流读取异常请检查”，并用红绿小点显示在线/离线和视频来源。
- “开始录入”会同时抓取左右两路最新画面，写入 `data/captures/<batch_id>/`，再交给后台检测调度线程调用 YOLO/OCR，弹窗确认后写入 SQLite，最后可批量上传 MySQL。

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
│   ├── database_service.py
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

## 前端切换视频源

在页面中点击 `进货区实时画面` 或 `秤面长焦摄像头` 标题，可以打开向上展开的视频源下拉框：

- Windows / Linux 本机摄像头会由后端用 OpenCV 自动探测，并以 `电脑摄像头 0`、`电脑摄像头 1` 等形式展示。
- 如果本机摄像头已经在某个画面中使用，下拉框会优先复用这个已确认可用的视频源，避免重新扫描时打断当前画面。
- 左右两侧选择同一个电脑摄像头时，系统会共享同一路最新帧，不会重复打开同一个物理摄像头。
- 下拉框中始终包含 `RTSP 视频流`，选择后会弹出输入框，填写 `rtsp://...` 地址后立即切换并重连该路摄像头。
- 切换接口只替换对应摄像头采集线程，不会影响另一侧摄像头或 Flask 主进程。

相关接口：

```http
GET /api/video-sources?camera_id=entrance
POST /api/cameras/entrance/source
```

本机摄像头切换请求：

```json
{
  "source_type": "webcam",
  "source": "0",
  "source_label": "电脑摄像头"
}
```

RTSP 切换请求：

```json
{
  "source_type": "rtsp",
  "source": "rtsp://user:password@192.168.1.10:554/stream1",
  "source_label": "RTSP"
}
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
  # auto 会通过 OpenCV DirectShow 打开摄像头索引 0。
  source: auto
```

如果内置摄像头不是索引 0，可改成：

```yaml
- id: entrance
  name: 进货区实时画面
  source_type: webcam
  source_label: 电脑摄像头
  source: "1"
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

## 检测、OCR、确认和入库流程

页面顶部提供两个模型下拉框：

- 目标检测模型：`YOLOv11`
- OCR 模型：`PaddleOCR`

点击 `开始录入` 后：

1. 同时抓取进货区和秤面两路最新帧。
2. 后台线程调用目标检测和 OCR 服务。
3. 前端显示检测进度，包括 CUDA/CPU 信息、模型加载、目标检测、OCR 等阶段日志。
4. 前端弹出确认框，展示建议的 `菜品名称`、`重量`、`单位`、`记录人`、`入库时间` 等字段。
5. 录入人员可直接修改字段。
6. 点击 `确认录入 SQLite` 后写入本机 SQLite。
7. 视频下方左侧展示本次系统启动后已确认、尚未上传 MySQL 的 SQLite 记录。
8. 点击 `数据入库` 后，本次待上传记录写入 MySQL，并将左侧区域清空，显示 `数据已入库，本地数据库暂无待上传数据`。
9. 如需重置本机缓存，可点击 `清除数据库缓存`，确认后会删除 SQLite 中全部记录。
10. 视频下方右侧展示 MySQL 中指定日期的数据，可通过日期选择器切换，只查询一天的数据。
11. MySQL 数据支持直接编辑；如果修改了入库时间的日期部分，保存后该条目会从当前日期列表消失，并出现在修改后的日期查询结果中。

`services/detection_service.py` 中的模型接口：

- `detect_products(image_paths, model_id="yolov11")`
- `recognize_weight(image_path, model_id="paddleocr")`

如果未安装模型依赖或未配置权重，接口会返回可编辑的空建议结果，不影响抓拍、确认和入库流程。配置 YOLOv11 权重：

```bash
export YOLO_MODEL_PATH=/path/to/yolov11.pt
```

PaddleOCR 为可选依赖，安装后会自动启用：

```bash
pip install paddleocr
```

`POST /api/capture/start` 的返回批次会在后台线程完成后更新为：

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

## SQLite / MySQL 数据库

本机 SQLite 默认路径：

```bash
data/intake_records.sqlite3
```

可通过环境变量修改：

```bash
export SQLITE_DB_PATH=data/intake_records.sqlite3
```

MySQL 连接通过环境变量配置：

```bash
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_USER=root
export MYSQL_PASSWORD=your_password
export MYSQL_DATABASE=canteen
export MYSQL_CHARSET=utf8mb4
```

SQLite 和 MySQL 使用同一张业务表。MySQL 建表语句：

```sql
CREATE TABLE IF NOT EXISTS intake_records (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  batch_id VARCHAR(64),
  product_name VARCHAR(128) NOT NULL,
  weight DECIMAL(10, 3),
  unit VARCHAR(16) NOT NULL DEFAULT 'kg',
  recorder VARCHAR(64),
  intake_datetime DATETIME NOT NULL,
  intake_date DATE NOT NULL,
  detection_model VARCHAR(64),
  ocr_model VARCHAR(64),
  trigger_type VARCHAR(32),
  frames_json JSON,
  raw_result_json JSON,
  notes VARCHAR(512),
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  INDEX idx_intake_records_date (intake_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

## API 接口

模型：

```http
GET /api/models
```

视频源：

```http
GET /api/cameras/status
GET /api/cameras/<camera_id>/stream
GET /api/video-sources?camera_id=entrance
POST /api/cameras/<camera_id>/source
```

抓拍检测：

```http
POST /api/capture/start
GET /api/capture/<batch_id>
GET /api/capture
```

确认入本地库：

```http
POST /api/records/local
GET /api/records/local/session
DELETE /api/records/local/cache
```

MySQL 查询和上传：

```http
POST /api/records/upload-mysql
GET /api/records/mysql?date=2026-05-16
PUT /api/records/mysql/<record_id>
```

MySQL 记录修改请求示例：

```json
{
  "product_name": "西红柿",
  "weight": 5.2,
  "unit": "kg",
  "recorder": "operator",
  "intake_datetime": "2026-05-18T10:20",
  "notes": "人工修正"
}
```
