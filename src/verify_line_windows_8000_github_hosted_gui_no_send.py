#!/usr/bin/env python3
"""Fail-closed static/runtime verifier for the exact Windows 8000 GUI harness."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "release_evidence/line_windows_8000_github_hosted_gui_no_send_contract.json"
WORKFLOW = ROOT / ".github/workflows/probe-line-windows-8000-gui-no-send.yml"
HARNESS = ROOT / "src/run_line_windows_8000_github_hosted_gui_no_send.ps1"
SELF = Path(__file__).resolve()
TEST = ROOT / "src/test_line_windows_8000_github_hosted_gui_no_send.py"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add(checks: list[dict], code: str, passed: bool, detail: str) -> None:
    checks.append({"code": code, "status": "PASS" if passed else "FAIL", "detail": detail})


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_contract(contract: dict) -> list[dict]:
    checks: list[dict] = []
    identity = contract.get("release_identity", {})
    candidate = contract.get("candidate", {})
    runner = contract.get("runner", {})
    lanes = contract.get("lanes", {})
    safety = contract.get("safety", {})
    workflow = WORKFLOW.read_text(encoding="utf-8")
    harness = HARNESS.read_text(encoding="utf-8")
    add(checks, "WIN-GUI-HARNESS-001", contract.get("schema_version") ==
        "line_windows_8000_github_hosted_gui_no_send_contract_v1"
        and contract.get("status") == "LOCAL_HARNESS_READY_REMOTE_CAPABILITY_UNVERIFIED",
        "Local harness is ready while remote GUI capability remains unverified.")
    add(checks, "WIN-GUI-HARNESS-002", identity == {
        "release_id": "DA-LINE-WINDOWS-20260717-8000", "version": "8.0.0",
        "app_id": "line_automation_windows", "client_id": "deal_alliance_line_windows",
        "callback": "dealalliance-line-windows://handoff", "pkce": "S256",
    }, "Exact release and OAuth PKCE identity are immutable.")
    add(checks, "WIN-GUI-HARNESS-003", candidate.get("source_run_id") == "29644293092"
        and candidate.get("source_commit") == "1eb9269932d17465befb819b284104f6053203ba"
        and candidate.get("artifact_name") == "LINE自動發訊息_Windows候選版"
        and candidate.get("exact_exe_bytes_must_not_change") is True
        and candidate.get("package_sha256") == "88556886e9b657b1038db2b6cccc457532d11cbd1e6a73fffe0943974a772aee"
        and candidate.get("exe_sha256") == "63594612df121c7bf49fb909c4f1b004a81e329fb1519a8250f50dce3f4145cd"
        and candidate.get("manifest_sha256") == "c9bbc0a94d40755a53006b2d4e366159ab2f434348bf8e8e40bf333a0c82d178"
        and candidate.get("sbom_sha256") == "540710435a2323c30fce2f578fbd1f6b071e674c0a976d01dd51bbce96444ab2",
        "Candidate run, commit and all artifact hashes are exact.")
    add(checks, "WIN-GUI-HARNESS-004", runner.get("label") == "windows-2022"
        and runner.get("github_hosted") is True
        and runner.get("interactive_desktop_guaranteed_by_provider") is False
        and runner.get("remote_capability_probe_required") is True,
        "Hosted runner GUI is treated as an observed capability, never an assumption.")
    add(checks, "WIN-GUI-HARNESS-005", lanes.get("capability_and_auth_required", {}).get("allowed") is True
        and lanes.get("capability_and_auth_required", {}).get("oauth_browser_replaced_with_zero_network_stub") is True
        and lanes.get("provider_dependent_main_window", {}).get("allowed") is False
        and lanes.get("provider_dependent_main_window", {}).get("forbidden_action") == "FINAL_CONFIRM_OK",
        "Auth-required probing is allowed; provider-dependent main-window actions are closed.")
    required_statuses = {
        "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_PASS_AUTH_REQUIRED_ONLY",
        "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_NO_INTERACTIVE_DESKTOP",
        "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_UIAUTOMATION_TREE_UNAVAILABLE",
        "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_TK_UIA_PATTERN_UNAVAILABLE",
        "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_AUTH_REQUIRED_WINDOW_NOT_OBSERVED",
        "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_BLOCKED_PROVIDER_IDENTITY_REQUIRED",
        "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_ABORTED_BROWSER_STUB_NOT_INVOKED",
        "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_ABORTED_LINE_PROCESS_PRESENT",
        "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_ABORTED_UNEXPECTED_AUTHENTICATED_MAIN_WINDOW",
    }
    add(checks, "WIN-GUI-HARNESS-006", set(contract.get("allowed_runtime_statuses", [])) == required_statuses,
        "Runtime capability and safety abort codes are closed and enumerable.")
    add(checks, "WIN-GUI-HARNESS-007", safety == {
        "deidentified_fixture_text": "Windows 8000 GitHub hosted GUI no-send fixture",
        "line_must_not_start": True, "final_send_must_not_be_clicked": True,
        "messages_sent": 0, "send_attempts": 0, "real_data": False,
        "secrets_allowed": False, "formal_registry_allowed": False,
        "authenticode_allowed": False, "upload_product_allowed": False,
        "download_catalog_allowed": False,
    }, "Safety contract forbids LINE, final confirmation, secrets and delivery.")
    required_workflow = (
        "runs-on: windows-2022", "run-id: 29644293092", "actions/download-artifact@v5",
        "actions: read", "CapabilityOnly", "if: always()", "retention-days: 3",
        "Language.Parser", "forbidden upload file type", "runtime-report.json", "evidence_allowlist.outcome == 'success'",
        "verify_line_windows_8000_github_hosted_gui_no_send.py",
        "run_line_windows_8000_github_hosted_gui_no_send.ps1",
    )
    add(checks, "WIN-GUI-HARNESS-008", all(token in workflow for token in required_workflow)
        and "push:" not in workflow and "pull_request:" not in workflow and "schedule:" not in workflow,
        "Workflow is manual, read-only, exact-run and capability-only.")
    required_harness = (
        "Get-LineProcesses", "Get-DesktopName", "System.Windows.Automation",
        "zero-network-browser.exe", "exact_exe_bytes_unchanged", "Stop-Process",
        "auth_required_window_visible", "blank_input_rejected", "deidentified_input_entered",
        "preview_visible", "preview_cancelled", "final_send_clicked = $false",
        "messages_sent = 0", "send_attempts = 0", "FINAL_CONFIRM_OK",
        "Clear-EphemeralState", "callback_registry_cleanup_completed", "RUNNER_TEMP",
        "LINE_GUI_SAFE_BROWSER_MARKER", "ABORTED_BROWSER_STUB_NOT_INVOKED",
    )
    add(checks, "WIN-GUI-HARNESS-009", all(token in harness for token in required_harness)
        and "pyautogui" not in harness.lower() and "LINE.exe" not in harness,
        "Harness uses UIAutomation and screenshots without LINE or physical-input tooling.")
    hashes = contract.get("implementation_hashes", {})
    add(checks, "WIN-GUI-HARNESS-010", hashes == {
        "workflow_sha256": digest(WORKFLOW), "harness_sha256": digest(HARNESS),
        "verifier_sha256": digest(SELF), "test_sha256": digest(TEST),
    }, "Implementation files are hash-bound to the contract.")
    add(checks, "WIN-GUI-HARNESS-011", contract.get("next_gate") ==
        "PUSH_AND_DISPATCH_ONLY_AFTER_MAIN_WINDOW_APPROVAL_THEN_CONSUME_FIXED_CAPABILITY_STATUS",
        "The only remote next step remains separately authorized push/dispatch.")
    return checks


def verify_runtime(contract: dict, report: dict) -> list[dict]:
    checks: list[dict] = []
    status = report.get("status")
    add(checks, "WIN-GUI-RUNTIME-001", report.get("schema_version") ==
        "line_windows_8000_github_hosted_gui_runtime_v1"
        and status in set(contract.get("allowed_runtime_statuses", [])),
        "Runtime report uses one closed capability status.")
    add(checks, "WIN-GUI-RUNTIME-002", report.get("release_id") == "DA-LINE-WINDOWS-20260717-8000"
        and report.get("source_run_id") == "29644293092"
        and report.get("candidate_exe_sha256") == contract["candidate"]["exe_sha256"]
        and report.get("exact_exe_bytes_unchanged") is True,
        "Runtime report binds the unchanged exact EXE.")
    add(checks, "WIN-GUI-RUNTIME-003", report.get("real_data") is False
        and report.get("line_process_started") is False and report.get("line_ui_touched") is False
        and report.get("desktop_driver_exercised") is False
        and report.get("keyboard_or_clipboard_sent_to_line") is False
        and report.get("final_send_clicked") is False
        and report.get("messages_sent") == report.get("send_attempts") == 0
        and report.get("external_delivery_actions") == [],
        "Runtime evidence is deidentified and zero-dispatch.")
    add(checks, "WIN-GUI-RUNTIME-003A", report.get("callback_registry_cleanup_completed") is True
        and report.get("local_ephemeral_writes") == ["isolated_appdata", "callback_registry_then_cleanup"]
        and report.get("external_writes") == 0,
        "Ephemeral callback/AppData writes are cleaned and never uploaded as evidence.")
    add(checks, "WIN-GUI-RUNTIME-004", report.get("gui_no_send_passed") is False
        and report.get("authenticode_allowed") is False
        and report.get("formal_registry_allowed") is False
        and report.get("upload_product_allowed") is False
        and report.get("download_catalog_allowed") is False,
        "A hosted capability probe cannot self-promote GUI, signing or delivery.")
    screenshots = report.get("screenshots", [])
    add(checks, "WIN-GUI-RUNTIME-005", isinstance(screenshots, list)
        and all(set(item) == {"name", "sha256"} and HEX64.fullmatch(item["sha256"])
                and "token" not in item["name"].lower() for item in screenshots),
        "Screenshot manifest contains names and hashes only.")
    observations = report.get("observations", {})
    if status == "GITHUB_HOSTED_WINDOWS_GUI_CAPABILITY_PASS_AUTH_REQUIRED_ONLY":
        valid_transition = (observations.get("auth_required_window_visible") is True
            and observations.get("cancel_by_closing_app") is True
            and observations.get("retry_by_relaunching_same_exe") is True
            and all(observations.get(key) is False for key in (
                "blank_input_rejected", "deidentified_input_entered", "preview_visible", "preview_cancelled"))
            and report.get("provider_dependent_cases_executed") is False and len(screenshots) >= 2)
    else:
        valid_transition = report.get("provider_dependent_cases_executed") is False
    add(checks, "WIN-GUI-RUNTIME-006", valid_transition,
        "Capability transition does not borrow provider-dependent main-window evidence.")
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--runtime-report", type=Path)
    args = parser.parse_args()
    contract = load(args.contract)
    checks = verify_contract(contract)
    if args.runtime_report:
        checks.extend(verify_runtime(contract, load(args.runtime_report)))
    overall = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    status = "READY_FOR_CONTROLLED_GITHUB_HOSTED_WINDOWS_CAPABILITY_PROBE" if overall == "PASS" else "WINDOWS_GUI_HARNESS_REJECTED"
    print(json.dumps({
        "suite": "LINE Windows 8000 GitHub-hosted GUI no-send harness",
        "status": status, "overall": overall,
        "checks_passed": sum(item["status"] == "PASS" for item in checks),
        "checks_total": len(checks),
        "messages_sent": 0, "send_attempts": 0, "real_data": False,
        "network_requests": 0, "external_writes": 0, "external_actions": [],
        "results": checks,
    }, ensure_ascii=False, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
