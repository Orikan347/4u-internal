#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Retired Windows functional-review shell.

This source intentionally contains no LINE, keyboard, clipboard, browser, or
network adapter. It exists only so historical references fail closed with a
clear message; the former no-auth real-driver channel must never be rebuilt.
"""

import tkinter as tk
from tkinter import messagebox

from functional_test_logger import GSheetLogger


APP_NAME = "LINE 自動發訊息・功能驗收已停用"
APP_CHANNEL = "functional-test"
APP_VERSION = "7.1.0-functional-test"
FUNCTIONAL_TEST_CHANNEL = True
FUNCTIONAL_TEST_NO_AUTH = False
RETIREMENT_CODE = "WIN-FUNCTIONAL-RETIRED"


def send_messages(_send_type, _msg_text, _img_path, _count, _progress_cb, done_cb,
                  _gsheet_logger=None, _add_name=False, error_cb=None,
                  authorization_cb=None):
    """Permanent zero-send boundary for direct imports and stale launchers."""
    _ = authorization_cb
    if callable(error_cb):
        error_cb(
            RETIREMENT_CODE,
            "功能驗收通道已停用",
            "此歷史通道沒有 LINE driver；請使用正式登入版。",
            "messages_sent=0",
        )
    if callable(done_cb):
        done_cb(0, True)
    return 0


class RetiredFunctionalReviewApp:
    def __init__(self, root):
        root.title(APP_NAME)
        root.geometry("560x260")
        root.resizable(True, True)
        frame = tk.Frame(root, padx=28, pady=28)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="功能驗收通道已安全停用", font=("Microsoft JhengHei", 18, "bold")).pack(anchor="w")
        tk.Label(
            frame,
            text="這個歷史入口不連線、不操作 LINE、不使用鍵盤或剪貼簿，也不會送出訊息。\n請改用成交聯盟正式登入版。",
            justify="left",
            wraplength=490,
        ).pack(anchor="w", pady=(18, 20))
        tk.Button(frame, text="關閉", command=root.destroy).pack(anchor="e")


def main():
    root = tk.Tk()
    RetiredFunctionalReviewApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
