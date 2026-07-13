"""Concurrency-safe request counter and access logger."""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone


def record_request(
    log_dir: str,
    remote_ip: str,
    user_agent: str,
    endpoint: str,
    status: str,
) -> int:
    """Append one JSON-line event and return the persistent request count."""
    os.makedirs(log_dir, mode=0o750, exist_ok=True)
    lock_path = os.path.join(log_dir, ".tracker.lock")
    counter_path = os.path.join(log_dir, "counter.txt")
    access_path = os.path.join(log_dir, "access.jsonl")

    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            try:
                with open(counter_path, encoding="ascii") as counter_file:
                    count = int(counter_file.read().strip() or "0")
            except (FileNotFoundError, ValueError):
                count = 0
            count += 1
            with open(counter_path, "w", encoding="ascii") as counter_file:
                counter_file.write(f"{count}\n")
            event = {
                "request_count": count,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "remote_ip": (remote_ip or "unknown")[:64],
                "user_agent": (user_agent or "")[:300],
                "endpoint": endpoint[:120],
                "status": status[:40],
            }
            with open(access_path, "a", encoding="utf-8") as access_file:
                access_file.write(json.dumps(event, ensure_ascii=True) + "\n")
            return count
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
