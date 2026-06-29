from data_tools.fund_universe import (
    load_progress,
    save_progress,
    update_progress,
    is_in_cooldown,
    EMPTY_PROGRESS_RECORD,
)


def test_load_progress_empty_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    assert load_progress() == {}


def test_save_and_load_progress_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    data = {
        "000001": {"last_sync_at": "2026-06-27T22:15:32", "last_status": "ok",
                   "fail_count": 0, "cooldown_until": None, "fields": {}}
    }
    save_progress(data)
    assert load_progress() == data


def test_update_progress_writes_new_record(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    update_progress(
        "000001",
        last_status="ok",
        fail_count=0,
        fields={"nav": "ok", "info": "ok"},
    )
    rec = load_progress()["000001"]
    assert rec["last_status"] == "ok"
    assert rec["fail_count"] == 0
    assert rec["fields"] == {"nav": "ok", "info": "ok"}
    assert rec["last_sync_at"]  # 非空


def test_update_progress_preserves_existing_fields(tmp_path, monkeypatch):
    monkeypatch.setattr("data_tools.fund_universe.get_meta_dir", lambda: str(tmp_path))
    update_progress("000001", last_status="ok", fail_count=0, fields={"nav": "ok"})
    update_progress("000001", last_status="ok", fail_count=0, fields={"info": "ok"})
    rec = load_progress()["000001"]
    assert rec["fields"] == {"nav": "ok", "info": "ok"}


def test_is_in_cooldown_no_record_returns_false():
    assert is_in_cooldown({}, {}) is False
    assert is_in_cooldown(None, {}) is False


def test_is_in_cooldown_expired_returns_false():
    from datetime import datetime, timedelta
    rec = {"cooldown_until": (datetime.now() - timedelta(days=1)).isoformat()}
    assert is_in_cooldown(rec, {}) is False


def test_is_in_cooldown_active_returns_true():
    from datetime import datetime, timedelta
    rec = {"cooldown_until": (datetime.now() + timedelta(days=2)).isoformat()}
    assert is_in_cooldown(rec, {}) is True


def test_is_in_cooldown_null_until_returns_false():
    rec = {"cooldown_until": None}
    assert is_in_cooldown(rec, {}) is False


def test_empty_progress_record_shape():
    assert set(EMPTY_PROGRESS_RECORD.keys()) == {
        "last_sync_at", "last_status", "fail_count", "cooldown_until", "fields"
    }
