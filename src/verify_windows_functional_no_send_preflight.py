#!/usr/bin/env python3
"""Static retirement gate for the historical Windows no-auth real driver."""

import ast
import json
import sys
from pathlib import Path


def result(code, passed, detail):
    return {"code": code, "status": "PASS" if passed else "FAIL", "detail": detail}


def main():
    if len(sys.argv) != 3:
        print("usage: verify_windows_functional_no_send_preflight.py <source.pyw> <functional_helper.py>", file=sys.stderr)
        return 2
    source = Path(sys.argv[1]).read_text(encoding="utf-8")
    helper = Path(sys.argv[2]).read_text(encoding="utf-8")
    checks = []
    try:
        ast.parse(source)
        ast.parse(helper)
        checks.append(result("WIN-FUNCTIONAL-001", True, "Functional source and isolated helper parse."))
    except SyntaxError as exc:
        checks.append(result("WIN-FUNCTIONAL-001", False, f"Syntax error: {exc}"))

    required = (
        'APP_CHANNEL = "functional-test"',
        'APP_VERSION = "7.1.0-functional-test"',
        'FUNCTIONAL_TEST_CHANNEL = True',
        'FUNCTIONAL_TEST_NO_AUTH = False',
        'from functional_test_logger import',
        'WIN-FUNCTIONAL-RETIRED',
    )
    for token in required:
        checks.append(result("WIN-FUNCTIONAL-002", token in source, f"Functional marker present: {token}"))

    checks.append(result(
        "WIN-FUNCTIONAL-005",
        "FUNCTIONAL_TEST_NO_AUTH = True" not in source,
        "Historical no-auth real-driver marker is absent.",
    ))

    forbidden = (
        "LicenseAPIClient", "load_license_api_url", "DEAL_ALLIANCE_LICENSE_API_URL",
        "oauth/authorize", "/api/apps/token", "/api/apps/license", "code_verifier",
        "code_challenge", "release_id", "APP_ID =", "CLIENT_ID =", "RELEASE_ID =",
        "webbrowser.open", "urlopen", "urllib", "https://",
        "pyautogui", "pyperclip", "win32clipboard", "ctypes.windll",
        "bring_line_to_front", "copy_image_to_clipboard", "paste_and_verify_line_input",
    )
    for token in forbidden:
        checks.append(result("WIN-FUNCTIONAL-003", token not in source and token not in helper,
                             f"Production authorization/network token absent: {token}"))

    checks.append(result("WIN-FUNCTIONAL-004", "no-network" in helper.lower() and "connected = False" in helper,
                         "Functional logger is a no-network compatibility stub."))
    overall = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    print(json.dumps({
        "suite": "Windows historical functional real-driver retirement preflight",
        "overall": overall,
        "real_data": False,
        "external_actions": [],
        "checks": checks,
    }, ensure_ascii=False, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
