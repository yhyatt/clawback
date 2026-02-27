"""Tests for Clawback audit module - raw input logging."""

from pathlib import Path

import pytest

from clawback.audit import get_log_path, log_input, read_log


class TestLogInput:
    """Tests for log_input function."""

    def test_log_ok_status(self, tmp_path: Path) -> None:
        """Test logging a successful parse."""
        log_path = tmp_path / "test.jsonl"

        log_input("kai add dinner ₪100 paid by dan", "chat123", "ok", log_path=log_path)

        entries = read_log(log_path)
        assert len(entries) == 1
        assert entries[0]["input"] == "kai add dinner ₪100 paid by dan"
        assert entries[0]["chat_id"] == "chat123"
        assert entries[0]["parse_status"] == "ok"
        assert "error_msg" not in entries[0]
        assert "ts" in entries[0]

    def test_log_error_status(self, tmp_path: Path) -> None:
        """Test logging a failed parse."""
        log_path = tmp_path / "test.jsonl"

        log_input(
            "gibberish",
            "chat456",
            "error",
            error_msg="Could not understand command",
            log_path=log_path,
        )

        entries = read_log(log_path)
        assert len(entries) == 1
        assert entries[0]["input"] == "gibberish"
        assert entries[0]["parse_status"] == "error"
        assert entries[0]["error_msg"] == "Could not understand command"

    def test_log_ignored_status(self, tmp_path: Path) -> None:
        """Test logging an ignored message."""
        log_path = tmp_path / "test.jsonl"

        log_input("random chat message", "chat789", "ignored", log_path=log_path)

        entries = read_log(log_path)
        assert len(entries) == 1
        assert entries[0]["parse_status"] == "ignored"

    def test_log_appends(self, tmp_path: Path) -> None:
        """Test that log_input appends to existing file."""
        log_path = tmp_path / "test.jsonl"

        log_input("first message", "chat1", "ok", log_path=log_path)
        log_input("second message", "chat1", "ok", log_path=log_path)
        log_input("third message", "chat2", "error", error_msg="oops", log_path=log_path)

        entries = read_log(log_path)
        assert len(entries) == 3
        assert entries[0]["input"] == "first message"
        assert entries[1]["input"] == "second message"
        assert entries[2]["input"] == "third message"

    def test_log_creates_directory(self, tmp_path: Path) -> None:
        """Test that log_input creates parent directories."""
        log_path = tmp_path / "subdir" / "nested" / "test.jsonl"

        log_input("test", "chat1", "ok", log_path=log_path)

        assert log_path.exists()
        entries = read_log(log_path)
        assert len(entries) == 1

    def test_log_unicode(self, tmp_path: Path) -> None:
        """Test logging Unicode/Hebrew text."""
        log_path = tmp_path / "test.jsonl"

        log_input("kai add ארוחת ערב ₪340 paid by yonatan", "chat1", "ok", log_path=log_path)

        entries = read_log(log_path)
        assert "ארוחת ערב" in entries[0]["input"]
        assert "₪340" in entries[0]["input"]

    def test_log_emoji(self, tmp_path: Path) -> None:
        """Test logging text with emojis."""
        log_path = tmp_path / "test.jsonl"

        log_input("kai add 🍕 pizza ₪100 paid by dan", "chat1", "ok", log_path=log_path)

        entries = read_log(log_path)
        assert "🍕" in entries[0]["input"]


class TestReadLog:
    """Tests for read_log function."""

    def test_read_empty_log(self, tmp_path: Path) -> None:
        """Test reading a non-existent log file."""
        log_path = tmp_path / "nonexistent.jsonl"

        entries = read_log(log_path)
        assert entries == []

    def test_read_with_limit(self, tmp_path: Path) -> None:
        """Test reading with a limit."""
        log_path = tmp_path / "test.jsonl"

        for i in range(10):
            log_input(f"message {i}", "chat1", "ok", log_path=log_path)

        entries = read_log(log_path, limit=3)
        assert len(entries) == 3
        assert entries[0]["input"] == "message 7"
        assert entries[1]["input"] == "message 8"
        assert entries[2]["input"] == "message 9"

    def test_read_limit_larger_than_file(self, tmp_path: Path) -> None:
        """Test reading with limit larger than entries."""
        log_path = tmp_path / "test.jsonl"

        log_input("only one", "chat1", "ok", log_path=log_path)

        entries = read_log(log_path, limit=100)
        assert len(entries) == 1


class TestGetLogPath:
    """Tests for get_log_path function."""

    def test_default_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test default log path when env var not set."""
        monkeypatch.delenv("CLAWBACK_LOG_PATH", raising=False)

        path = get_log_path()
        assert path == Path.home() / ".clawback" / "raw_inputs.jsonl"

    def test_custom_path_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test custom log path from environment variable."""
        monkeypatch.setenv("CLAWBACK_LOG_PATH", "/custom/path/audit.jsonl")

        path = get_log_path()
        assert path == Path("/custom/path/audit.jsonl")
