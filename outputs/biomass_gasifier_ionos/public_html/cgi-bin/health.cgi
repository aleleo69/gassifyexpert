#!/usr/bin/env python3
"""Minimal deployment diagnostic for IONOS CGI hosting."""

import json
import sys

payload = json.dumps(
    {
        "ok": True,
        "message": "Python CGI attivo",
        "python": sys.version.split()[0],
    }
)

print("Status: 200 OK")
print("Content-Type: application/json; charset=utf-8")
print(f"Content-Length: {len(payload.encode('utf-8'))}")
print()
print(payload)

