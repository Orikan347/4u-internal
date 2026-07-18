#!/usr/bin/env python3
"""Create private Windows candidate SBOM and evidence after a Windows build.

This tool is local-only and does not build, sign, upload, register, or send.
It accepts an already-built unsigned EXE plus its no-send self-test report and
writes deterministic JSON evidence.  A fake EXE may be used only with
``--test-fixture``; that mode is visibly non-candidate and non-deliverable.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
from pathlib import Path


RELEASE_ID_RE = re.compile(r"DA-LINE-WINDOWS-[0-9]{8}-[0-9]+$")
EXPECTED_RELEASE_ID = "DA-LINE-WINDOWS-20260717-8000"
EXPECTED_BOUND_SOURCE_SHA256 = "8a27557bbfed371391a3ec648ff596c27a6ab2e8daf18bcd1f02077c8aa101c4"
EXPECTED_TEMPLATE_SOURCE_SHA256 = "116dcd7f89a933029f054f83ec90dbc94ea100fe369b22796652aa0c12d6e3c0"
EXPECTED_HELPER_SHA256 = "29fd73ca9c347aa6f7f20ccfb21aa495f7764131565603d62125a25aa5017844"
PACKAGES = ("pyautogui", "pyperclip", "Pillow", "pyinstaller")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed-in-evidence-runtime"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--binding-manifest", type=Path, required=True)
    parser.add_argument("--bound-source", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--self-test-report", type=Path, required=True)
    parser.add_argument("--sbom-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--test-fixture", action="store_true")
    args = parser.parse_args()

    if not RELEASE_ID_RE.fullmatch(args.release_id) or args.release_id != EXPECTED_RELEASE_ID:
        raise SystemExit("WIN-EVIDENCE-001: exact allocated release_id is required")

    required_inputs = (
        args.binding_manifest, args.bound_source, args.helper, args.exe, args.self_test_report,
    )
    if not all(path.is_file() for path in required_inputs):
        raise SystemExit("WIN-EVIDENCE-000: every required input must exist before any evidence output")

    binding = json.loads(args.binding_manifest.read_text(encoding="utf-8"))
    self_test = json.loads(args.self_test_report.read_text(encoding="utf-8"))
    if not all((
        binding.get("release_id") == EXPECTED_RELEASE_ID,
        binding.get("template_source_sha256") == EXPECTED_TEMPLATE_SOURCE_SHA256,
        binding.get("bound_source_sha256") == EXPECTED_BOUND_SOURCE_SHA256,
        sha256(args.bound_source) == EXPECTED_BOUND_SOURCE_SHA256,
        sha256(args.helper) == EXPECTED_HELPER_SHA256,
        len(args.exe.read_bytes()) > 0,
    )):
        raise SystemExit("WIN-EVIDENCE-002: source or binding drift")
    if not all((
        self_test.get("overall") == "PASS",
        self_test.get("real_data") is False,
        self_test.get("line_ui_opened") is False,
        self_test.get("keyboard_or_clipboard_used") is False,
        self_test.get("external_actions") == [],
    )):
        raise SystemExit("WIN-EVIDENCE-003: no-send self-test boundary is incomplete")

    fixture = bool(args.test_fixture)
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000008000" if fixture else "urn:uuid:00000000-0000-4000-8000-000000008001",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "LINE_AutoSender",
                "version": "8.0.0",
                "properties": [
                    {"name": "deal_alliance.release_id", "value": EXPECTED_RELEASE_ID},
                    {"name": "deal_alliance.channel", "value": "test-fixture" if fixture else "private-unsigned-candidate"},
                ],
            }
        },
        "components": [
            {"type": "library", "name": name, "version": package_version(name)} for name in PACKAGES
        ],
    }
    write_json(args.sbom_output, sbom)

    manifest = {
        "schema_version": "line_windows_private_unsigned_candidate_v1",
        "status": "TEST_FIXTURE_ONLY_ZERO_DELIVERY" if fixture else "PRIVATE_UNSIGNED_CANDIDATE_NOT_FOR_DELIVERY",
        "classification": "FAKE_BINARY_PIPELINE_E2E" if fixture else "CURRENT_PRIVATE_UNSIGNED_WINDOWS_CANDIDATE",
        "reservation_id": "DA-RID-LINE-WINDOWS-PRIVATE-20260717-01",
        "release_id": EXPECTED_RELEASE_ID,
        "version": "8.0.0",
        "app_id": "line_automation_windows",
        "client_id": "deal_alliance_line_windows",
        "product_id": "line_automation",
        "platform": "windows",
        "callback": "dealalliance-line-windows://handoff",
        "pkce": "S256",
        "hashes": {
            "template_source_sha256": EXPECTED_TEMPLATE_SOURCE_SHA256,
            "bound_source_sha256": sha256(args.bound_source),
            "helper_sha256": sha256(args.helper),
            "binary_sha256": sha256(args.exe),
            "sbom_sha256": sha256(args.sbom_output),
            "package_sha256": None,
        },
        "no_send": {
            "self_test_status": "PASS",
            "real_data": False,
            "messages_sent": 0,
            "send_attempts": 0,
            "line_ui_opened": False,
            "keyboard_or_clipboard_used": False,
            "external_actions": [],
        },
        "gates": {
            "formal_registry_allowed": False,
            "customer_delivery_allowed": False,
            "protected_download_allowed": False,
            "authenticode_verified": False,
            "clean_windows_gui_no_send_verified": False,
        },
        "test_fixture": fixture,
    }
    write_json(args.manifest_output, manifest)
    print(json.dumps({
        "status": "FAKE_PIPELINE_E2E_PASS" if fixture else "PRIVATE_UNSIGNED_EVIDENCE_CREATED",
        "manifest_sha256": sha256(args.manifest_output),
        "sbom_sha256": sha256(args.sbom_output),
        "messages_sent": 0,
        "send_attempts": 0,
        "external_actions": [],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
