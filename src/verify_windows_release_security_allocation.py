#!/usr/bin/env python3
"""Fail closed unless Release Security allocated this exact bound source."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_RELEASE = "DA-LINE-WINDOWS-20260717-8000"
EXPECTED_TEMPLATE = "116dcd7f89a933029f054f83ec90dbc94ea100fe369b22796652aa0c12d6e3c0"
EXPECTED_BOUND = "8a27557bbfed371391a3ec648ff596c27a6ab2e8daf18bcd1f02077c8aa101c4"
EXPECTED_CONTRACT = "249872f189d14cea7a33ac0910159c036f5ac7cc141ff0d3d1c69748bcbc4b4b"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add(checks: list[dict], code: str, passed: bool, detail: str) -> None:
    checks.append({"code": code, "status": "PASS" if passed else "FAIL", "detail": detail})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bound_source", type=Path)
    parser.add_argument("binding_manifest", type=Path)
    parser.add_argument("allocation_evidence", type=Path)
    args = parser.parse_args()
    binding = json.loads(args.binding_manifest.read_text(encoding="utf-8"))
    evidence = json.loads(args.allocation_evidence.read_text(encoding="utf-8"))
    checks: list[dict] = []

    add(checks, "WIN-ALLOCATION-001", evidence.get("schema_version") == "line_windows_release_security_allocation_v1"
        and evidence.get("evidence_status") == "RELEASE_SECURITY_ALLOCATION_READBACK_CAPTURED"
        and evidence.get("source_contract_sha256") == EXPECTED_CONTRACT,
        "Exact Release Security allocation contract is referenced.")
    add(checks, "WIN-ALLOCATION-002", evidence.get("reservation_id") == "DA-RID-LINE-WINDOWS-PRIVATE-20260717-01"
        and evidence.get("release_id") == binding.get("release_id") == EXPECTED_RELEASE
        and evidence.get("version") == "8.0.0",
        "Reservation, final release ID and target version are exact.")
    expected_identity = {
        "app_id": "line_automation_windows", "client_id": "deal_alliance_line_windows",
        "product_id": "line_automation", "platform": "windows",
        "callback": "dealalliance-line-windows://handoff", "pkce": "S256",
    }
    add(checks, "WIN-ALLOCATION-003", all(evidence.get(key) == binding.get(key) == value
        for key, value in expected_identity.items()), "OAuth PKCE consumer identity is unchanged.")
    add(checks, "WIN-ALLOCATION-004", evidence.get("template_source_sha256") == binding.get("template_source_sha256") == EXPECTED_TEMPLATE
        and evidence.get("bound_source_sha256") == binding.get("bound_source_sha256") == EXPECTED_BOUND
        and sha256(args.bound_source) == EXPECTED_BOUND,
        "Allocation and binding refer to the byte-exact source.")
    add(checks, "WIN-ALLOCATION-005", evidence.get("allocation_state") ==
        "IDENTITY_ALLOCATED_UNSIGNED_ARTIFACT_PREFLIGHT_BINARY_PACKAGE_SBOM_PENDING"
        and evidence.get("unsigned_artifact_rebuild_preflight_allowed") is True,
        "Only an unsigned private artifact rebuild is authorized by the allocation.")
    add(checks, "WIN-ALLOCATION-006", all(evidence.get(key) is None for key in (
        "binary_sha256", "package_sha256", "sbom_sha256",
    )), "Pre-build evidence does not fabricate artifact hashes.")
    add(checks, "WIN-ALLOCATION-007", all(evidence.get(key) is False for key in (
        "formal_registry_allowed", "upload_allowed", "customer_delivery_allowed",
        "protected_download_allowed", "real_data",
    )) and evidence.get("external_actions") == [],
        "Formal registry, upload, delivery and download remain closed.")

    overall = "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL"
    print(json.dumps({"suite": "Windows Release Security allocation gate", "overall": overall,
                      "status": "READY_FOR_UNSIGNED_WINDOWS_BUILD" if overall == "PASS" else "ALLOCATION_REJECTED",
                      "real_data": False, "messages_sent": 0, "send_attempts": 0,
                      "network_requests": 0, "external_writes": 0, "external_actions": [],
                      "results": checks}, ensure_ascii=False, indent=2))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
