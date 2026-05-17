from services.database_service import DatabaseService


def test_insert_and_list_session_records(tmp_path):
    service = DatabaseService(tmp_path / "records.sqlite3")

    record = service.insert_local_record(
        {
            "batch_id": "batch-1",
            "product_name": "土豆",
            "weight": "12.5",
            "unit": "kg",
            "recorder": "tester",
            "intake_datetime": "2026-05-16 08:00:00",
            "detection_model": "yolov11",
            "ocr_model": "paddleocr",
            "frames": {"entrance": "entrance.jpg"},
            "raw_result": {"status": "ok"},
        }
    )

    records = service.list_session_records()

    assert record["id"] == records[0]["id"]
    assert records[0]["product_name"] == "土豆"
    assert records[0]["weight"] == 12.5
    assert records[0]["intake_date"] == "2026-05-16"
    assert records[0]["frames"] == {"entrance": "entrance.jpg"}


def test_upload_without_mysql_config_returns_clear_error(tmp_path, monkeypatch):
    service = DatabaseService(tmp_path / "records.sqlite3")
    service.insert_local_record({"product_name": "白菜", "weight": 3})
    monkeypatch.delenv("MYSQL_HOST", raising=False)
    monkeypatch.delenv("MYSQL_USER", raising=False)
    monkeypatch.delenv("MYSQL_PASSWORD", raising=False)
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)

    try:
        service.upload_session_pending_to_mysql()
    except RuntimeError as exc:
        assert "MySQL is not configured" in str(exc)
    else:
        raise AssertionError("Expected missing MySQL configuration to fail")


def test_clear_local_cache_deletes_records_and_session_ids(tmp_path):
    service = DatabaseService(tmp_path / "records.sqlite3")
    service.insert_local_record({"product_name": "白菜", "weight": 3})

    result = service.clear_local_cache()

    assert result["deleted"] == 1
    assert service.list_session_records() == []


def test_normalize_datetime_accepts_datetime_local_value():
    assert DatabaseService._normalize_datetime("2026-05-18T10:20") == "2026-05-18 10:20:00"
