#!/usr/bin/env python3
"""Fail closed unless Release Security allocated this exact bound source."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_RELEASE = "DA-LINE-WINDOWS-20260802-8001"
EXPECTED_VERSION = "8.0.1"
EXPECTED_TEMPLATE = "e4fbfb4a96e1bd24ac49c8f336524c709894ba8bbb5205bf4a0dd5ed01445ed4"
EXPECTED_BOUND = "d85a75dde5892a799fb9f0d952c2ffe2397fc689db5bd40dc3b39bdf92a2a907"
EXPECTED_BACKEND_CONTRACT = "93092b1d3dc2d8e26842c11e9d7b8b55374bc90e8ba74cdba96d28ffe2633c5d"


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

    add(checks, "WIN-ALLOCATION-001", evidence.get("schema_version") == "line_windows_private_unsigned_successor_allocation_v1"
        and evidence.get("evidence_status") == "PRIVATE_SUCCESSOR_IDENTITY_ALLOCATED_BUILD_ONLY"
        and evidence.get("backend_contract_sha256") == EXPECTED_BACKEND_CONTRACT,
        "Exact backend live-dispatch contract is referenced.")
    add(checks, "WIN-ALLOCATION-002", evidence.get("reservation_id") == "DA-RID-LINE-WINDOWS-PRIVATE-20260802-8001"
        and evidence.get("release_id") == binding.get("release_id") == EXPECTED_RELEASE
        and evidence.get("version") == binding.get("version") == EXPECTED_VERSION
        and evidence.get("build") == "8001",
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
        "IDENTITY_ALLOCATED_PRIVATE_UNSIGNED_BUILD_ONLY"
        and evidence.get("unsigned_artifact_rebuild_preflight_allowed") is True,
        "Only an unsigned private artifact rebuild is authorized by the allocation.")
    add(checks, "WIN-ALLOCATION-006", all(evidence.get(key) is None for key in (
        "binary_sha256", "package_sha256", "sbom_sha256",
    )), "Pre-build evidence does not fabricate artifact hashes.")
    add(checks, "WIN-ALLOCATION-007", all(evidence.get(key) is False for key in (
        "formal_registry_allowed", "product_upload_allowed", "customer_delivery_allowed",
        "protected_download_allowed", "authenticode_allowed", "real_data",
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
