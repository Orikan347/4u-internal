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
    check(results, "WIN-ARTIFACT-002", manifest.get("release_id") == "DA-LINE-WINDOWS-20260717-8000"
          and manifest.get("version") == "8.0.0" and manifest.get("app_id") == "line_automation_windows",
          "Exact allocated Windows identity is present.")
    hashes = manifest.get("hashes", {})
    check(results, "WIN-ARTIFACT-003", hashes.get("binary_sha256") == sha256(args.exe)
          and hashes.get("sbom_sha256") == sha256(args.sbom)
          and hashes.get("bound_source_sha256") == "8a27557bbfed371391a3ec648ff596c27a6ab2e8daf18bcd1f02077c8aa101c4",
          "Binary, SBOM and release-bound source hashes are exact.")
    evidence_hashes = evidence.get("hashes", {})
    check(results, "WIN-ARTIFACT-004", evidence_hashes.get("binary_sha256") == sha256(args.exe)
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
