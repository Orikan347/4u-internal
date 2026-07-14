#!/usr/bin/env python3
"""Console-only loader for the Windows candidate's no-send runner check.

This file is never included in the private candidate archive.  It loads the
same .pyw source bundled in the GUI EXE so GitHub Actions can surface startup
errors that a Windows GUI bootloader would otherwise hide.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path


def _runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent / "source"


def _write_failure(exc: BaseException) -> None:
    report_path = os.environ.get("LINE_SELF_TEST_REPORT", "")
    if not report_path:
        return
    report = {
        "suite": "LINE Windows EXE self-test no-send",
        "overall": "FAIL",
        "error_type": type(exc).__name__,
        "error": str(exc)[:500],
        "real_data": False,
        "external_actions": [],
        "line_ui_opened": False,
        "keyboard_or_clipboard_used": False,
    }
    Path(report_path).write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")


def main() -> int:
    try:
        runtime_dir = _runtime_dir()
        source_path = runtime_dir / "line_auto_sender_windows.pyw"
        if not source_path.is_file():
            raise FileNotFoundError(f"candidate source missing: {source_path}")
        sys.path.insert(0, str(runtime_dir))
        loader = importlib.machinery.SourceFileLoader("line_windows_candidate_runtime", str(source_path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        if spec is None:
            raise RuntimeError("cannot create source loader spec")
        module = importlib.util.module_from_spec(spec)
        sys.modules[loader.name] = module
        loader.exec_module(module)
        return int(module.run_no_send_self_test())
    except BaseException as exc:
        _write_failure(exc)
        print(f"SELF_TEST_STARTUP_FAILURE {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
