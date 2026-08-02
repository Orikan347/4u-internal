#!/usr/bin/env python3
"""Zero-network fail-closed tests for the Windows 8001 private build lane."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SOURCE = SRC / "LINE自動發訊息_Windows.pyw"
HELPER = SRC / "gsheet_helper.py"
ALLOCATION = ROOT / "release_evidence/CURRENT_SUCCESSOR_RELEASE_ALLOCATION.json"
RELEASE_ID = "DA-LINE-WINDOWS-20260802-8001"
VERSION = "8.0.1"


def run(*args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != expected:
        raise AssertionError(
            f"expected exit {expected}, got {result.returncode}\n{result.stdout}\n{result.stderr}"
        )
    return result


class SuccessorPrebuildTests(unittest.TestCase):
    def prepare(self, root: Path, *, allocation: Path = ALLOCATION) -> dict[str, Path]:
        bound = root / "LINE自動發訊息_Windows.pyw"
        binding = root / "BOUND_SOURCE_MANIFEST.json"
        helper = root / "gsheet_helper.py"
        helper.write_bytes(HELPER.read_bytes())
        run(
            "python3", str(SRC / "prepare_windows_release_binding.py"), str(SOURCE), RELEASE_ID,
            "--version", VERSION, "--bound-source", str(bound), "--binding-output", str(binding),
        )
        run(
            "python3", str(SRC / "verify_windows_release_security_allocation.py"),
            str(bound), str(binding), str(allocation),
        )
        run("python3", str(SRC / "verify_windows_no_send_preflight.py"), str(bound), str(helper))
        return {"bound": bound, "binding": binding, "helper": helper}

    def build_fixture(self, root: Path) -> dict[str, Path]:
        prepared = self.prepare(root)
        candidate = root / "private_candidate/LINE自動發訊息_Windows候選版"
        candidate.mkdir(parents=True)
        exe = candidate / "LINE_AutoSender.exe"
        exe.write_bytes(b"MZ-DEIDENTIFIED-WINDOWS-PRIVATE-UNSIGNED-FIXTURE")
        self_test = root / "windows_exe_no_send_self_test.json"
        self_test.write_text(json.dumps({
            "overall": "PASS", "real_data": False, "line_ui_opened": False,
            "keyboard_or_clipboard_used": False, "external_actions": [],
        }), encoding="utf-8")
        sbom = candidate / "SBOM.cdx.json"
        manifest = candidate / "CANDIDATE_MANIFEST.json"
        run(
            "python3", str(SRC / "create_windows_private_candidate_evidence.py"),
            "--release-id", RELEASE_ID, "--allocation", str(ALLOCATION),
            "--binding-manifest", str(prepared["binding"]), "--bound-source", str(prepared["bound"]),
            "--helper", str(prepared["helper"]), "--exe", str(exe),
            "--self-test-report", str(self_test), "--sbom-output", str(sbom),
            "--manifest-output", str(manifest), "--test-fixture",
        )
        package = root / "LINE自動發訊息_Windows候選版.zip"
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(candidate.iterdir()):
                archive.write(path, f"LINE自動發訊息_Windows候選版/{path.name}")
        final = root / "WINDOWS_PRIVATE_CANDIDATE_EVIDENCE.json"
        run(
            "python3", str(SRC / "finalize_windows_private_candidate_evidence.py"),
            "--manifest", str(manifest), "--sbom", str(sbom), "--exe", str(exe),
            "--package", str(package), "--output", str(final),
        )
        return {**prepared, "exe": exe, "sbom": sbom, "manifest": manifest,
                "package": package, "final": final}

    def test_01_exact_prebuild(self):
        with tempfile.TemporaryDirectory() as raw:
            prepared = self.prepare(Path(raw))
            binding = json.loads(prepared["binding"].read_text(encoding="utf-8"))
            self.assertEqual(binding["release_id"], RELEASE_ID)
            self.assertEqual(binding["version"], VERSION)
            self.assertEqual(
                binding["bound_source_sha256"],
                "d85a75dde5892a799fb9f0d952c2ffe2397fc689db5bd40dc3b39bdf92a2a907",
            )

    def test_02_wrong_release_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            run(
                "python3", str(SRC / "prepare_windows_release_binding.py"), str(SOURCE),
                "DA-LINE-WINDOWS-WRONG", "--version", VERSION,
                "--bound-source", str(Path(raw) / "bound.pyw"), expected=1,
            )
            self.assertFalse((Path(raw) / "bound.pyw").exists())

    def test_03_wrong_version_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            run(
                "python3", str(SRC / "prepare_windows_release_binding.py"), str(SOURCE), RELEASE_ID,
                "--version", "beta", "--bound-source", str(Path(raw) / "bound.pyw"), expected=1,
            )
            self.assertFalse((Path(raw) / "bound.pyw").exists())

    def test_04_backend_contract_drift_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            prepared = self.prepare(root)
            changed = json.loads(ALLOCATION.read_text(encoding="utf-8"))
            changed["backend_contract_sha256"] = "0" * 64
            allocation = root / "allocation.json"
            allocation.write_text(json.dumps(changed), encoding="utf-8")
            run(
                "python3", str(SRC / "verify_windows_release_security_allocation.py"),
                str(prepared["bound"]), str(prepared["binding"]), str(allocation), expected=1,
            )

    def test_05_source_drift_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            prepared = self.prepare(root)
            prepared["bound"].write_bytes(prepared["bound"].read_bytes() + b"\n# drift\n")
            run(
                "python3", str(SRC / "verify_windows_release_security_allocation.py"),
                str(prepared["bound"]), str(prepared["binding"]), str(ALLOCATION), expected=1,
            )

    def test_06_fixture_pipeline_and_artifact_verifier(self):
        with tempfile.TemporaryDirectory() as raw:
            value = self.build_fixture(Path(raw))
            run(
                "python3", str(SRC / "verify_windows_private_candidate_artifacts.py"),
                "--manifest", str(value["manifest"]), "--sbom", str(value["sbom"]),
                "--exe", str(value["exe"]), "--package", str(value["package"]),
                "--final-evidence", str(value["final"]), "--allow-test-fixture",
            )

    def test_07_binary_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            value = self.build_fixture(Path(raw))
            value["exe"].write_bytes(value["exe"].read_bytes() + b"tamper")
            run(
                "python3", str(SRC / "verify_windows_private_candidate_artifacts.py"),
                "--manifest", str(value["manifest"]), "--sbom", str(value["sbom"]),
                "--exe", str(value["exe"]), "--package", str(value["package"]),
                "--final-evidence", str(value["final"]), "--allow-test-fixture", expected=1,
            )

    def test_08_delivery_gate_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            value = self.build_fixture(Path(raw))
            manifest = json.loads(value["manifest"].read_text(encoding="utf-8"))
            manifest["gates"]["customer_delivery_allowed"] = True
            value["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
            run(
                "python3", str(SRC / "verify_windows_private_candidate_artifacts.py"),
                "--manifest", str(value["manifest"]), "--sbom", str(value["sbom"]),
                "--exe", str(value["exe"]), "--package", str(value["package"]),
                "--final-evidence", str(value["final"]), "--allow-test-fixture", expected=1,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
