#!/usr/bin/env python3
"""Finalize package hash evidence without changing the packaged manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("test_fixture") is True:
        status = "TEST_FIXTURE_FINAL_EVIDENCE_NOT_A_CANDIDATE"
    elif manifest.get("status") == "PRIVATE_UNSIGNED_CANDIDATE_NOT_FOR_DELIVERY":
        status = "PRIVATE_UNSIGNED_CANDIDATE_HASHES_COMPLETE_NOT_FOR_DELIVERY"
    else:
        raise SystemExit("WIN-FINALIZE-001: manifest state is not finalizable")
    expected = manifest.get("hashes", {})
    if expected.get("binary_sha256") != sha256(args.exe) or expected.get("sbom_sha256") != sha256(args.sbom):
        raise SystemExit("WIN-FINALIZE-002: binary or SBOM drift")

    evidence = {
        "schema_version": "line_windows_private_unsigned_package_evidence_v1",
        "status": status,
        "release_id": manifest.get("release_id"),
        "version": manifest.get("version"),
        "app_id": manifest.get("app_id"),
        "hashes": {
            "binary_sha256": sha256(args.exe),
            "package_sha256": sha256(args.package),
            "sbom_sha256": sha256(args.sbom),
            "candidate_manifest_sha256": sha256(args.manifest),
            "bound_source_sha256": expected.get("bound_source_sha256"),
        },
        "messages_sent": 0,
        "send_attempts": 0,
        "formal_registry_allowed": False,
        "customer_delivery_allowed": False,
        "protected_download_allowed": False,
        "external_actions": [],
        "test_fixture": manifest.get("test_fixture") is True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "evidence_sha256": sha256(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
