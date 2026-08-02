#!/usr/bin/env python3
"""Verify exact private Windows artifact hashes and closed delivery gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath


ALLOWED = {
    "LINE_AutoSender.exe",
    "CANDIDATE_MANIFEST.json",
    "SBOM.cdx.json",
    "Windows使用說明書.pdf",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(results: list[dict], code: str, passed: bool, detail: str) -> None:
    results.append({"code": code, "status": "PASS" if passed else "FAIL", "detail": detail})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--final-evidence", type=Path, required=True)
    parser.add_argument("--allow-test-fixture", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    evidence = json.loads(args.final_evidence.read_text(encoding="utf-8"))
    fixture = manifest.get("test_fixture") is True
    results: list[dict] = []

    check(results, "WIN-ARTIFACT-001", not fixture or args.allow_test_fixture,
          "Test fixtures require an explicit verifier flag and can never become candidates.")
    check(results, "WIN-ARTIFACT-002", manifest.get("release_id") == "DA-LINE-WINDOWS-20260802-8001"
          and manifest.get("version") == "8.0.1" and manifest.get("app_id") == "line_automation_windows"
          and manifest.get("client_id") == "deal_alliance_line_windows"
          and manifest.get("product_id") == "line_automation"
          and manifest.get("platform") == "windows"
          and manifest.get("callback") == "dealalliance-line-windows://handoff"
          and manifest.get("pkce") == "S256"
          and manifest.get("backend_contract_sha256")
          == "93092b1d3dc2d8e26842c11e9d7b8b55374bc90e8ba74cdba96d28ffe2633c5d",
          "Exact allocated Windows identity is present.")
    hashes = manifest.get("hashes", {})
    check(results, "WIN-ARTIFACT-003", hashes.get("binary_sha256") == sha256(args.exe)
          and hashes.get("sbom_sha256") == sha256(args.sbom)
          and hashes.get("bound_source_sha256") == "d85a75dde5892a799fb9f0d952c2ffe2397fc689db5bd40dc3b39bdf92a2a907",
          "Binary, SBOM and release-bound source hashes are exact.")
    evidence_hashes = evidence.get("hashes", {})
    check(results, "WIN-ARTIFACT-004", evidence.get("release_id") == manifest.get("release_id")
          and evidence.get("version") == manifest.get("version")
          and evidence.get("app_id") == manifest.get("app_id")
          and evidence_hashes.get("binary_sha256") == sha256(args.exe)
          and evidence_hashes.get("sbom_sha256") == sha256(args.sbom)
          and evidence_hashes.get("package_sha256") == sha256(args.package)
          and evidence_hashes.get("candidate_manifest_sha256") == sha256(args.manifest),
          "Outer evidence binds binary, package, SBOM and immutable packaged manifest.")
    with zipfile.ZipFile(args.package) as archive:
        names = {
            PurePosixPath(name).name for name in archive.namelist()
            if name and not name.endswith("/")
        }
    check(results, "WIN-ARTIFACT-005", {"LINE_AutoSender.exe", "CANDIDATE_MANIFEST.json", "SBOM.cdx.json"}.issubset(names)
          and names.issubset(ALLOWED), "Package contains only the private-candidate allowlist.")
    no_send = manifest.get("no_send", {})
    check(results, "WIN-ARTIFACT-006", no_send.get("messages_sent") == 0
          and no_send.get("send_attempts") == 0 and no_send.get("external_actions") == []
          and no_send.get("line_ui_opened") is False and no_send.get("keyboard_or_clipboard_used") is False,
          "No-send evidence is zero-dispatch and deidentified.")
    gates = manifest.get("gates", {})
    check(results, "WIN-ARTIFACT-007", all(gates.get(key) is False for key in (
        "formal_registry_allowed", "customer_delivery_allowed", "protected_download_allowed",
        "authenticode_verified", "clean_windows_gui_no_send_verified",
    )) and evidence.get("formal_registry_allowed") is False
          and evidence.get("customer_delivery_allowed") is False
          and evidence.get("protected_download_allowed") is False,
          "Formal registry, delivery, download, Authenticode and clean-Windows gates remain closed.")
    check(results, "WIN-ARTIFACT-008", (fixture and evidence.get("test_fixture") is True
          and manifest.get("status") == "TEST_FIXTURE_ONLY_ZERO_DELIVERY") or (not fixture
          and evidence.get("test_fixture") is False
          and manifest.get("status") == "PRIVATE_UNSIGNED_CANDIDATE_NOT_FOR_DELIVERY"),
          "Fixture and real private-candidate states cannot be confused.")

    overall = "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL"
    print(json.dumps({"suite": "Windows private candidate artifact verifier", "overall": overall,
                      "test_fixture": fixture, "real_data": False, "messages_sent": 0,
                      "send_attempts": 0, "external_actions": [], "results": results},
                     ensure_ascii=False, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
