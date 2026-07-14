#!/usr/bin/env python3
"""Static, no-send Windows candidate preflight for the controlled Windows runner."""

import ast
import json
import sys
from pathlib import Path


def require(condition: bool, code: str, detail: str, results: list[dict]) -> None:
    results.append({"code": code, "status": "PASS" if condition else "FAIL", "detail": detail})


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: verify_windows_no_send_preflight.py <windows_source.pyw> <helper.py>", file=sys.stderr)
        return 2
    source_path, helper_path = map(Path, sys.argv[1:])
    source = source_path.read_text(encoding="utf-8")
    helper = helper_path.read_text(encoding="utf-8")
    results: list[dict] = []

    try:
        ast.parse(source)
        ast.parse(helper)
        require(True, "WIN-PREFLIGHT-001", "Python AST parse passed for source and helper.", results)
    except SyntaxError as exc:
        require(False, "WIN-PREFLIGHT-001", f"Python syntax error: {exc}", results)

    forbidden = (
        "ORIKAN_TX_2024", "script.google.com/macros", "verify_license",
        "PERMANENT-*", "SUB-*", "LINE Official Account", "Messaging API",
        "def activate_license", "def issue_lease", "啟用授權碼",
        "DEFAULT_LICENSE_API_URL", "deal-alliance-license-staging",
    )
    for token in forbidden:
        require(token not in source and token not in helper, "WIN-PREFLIGHT-002", f"Forbidden token absent: {token}", results)

    required_source = (
        "class LicenseManager", "acquire_browser_handoff", "refresh_lease",
        "messagebox.askokcancel", "WIN-MSG-001", "WIN-DUP-001",
        "WIN-LINE-003", "WIN-LINE-004", "WIN-CLIP-IMG-001", "send_messages",
        "重複發送次數", "恭喜你已發完全部，或發到重覆的人。",
    )
    for token in required_source:
        require(token in source, "WIN-PREFLIGHT-003", f"Required source guard present: {token}", results)

    require("self.add_name_var" not in source and "final_msg = msg_text" in source,
            "WIN-PREFLIGHT-005",
            "Mac-aligned no-name-prefix behavior is present.", results)

    required_helper = (
        "normalize_license_api_url", "LICENSE_API_ENV", "exchange_app_handoff",
        "renew_app_lease", "/api/apps/handoff/exchange", "/api/apps/lease/renew",
    )
    for token in required_helper:
        require(token in helper, "WIN-PREFLIGHT-004", f"Required short-lease helper contract present: {token}", results)

    overall = "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL"
    print(json.dumps({
        "suite": "Windows private-candidate static no-send preflight",
        "overall": overall,
        "real_data": False,
        "external_actions": [],
        "results": results,
    }, ensure_ascii=False, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
