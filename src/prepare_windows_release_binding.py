#!/usr/bin/env python3
"""Create a deterministic, private Windows source binding for one release ID.

This tool performs no network access.  It replaces the checked-in release-ID
placeholder in bytes, calculates both template and bound source hashes, and
can write a temporary build input plus a binding manifest.  The resulting
bound hash is the value that must be recorded and read back from the server
registry before a controlled runner may build an EXE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


PLACEHOLDER = b"__DEAL_ALLIANCE_RELEASE_ID_AT_BUILD__"
RELEASE_ID_RE = re.compile(r"DA-LINE-WINDOWS-[0-9]{8}-[0-9]+$")
REQUIRED_TOKENS = (
    b'APP_ID = "line_automation_windows"',
    b'CLIENT_ID = "deal_alliance_line_windows"',
    b'APP_CALLBACK_SCHEME = "dealalliance-line-windows"',
    b"code_challenge_method",
    b"S256",
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("release_id")
    parser.add_argument("--bound-source", type=Path)
    parser.add_argument("--binding-output", type=Path)
    args = parser.parse_args()

    if not RELEASE_ID_RE.fullmatch(args.release_id):
        raise SystemExit("WIN-REGISTRY-BIND-001: release_id format is invalid")

    template = args.source.read_bytes()
    if template.count(PLACEHOLDER) != 1:
        raise SystemExit("WIN-REGISTRY-BIND-002: source must contain exactly one unbound release placeholder")
    if not all(token in template for token in REQUIRED_TOKENS):
        raise SystemExit("WIN-REGISTRY-BIND-003: source is not the expected Windows OAuth v2 PKCE template")

    bound = template.replace(PLACEHOLDER, args.release_id.encode("ascii"))
    binding = {
        "schema_version": "line_windows_bound_source_v1",
        "status": "LOCAL_BINDING_PREPARED_NOT_SERVER_REGISTERED",
        "release_id": args.release_id,
        "app_id": "line_automation_windows",
        "client_id": "deal_alliance_line_windows",
        "product_id": "line_automation",
        "platform": "windows",
        "callback": "dealalliance-line-windows://handoff",
        "pkce": "S256",
        "template_source_sha256": digest(template),
        "bound_source_sha256": digest(bound),
        "real_data": False,
        "external_actions": [],
    }
    if args.bound_source:
        args.bound_source.parent.mkdir(parents=True, exist_ok=True)
        args.bound_source.write_bytes(bound)
    if args.binding_output:
        args.binding_output.parent.mkdir(parents=True, exist_ok=True)
        args.binding_output.write_text(json.dumps(binding, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"overall": "PASS", "binding": binding}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
