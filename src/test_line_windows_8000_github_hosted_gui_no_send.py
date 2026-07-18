#!/usr/bin/env python3
"""Success/rejection/cancellation fixtures for the Windows hosted GUI harness."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "src/verify_line_windows_8000_github_hosted_gui_no_send.py"
CONTRACT = ROOT / "release_evidence/line_windows_8000_github_hosted_gui_no_send_contract.json"
EXE_HASH = "63594612df121c7bf49fb909c4f1b004a81e329fb1519a8250f50dce3f4145cd"


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(contract: Path, report: Path | None = None) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(VERIFY), "--contract", str(contract)]
    if report:
        args.extend(("--runtime-report", str(report)))
    return subprocess.run(args, text=True, capture_output=True, check=False)


def base_report(status: str) -> dict:
    return {
        "schema_version": "line_windows_8000_github_hosted_gui_runtime_v1",
        "status": status,
        "overall": "CAPABILITY_PASS_GUI_GATE_PENDING",
        "mode": "CapabilityOnly",
        "release_id": "DA-LINE-WINDOWS-20260717-8000",
        "source_run_id": "29644293092",
        "candidate_exe_sha256": EXE_HASH,
        "exact_exe_bytes_unchanged": True,
        "detail": "deidentified fixture",
        "environment": {
            "user_interactive": True, "session_id": 1, "desktop_name": "Default",
            "screen_width": 1920, "screen_height": 1080, "uiautomation_root_available": True,
        },
        "observations": {
            "auth_required_window_visible": True,
            "cancel_by_closing_app": True,
            "retry_by_relaunching_same_exe": True,
            "blank_input_rejected": False,
            "deidentified_input_entered": False,
            "preview_visible": False,
            "preview_cancelled": False,
        },
        "screenshots": [
            {"name": "01-auth-required.png", "sha256": "a" * 64},
            {"name": "02-auth-required-retry.png", "sha256": "b" * 64},
        ],
        "callback_registry_cleanup_completed": True,
        "local_ephemeral_writes": ["isolated_appdata", "callback_registry_then_cleanup"],
        "external_writes": 0,
        "provider_dependent_cases_executed": False,
        "real_data": False,
        "line_process_started": False,
        "line_ui_touched": False,
        "desktop_driver_exercised": False,
        "keyboard_or_clipboard_sent_to_line": False,
        "final_send_clicked": False,
        "messages_sent": 0,
        "send_attempts": 0,
        "external_delivery_actions": [],
        "gui_no_send_passed": False,
        "authenticode_allowed": False,
        "formal_registry_allowed": False,
        "upload_product_allowed": False,
        "download_catalog_allowed": False,
    }


def main() -> int:
    baseline = run(CONTRACT)
    if baseline.returncode != 0:
        raise AssertionError(f"baseline contract failed\n{baseline.stdout}\n{baseline.stderr}")
    source = json.loads(CONTRACT.read_text(encoding="utf-8"))
    contract_mutations = [
        ("wrong-release", lambda x: x["release_identity"].update(release_id="DA-LINE-WINDOWS-20260717-9999")),
        ("wrong-run", lambda x: x["candidate"].update(source_run_id="1")),
        ("wrong-exe", lambda x: x["candidate"].update(exe_sha256="0" * 64)),
        ("desktop-assumed", lambda x: x["runner"].update(interactive_desktop_guaranteed_by_provider=True)),
        ("provider-open", lambda x: x["lanes"]["provider_dependent_main_window"].update(allowed=True)),
        ("send-open", lambda x: x["safety"].update(send_attempts=1)),
        ("secret-open", lambda x: x["safety"].update(secrets_allowed=True)),
        ("sign-open", lambda x: x["safety"].update(authenticode_allowed=True)),
        ("download-open", lambda x: x["safety"].update(download_catalog_allowed=True)),
        ("wrong-next-gate", lambda x: x.update(next_gate="RELEASE_READY")),
    ]
    report_mutations = [
        ("runtime-wrong-exe", lambda x: x.update(candidate_exe_sha256="0" * 64)),
        ("runtime-line-started", lambda x: x.update(line_process_started=True)),
        ("runtime-registry-left", lambda x: x.update(callback_registry_cleanup_completed=False)),
        ("runtime-external-write", lambda x: x.update(external_writes=1)),
        ("runtime-final-send", lambda x: x.update(final_send_clicked=True)),
        ("runtime-send-attempt", lambda x: x.update(send_attempts=1)),
        ("runtime-gui-overclaim", lambda x: x.update(gui_no_send_passed=True)),
        ("runtime-sign-open", lambda x: x.update(authenticode_allowed=True)),
        ("runtime-provider-borrow", lambda x: x.update(provider_dependent_cases_executed=True)),
        ("runtime-preview-borrow", lambda x: x["observations"].update(preview_visible=True)),
        ("runtime-bad-screenshot", lambda x: x["screenshots"][0].update(sha256="bad")),
        ("runtime-unknown-status", lambda x: x.update(status="RELEASE_READY")),
    ]
    with tempfile.TemporaryDirectory(prefix="line-win-8000-hosted-gui-") as raw:
        tmp = Path(raw)
        for index, (label, mutate) in enumerate(contract_mutations):
            item = copy.deepcopy(source)
            mutate(item)
            path = tmp / f"contract-{index}-{label}.json"
            write(path, item)
            if run(path).returncode == 0:
                raise AssertionError(f"{label} unexpectedly passed")
        success = tmp / "runtime-success.json"
        write(success, base_report("GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_PASS_AUTH_REQUIRED_ONLY"))
        if run(CONTRACT, success).returncode != 0:
            raise AssertionError("safe auth-required capability fixture failed")
        for index, (label, mutate) in enumerate(report_mutations):
            item = base_report("GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_PASS_AUTH_REQUIRED_ONLY")
            mutate(item)
            path = tmp / f"runtime-{index}-{label}.json"
            write(path, item)
            if run(CONTRACT, path).returncode == 0:
                raise AssertionError(f"{label} unexpectedly passed")
        blocked = base_report("GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_NO_INTERACTIVE_DESKTOP")
        blocked["overall"] = "CAPABILITY_BLOCKED"
        blocked["environment"].update(user_interactive=False, session_id=0, desktop_name="Service-0x0-3e7$")
        blocked["observations"] = {key: False for key in blocked["observations"]}
        blocked["screenshots"] = []
        blocked_path = tmp / "runtime-controlled-capability-block.json"
        write(blocked_path, blocked)
        if run(CONTRACT, blocked_path).returncode != 0:
            raise AssertionError("fixed noninteractive capability Gate was not safely consumable")
    print(json.dumps({
        "suite": "LINE Windows 8000 GitHub-hosted GUI harness fail-closed",
        "overall": "PASS",
        "success_cases": 2,
        "rejection_cases": len(contract_mutations) + len(report_mutations),
        "cancellation_cases": 1,
        "messages_sent": 0,
        "send_attempts": 0,
        "real_data": False,
        "network_requests": 0,
        "external_writes": 0,
        "external_actions": [],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
