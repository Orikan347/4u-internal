#!/usr/bin/env python3
"""Static and model tests for the successor-safe Windows build workflow.

These tests never grant an authorization, build an EXE, invoke Actions, start
LINE, or access the network.  The model exists only to prove that the workflow's
pre-build decision contract rejects drift/replay/output collisions.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/build-line-autosender-windows.yml"
WORKFLOW_BYTES = WORKFLOW.read_bytes()
WORKFLOW_TEXT = WORKFLOW_BYTES.decode("utf-8")

IDENTITY_KEYS = (
    "release_id", "version", "build", "app_id", "client_id",
    "product_id", "platform", "callback", "pkce", "source_path",
    "source_sha256", "bound_source_sha256", "helper_path", "helper_sha256",
    "functional_test_path", "functional_test_sha256", "backend_contract_sha256",
)
OUTPUT_KEYS = (
    "bound_source_path", "binding_manifest_path", "binding_helper_path",
    "pyinstaller_work_path", "pyinstaller_spec_path", "gui_exe_path",
    "self_test_source_path", "self_test_exe_path", "functional_report_path", "self_test_report_path",
    "candidate_directory", "candidate_exe_path", "candidate_manifest_path",
    "candidate_sbom_path", "package_path", "final_evidence_path",
    "artifact_name",
)


class PreflightRejected(RuntimeError):
    pass


def packed(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def preflight_model(
    allocation: dict,
    guard: dict,
    authorization: dict,
    *,
    dispatch_hashes: dict[str, str],
    actual_hashes: dict[str, str],
    existing_outputs: set[str] | None = None,
) -> dict:
    """Small dependency-free model of the workflow's pre-build gate."""
    existing_outputs = existing_outputs or set()
    for name in ("allocation", "guard", "authorization"):
        if dispatch_hashes[name] != actual_hashes[name]:
            raise PreflightRejected("WIN-SUCCESSOR-HASH-003")
    for key in IDENTITY_KEYS:
        values = (allocation.get(key), guard.get(key), authorization.get(key))
        if not values[0] or len(set(values)) != 1:
            raise PreflightRejected("WIN-SUCCESSOR-IDENTITY-002")
    for document in (allocation, guard, authorization):
        if document.get("workflow_sha256") != sha(WORKFLOW_BYTES):
            raise PreflightRejected("WIN-SUCCESSOR-HASH-003")
    tooling = tuple(
        tuple((item.get("path"), item.get("sha256")) for item in document.get("tooling_files", ()))
        for document in (allocation, guard, authorization)
    )
    if len(tooling[0]) < 7 or len(set(tooling)) != 1:
        raise PreflightRejected("WIN-SUCCESSOR-HASH-003")
    if guard.get("allocation_sha256") != actual_hashes["allocation"]:
        raise PreflightRejected("WIN-SUCCESSOR-HASH-003")
    if authorization.get("allocation_sha256") != actual_hashes["allocation"]:
        raise PreflightRejected("WIN-SUCCESSOR-HASH-003")
    if authorization.get("guard_sha256") != actual_hashes["guard"]:
        raise PreflightRejected("WIN-SUCCESSOR-HASH-003")
    if not all(document.get("predecessor_release_reuse_forbidden") is True for document in (allocation, guard, authorization)):
        raise PreflightRejected("WIN-SUCCESSOR-IDENTITY-002")
    if not (
        authorization.get("file_mode") == "0600"
        and authorization.get("private_input") is True
        and authorization.get("granted") is True
        and authorization.get("build_authorized") is True
        and authorization.get("consumed") is False
        and authorization.get("maximum_build_attempts") == 1
        and authorization.get("nonce")
    ):
        raise PreflightRejected("WIN-SUCCESSOR-REPLAY-004")
    for key in OUTPUT_KEYS:
        values = tuple(document.get("output_contract", {}).get(key) for document in (allocation, guard, authorization))
        if not values[0] or len(set(values)) != 1:
            raise PreflightRejected("WIN-SUCCESSOR-OUTPUT-005")
        if key != "artifact_name" and values[0] in existing_outputs:
            raise PreflightRejected("WIN-SUCCESSOR-OUTPUT-005")
    allowlists = tuple(tuple(document["output_contract"].get("zip_allowlist", ())) for document in (allocation, guard, authorization))
    if len(allowlists[0]) < 3 or len(set(allowlists)) != 1:
        raise PreflightRejected("WIN-SUCCESSOR-OUTPUT-005")
    return {"status": "PASS", "build_started": False, "output_count": 0}


def make_fixture() -> tuple[dict, dict, dict, dict[str, str]]:
    workflow_hash = sha(WORKFLOW_BYTES)
    output_contract = {
        "bound_source_path": "successor/bound/app.pyw",
        "binding_manifest_path": "successor/bound/manifest.json",
        "binding_helper_path": "successor/bound/helper.py",
        "pyinstaller_work_path": "successor/work",
        "pyinstaller_spec_path": "successor/spec",
        "gui_exe_path": "successor/dist/LINE_AutoSender.exe",
        "self_test_source_path": "successor/bound/self_test.py",
        "self_test_exe_path": "successor/dist/LINE_AutoSenderSelfTest.exe",
        "functional_report_path": "successor/evidence/functional.json",
        "self_test_report_path": "successor/evidence/self-test.json",
        "candidate_directory": "successor/candidate/LINE_Windows",
        "candidate_exe_path": "successor/candidate/LINE_Windows/LINE_AutoSender.exe",
        "candidate_manifest_path": "successor/candidate/LINE_Windows/CANDIDATE_MANIFEST.json",
        "candidate_sbom_path": "successor/candidate/LINE_Windows/SBOM.cdx.json",
        "package_path": "successor/package/LINE_Windows.zip",
        "final_evidence_path": "successor/evidence/final.json",
        "artifact_name": "LINE-WINDOWS-SUCCESSOR-PRIVATE-UNSIGNED",
        "zip_allowlist": ["LINE_AutoSender.exe", "CANDIDATE_MANIFEST.json", "SBOM.cdx.json"],
    }
    identity = {
        "release_id": "DA-LINE-WINDOWS-20991231-9999",
        "version": "9.9.9",
        "build": "9999",
        "app_id": "line_automation_windows",
        "client_id": "deal_alliance_line_windows",
        "product_id": "line_automation",
        "platform": "windows",
        "callback": "dealalliance-line-windows://handoff",
        "pkce": "S256",
        "source_path": "release_binding/LINE_source.pyw",
        "source_sha256": "1" * 64,
        "helper_path": "src/gsheet_helper.py",
        "helper_sha256": "2" * 64,
        "functional_test_path": "src/test_line_windows_successor_functional_dry_run.py",
        "functional_test_sha256": "5" * 64,
        "backend_contract_sha256": "3" * 64,
        "workflow_path": ".github/workflows/build-line-autosender-windows.yml",
        "workflow_sha256": workflow_hash,
        "bound_source_sha256": "4" * 64,
        "predecessor_release_reuse_forbidden": True,
        "tooling_files": [
            {"path": f"src/tool-{index}.py", "sha256": str(index) * 64}
            for index in range(1, 8)
        ],
        "output_contract": output_contract,
    }
    allocation = copy.deepcopy(identity)
    allocation_hash = sha(packed(allocation))
    guard = copy.deepcopy(identity)
    guard.update({"allocation_path": "allocation.json", "allocation_sha256": allocation_hash})
    guard_hash = sha(packed(guard))
    authorization = copy.deepcopy(identity)
    authorization.update({
        "allocation_path": "allocation.json",
        "allocation_sha256": allocation_hash,
        "guard_path": "guard.json",
        "guard_sha256": guard_hash,
        "file_mode": "0600",
        "private_input": True,
        "granted": True,
        "build_authorized": True,
        "consumed": False,
        "maximum_build_attempts": 1,
        "nonce": "fixture-only-not-a-real-secret",
    })
    hashes = {
        "allocation": allocation_hash,
        "guard": guard_hash,
        "authorization": sha(packed(authorization)),
    }
    return allocation, guard, authorization, hashes


class WorkflowStaticTests(unittest.TestCase):
    def test_01_utf8_lf_and_dispatch_only(self) -> None:
        self.assertFalse(WORKFLOW_BYTES.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r\n", WORKFLOW_BYTES)
        self.assertIn("workflow_dispatch:", WORKFLOW_TEXT)
        self.assertNotRegex(WORKFLOW_TEXT, r"(?m)^\s+push:\s*$")
        self.assertIn('PYTHONUTF8: "1"', WORKFLOW_TEXT)
        self.assertIn('PYTHONIOENCODING: "utf-8"', WORKFLOW_TEXT)

    def test_02_no_predecessor_or_release_defaults(self) -> None:
        self.assertNotIn("8001", WORKFLOW_TEXT)
        self.assertNotRegex(WORKFLOW_TEXT, r"DA-LINE-WINDOWS-[0-9]{8}-[0-9]+")
        self.assertNotIn("||", WORKFLOW_TEXT)
        for name in (
            "allocation_path", "allocation_sha256", "guard_path", "guard_sha256",
            "authorization_input_path", "authorization_input_sha256",
        ):
            block = re.search(rf"(?ms)^      {name}:\n(.*?)(?=^      [a-z_]+:|^permissions:)", WORKFLOW_TEXT)
            self.assertIsNotNone(block, name)
            self.assertIn("required: true", block.group(1))
            self.assertNotIn("default:", block.group(1))

    def test_03_gate_precedes_every_build_or_output_step(self) -> None:
        preflight = WORKFLOW_TEXT.index("Exact successor authority preflight and zero-output gate")
        materialize = WORKFLOW_TEXT.index("Materialize exact successor release binding")
        install = WORKFLOW_TEXT.index("Install dependencies")
        build = WORKFLOW_TEXT.index("Build GUI EXE and console self-test sibling")
        package = WORKFLOW_TEXT.index("Create exact private unsigned candidate")
        self.assertLess(preflight, materialize)
        self.assertLess(preflight, install)
        self.assertLess(preflight, build)
        self.assertLess(preflight, package)
        for code in (
            "WIN-SUCCESSOR-IDENTITY-002", "WIN-SUCCESSOR-HASH-003",
            "WIN-SUCCESSOR-REPLAY-004", "WIN-SUCCESSOR-OUTPUT-005",
        ):
            self.assertIn(code, WORKFLOW_TEXT)
        self.assertIn('if (Test-Path -LiteralPath $path)', WORKFLOW_TEXT)

    def test_04_dynamic_job_identity_gui_self_test_and_zip_allowlist(self) -> None:
        for name in ("RELEASE_ID", "RELEASE_VERSION", "RELEASE_BUILD"):
            self.assertIn(f'ExportEnv "{name}"', WORKFLOW_TEXT)
        self.assertIn('"artifact_name"', WORKFLOW_TEXT)
        self.assertIn("$key.ToUpperInvariant()", WORKFLOW_TEXT)
        self.assertIn("--onefile --windowed", WORKFLOW_TEXT)
        self.assertIn("--onefile --console", WORKFLOW_TEXT)
        self.assertIn('"--self-test-no-send"', WORKFLOW_TEXT)
        self.assertIn("messages_sent -ne 0", WORKFLOW_TEXT)
        self.assertIn("send_attempts -ne 0", WORKFLOW_TEXT)
        self.assertIn("ZIP_ALLOWLIST_JSON", WORKFLOW_TEXT)
        self.assertIn('Status -ne "NotSigned"', WORKFLOW_TEXT)
        self.assertIn("steps.authority.outputs.artifact_name", WORKFLOW_TEXT)
        self.assertIn('ExportEnv "FUNCTIONAL_TEST_PATH"', WORKFLOW_TEXT)
        self.assertIn('python $env:FUNCTIONAL_TEST_PATH', WORKFLOW_TEXT)
        self.assertIn("$allocation.tooling_files", WORKFLOW_TEXT)
        self.assertIn('Fail "WIN-SUCCESSOR-HASH-003" "tooling file hash mismatch"', WORKFLOW_TEXT)
        for option in (
            "--release-id $env:RELEASE_ID",
            "--version $env:RELEASE_VERSION",
            "--build $env:RELEASE_BUILD",
            "--bound-source-sha256 $env:EXPECTED_BOUND_SOURCE_SHA256",
            "--backend-contract-sha256 $env:BACKEND_CONTRACT_SHA256",
        ):
            self.assertIn(option, WORKFLOW_TEXT)

    def test_05_valid_model_remains_zero_build(self) -> None:
        allocation, guard, authorization, hashes = make_fixture()
        result = preflight_model(
            allocation, guard, authorization,
            dispatch_hashes=hashes, actual_hashes=hashes,
        )
        self.assertEqual(result, {"status": "PASS", "build_started": False, "output_count": 0})

    def test_06_wrong_identity_is_zero_build_rejected(self) -> None:
        allocation, guard, authorization, hashes = make_fixture()
        guard["version"] = "0.0.1"
        with self.assertRaisesRegex(PreflightRejected, "WIN-SUCCESSOR-IDENTITY-002"):
            preflight_model(allocation, guard, authorization, dispatch_hashes=hashes, actual_hashes=hashes)

    def test_07_wrong_hash_is_zero_build_rejected(self) -> None:
        allocation, guard, authorization, hashes = make_fixture()
        dispatch = dict(hashes)
        dispatch["guard"] = "0" * 64
        with self.assertRaisesRegex(PreflightRejected, "WIN-SUCCESSOR-HASH-003"):
            preflight_model(allocation, guard, authorization, dispatch_hashes=dispatch, actual_hashes=hashes)

    def test_08_replay_is_zero_build_rejected(self) -> None:
        allocation, guard, authorization, hashes = make_fixture()
        authorization["consumed"] = True
        with self.assertRaisesRegex(PreflightRejected, "WIN-SUCCESSOR-REPLAY-004"):
            preflight_model(allocation, guard, authorization, dispatch_hashes=hashes, actual_hashes=hashes)

    def test_09_existing_output_is_zero_build_rejected(self) -> None:
        allocation, guard, authorization, hashes = make_fixture()
        existing = {allocation["output_contract"]["gui_exe_path"]}
        with self.assertRaisesRegex(PreflightRejected, "WIN-SUCCESSOR-OUTPUT-005"):
            preflight_model(
                allocation, guard, authorization,
                dispatch_hashes=hashes, actual_hashes=hashes,
                existing_outputs=existing,
            )

    def test_10_tooling_hash_roster_drift_is_rejected(self) -> None:
        allocation, guard, authorization, hashes = make_fixture()
        guard["tooling_files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(PreflightRejected, "WIN-SUCCESSOR-HASH-003"):
            preflight_model(
                allocation, guard, authorization,
                dispatch_hashes=hashes, actual_hashes=hashes,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
