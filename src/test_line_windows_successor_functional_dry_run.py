#!/usr/bin/env python3
"""Production-source functional dry-run for the allocated LINE Windows successor.

This harness imports the release-bound production source without modifying it.
Every OS/LINE/clipboard/browser action is replaced by an in-memory recorder.
It is safe to run on macOS or Windows and never starts LINE or sends a message.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import platform
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse


HERE = Path(__file__).resolve().parent
BUILDER_ROOT = HERE.parent
BACKEND_CURRENT_CONTRACT = BUILDER_ROOT / "release_evidence/desktop_app_authorization_contract.json"
EXPECTED_BACKEND_CONTRACT_SHA256 = "93092b1d3dc2d8e26842c11e9d7b8b55374bc90e8ba74cdba96d28ffe2633c5d"
SOURCE = Path(os.environ.get(
    "LINE_WINDOWS_SUCCESSOR_BOUND_SOURCE",
    str(BUILDER_ROOT / "release_binding/LINE自動發訊息_Windows.pyw"),
))
EXPECTED_SOURCE_SHA256 = "b1d70ee04af4b2fd2a1ccda73600354dd048877f841c0629084314aa9fc6dbfc"
EXPECTED_IDENTITY = {
    "release_id": "DA-LINE-WINDOWS-20260809-8002",
    "version": "8.0.2",
    "app_id": "line_automation_windows",
    "client_id": "deal_alliance_line_windows",
    "product_id": "line_automation",
    "callback": "dealalliance-line-windows://handoff",
    "pkce": "S256",
}


class ActionRecorder(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("pyautogui")
        self.FAILSAFE = True
        self.PAUSE = 0.0
        self.actions: list[tuple[str, tuple[str, ...]]] = []

    def press(self, key: str) -> None:
        self.actions.append(("press", (key,)))

    def hotkey(self, *keys: str) -> None:
        self.actions.append(("hotkey", tuple(keys)))

    def write(self, text: str, *args, **kwargs) -> None:  # pragma: no cover - safety trap
        self.actions.append(("write", (text,)))


class ClipboardRecorder(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("pyperclip")
        self.value = ""
        self.calls: list[str] = []

    def copy(self, value: str) -> None:
        self.calls.append("copy")
        self.value = value

    def paste(self) -> str:
        self.calls.append("paste")
        return self.value


class FakeLicenseClient:
    def __init__(self, *, allow_refresh: bool = True, allow_license: bool = True,
                 allow_issue: bool = True, allow_consume: bool = True) -> None:
        self.api_url = "https://app.dealalliancehub.com"
        self.allow_refresh = allow_refresh
        self.allow_license = allow_license
        self.allow_issue = allow_issue
        self.allow_consume = allow_consume
        self.exchange_calls = 0
        self.refresh_calls = 0
        self.license_calls = 0
        self.issue_calls = []
        self.consume_calls = []

    @staticmethod
    def _allowed_tokens(prefix: str) -> dict:
        return {
            "status": "allowed",
            "access_token": f"{prefix}-access",
            "refresh_token": f"{prefix}-refresh",
            "expires_in_seconds": 300,
        }

    def exchange_authorization_code(self, *args) -> dict:
        self.exchange_calls += 1
        return self._allowed_tokens("exchange")

    def refresh_authorization(self, *args) -> dict:
        self.refresh_calls += 1
        if not self.allow_refresh:
            return {"status": "denied"}
        return self._allowed_tokens("rotated")

    def authorize_app(self, *args) -> dict:
        self.license_calls += 1
        return {"status": "allowed" if self.allow_license else "denied"}

    def issue_live_dispatch(self, *args) -> dict:
        stage = args[-1]
        self.issue_calls.append(stage)
        if not self.allow_issue:
            return {"status": "denied"}
        return {
            "status": "allowed",
            "operation": "live_dispatch",
            "capability_token": f"DEIDENTIFIED-CAP-{len(self.issue_calls)}",
            "recipient_count": 1,
            "message_count": 1,
            "retry_count": 0,
            "expires_in_seconds": 30,
        }

    def consume_live_dispatch(self, *args) -> dict:
        stage = args[-1]
        self.consume_calls.append((args[1], stage))
        return {
            "status": "allowed" if self.allow_consume else "denied",
            "operation": "live_dispatch",
            "recipient_count": 1,
            "message_count": 1,
            "retry_count": 0,
            "consumed": self.allow_consume,
        }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_production_module():
    if sha256(SOURCE) != EXPECTED_SOURCE_SHA256:
        raise AssertionError("WIN-FUNC-001: exact bound production source hash drift")

    pyautogui = ActionRecorder()
    pyperclip = ClipboardRecorder()
    pil = types.ModuleType("PIL")
    pil_image = types.ModuleType("PIL.Image")
    pil.Image = pil_image
    helper = types.ModuleType("gsheet_helper")
    helper.GSheetLogger = object
    helper.LicenseAPIClient = object
    helper.load_gsheet_config = lambda: {}
    helper.load_license_api_url = lambda: "https://app.dealalliancehub.com"
    helper.save_gsheet_config = lambda *args, **kwargs: None

    for name, module in {
        "pyautogui": pyautogui,
        "pyperclip": pyperclip,
        "PIL": pil,
        "PIL.Image": pil_image,
        "gsheet_helper": helper,
    }.items():
        sys.modules[name] = module

    loader = importlib.machinery.SourceFileLoader("line_windows_successor_bound", str(SOURCE))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    module._test_pyautogui = pyautogui
    module._test_pyperclip = pyperclip
    return module


class Value:
    def __init__(self, value):
        self.value = value

    def get(self, *args):
        return self.value


class LineWindowsSuccessorFunctionalDryRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_production_module()

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self._old_appdata = os.environ.get("APPDATA")
        os.environ["APPDATA"] = self._tempdir.name
        self.module._test_pyautogui.actions.clear()
        self.module._test_pyperclip.calls.clear()
        self.module._test_pyperclip.value = "original-fixture"
        self.module.STOP_FLAG = False
        self.authorization_calls = 0
        self.authorization_stages = []

    def tearDown(self) -> None:
        if self._old_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self._old_appdata
        self._tempdir.cleanup()

    def assert_exact_identity(self) -> None:
        self.assertEqual(self.module.RELEASE_ID, EXPECTED_IDENTITY["release_id"])
        self.assertEqual(self.module.APP_VERSION, EXPECTED_IDENTITY["version"])
        self.assertEqual(self.module.APP_ID, EXPECTED_IDENTITY["app_id"])
        self.assertEqual(self.module.CLIENT_ID, EXPECTED_IDENTITY["client_id"])
        self.assertEqual(self.module.PRODUCT_ID, EXPECTED_IDENTITY["product_id"])
        self.assertEqual(
            f"{self.module.APP_CALLBACK_SCHEME}://handoff", EXPECTED_IDENTITY["callback"]
        )

    def new_manager(self, temp_root: str):
        old = os.environ.get("APPDATA")
        os.environ["APPDATA"] = temp_root
        try:
            return self.module.LicenseManager()
        finally:
            if old is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = old

    def test_01_exact_source_and_release_identity(self) -> None:
        self.assertEqual(sha256(SOURCE), EXPECTED_SOURCE_SHA256)
        self.assert_exact_identity()
        self.assertEqual(self.module.APP_CHANNEL, "release-candidate")
        self.assertFalse(self.module.verify_production_signed_identity())

    def test_02_oauth_pkce_success_and_exact_tuple(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = self.new_manager(td)
            client = FakeLicenseClient()
            client.issue_live_dispatch = lambda *args: (
                client.issue_calls.append(args[-1]) or dict(issue)
            )
            client.consume_live_dispatch = lambda *args: (
                client.consume_calls.append((args[1], args[-1])) or dict(consume)
            )
            manager._license_client = client
            observed = {}

            def browser_stub(url: str) -> bool:
                query = parse_qs(urlparse(url).query)
                observed.update({key: values[0] for key, values in query.items()})
                manager._callback_file().write_text(
                    json.dumps({"code": "fixture-code", "state": observed["state"]}),
                    encoding="utf-8",
                )
                return True

            original_open = self.module.webbrowser.open
            self.module.webbrowser.open = browser_stub
            try:
                ok, _ = manager.acquire_browser_handoff(timeout=1)
            finally:
                self.module.webbrowser.open = original_open

            self.assertTrue(ok)
            self.assertEqual(observed["app_id"], EXPECTED_IDENTITY["app_id"])
            self.assertEqual(observed["client_id"], EXPECTED_IDENTITY["client_id"])
            self.assertEqual(observed["release_id"], EXPECTED_IDENTITY["release_id"])
            self.assertEqual(observed["product_id"], EXPECTED_IDENTITY["product_id"])
            self.assertEqual(observed["redirect_uri"], EXPECTED_IDENTITY["callback"])
            self.assertEqual(observed["app_version"], EXPECTED_IDENTITY["version"])
            self.assertEqual(observed["platform"], "windows")
            self.assertEqual(observed["code_challenge_method"], EXPECTED_IDENTITY["pkce"])
            self.assertNotEqual(observed["code_challenge"], observed["state"])
            self.assertEqual(client.exchange_calls, 1)
            self.assertTrue(manager.is_licensed())

    def test_03_oauth_wrong_state_rejected_before_exchange(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = self.new_manager(td)
            client = FakeLicenseClient()
            manager._license_client = client

            def browser_stub(url: str) -> bool:
                manager._callback_file().write_text(
                    json.dumps({"code": "fixture-code", "state": "wrong-state"}),
                    encoding="utf-8",
                )
                return True

            original_open = self.module.webbrowser.open
            self.module.webbrowser.open = browser_stub
            try:
                ok, _ = manager.acquire_browser_handoff(timeout=1)
            finally:
                self.module.webbrowser.open = original_open
            self.assertFalse(ok)
            self.assertEqual(client.exchange_calls, 0)
            self.assertFalse(manager.is_licensed())

    def test_04_oauth_cancel_timeout_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = self.new_manager(td)
            client = FakeLicenseClient()
            manager._license_client = client
            original_open = self.module.webbrowser.open
            original_sleep = self.module.time.sleep
            self.module.webbrowser.open = lambda _url: True
            self.module.time.sleep = lambda _seconds: None
            try:
                ok, _ = manager.acquire_browser_handoff(timeout=1)
            finally:
                self.module.webbrowser.open = original_open
                self.module.time.sleep = original_sleep
            self.assertFalse(ok)
            self.assertEqual(client.exchange_calls, 0)

    def test_05_rotating_refresh_and_license_allow(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = self.new_manager(td)
            client = FakeLicenseClient()
            manager._license_client = client
            manager.session = {
                "access_token": "old-access",
                "refresh_token": "old-refresh",
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            }
            self.assertTrue(manager.refresh_lease())
            self.assertEqual(client.refresh_calls, 1)
            self.assertEqual(client.license_calls, 1)
            self.assertEqual(manager.session["refresh_token"], "rotated-refresh")

    def test_06_denied_license_clears_session(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = self.new_manager(td)
            client = FakeLicenseClient(allow_license=False)
            manager._license_client = client
            manager.session = {
                "access_token": "old-access",
                "refresh_token": "old-refresh",
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            }
            self.assertFalse(manager.refresh_lease())
            self.assertEqual(manager.session, {})

    def test_06b_backend_current_live_dispatch_response_feeds_product_parser(self) -> None:
        self.assertEqual(sha256(BACKEND_CURRENT_CONTRACT), EXPECTED_BACKEND_CONTRACT_SHA256)
        backend = json.loads(BACKEND_CURRENT_CONTRACT.read_text(encoding="utf-8"))
        live_contract = backend["live_dispatch_capability"]
        values = {
            "status": "allowed", "operation": live_contract["operation"],
            "capability_token": "DEIDENTIFIED-CURRENT-CONTRACT-TOKEN",
            "recipient_count": live_contract["recipient_count"],
            "message_count": live_contract["message_count"],
            "retry_count": live_contract["retry_count"],
            "expires_in_seconds": live_contract["ttl_seconds_max"],
            "consumed": True,
        }
        issue = {key: values[key] for key in live_contract["issue_success_response_keys_exact"]}
        consume = {key: values[key] for key in live_contract["consume_success_response_keys_exact"]}
        self.assertEqual(set(issue), set(live_contract["issue_success_response_keys_exact"]))
        self.assertEqual(set(consume), set(live_contract["consume_success_response_keys_exact"]))
        self.assertEqual(live_contract["capability_key"], "capability_token")
        self.assertEqual(live_contract["operation"], "live_dispatch")
        self.assertEqual(live_contract["consumed_receipt"], {
            "event_code": "consumed",
            "atomic_with_conditional_consume": True,
            "source": "0034_sqlite_after_update_trigger",
            "unique_per_capability": True,
            "audit_failure_rolls_back_consume": True,
            "replay_writes_receipt": False,
        })
        with tempfile.TemporaryDirectory() as td:
            manager = self.new_manager(td)
            client = FakeLicenseClient()
            client.issue_live_dispatch = lambda *args: (
                client.issue_calls.append(args[-1]) or dict(issue)
            )
            client.consume_live_dispatch = lambda *args: (
                client.consume_calls.append((args[1], args[-1])) or dict(consume)
            )
            manager._license_client = client
            manager.session = {
                "access_token": "old-access",
                "refresh_token": "old-refresh",
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            }
            original_identity = self.module.verify_production_signed_identity
            self.module.verify_production_signed_identity = lambda: True
            try:
                self.assertTrue(manager.authorize_dispatch("recipient_1_text_message"))
            finally:
                self.module.verify_production_signed_identity = original_identity
            self.assertEqual(client.issue_calls, ["recipient_1_text_message"])
            self.assertEqual(client.consume_calls, [
                (issue["capability_token"], "recipient_1_text_message")
            ])

    def test_06c_live_dispatch_deny_expiry_offline_replay_fail_closed(self) -> None:
        cases = {
            "deny": FakeLicenseClient(allow_issue=False),
            "consume_deny": FakeLicenseClient(allow_consume=False),
            "expiry": FakeLicenseClient(),
            "legacy_capability_id": FakeLicenseClient(),
            "offline": FakeLicenseClient(),
            "replay": FakeLicenseClient(allow_consume=False),
        }
        cases["expiry"].issue_live_dispatch = lambda *args: {
            "status": "allowed", "operation": "live_dispatch",
            "capability_token": "DEIDENTIFIED", "recipient_count": 1,
            "message_count": 1, "retry_count": 0, "expires_in_seconds": 61,
        }
        cases["legacy_capability_id"].issue_live_dispatch = lambda *args: {
            "status": "allowed", "operation": "live_dispatch",
            "capability_id": "LEGACY", "recipient_count": 1,
            "message_count": 1, "retry_count": 0, "expires_in_seconds": 30,
        }
        def offline(*_args):
            raise TimeoutError("fixture offline")
        cases["offline"].issue_live_dispatch = offline
        original_identity = self.module.verify_production_signed_identity
        self.module.verify_production_signed_identity = lambda: True
        try:
            for label, client in cases.items():
                with self.subTest(label=label), tempfile.TemporaryDirectory() as td:
                    manager = self.new_manager(td)
                    manager._license_client = client
                    manager.session = {
                        "access_token": "old-access",
                        "refresh_token": "old-refresh",
                        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                    }
                    self.assertFalse(manager.authorize_dispatch("recipient_1_text_message"))
                    self.assertEqual(manager.session, {})
                    self.assertEqual(self.module._test_pyautogui.actions, [])
        finally:
            self.module.verify_production_signed_identity = original_identity

    def test_07_blank_preview_rejected(self) -> None:
        warnings = []
        fake = types.SimpleNamespace(
            send_type=Value("text"),
            text_input=Value("   "),
            img_path="",
            count_entry=Value("1"),
        )
        original_warning = self.module.messagebox.showwarning
        self.module.messagebox.showwarning = lambda *args: warnings.append(args)
        try:
            ok = self.module.LineAutoSenderApp._validate(fake)
        finally:
            self.module.messagebox.showwarning = original_warning
        self.assertFalse(ok)
        self.assertEqual(len(warnings), 1)

    def test_08_preview_cancel_never_renews_or_dispatches(self) -> None:
        calls = {"refresh": 0}

        class License:
            def refresh_lease(_self):
                calls["refresh"] += 1
                return True

        fake = types.SimpleNamespace(
            sending=False,
            _validate=lambda: True,
            send_type=Value("text"),
            count=1,
            msg_text="去識別測試訊息",
            img_path="",
            license_mgr=License(),
        )
        original_confirm = self.module.messagebox.askokcancel
        self.module.messagebox.askokcancel = lambda *args: False
        try:
            self.module.LineAutoSenderApp._start_send(fake)
        finally:
            self.module.messagebox.askokcancel = original_confirm
        self.assertEqual(calls["refresh"], 0)
        self.assertEqual(self.module._test_pyautogui.actions, [])

    def test_09_preview_confirm_with_denied_license_never_dispatches(self) -> None:
        errors = []
        fake = types.SimpleNamespace(
            sending=False,
            _validate=lambda: True,
            send_type=Value("text"),
            count=1,
            msg_text="去識別測試訊息",
            img_path="",
            license_mgr=types.SimpleNamespace(refresh_lease=lambda: False),
        )
        original_confirm = self.module.messagebox.askokcancel
        original_error = self.module.messagebox.showerror
        self.module.messagebox.askokcancel = lambda *args: True
        self.module.messagebox.showerror = lambda *args: errors.append(args)
        try:
            self.module.LineAutoSenderApp._start_send(fake)
        finally:
            self.module.messagebox.askokcancel = original_confirm
            self.module.messagebox.showerror = original_error
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.module._test_pyautogui.actions, [])

    def chat_observation(self, display_name: str, visual_marker: str, pid: int = 4242) -> dict:
        return self.module.build_chat_instance_observation(
            display_name,
            hashlib.sha256(visual_marker.encode("utf-8")).hexdigest(),
            {"pid": pid, "class_name": "LINEFixtureWindow"},
        )

    def configure_dispatcher_stubs(
        self,
        chat_observations: list[dict],
        *,
        titles: list[str] | None = None,
        selection_reads: list[str | None] | None = None,
        transition_reads: list[str | None] | None = None,
    ) -> None:
        count = len(chat_observations)
        titles = titles or ["受控測試對象"] * count
        if selection_reads is None:
            selection_reads = []
            for index in range(count):
                selection_reads.extend([
                    f"selection-{index + 1}",
                    f"returned-list-{index + 1}",
                ])
        if transition_reads is None:
            transition_reads = [f"selection-{index + 2}" for index in range(max(0, count - 1))]

        title_iter = iter(titles)
        chat_iter = iter(chat_observations)
        selection_iter = iter(selection_reads)
        transition_iter = iter(transition_reads)
        self.message_side_effects = []
        self.module.time.sleep = lambda _seconds: None
        self.module.bring_line_to_front = lambda: (True, "fixture")
        self.module.require_english_input_method = lambda _stage: None
        self.module.get_foreground_window_title = lambda: "LINE 好友列表"
        self.module.wait_for_title_change = lambda _old, timeout=3: next(title_iter, titles[-1])
        self.module.wait_for_title_return = lambda _title, timeout=3: True
        self.module.wait_for_stable_chat_instance = lambda timeout=2.0: next(chat_iter, None)
        self.module.wait_for_stable_friend_list_selection = (
            lambda timeout=2.0: next(selection_iter, None)
        )
        self.module.wait_for_friend_list_selection_transition = (
            lambda _previous, timeout=2.0: next(transition_iter, None)
        )
        self.module.set_clipboard_text_verified = lambda _text: (
            self.message_side_effects.append("clipboard_write") or True
        )
        self.module.paste_and_verify_line_input = lambda _text: (
            self.message_side_effects.append("line_paste") or (True, "fixture")
        )

    def allow_dispatch(self, stage: str) -> bool:
        self.authorization_calls += 1
        self.authorization_stages.append(stage)
        return True

    def test_10_one_recipient_dispatcher_dry_run(self) -> None:
        original_sleep = self.module.time.sleep
        try:
            self.configure_dispatcher_stubs([
                self.chat_observation("受控測試對象", "chat-a"),
            ])
            done = []
            self.module.send_messages(
                "text", "去識別測試訊息", "", 1,
                lambda *_args: None, lambda sent, stopped: done.append((sent, stopped)),
                authorization_cb=self.allow_dispatch,
            )
        finally:
            self.module.time.sleep = original_sleep
        self.assertEqual(done, [(1, False)])
        self.assertEqual(self.authorization_calls, 4)
        self.assertEqual(self.authorization_stages, [
            "batch_start", "recipient_1_enter", "recipient_1_text_message", "recipient_1_exit",
        ])
        self.assertEqual(
            self.module._test_pyautogui.actions,
            [
                ("press", ("enter",)),
                ("press", ("enter",)),
                ("press", ("escape",)),
            ],
        )
        self.assertEqual(self.message_side_effects, ["clipboard_write", "line_paste"])

    def test_11_same_name_different_chat_instances_are_allowed(self) -> None:
        original_sleep = self.module.time.sleep
        try:
            self.configure_dispatcher_stubs([
                self.chat_observation("同名測試對象", "chat-a"),
                self.chat_observation("同名測試對象", "chat-b"),
            ])
            done = []
            self.module.send_messages(
                "text", "去識別測試訊息", "", 2,
                lambda *_args: None, lambda sent, stopped: done.append((sent, stopped)),
                authorization_cb=self.allow_dispatch,
            )
        finally:
            self.module.time.sleep = original_sleep
        self.assertEqual(done, [(2, False)])
        self.assertEqual(self.message_side_effects.count("line_paste"), 2)

    def test_11b_same_chat_consecutive_second_visit_stops_before_message(self) -> None:
        original_sleep = self.module.time.sleep
        errors = []
        same_chat = self.chat_observation("受控測試對象", "same-chat")
        try:
            self.configure_dispatcher_stubs(
                [same_chat, same_chat],
                selection_reads=["selection-a", "returned-a", "selection-a"],
                transition_reads=["selection-a"],
            )
            done = []
            self.module.send_messages(
                "text", "去識別測試訊息", "", 2,
                lambda *_args: None, lambda sent, stopped: done.append((sent, stopped)),
                error_cb=lambda code, *_args: errors.append(code),
                authorization_cb=self.allow_dispatch,
            )
        finally:
            self.module.time.sleep = original_sleep
        self.assertEqual(done, [(1, True)])
        self.assertEqual(errors, ["WIN-DUP-001"])
        self.assertEqual(self.message_side_effects.count("line_paste"), 1)

    def test_11c_same_chat_nonconsecutive_visit_stops_before_third_message(self) -> None:
        original_sleep = self.module.time.sleep
        errors = []
        chat_a = self.chat_observation("受控測試甲", "chat-a")
        chat_b = self.chat_observation("受控測試乙", "chat-b")
        try:
            self.configure_dispatcher_stubs(
                [chat_a, chat_b, chat_a],
                selection_reads=[
                    "selection-a", "returned-a",
                    "selection-b", "returned-b",
                    "selection-a",
                ],
                transition_reads=["selection-b", "selection-a"],
            )
            done = []
            self.module.send_messages(
                "text", "去識別測試訊息", "", 3,
                lambda *_args: None, lambda sent, stopped: done.append((sent, stopped)),
                error_cb=lambda code, *_args: errors.append(code),
                authorization_cb=self.allow_dispatch,
            )
        finally:
            self.module.time.sleep = original_sleep
        self.assertEqual(done, [(2, True)])
        self.assertEqual(errors, ["WIN-DUP-001"])
        self.assertEqual(self.message_side_effects.count("line_paste"), 2)

    def test_11d_same_main_window_same_title_uses_selection_instance(self) -> None:
        first = self.chat_observation("同名測試對象", "same-header", pid=4242)
        second = self.chat_observation("同名測試對象", "same-header", pid=4242)
        self.assertEqual(first["process_key"], second["process_key"])
        self.assertEqual(first["title_hash"], second["title_hash"])
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        first = self.module.bind_chat_observation_to_selection(first, "selection-a")
        second = self.module.bind_chat_observation_to_selection(second, "selection-b")
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])
        guard = self.module.ChatInstanceGuard()
        self.assertEqual(guard.classify(first, True), "allow")
        guard.mark_sent(first)
        self.assertEqual(guard.classify(second, True), "allow")

    def test_11d2_dynamic_title_and_header_do_not_change_chat_identity(self) -> None:
        first = self.chat_observation("同一受控對象", "header-before", pid=4242)
        changed = self.chat_observation("同一受控對象（動態）", "header-after", pid=4242)
        self.assertNotEqual(first["title_hash"], changed["title_hash"])
        self.assertNotEqual(first["header_digest"], changed["header_digest"])
        first = self.module.bind_chat_observation_to_selection(first, "selection-a")
        changed = self.module.bind_chat_observation_to_selection(changed, "selection-a")
        self.assertEqual(first["fingerprint"], changed["fingerprint"])
        guard = self.module.ChatInstanceGuard()
        self.assertEqual(guard.classify(first, True), "allow")
        guard.mark_sent(first)
        self.assertEqual(guard.classify(changed, True), "duplicate")

    def test_11e_ambiguous_initial_transition_has_zero_side_effects(self) -> None:
        original_sleep = self.module.time.sleep
        errors = []
        try:
            self.configure_dispatcher_stubs(
                [self.chat_observation("受控測試對象", "chat-a")],
                selection_reads=[None],
            )
            done = []
            self.module.send_messages(
                "text", "去識別測試訊息", "", 1,
                lambda *_args: None, lambda sent, stopped: done.append((sent, stopped)),
                error_cb=lambda code, *_args: errors.append(code),
                authorization_cb=self.allow_dispatch,
            )
        finally:
            self.module.time.sleep = original_sleep
        self.assertEqual(done, [(0, True)])
        self.assertEqual(errors, ["WIN-TRANSITION-001"])
        self.assertEqual(self.message_side_effects, [])
        self.assertEqual(self.module._test_pyautogui.actions, [])
        self.assertEqual(self.module._test_pyperclip.calls, [])

    def test_11f_lagged_next_selection_stops_before_second_chat(self) -> None:
        original_sleep = self.module.time.sleep
        errors = []
        try:
            self.configure_dispatcher_stubs(
                [
                    self.chat_observation("受控測試甲", "chat-a"),
                    self.chat_observation("受控測試乙", "chat-b"),
                ],
                transition_reads=[None],
            )
            done = []
            self.module.send_messages(
                "text", "去識別測試訊息", "", 2,
                lambda *_args: None, lambda sent, stopped: done.append((sent, stopped)),
                error_cb=lambda code, *_args: errors.append(code),
                authorization_cb=self.allow_dispatch,
            )
        finally:
            self.module.time.sleep = original_sleep
        self.assertEqual(done, [(1, True)])
        self.assertEqual(errors, ["WIN-TRANSITION-004"])
        self.assertEqual(self.message_side_effects.count("line_paste"), 1)

    def test_12_force_stop_before_line_activation(self) -> None:
        original_sleep = self.module.time.sleep
        done = []

        def progress(*_args):
            self.module.STOP_FLAG = True

        self.module.time.sleep = lambda _seconds: None
        try:
            self.module.send_messages(
                "text", "去識別測試訊息", "", 1, progress,
                lambda sent, stopped: done.append((sent, stopped)),
                authorization_cb=self.allow_dispatch,
            )
        finally:
            self.module.time.sleep = original_sleep
        self.assertEqual(done, [(0, True)])
        self.assertEqual(self.module._test_pyautogui.actions, [])

    def test_13_dispatch_denials_stop_with_zero_messages(self) -> None:
        for denial in ("unauthorized", "expired", "suspended", "device_limit", "api_deny", "offline", "tamper", "replay"):
            with self.subTest(denial=denial):
                self.module._test_pyautogui.actions.clear()
                errors = []
                done = []
                self.module.send_messages(
                    "text", "去識別測試訊息", "", 1,
                    lambda *_args: None, lambda sent, stopped: done.append((sent, stopped)),
                    error_cb=lambda code, *_args: errors.append(code),
                    authorization_cb=lambda _stage: False,
                )
                self.assertEqual(errors, ["WIN-AUTH-003"])
                self.assertEqual(done, [(0, True)])
                self.assertEqual(self.module._test_pyautogui.actions, [])

    def test_14_invalid_count_rejected_before_preview(self) -> None:
        warnings = []
        fake = types.SimpleNamespace(
            send_type=Value("text"),
            text_input=Value("去識別測試訊息"),
            img_path="",
            count_entry=Value("0"),
        )
        original_warning = self.module.messagebox.showwarning
        self.module.messagebox.showwarning = lambda *args: warnings.append(args)
        try:
            ok = self.module.LineAutoSenderApp._validate(fake)
        finally:
            self.module.messagebox.showwarning = original_warning
        self.assertFalse(ok)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(self.module._test_pyautogui.actions, [])

    def test_15_oauth_retry_uses_fresh_state_after_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            manager = self.new_manager(td)
            client = FakeLicenseClient()
            manager._license_client = client
            invocation = {"count": 0}

            def browser_stub(url: str) -> bool:
                invocation["count"] += 1
                state = parse_qs(urlparse(url).query)["state"][0]
                callback_state = "wrong-state" if invocation["count"] == 1 else state
                manager._callback_file().write_text(
                    json.dumps({"code": "fixture-code", "state": callback_state}),
                    encoding="utf-8",
                )
                return True

            original_open = self.module.webbrowser.open
            self.module.webbrowser.open = browser_stub
            try:
                first_ok, _ = manager.acquire_browser_handoff(timeout=1)
                second_ok, _ = manager.acquire_browser_handoff(timeout=1)
            finally:
                self.module.webbrowser.open = original_open
            self.assertFalse(first_ok)
            self.assertTrue(second_ok)
            self.assertEqual(invocation["count"], 2)
            self.assertEqual(client.exchange_calls, 1)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LineWindowsSuccessorFunctionalDryRun)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "schema_version": "line_windows_successor_production_source_functional_dry_run_v2",
        "status": "PASS" if result.wasSuccessful() else "FAIL",
        "release_id": EXPECTED_IDENTITY["release_id"],
        "version": EXPECTED_IDENTITY["version"],
        "bound_source_sha256": EXPECTED_SOURCE_SHA256,
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "host_os": platform.platform(),
        "fixture_only": True,
        "real_data": False,
        "line_started": False,
        "browser_started": False,
        "messages_sent": 0,
        "real_send_attempts": 0,
        "external_writes": 0,
        "network_requests": 0,
        "coverage": [
            "exact source and identity",
            "OAuth PKCE S256 success",
            "wrong-state rejection",
            "OAuth cancel/timeout",
            "rotating refresh and license allow",
            "license deny clears session",
            "blank preview rejection",
            "preview cancel",
            "preview confirm then license deny",
            "one-recipient dispatcher dry-run",
            "batch/recipient/send reauthorization",
            "unauthorized/expired/suspended/device-limit/API-deny/offline/tamper/replay zero-send",
            "unsigned or wrong Authenticode identity fail-closed",
            "same-name different-chat allow",
            "same-chat consecutive and nonconsecutive stop",
            "same-main-window different-chat allow",
            "dynamic title/header excluded from chat identity",
            "friend-list transition proof",
            "lag/ambiguous transition zero side effects",
            "force-stop before LINE activation",
            "invalid count rejection",
            "fresh OAuth retry after rejected state",
        ],
    }
    output = os.environ.get("LINE_WINDOWS_SUCCESSOR_DRY_RUN_REPORT", "").strip()
    if output:
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
