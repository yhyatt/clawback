"""Append-only raw input log. Every message directed at Kai is recorded before parsing."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

# Default log location
DEFAULT_LOG_PATH = Path.home() / ".clawback" / "raw_inputs.jsonl"

ParseStatus = Literal["ok", "error", "ignored"]


def get_log_path() -> Path:
    """Get the log file path, respecting CLAWBACK_LOG_PATH env var."""
    env_path = os.environ.get("CLAWBACK_LOG_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_LOG_PATH


def ensure_log_dir(log_path: Path) -> None:
    """Ensure the log directory exists."""
    log_path.parent.mkdir(parents=True, exist_ok=True)


def log_input(
    input_text: str,
    chat_id: str,
    parse_status: ParseStatus,
    error_msg: str | None = None,
    log_path: Path | None = None,
) -> None:
    """
    Append a raw input entry to the log file.

    Args:
        input_text: The raw input text from the user
        chat_id: Unique identifier for the chat/conversation
        parse_status: Result of parsing - "ok", "error", or "ignored"
        error_msg: Error message if parse_status is "error"
        log_path: Optional custom log path (for testing)
    """
    if log_path is None:
        log_path = get_log_path()

    ensure_log_dir(log_path)

    entry = {
        "ts": datetime.now().isoformat(),
        "chat_id": chat_id,
        "input": input_text,
        "parse_status": parse_status,
    }

    if error_msg is not None:
        entry["error_msg"] = error_msg

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_log(log_path: Path | None = None, limit: int | None = None) -> list[dict[str, object]]:
    """
    Read entries from the log file.

    Args:
        log_path: Optional custom log path
        limit: Maximum number of entries to return (from end of file)

    Returns:
        List of log entries as dictionaries
    """
    if log_path is None:
        log_path = get_log_path()

    if not log_path.exists():
        return []

    entries = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    if limit is not None:
        return entries[-limit:]
    return entries
