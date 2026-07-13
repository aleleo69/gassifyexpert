#!/usr/bin/env python3
"""CGI endpoint that returns posted JSON/CSV content as a file download."""

from __future__ import annotations

import os
import sys
from urllib.parse import parse_qs


def main() -> None:
    """Read posted content and emit it with Content-Disposition."""
    length = int(os.environ.get("CONTENT_LENGTH") or "0")
    raw = sys.stdin.buffer.read(length).decode("utf-8") if length else ""
    form = parse_qs(raw, keep_blank_values=True)
    file_type = (form.get("file_type", ["json"])[0] or "json").lower()
    content = form.get("content", [""])[0]

    if file_type == "csv":
        filename = "gasifier_result.csv"
        content_type = "text/csv; charset=utf-8"
    else:
        filename = "gasifier_result.json"
        content_type = "application/json; charset=utf-8"

    body = content.encode("utf-8")
    headers = (
        "Status: 200 OK\r\n"
        f"Content-Type: {content_type}\r\n"
        f'Content-Disposition: attachment; filename="{filename}"\r\n'
        f"Content-Length: {len(body)}\r\n"
        "\r\n"
    ).encode("utf-8")
    sys.stdout.buffer.write(headers)
    sys.stdout.buffer.write(body)


if __name__ == "__main__":
    main()
