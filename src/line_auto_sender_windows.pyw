#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LINE 自動發訊息 — Windows 版 v2.0
Orikan 李泰欣 | 亞洲銷冠系統架構導師
高單價無限成交系統
支援：文字 / 圖片 / 文字+圖片 + 強制停止
IG @eintaixin

v2.0 新增：
1. 線上授權驗證（Google Sheet 授權白名單）
2. 視窗標題偵測（等待 LINE 狀態切換）
3. 訊息範本（儲存/載入/挑選常用訊息）
4. 逐筆發送紀錄（好友名稱 + 狀態 → Google Sheet）
5. 進度顯示（好友名稱 + 百分比）

需安裝套件（打包前）：pip install pyautogui pyperclip Pillow
打包成 exe：pyinstaller --onefile --windowed --name "LINE自動發訊息" --add-data "gsheet_helper.py;." LINE自動發訊息_Windows.pyw
"""

import sys
import os
import re
import time
import json
import threading
import webbrowser
import struct
import ctypes
import subprocess
import platform
import traceback
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext

try:
    import pyautogui
except ImportError:
    root = tk.Tk(); root.withdraw()
    messagebox.showerror("缺少套件", "請先安裝 pyautogui：\n\npip install pyautogui")
    sys.exit(1)

try:
    import pyperclip
except ImportError:
    root = tk.Tk(); root.withdraw()
    messagebox.showerror("缺少套件", "請先安裝 pyperclip：\n\npip install pyperclip")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    root = tk.Tk(); root.withdraw()
    messagebox.showerror("缺少套件", "請先安裝 Pillow：\n\npip install Pillow")
    sys.exit(1)

# Google Sheet 回寫模組（選用，透過 Apps Script Web App）
GSHEET_AVAILABLE = True
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from gsheet_helper import GSheetLogger, load_gsheet_config, save_gsheet_config
except ImportError:
    GSHEET_AVAILABLE = False


# ==========================================
# 全域設定
# ==========================================
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1
STOP_FLAG = False

IG_URL = "https://www.instagram.com/eintaixin?igsh=MWtnM2sxMnRvcHdoNg%3D%3D&utm_source=qr"
BRAND_NAME = "Orikan 李泰欣"
BRAND_TITLE = "亞洲銷冠系統架構導師"
APP_NAME = "LINE 自動發訊息"
TRIAL_DAYS = 7

# 色彩
C_BG = '#4A5568'
C_BG_DARK = '#2D3748'
C_BG_MID = '#3D4A5C'
C_ORANGE = '#ED8936'
C_GOLD = '#D4A856'
C_GREEN = '#48BB78'
C_RED = '#FC8181'
C_WHITE = '#F7FAFC'
C_LIGHT = '#CBD5E0'
C_DIM = '#A0AEC0'
C_BLUE = '#4299E1'


# ==========================================
# 智慧名字清理（與 Mac 版同步）
# ==========================================
_CJK = r'\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af'

_NOISE_WORDS = [
    '帥哥', '美女',
    '可愛', '機車', '不好搞', '難搞', '厲害',
    '超強', '認真', '積極', '熱情', '優秀', '囉嗦',
    'A級', 'B級', 'C級', 'D級', 'S級',
    'a級', 'b級', 'c級', 'd級', 's級',
    'VIP', 'vip', 'Vip',
    '已成交', '未成交', '已聯繫', '未聯繫', '待跟進', '待追蹤',
    '已購買', '已報名', '已繳費', '潛在', '重要', '普通',
    '轉介紹', '陌生', '網路', '朋友', '同事',
    '保險', '房仲', '直銷', '業務', '銷售', '顧問', '達人',
    '每日更新', '高單價', '成交導師', '女王', '國王', '客戶',
]

_SURNAMES = set(list(
    '陳林黃張李王吳劉蔡楊許鄭謝洪郭邱曾廖賴徐周葉蘇莊呂'
    '江何蕭羅高潘簡朱鍾彭游詹胡施沈余盧梁趙顏柯翁魏孫戴'
    '范方宋鄧杜傅侯曹薛丁卓馬阮董溫紀黎韓蔣唐田石鄒巫錢'
    '尤官程秦古龍雷湯姚段殷康塗童鄂萬俞錡白熊萬姜嚴'
) + ['歐陽', '司馬', '諸葛', '上官'])

_NICK_PREFIX = set('小老阿')


def clean_friend_name(raw: str) -> str:
    """
    從 LINE 視窗標題智慧擷取對方暱稱。
    規則：去 LINE→去 emoji/符號→去噪音詞→去數字/日期→
         優先中文（跳過品牌英文）→偵測姓氏去姓留名→限制長度。
    """
    if not raw or not raw.strip():
        return ""

    name = re.sub(r'LINE', '', raw, flags=re.IGNORECASE).strip()

    # 只保留中日韓英數+空格
    name = re.sub(f'[^{_CJK}a-zA-Z0-9\\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    if not name:
        return ""

    # 去噪音詞（形容詞、標籤、職業描述，保留尊稱如老師經理）
    for w in _NOISE_WORDS:
        name = name.replace(w, '')
    name = re.sub(r'\s+', ' ', name).strip()

    # 去數字（日期如 0315、標籤如 A1B2）
    name = re.sub(r'\d+', '', name)
    name = re.sub(r'^[年月日]+', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    if not name:
        return ""

    # 在英文和中文交界處插入空格
    name = re.sub(f'([a-zA-Z])([{_CJK}])', r'\1 \2', name)
    name = re.sub(f'([{_CJK}])([a-zA-Z])', r'\1 \2', name)

    parts = name.split()

    # 優先找中文段落（英文常是品牌/裝飾字）
    cjk_parts = [p for p in parts if re.match(f'[{_CJK}]', p)]

    if cjk_parts:
        first = ''.join(cjk_parts)
        # 去姓邏輯：三字全名且首字是姓氏 → 去姓留名
        if (len(first) >= 3
                and first[0] in _SURNAMES
                and first[0] not in _NICK_PREFIX
                and first[:2] not in _SURNAMES):
            first = first[1:]   # 單姓去掉
        elif (len(first) >= 4
              and first[:2] in _SURNAMES):
            first = first[2:]   # 複姓去掉
        result = first[:5] if len(first) > 5 else first
    else:
        # 純英文 → 取第一個英文單字
        first = parts[0] if parts else name
        result = first

    # 安全檢查：不要把 "LINE" 當人名
    if result.upper() == 'LINE':
        return ""

    return result


# ==========================================
# 訊息範本管理
# ==========================================
def get_config_dir():
    """取得設定檔目錄"""
    config_dir = Path(os.environ.get('APPDATA', Path.home())) / 'LINE自動發訊息'
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


class SendStopError(Exception):
    """安全停止：會顯示錯誤碼並寫入診斷檔。"""

    def __init__(self, code, title, message, detail=""):
        super().__init__(f"{code} {title}")
        self.code = code
        self.title = title
        self.message = message
        self.detail = detail
        self.error_file = write_error_diagnostic(code, title, message, detail)


def write_error_diagnostic(code, title, message, detail=""):
    """寫入學生可回傳的最新錯誤診斷檔。"""
    error_file = get_config_dir() / "latest_error.txt"
    try:
        with open(error_file, 'w', encoding='utf-8') as f:
            f.write(f"錯誤碼：{code}\n")
            f.write(f"時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"系統：{platform.platform()}\n")
            f.write(f"程式：{APP_NAME} Windows 版\n")
            f.write(f"標題：{title}\n\n")
            f.write(message)
            if detail:
                f.write("\n\n--- 詳細資訊 ---\n")
                f.write(str(detail))
    except Exception:
        pass
    return error_file


def raise_send_error(code, title, message, detail=""):
    raise SendStopError(code, title, message, detail)


def load_templates():
    """載入訊息範本"""
    tpl_file = get_config_dir() / 'templates.json'
    try:
        if tpl_file.exists():
            with open(tpl_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return []


def save_templates(templates):
    """儲存訊息範本"""
    tpl_file = get_config_dir() / 'templates.json'
    try:
        with open(tpl_file, 'w', encoding='utf-8') as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ==========================================
# Windows 視窗標題偵測
# ==========================================
def get_foreground_window_title():
    """取得目前最前方視窗的標題"""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.strip()
    except Exception:
        return ""


def wait_for_title_change(old_title, timeout=3):
    """
    等待視窗標題改變（表示 LINE 已進入聊天室）
    回傳新標題，或超時回傳空字串
    """
    start = time.time()
    while time.time() - start < timeout:
        if STOP_FLAG:
            return ""
        new_title = get_foreground_window_title()
        if new_title and new_title != old_title:
            return new_title
        time.sleep(0.1)
    return ""


def wait_for_title_return(chat_title, timeout=2):
    """
    等待視窗標題回到好友列表（表示已離開聊天室）
    即標題從聊天對象名稱變回其他
    """
    start = time.time()
    while time.time() - start < timeout:
        if STOP_FLAG:
            return
        current = get_foreground_window_title()
        if current != chat_title:
            return
        time.sleep(0.1)


# ==========================================
# 授權管理（線上驗證 + 試用期）
# ==========================================
class LicenseManager:
    """管理授權：線上驗證 → 本地快取"""

    def __init__(self):
        self.data_dir = Path(os.environ.get('APPDATA', Path.home())) / 'LINE自動發訊息'
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.license_file = self.data_dir / 'license.json'
        self.data = self._load()
        self._gsheet_logger = None  # 延遲初始化

    def _load(self):
        try:
            if self.license_file.exists():
                with open(self.license_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save(self):
        try:
            with open(self.license_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _get_logger(self):
        """取得 GSheetLogger（用於線上授權驗證）"""
        if self._gsheet_logger is None and GSHEET_AVAILABLE:
            try:
                config = load_gsheet_config()
                url = config.get('webapp_url', '')
                if url:
                    self._gsheet_logger = GSheetLogger(url)
                    self._gsheet_logger.connect()
            except Exception:
                pass
        return self._gsheet_logger

    def get_first_use_date(self):
        """取得首次使用日期"""
        if 'first_use' not in self.data:
            self.data['first_use'] = datetime.now().isoformat()
            self._save()
        return datetime.fromisoformat(self.data['first_use'])

    def get_remaining_days(self):
        """取得剩餘試用天數"""
        first_use = self.get_first_use_date()
        expire = first_use + timedelta(days=TRIAL_DAYS)
        remaining = (expire - datetime.now()).days
        return max(0, remaining)

    def is_trial_active(self):
        """試用期是否仍有效"""
        return self.get_remaining_days() > 0

    def is_licensed(self):
        """是否有有效授權（訂閱 or 永久）"""
        license_type = self.data.get('license_type', 'trial')
        if license_type == 'permanent':
            return True
        if license_type == 'subscription':
            expire_str = self.data.get('subscription_expire', '')
            if expire_str:
                try:
                    expire = datetime.fromisoformat(expire_str)
                    return datetime.now() < expire
                except Exception:
                    pass
        return False

    def activate_license(self, key):
        """
        啟用授權碼 — 優先線上驗證，線上不通時離線解析
        """
        key = key.strip().upper()
        if not key:
            return False, "請輸入授權碼"

        # ===== 1. 線上驗證 =====
        logger = self._get_logger()
        if logger and logger.connected:
            try:
                valid, info = logger.verify_license(key)
                if valid:
                    lic_type = info.get("type", "permanent")
                    expire = info.get("expire", "")
                    customer = info.get("customer", "")

                    # 通用延期碼：重設試用期（只能用一次）
                    if lic_type == 'extend_trial':
                        if self.data.get('extend_used'):
                            return False, "延期碼只能使用一次，已使用過。\n如需繼續使用，請私訊 IG @eintaixin 取得授權碼"
                        extend_days = info.get("days", 7)
                        self.data['first_use'] = datetime.utcnow().isoformat()
                        self.data['extend_used'] = True
                        self.data.pop('license_type', None)
                        self.data.pop('license_key', None)
                        self._save()
                        return True, f"試用已延長 {extend_days} 天！"

                    self.data['license_type'] = lic_type
                    self.data['license_key'] = key
                    self.data['verified_online'] = True
                    self.data['verify_date'] = datetime.now().isoformat()

                    if lic_type == 'subscription' and expire:
                        self.data['subscription_expire'] = expire

                    self._save()

                    if lic_type == 'permanent':
                        msg = f"永久授權啟用成功！"
                    else:
                        msg = f"訂閱授權啟用成功！到期日：{expire}"
                    if customer:
                        msg += f"\n歡迎，{customer}！"
                    return True, msg
                else:
                    reason = info.get("reason", "")
                    if reason == "subscription_expired":
                        return False, f"此授權碼已過期（{info.get('expire', '')}），請聯繫續約。"
                    elif reason == "not_found":
                        return False, "授權碼無效，請確認後重試。"
                    else:
                        return False, "授權碼驗證失敗，請確認後重試。"
            except Exception:
                pass  # 線上驗證失敗，改走離線

        # ===== 2. 離線解析（備援）=====
        if key.startswith('PERMANENT-'):
            self.data['license_type'] = 'permanent'
            self.data['license_key'] = key
            self.data['verified_online'] = False
            self._save()
            return True, "永久授權啟用成功！（離線模式）"
        elif key.startswith('SUB-'):
            parts = key.split('-')
            if len(parts) >= 5:
                try:
                    date_str = f"{parts[1]}-{parts[2]}-{parts[3]}"
                    expire = datetime.fromisoformat(date_str)
                    self.data['license_type'] = 'subscription'
                    self.data['subscription_expire'] = expire.isoformat()
                    self.data['license_key'] = key
                    self.data['verified_online'] = False
                    self._save()
                    return True, f"訂閱授權啟用成功！到期日：{date_str}（離線模式）"
                except Exception:
                    pass

        return False, "授權碼無效，請確認後重試。"

    def can_use(self):
        """是否可以使用程式"""
        return self.is_licensed() or self.is_trial_active()

    def get_status_text(self):
        """取得授權狀態說明"""
        if self.is_licensed():
            lt = self.data.get('license_type', '')
            if lt == 'permanent':
                return "已授權（永久版）", C_GREEN
            elif lt == 'subscription':
                expire = self.data.get('subscription_expire', '')
                return f"已授權（訂閱制，到期：{expire[:10]}）", C_GREEN
        remaining = self.get_remaining_days()
        if remaining > 0:
            return f"試用期剩餘 {remaining} 天", C_ORANGE
        return "試用期已到期", C_RED


# ==========================================
# 圖片剪貼簿操作
# ==========================================
def copy_image_to_clipboard(image_path):
    """將圖片複製到 Windows 剪貼簿"""
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        CF_DIB = 8
        img = Image.open(image_path)
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        width, height = img.size
        bmi_header = struct.pack('<IiiHHIIiiII',
            40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        pixels = img.tobytes('raw', 'BGRA')
        dib_data = bmi_header + pixels

        if not user32.OpenClipboard(0):
            return False
        user32.EmptyClipboard()

        GMEM_MOVEABLE = 0x0002
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dib_data))
        if not h_mem:
            user32.CloseClipboard()
            return False

        p_mem = kernel32.GlobalLock(h_mem)
        ctypes.memmove(p_mem, dib_data, len(dib_data))
        kernel32.GlobalUnlock(h_mem)
        user32.SetClipboardData(CF_DIB, h_mem)
        user32.CloseClipboard()
        return True
    except Exception:
        return False


def bring_line_to_front():
    """將 LINE 視窗移到最前方"""
    try:
        proc = subprocess.run([
            'powershell', '-Command',
            '[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; '
            '$ok=(New-Object -ComObject WScript.Shell).AppActivate("LINE"); '
            'Write-Output $ok'
        ], capture_output=True, text=True, timeout=5)
        time.sleep(0.3)
        return proc.stdout.strip().lower() == 'true', (proc.stdout + proc.stderr).strip()
    except Exception as e:
        return False, str(e)


def switch_to_english_input_method():
    """嘗試把目前前景視窗切到英文鍵盤配置，避免中文輸入法攔截 Ctrl+V 或 Enter。"""
    if not sys.platform.startswith('win'):
        return True, "not_windows"

    try:
        from ctypes import wintypes

        user32 = ctypes.WinDLL('user32', use_last_error=True)
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

        KLF_ACTIVATE = 0x00000001
        WM_INPUTLANGCHANGEREQUEST = 0x0050
        EN_US_KLID = "00000409"
        EN_US_LANGID = 0x0409

        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
        user32.GetKeyboardLayout.restype = ctypes.c_void_p
        user32.LoadKeyboardLayoutW.argtypes = [wintypes.LPCWSTR, wintypes.UINT]
        user32.LoadKeyboardLayoutW.restype = ctypes.c_void_p
        user32.ActivateKeyboardLayout.argtypes = [ctypes.c_void_p, wintypes.UINT]
        user32.ActivateKeyboardLayout.restype = ctypes.c_void_p
        user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        user32.AttachThreadInput.restype = wintypes.BOOL
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
        user32.PostMessageW.restype = wintypes.BOOL
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False, "找不到目前前景視窗"

        target_pid = wintypes.DWORD()
        target_thread = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(target_pid))
        current_thread = kernel32.GetCurrentThreadId()

        hkl = user32.LoadKeyboardLayoutW(EN_US_KLID, KLF_ACTIVATE)
        if not hkl:
            return False, f"LoadKeyboardLayoutW({EN_US_KLID}) failed: {ctypes.get_last_error()}"

        attached = False
        if target_thread and target_thread != current_thread:
            attached = bool(user32.AttachThreadInput(current_thread, target_thread, True))

        try:
            activated = user32.ActivateKeyboardLayout(hkl, KLF_ACTIVATE)
            posted = bool(user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, int(hkl)))
        finally:
            if attached:
                user32.AttachThreadInput(current_thread, target_thread, False)

        time.sleep(0.25)
        target_layout = int(user32.GetKeyboardLayout(target_thread) or 0)
        current_layout = int(user32.GetKeyboardLayout(0) or 0)
        target_lang = target_layout & 0xFFFF
        current_lang = current_layout & 0xFFFF

        if target_lang == EN_US_LANGID or current_lang == EN_US_LANGID:
            return True, (
                f"target_lang=0x{target_lang:04x}, current_lang=0x{current_lang:04x}, "
                f"activated={int(activated or 0)}, posted={posted}, attached={attached}"
            )

        return False, (
            f"無法確認已切到英文鍵盤。target_lang=0x{target_lang:04x}, "
            f"current_lang=0x{current_lang:04x}, activated={int(activated or 0)}, "
            f"posted={posted}, attached={attached}"
        )
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def require_english_input_method(stage):
    ok, detail = switch_to_english_input_method()
    if ok:
        return detail
    raise_send_error(
        "WIN-IME-001",
        "輸入法不是英文",
        "程式無法自動切換到英文鍵盤配置，所以已停止，避免中文輸入法攔截 Ctrl + V 或 Enter，造成空白發送或發不出去。\n\n"
        "請先在 Windows 右下角語言列切到 ENG / English，再重新執行。\n\n"
        "如果看不到 ENG，請到 Windows 設定新增 English 鍵盤配置。",
        f"stage={stage}; {detail}"
    )


def set_clipboard_text_verified(text, retries=2):
    """寫入剪貼簿並讀回確認，避免空白或錯誤內容被貼出。"""
    for _ in range(retries):
        pyperclip.copy(text)
        time.sleep(0.08)
        try:
            if pyperclip.paste() == text:
                return True
        except Exception:
            pass
        time.sleep(0.12)
    return False


def paste_and_verify_line_input(expected_text, retries=2):
    """貼上後讀回 LINE 輸入框內容；完全一致才允許 Enter 送出。"""
    for _ in range(retries):
        if not set_clipboard_text_verified(expected_text):
            return False, "clipboard_write_failed"

        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.25)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.08)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.12)
        try:
            pasted_text = pyperclip.paste()
        except Exception as e:
            return False, f"clipboard_read_failed: {e}"

        if pasted_text == expected_text:
            return True, ""

        time.sleep(0.2)
    return False, "line_input_verify_mismatch"


# ==========================================
# 發送核心邏輯 v2.0
# ==========================================
def send_messages(send_type, msg_text, img_path, count, progress_cb, done_cb,
                  gsheet_logger=None, add_name=False, error_cb=None):
    """
    v2.0：加入視窗標題偵測 + 逐筆好友紀錄 + 進度百分比
    """
    global STOP_FLAG
    STOP_FLAG = False
    sent = 0
    seen_customers = {}

    type_names = {'text': '純文字', 'image': '純圖片', 'both': '文字+圖片'}
    type_label = type_names.get(send_type, send_type)
    batch_id = gsheet_logger.get_batch_id() if gsheet_logger else f"WIN-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # 訊息摘要（用於 Google Sheet）
    msg_summary = msg_text[:50] if msg_text else f"[{type_label}]"

    # 保存用戶原有的剪貼簿內容
    original_clipboard = ""
    try:
        original_clipboard = pyperclip.paste()
    except Exception:
        pass

    try:
        for i in range(2, 0, -1):
            if STOP_FLAG:
                done_cb(sent, True); return
            progress_cb(f"⏳ {i} 秒後開始...", "")
            time.sleep(1)

        line_ok, line_detail = bring_line_to_front()
        if not line_ok:
            raise_send_error(
                "WIN-LINE-001",
                "LINE 沒有開啟",
                "無法把 LINE 電腦版切到最前面。\n\n請確認這台 Windows 已安裝 LINE 桌面版，而且已登入要發送訊息的帳號。",
                line_detail
            )
        time.sleep(0.3)
        progress_cb("⌨️ 正在切換英文輸入法...", "")
        require_english_input_method("before_send_loop")

        for i in range(1, count + 1):
            if STOP_FLAG:
                break

            pct = int((i - 1) / count * 100)
            progress_cb(f"📊 {i-1}/{count} 完成（{pct}%）", f"正在準備第 {i} 位...")

            # 記住進入聊天室前的視窗標題
            old_title = get_foreground_window_title()

            line_ok, line_detail = bring_line_to_front()
            if not line_ok:
                raise_send_error(
                    "WIN-LINE-002",
                    "LINE 沒有準備好",
                    "程式無法偵測或切換到 LINE 視窗。\n\n請先手動打開 LINE 電腦版、登入帳號，並切到好友列表後再重新執行。",
                    line_detail
                )
            time.sleep(0.15)

            # 按 Enter 進入聊天室
            pyautogui.press('enter')
            time.sleep(0.3)

            # ★ 偵測視窗標題變化（取得好友名稱）
            friend_name_raw = ""
            new_title = wait_for_title_change(old_title, timeout=3)
            if new_title:
                friend_name_raw = new_title
            else:
                raise_send_error(
                    "WIN-LINE-003",
                    "沒有成功進入聊天室",
                    "沒有成功進入聊天室，所以程式已停止，避免送錯人。\n\n"
                    "請照這樣重新準備 LINE：\n"
                    "1. 打開 LINE 電腦版並登入。\n"
                    "2. 回到左側好友列表，不要停在搜尋框。\n"
                    "3. 用滑鼠點一下第一位要發送的好友，讓他呈現選取狀態。\n"
                    "4. 不要把 LINE 縮小或蓋住，再重新執行本程式。\n\n"
                    "如果你原本已經在聊天室，請先按 Esc 回到好友列表再開始。",
                    f"old_title={old_title!r}, current_title={get_foreground_window_title()!r}"
                )

            # ★ 智慧清理名字（去品牌、去姓氏、去標籤）
            friend_name = clean_friend_name(friend_name_raw)

            # 更新進度（顯示好友名稱）
            pct = int(i / count * 100)
            display_name = friend_name if friend_name else f"第 {i} 位"
            progress_cb(f"📊 {i}/{count} 完成（{pct}%）", f"👤 {display_name}")

            send_ok = True
            send_note = ""

            recipient_key = (friend_name_raw or friend_name or "").strip()
            if recipient_key.upper() == "LINE":
                recipient_key = friend_name or ""
            if recipient_key:
                duplicate_count = seen_customers.get(recipient_key, 0)
                if duplicate_count >= 1:
                    raise_send_error(
                        "WIN-DUP-001",
                        "重複發送保護",
                        "偵測到同一位客戶已成功發送 1 次，程式已在第 2 次送出前停止。\n\n"
                        f"客戶：{recipient_key}\n\n"
                        "請確認 LINE 是否沒有跳到下一位好友。",
                        f"recipient_key={recipient_key!r}, duplicate_count={duplicate_count}"
                    )

            if send_type in ('text', 'both'):
                require_english_input_method(f"before_text_paste:{i}")

                if not msg_text or not msg_text.strip():
                    raise_send_error(
                        "WIN-MSG-001",
                        "文字內容空白",
                        "本次文字內容是空白，所以程式已停止，避免送出空白訊息。\n\n請重新輸入要發送的文字，再執行一次。"
                    )

                if friend_name and add_name:
                    final_msg = f"{friend_name}，{msg_text}"
                else:
                    final_msg = msg_text

                if not set_clipboard_text_verified(final_msg):
                    raise_send_error(
                        "WIN-CLIP-001",
                        "剪貼簿異常",
                        "程式無法把本次訊息穩定寫入剪貼簿，所以已停止，避免送出空白或錯誤內容。\n\n"
                        "請先確認：\n"
                        "1. 不要同時使用其他剪貼簿管理工具。\n"
                        "2. LINE 視窗在最前面。\n"
                        "3. 關掉本程式後重新開一次。"
                    )

                input_ok, input_detail = paste_and_verify_line_input(final_msg)
                if not input_ok:
                    raise_send_error(
                        "WIN-INPUT-001",
                        "LINE 沒有接到訊息",
                        "程式已把訊息放進剪貼簿，但無法確認 LINE 輸入框真的貼上本次訊息，所以已停止，避免空白發送。\n\n"
                        "請學生檢查：\n"
                        "1. LINE 視窗要在最前面，不能被其他視窗蓋住。\n"
                        "2. 第一位好友要在好友列表被選取，不要點在搜尋框。\n"
                        "3. 不要同時使用其他剪貼簿管理工具。\n"
                        "4. 如果還是不行，請錄下從按「開始發送」到停止提示的畫面。",
                        input_detail
                    )

                pyautogui.press('enter')
                time.sleep(0.4)

            if send_type in ('image', 'both'):
                require_english_input_method(f"before_image_paste:{i}")

                if copy_image_to_clipboard(img_path):
                    time.sleep(0.2)
                    pyautogui.hotkey('ctrl', 'v')
                    time.sleep(0.8)
                    pyautogui.press('enter')
                    time.sleep(0.4)
                else:
                    raise_send_error(
                        "WIN-IMG-001",
                        "圖片複製失敗",
                        "程式無法把圖片放進 Windows 剪貼簿，所以已停止。\n\n請確認圖片檔案存在、格式正常，並避免使用過大的圖片。",
                        img_path
                    )

            if recipient_key:
                seen_customers[recipient_key] = seen_customers.get(recipient_key, 0) + 1

            # 離開聊天室
            pyautogui.press('escape')
            time.sleep(0.15)

            # ★ 等待標題回到好友列表
            if friend_name_raw:
                wait_for_title_return(friend_name_raw, timeout=2)
            else:
                time.sleep(0.3)

            # 移到下一個好友
            pyautogui.press('down')
            time.sleep(0.15)

            sent = i

            # ★ Google Sheet 逐筆紀錄 v2.0（含好友名稱）
            if gsheet_logger:
                try:
                    status = "✅ 成功" if send_ok else "⚠️ 部分失敗"
                    gsheet_logger.log_send_detail(
                        batch_id, i, friend_name, type_label, status, msg_summary
                    )
                except Exception:
                    pass

        # 最終進度
        pct = int(sent / count * 100) if count > 0 else 100
        progress_cb(f"📊 {sent}/{count} 完成（{pct}%）", "")

        # ★ 寫入批次摘要
        if gsheet_logger:
            try:
                gsheet_logger.log_batch_summary(batch_id, count, sent, STOP_FLAG)
            except Exception:
                pass

        # 恢復用戶原有的剪貼簿內容
        if original_clipboard:
            try:
                pyperclip.copy(original_clipboard)
            except Exception:
                pass

        done_cb(sent, STOP_FLAG)

    except SendStopError as e:
        progress_cb(f"❌ {e.code}：{e.title}", "")
        if error_cb:
            error_cb(e.code, e.title, e.message, e.error_file)
        if gsheet_logger and batch_id:
            try:
                gsheet_logger.log_send_detail(
                    batch_id, sent + 1, "", type_label, f"❌ {e.code}", e.title[:50]
                )
                gsheet_logger.log_batch_summary(batch_id, count, sent, True)
            except Exception:
                pass
        if original_clipboard:
            try:
                pyperclip.copy(original_clipboard)
            except Exception:
                pass
        done_cb(sent, True)

    except Exception as e:
        error_file = write_error_diagnostic(
            "WIN-UNKNOWN-001",
            "未知錯誤",
            "程式發生未預期錯誤，已停止。",
            traceback.format_exc()
        )
        progress_cb(f"❌ 發生錯誤：{str(e)}", "")
        if error_cb:
            error_cb("WIN-UNKNOWN-001", "未知錯誤", f"程式發生未預期錯誤：{e}", error_file)
        if gsheet_logger and batch_id:
            try:
                gsheet_logger.log_send_detail(
                    batch_id, sent + 1, "", type_label, "❌ 錯誤", str(e)[:50]
                )
                gsheet_logger.log_batch_summary(batch_id, count, sent, True)
            except Exception:
                pass
        # 恢復剪貼簿
        if original_clipboard:
            try:
                pyperclip.copy(original_clipboard)
            except Exception:
                pass
        done_cb(sent, True)


# ==========================================
# 共用 UI 元件
# ==========================================
def make_title_bar(parent, title, on_close):
    """自訂標題列：左上角關閉按鈕 X + 程式名稱"""
    bar = tk.Frame(parent, bg=C_BG_DARK, height=36)
    bar.pack(fill='x', side='top')
    bar.pack_propagate(False)

    close_btn = tk.Label(bar, text=" ✕ ", font=("Consolas", 14, "bold"),
                         fg=C_DIM, bg=C_BG_DARK, cursor='hand2')
    close_btn.pack(side='left', padx=(6, 0))
    close_btn.bind('<Enter>', lambda e: close_btn.config(fg=C_WHITE, bg=C_RED))
    close_btn.bind('<Leave>', lambda e: close_btn.config(fg=C_DIM, bg=C_BG_DARK))
    close_btn.bind('<Button-1>', lambda e: on_close())

    tk.Label(bar, text=f"  {APP_NAME} — {title}",
             font=("Microsoft JhengHei", 10),
             fg=C_LIGHT, bg=C_BG_DARK, anchor='w').pack(side='left', fill='x', expand=True)

    def start_move(event):
        parent._drag_x = event.x
        parent._drag_y = event.y
    def on_move(event):
        x = parent.winfo_x() + event.x - parent._drag_x
        y = parent.winfo_y() + event.y - parent._drag_y
        parent.geometry(f"+{x}+{y}")
    bar.bind('<Button-1>', start_move)
    bar.bind('<B1-Motion>', on_move)

    return bar


def make_brand_footer(parent):
    """品牌署名 + IG 導流按鈕"""
    footer = tk.Frame(parent, bg=C_BG)
    footer.pack(fill='x', side='bottom', pady=(5, 0))

    # 分隔線
    tk.Frame(footer, bg=C_GOLD, height=2).pack(fill='x', padx=20, pady=(0, 8))

    # IG 導流按鈕
    ig_btn = tk.Label(footer,
                      text="  📷 追蹤 IG @eintaixin → 獲取更多銷售秘訣  ",
                      font=("Microsoft JhengHei", 11, "bold"),
                      fg=C_WHITE, bg='#E1306C', cursor='hand2',
                      padx=16, pady=8)
    ig_btn.pack(pady=(4, 8), padx=30)
    ig_btn.bind('<Enter>', lambda e: ig_btn.config(bg='#C13584'))
    ig_btn.bind('<Leave>', lambda e: ig_btn.config(bg='#E1306C'))
    ig_btn.bind('<Button-1>', lambda e: webbrowser.open(IG_URL))

    # 署名
    tk.Label(footer, text=f"{BRAND_NAME}",
             font=("Microsoft JhengHei", 10, "bold"),
             fg=C_GOLD, bg=C_BG).pack()
    tk.Label(footer, text=f"{BRAND_TITLE}",
             font=("Microsoft JhengHei", 9),
             fg=C_DIM, bg=C_BG).pack(pady=(0, 10))

    return footer


# ==========================================
# 試用到期畫面
# ==========================================
class ExpiredWindow:
    def __init__(self, license_mgr):
        self.license_mgr = license_mgr
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # 無邊框
        self.root.geometry("480x420")
        self.root.configure(bg=C_BG)
        self._center()

        make_title_bar(self.root, "授權", self.root.destroy)

        body = tk.Frame(self.root, bg=C_BG)
        body.pack(fill='both', expand=True, padx=25, pady=10)

        tk.Label(body, text="試用期已到期",
                 font=("Microsoft JhengHei", 20, "bold"),
                 fg=C_RED, bg=C_BG).pack(pady=(10, 5))

        tk.Label(body, text="感謝您試用 LINE 自動發訊息！\n如需繼續使用，請輸入授權碼。",
                 font=("Microsoft JhengHei", 11),
                 fg=C_LIGHT, bg=C_BG, justify='center').pack(pady=(5, 15))

        # 授權碼輸入
        tk.Label(body, text="授權碼：",
                 font=("Microsoft JhengHei", 10),
                 fg=C_WHITE, bg=C_BG, anchor='w').pack(fill='x')

        self.key_entry = tk.Entry(body, font=("Consolas", 12),
                                   bg=C_BG_DARK, fg=C_WHITE,
                                   insertbackground=C_WHITE, relief='flat')
        self.key_entry.pack(fill='x', pady=(3, 10), ipady=6)

        activate_btn = tk.Button(body, text="啟用授權碼",
                                  font=("Microsoft JhengHei", 12, "bold"),
                                  bg=C_GREEN, fg=C_WHITE, relief='flat',
                                  padx=20, pady=6, command=self._activate)
        activate_btn.pack(pady=(0, 5))

        self.msg_label = tk.Label(body, text="",
                                   font=("Microsoft JhengHei", 9),
                                   fg=C_ORANGE, bg=C_BG)
        self.msg_label.pack()

        # 驗證中提示
        self.verify_label = tk.Label(body, text="",
                                      font=("Microsoft JhengHei", 8),
                                      fg=C_DIM, bg=C_BG)
        self.verify_label.pack()

        # 問卷按鈕
        survey_btn = tk.Button(body, text="📋 填寫回饋問卷（30秒）",
                                font=("Microsoft JhengHei", 10),
                                bg=C_ORANGE, fg=C_WHITE, relief='flat',
                                padx=12, pady=4, command=self._open_survey)
        survey_btn.pack(pady=(8, 3))

        # 聯絡資訊
        tk.Label(body, text="取得授權碼請私訊 IG 聯繫：",
                 font=("Microsoft JhengHei", 10),
                 fg=C_LIGHT, bg=C_BG).pack(pady=(5, 0))

        make_brand_footer(self.root)

    def _center(self):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 480) // 2
        y = (self.root.winfo_screenheight() - 420) // 2
        self.root.geometry(f"+{x}+{y}")

    def _open_survey(self):
        SurveyWindow(source="trial_expired")

    def _activate(self):
        self.verify_label.config(text="⏳ 正在驗證授權碼...", fg=C_ORANGE)
        self.root.update()
        key = self.key_entry.get()
        success, msg = self.license_mgr.activate_license(key)
        self.verify_label.config(text="")
        if success:
            messagebox.showinfo("成功", msg)
            self.root.destroy()
            app = LineAutoSenderApp(self.license_mgr)
            app.run()
        else:
            self.msg_label.config(text=msg, fg=C_RED)

    def run(self):
        self.root.mainloop()


# ==========================================
# 主程式 GUI v2.0
# ==========================================
class LineAutoSenderApp:
    def __init__(self, license_mgr):
        self.license_mgr = license_mgr
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.geometry("540x780")
        self.root.configure(bg=C_BG)
        self._center()

        self.send_type = tk.StringVar(value='text')
        self.msg_text = ''
        self.img_path = ''
        self.count = 3
        self.sending = False
        self.last_error_code = ""
        self.gsheet_logger = None
        self.templates = load_templates()

        # 載入 Google Sheet 設定
        self.gsheet_config = {}
        if GSHEET_AVAILABLE:
            self.gsheet_config = load_gsheet_config()

        self._build_ui()

    def _center(self):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 540) // 2
        y = (self.root.winfo_screenheight() - 780) // 2
        self.root.geometry(f"+{x}+{y}")

    def _on_close(self):
        global STOP_FLAG
        if self.sending:
            if messagebox.askokcancel("確認", "正在發送中，確定要關閉嗎？"):
                STOP_FLAG = True
                time.sleep(0.5)
                self.root.destroy()
        else:
            self.root.destroy()

    def _build_ui(self):
        # === 自訂標題列 ===
        make_title_bar(self.root, "主畫面", self._on_close)

        # === 可滾動內容區 ===
        canvas = tk.Canvas(self.root, bg=C_BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(self.root, orient='vertical', command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas, bg=C_BG)

        self.scroll_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=self.scroll_frame, anchor='nw', width=520)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side='left', fill='both', expand=True, padx=(10, 0))
        scrollbar.pack(side='right', fill='y')

        # 滑鼠滾輪
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all('<MouseWheel>', _on_mousewheel)

        main = self.scroll_frame

        # === 頂部品牌區 ===
        header = tk.Frame(main, bg=C_BG)
        header.pack(fill='x', padx=10, pady=(12, 3))

        tk.Label(header, text=f"  {APP_NAME}",
                 font=("Microsoft JhengHei", 18, "bold"),
                 fg=C_WHITE, bg=C_BG).pack(anchor='w')

        tk.Label(header, text=f"{BRAND_NAME}｜{BRAND_TITLE}",
                 font=("Microsoft JhengHei", 9), fg=C_DIM, bg=C_BG).pack(anchor='w')

        tk.Frame(main, bg=C_ORANGE, height=3).pack(fill='x', padx=10, pady=(5, 10))

        # 授權狀態
        status_text, status_color = self.license_mgr.get_status_text()
        tk.Label(main, text=f"  {status_text}",
                 font=("Microsoft JhengHei", 9),
                 fg=status_color, bg=C_BG).pack(anchor='w', padx=10)

        # Step 1: 發送類型
        tk.Label(main, text="  選擇發送類型",
                 font=("Microsoft JhengHei", 12, "bold"),
                 fg=C_WHITE, bg=C_BG).pack(anchor='w', padx=10, pady=(8, 5))

        type_frame = tk.Frame(main, bg=C_BG)
        type_frame.pack(fill='x', padx=10, pady=(0, 8))

        for val, label in [('text', '  純文字'), ('image', '  純圖片'), ('both', '  都發')]:
            tk.Radiobutton(type_frame, text=label, variable=self.send_type, value=val,
                          font=("Microsoft JhengHei", 10), fg=C_WHITE, bg=C_BG,
                          selectcolor=C_BG_MID, activebackground=C_BG,
                          activeforeground=C_WHITE,
                          command=self._on_type_change).pack(side='left', padx=(0, 12))

        # Step 2: 文字輸入
        self.text_frame = tk.Frame(main, bg=C_BG)
        self.text_frame.pack(fill='x', padx=10)

        text_header = tk.Frame(self.text_frame, bg=C_BG)
        text_header.pack(fill='x', pady=(0, 3))

        tk.Label(text_header, text="  輸入文字內容",
                 font=("Microsoft JhengHei", 12, "bold"),
                 fg=C_WHITE, bg=C_BG).pack(side='left')

        # ★ 範本按鈕
        tpl_btn_frame = tk.Frame(text_header, bg=C_BG)
        tpl_btn_frame.pack(side='right')

        tk.Button(tpl_btn_frame, text="📋 載入範本",
                  font=("Microsoft JhengHei", 9),
                  bg=C_BG_MID, fg=C_WHITE, relief='flat',
                  padx=6, pady=1, command=self._load_template).pack(side='left', padx=2)

        tk.Button(tpl_btn_frame, text="💾 存為範本",
                  font=("Microsoft JhengHei", 9),
                  bg=C_BG_MID, fg=C_WHITE, relief='flat',
                  padx=6, pady=1, command=self._save_template).pack(side='left', padx=2)

        tk.Button(tpl_btn_frame, text="🗑 管理",
                  font=("Microsoft JhengHei", 9),
                  bg=C_BG_MID, fg=C_WHITE, relief='flat',
                  padx=6, pady=1, command=self._manage_templates).pack(side='left', padx=2)

        self.text_input = scrolledtext.ScrolledText(
            self.text_frame, width=55, height=6,
            font=("Microsoft JhengHei", 10),
            bg=C_BG_DARK, fg=C_WHITE, insertbackground=C_WHITE,
            relief='flat', padx=8, pady=8)
        self.text_input.pack(fill='x', pady=(0, 4))

        self.add_name_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.text_frame, text="  👤 自動帶入對方名字（例如：王小明，你好...）",
                       variable=self.add_name_var,
                       font=("Microsoft JhengHei", 10),
                       fg=C_LIGHT, bg=C_BG, selectcolor=C_BG_MID,
                       activebackground=C_BG, activeforeground=C_WHITE
                       ).pack(anchor='w', pady=(0, 8))

        # Step 3: 圖片選擇
        self.img_frame = tk.Frame(main, bg=C_BG)

        tk.Label(self.img_frame, text="  選擇圖片",
                 font=("Microsoft JhengHei", 12, "bold"),
                 fg=C_WHITE, bg=C_BG).pack(anchor='w', padx=10, pady=(0, 3))

        img_row = tk.Frame(self.img_frame, bg=C_BG)
        img_row.pack(fill='x', padx=10)

        tk.Button(img_row, text="  選擇圖片檔案...",
                  font=("Microsoft JhengHei", 10),
                  bg=C_BG_MID, fg=C_WHITE, relief='flat',
                  padx=10, pady=4, command=self._choose_image).pack(side='left')

        self.img_path_label = tk.Label(img_row, text="（尚未選擇）",
                                        font=("Microsoft JhengHei", 9),
                                        fg=C_DIM, bg=C_BG)
        self.img_path_label.pack(side='left', padx=(10, 0))

        # Step 4: 發送人數
        count_frame = tk.Frame(main, bg=C_BG)
        count_frame.pack(fill='x', padx=10, pady=(8, 8))

        tk.Label(count_frame, text="  發送人數",
                 font=("Microsoft JhengHei", 12, "bold"),
                 fg=C_WHITE, bg=C_BG).pack(side='left')

        self.count_entry = tk.Entry(count_frame, width=5,
                                     font=("Microsoft JhengHei", 12),
                                     bg=C_BG_DARK, fg=C_WHITE,
                                     insertbackground=C_WHITE,
                                     relief='flat', justify='center')
        self.count_entry.insert(0, '3')
        self.count_entry.pack(side='left', padx=(10, 5))

        tk.Label(count_frame, text="人（建議先用 3 人測試）",
                 font=("Microsoft JhengHei", 9),
                 fg=C_DIM, bg=C_BG).pack(side='left')

        # ★ Google Sheet 回寫設定
        if GSHEET_AVAILABLE:
            gsheet_frame = tk.Frame(main, bg=C_BG)
            gsheet_frame.pack(fill='x', padx=10, pady=(5, 5))

            self.gsheet_enabled = tk.BooleanVar(value=self.gsheet_config.get('enabled', False))
            tk.Checkbutton(gsheet_frame, text="  📊 發送結果回寫 Google Sheet",
                           variable=self.gsheet_enabled,
                           font=("Microsoft JhengHei", 11, "bold"),
                           fg=C_WHITE, bg=C_BG, selectcolor=C_BG_MID,
                           activebackground=C_BG, activeforeground=C_WHITE,
                           command=self._toggle_gsheet).pack(anchor='w')

            self.gsheet_detail = tk.Frame(main, bg=C_BG_MID, padx=10, pady=8)

            tk.Label(self.gsheet_detail, text="Apps Script Web App 網址：",
                     font=("Microsoft JhengHei", 9),
                     fg=C_LIGHT, bg=C_BG_MID).pack(anchor='w')
            self.webapp_url_entry = tk.Entry(self.gsheet_detail,
                                              font=("Consolas", 9),
                                              bg=C_BG_DARK, fg=C_WHITE,
                                              insertbackground=C_WHITE, relief='flat')
            self.webapp_url_entry.pack(fill='x', ipady=4, pady=(2, 6))
            self.webapp_url_entry.insert(0, self.gsheet_config.get('webapp_url', ''))

            self.gsheet_status = tk.Label(self.gsheet_detail, text="",
                                           font=("Microsoft JhengHei", 8),
                                           fg=C_DIM, bg=C_BG_MID)
            self.gsheet_status.pack(anchor='w')

            tk.Button(self.gsheet_detail, text="🔗 測試連線",
                      font=("Microsoft JhengHei", 9),
                      bg=C_BLUE, fg=C_WHITE, relief='flat',
                      padx=8, pady=2, command=self._test_gsheet).pack(anchor='w', pady=(4, 0))

            if self.gsheet_enabled.get():
                self.gsheet_detail.pack(fill='x', padx=10, pady=(0, 5))

        # 開始 / 停止
        btn_frame = tk.Frame(main, bg=C_BG)
        btn_frame.pack(fill='x', padx=10, pady=(8, 5))

        self.start_btn = tk.Button(btn_frame, text="  開始發送！",
                                    font=("Microsoft JhengHei", 14, "bold"),
                                    bg=C_GREEN, fg=C_WHITE, relief='flat',
                                    padx=18, pady=7, command=self._start_send)
        self.start_btn.pack(side='left', expand=True, fill='x', padx=(0, 5))

        self.stop_btn = tk.Button(btn_frame, text="  強制停止",
                                   font=("Microsoft JhengHei", 14, "bold"),
                                   bg=C_RED, fg=C_WHITE, relief='flat',
                                   padx=18, pady=7, command=self._stop_send,
                                   state='disabled')
        self.stop_btn.pack(side='left', expand=True, fill='x', padx=(5, 0))

        # ★ 進度顯示區（兩行：進度 + 好友名稱）
        progress_frame = tk.Frame(main, bg=C_BG_MID, padx=10, pady=8)
        progress_frame.pack(fill='x', padx=10, pady=(5, 3))

        self.status_label = tk.Label(progress_frame, text="  準備就緒",
                                      font=("Microsoft JhengHei", 11, "bold"),
                                      fg=C_GREEN, bg=C_BG_MID, anchor='w')
        self.status_label.pack(fill='x')

        self.friend_label = tk.Label(progress_frame, text="",
                                      font=("Microsoft JhengHei", 10),
                                      fg=C_LIGHT, bg=C_BG_MID, anchor='w')
        self.friend_label.pack(fill='x')

        # ★ 進度條
        bar_outer = tk.Frame(progress_frame, bg=C_BG_DARK, height=20,
                             highlightbackground=C_DIM, highlightthickness=1)
        bar_outer.pack(fill='x', pady=(5, 0))
        bar_outer.pack_propagate(False)

        self.bar_fill = tk.Frame(bar_outer, bg=C_ORANGE, width=0)
        self.bar_fill.place(x=0, y=0, relheight=1)
        self.bar_max_width = 480

        # === 底部品牌 + IG 導流 ===
        make_brand_footer(main)

        # 初始化欄位可見性
        self._on_type_change()

    # ==========================================
    # 範本功能
    # ==========================================
    def _load_template(self):
        """載入訊息範本"""
        if not self.templates:
            messagebox.showinfo("提示", "尚未儲存任何範本。\n先輸入訊息內容，再按「💾 存為範本」。")
            return

        # 彈出選擇視窗
        picker = tk.Toplevel(self.root)
        picker.title("選擇範本")
        picker.geometry("400x350")
        picker.configure(bg=C_BG)
        picker.transient(self.root)
        picker.grab_set()

        # 置中
        picker.update_idletasks()
        x = (picker.winfo_screenwidth() - 400) // 2
        y = (picker.winfo_screenheight() - 350) // 2
        picker.geometry(f"+{x}+{y}")

        tk.Label(picker, text="📋 選擇訊息範本",
                 font=("Microsoft JhengHei", 14, "bold"),
                 fg=C_WHITE, bg=C_BG).pack(pady=(10, 5))

        listbox = tk.Listbox(picker, font=("Microsoft JhengHei", 10),
                              bg=C_BG_DARK, fg=C_WHITE,
                              selectbackground=C_ORANGE,
                              selectforeground=C_WHITE,
                              relief='flat', height=12)
        listbox.pack(fill='both', expand=True, padx=15, pady=5)

        for tpl in self.templates:
            name = tpl.get('name', '未命名')
            preview = tpl.get('text', '')[:30]
            listbox.insert('end', f"  {name}  —  {preview}...")

        def _use():
            sel = listbox.curselection()
            if sel:
                tpl = self.templates[sel[0]]
                self.text_input.delete('1.0', 'end')
                self.text_input.insert('1.0', tpl.get('text', ''))
                picker.destroy()

        tk.Button(picker, text="✅ 使用此範本",
                  font=("Microsoft JhengHei", 12, "bold"),
                  bg=C_GREEN, fg=C_WHITE, relief='flat',
                  padx=15, pady=5, command=_use).pack(pady=(5, 10))

    def _save_template(self):
        """儲存目前文字為範本"""
        text = self.text_input.get('1.0', 'end-1c').strip()
        if not text:
            messagebox.showwarning("提示", "請先輸入文字內容！")
            return

        # 簡單輸入名稱
        name_win = tk.Toplevel(self.root)
        name_win.title("範本名稱")
        name_win.geometry("350x150")
        name_win.configure(bg=C_BG)
        name_win.transient(self.root)
        name_win.grab_set()

        name_win.update_idletasks()
        x = (name_win.winfo_screenwidth() - 350) // 2
        y = (name_win.winfo_screenheight() - 150) // 2
        name_win.geometry(f"+{x}+{y}")

        tk.Label(name_win, text="為這個範本取個名字：",
                 font=("Microsoft JhengHei", 11),
                 fg=C_WHITE, bg=C_BG).pack(pady=(15, 5))

        name_entry = tk.Entry(name_win, font=("Microsoft JhengHei", 11),
                               bg=C_BG_DARK, fg=C_WHITE,
                               insertbackground=C_WHITE, relief='flat')
        name_entry.pack(fill='x', padx=20, ipady=5)
        name_entry.insert(0, text[:20])
        name_entry.focus_set()

        def _save():
            name = name_entry.get().strip()
            if not name:
                name = text[:20]
            self.templates.append({
                'name': name,
                'text': text,
                'created': datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            save_templates(self.templates)
            name_win.destroy()
            messagebox.showinfo("已儲存", f"範本「{name}」已儲存！")

        tk.Button(name_win, text="💾 儲存",
                  font=("Microsoft JhengHei", 11, "bold"),
                  bg=C_GREEN, fg=C_WHITE, relief='flat',
                  padx=15, pady=4, command=_save).pack(pady=(10, 0))

    def _manage_templates(self):
        """管理（刪除）範本"""
        if not self.templates:
            messagebox.showinfo("提示", "尚未儲存任何範本。")
            return

        mgr = tk.Toplevel(self.root)
        mgr.title("管理範本")
        mgr.geometry("400x350")
        mgr.configure(bg=C_BG)
        mgr.transient(self.root)
        mgr.grab_set()

        mgr.update_idletasks()
        x = (mgr.winfo_screenwidth() - 400) // 2
        y = (mgr.winfo_screenheight() - 350) // 2
        mgr.geometry(f"+{x}+{y}")

        tk.Label(mgr, text="🗑 管理訊息範本",
                 font=("Microsoft JhengHei", 14, "bold"),
                 fg=C_WHITE, bg=C_BG).pack(pady=(10, 5))

        listbox = tk.Listbox(mgr, font=("Microsoft JhengHei", 10),
                              bg=C_BG_DARK, fg=C_WHITE,
                              selectbackground=C_RED,
                              selectforeground=C_WHITE,
                              relief='flat', height=12)
        listbox.pack(fill='both', expand=True, padx=15, pady=5)

        def _refresh():
            listbox.delete(0, 'end')
            for tpl in self.templates:
                name = tpl.get('name', '未命名')
                listbox.insert('end', f"  {name}")

        _refresh()

        def _delete():
            sel = listbox.curselection()
            if sel:
                idx = sel[0]
                name = self.templates[idx].get('name', '未命名')
                if messagebox.askyesno("確認", f"確定刪除範本「{name}」？"):
                    self.templates.pop(idx)
                    save_templates(self.templates)
                    _refresh()

        tk.Button(mgr, text="🗑 刪除選取的範本",
                  font=("Microsoft JhengHei", 11, "bold"),
                  bg=C_RED, fg=C_WHITE, relief='flat',
                  padx=15, pady=5, command=_delete).pack(pady=(5, 10))

    # ==========================================
    # Google Sheet
    # ==========================================
    def _toggle_gsheet(self):
        if not GSHEET_AVAILABLE:
            return
        if self.gsheet_enabled.get():
            self.gsheet_detail.pack(fill='x', padx=10, pady=(0, 5))
        else:
            self.gsheet_detail.pack_forget()

    def _test_gsheet(self):
        url = self.webapp_url_entry.get().strip()
        if not url:
            self.gsheet_status.config(text="❌ 請先貼入 Web App 網址", fg=C_RED)
            return

        self.gsheet_status.config(text="⏳ 連線中...", fg=C_ORANGE)
        self.root.update()

        logger = GSheetLogger(url)
        if logger.connect():
            self.gsheet_status.config(text="✅ 連線成功！", fg=C_GREEN)
            self.gsheet_config['webapp_url'] = url
            self.gsheet_config['enabled'] = True
            save_gsheet_config(self.gsheet_config)
        else:
            self.gsheet_status.config(text=f"❌ {logger.error_msg}", fg=C_RED)

    def _init_gsheet(self):
        """發送前初始化 Google Sheet 連線"""
        if not GSHEET_AVAILABLE or not self.gsheet_enabled.get():
            return None
        url = self.webapp_url_entry.get().strip()
        if not url:
            return None
        logger = GSheetLogger(url)
        if logger.connect():
            self.gsheet_config['webapp_url'] = url
            self.gsheet_config['enabled'] = True
            save_gsheet_config(self.gsheet_config)
            return logger
        return None

    # ==========================================
    # 發送控制
    # ==========================================
    def _on_type_change(self):
        t = self.send_type.get()
        if t == 'text':
            self.text_frame.pack(fill='x', padx=10)
            self.img_frame.pack_forget()
        elif t == 'image':
            self.text_frame.pack_forget()
            self.img_frame.pack(fill='x', padx=10)
        else:
            self.text_frame.pack(fill='x', padx=10)
            self.img_frame.pack(fill='x', padx=10, after=self.text_frame)

    def _choose_image(self):
        path = filedialog.askopenfilename(
            title="選擇要發送的圖片",
            filetypes=[("圖片檔案", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("所有檔案", "*.*")])
        if path:
            self.img_path = path
            self.img_path_label.config(text=f"  {os.path.basename(path)}")

    def _validate(self):
        t = self.send_type.get()
        if t in ('text', 'both'):
            self.msg_text = self.text_input.get('1.0', 'end-1c').strip()
            if not self.msg_text:
                messagebox.showwarning("提醒", "請輸入要發送的文字內容！")
                return False
        if t in ('image', 'both'):
            if not self.img_path or not os.path.exists(self.img_path):
                messagebox.showwarning("提醒", "請選擇要發送的圖片！")
                return False
        try:
            self.count = int(self.count_entry.get().strip())
            if self.count <= 0: raise ValueError
        except ValueError:
            messagebox.showwarning("提醒", "請輸入有效的發送人數！")
            return False
        return True

    def _start_send(self):
        if self.sending: return
        if not self._validate(): return

        t = self.send_type.get()
        names = {'text': '純文字', 'image': '純圖片', 'both': '文字+圖片'}
        preview_lines = [
            f"發送類型：{names[t]}",
            f"發送人數：{self.count} 位",
        ]
        if t in ('text', 'both'):
            text_preview = self.msg_text[:220]
            if self.add_name_var.get():
                text_preview = f"對方名字，{text_preview}"
            preview_lines.extend(["", "文字預覽：", text_preview])
        if t in ('image', 'both'):
            preview_lines.extend(["", f"圖片：{os.path.basename(self.img_path)}"])

        confirm = messagebox.askokcancel(
            "確認發送",
            "\n".join(preview_lines) + "\n\n"
            f"執行期間請不要碰滑鼠和鍵盤！\n"
            f"按下「確定」後有 2 秒準備時間。\n\n"
            f"請確保 LINE 好友列表已打開，\n"
            f"且已點選一位好友（灰底狀態）。\n\n"
            f"程式會自動嘗試切到英文輸入法，避免中文輸入法攔截貼上或 Enter。")
        if not confirm: return

        self.sending = True
        self.last_error_code = ""
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')

        # 重置進度條
        self.bar_fill.place(x=0, y=0, relheight=1, width=0)

        # 初始化 Google Sheet
        self.gsheet_logger = self._init_gsheet()

        threading.Thread(
            target=send_messages,
            args=(t, self.msg_text, self.img_path, self.count,
                  self._update_progress, self._on_done, self.gsheet_logger,
                  self.add_name_var.get(), self._show_error),
            daemon=True).start()

    def _stop_send(self):
        global STOP_FLAG
        STOP_FLAG = True
        self._update_progress("⛔ 正在停止...", "")

    def _update_progress(self, status_text, friend_text):
        """★ 更新進度顯示（狀態 + 好友名稱 + 進度條）"""
        def _update():
            self.status_label.config(text=f"  {status_text}")
            self.friend_label.config(text=f"  {friend_text}" if friend_text else "")

            # 解析百分比更新進度條
            try:
                if "%" in status_text:
                    pct_str = status_text.split("（")[1].split("%")[0]
                    pct = int(pct_str) / 100
                    w = int(self.bar_max_width * pct)
                    self.bar_fill.place(x=0, y=0, relheight=1, width=max(w, 0))
                    if pct >= 1.0:
                        self.bar_fill.configure(bg=C_GREEN)
                    else:
                        self.bar_fill.configure(bg=C_ORANGE)
            except Exception:
                pass
        self.root.after(0, _update)

    def _show_error(self, code, title, message, error_file):
        """在主執行緒顯示錯誤碼與診斷檔位置。"""
        self.last_error_code = code

        def _show():
            self.status_label.config(text=f"  ❌ {code}：{title}", fg=C_RED)
            self.friend_label.config(text=f"  診斷檔：{error_file}")
            messagebox.showerror(
                title,
                f"錯誤碼：{code}\n\n{message}\n\n診斷檔已儲存：\n{error_file}"
            )

        self.root.after(0, _show)

    def _on_done(self, sent, stopped):
        def _finish():
            self.sending = False
            self.start_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            if self.last_error_code:
                self.status_label.config(text=f"  ❌ 已停止：{self.last_error_code}", fg=C_RED)
                return
            if stopped and sent > 0:
                self.status_label.config(text=f"  ⛔ 已在第 {sent} 位停下", fg=C_ORANGE)
                self.friend_label.config(text="")
                messagebox.showinfo("已停止", f"已在第 {sent} 位停下。")
                SurveyWindow(source="force_stopped", gsheet_logger=self.gsheet_logger)
            elif stopped:
                self.status_label.config(text="  已取消", fg=C_ORANGE)
                self.friend_label.config(text="")
                SurveyWindow(source="force_stopped", gsheet_logger=self.gsheet_logger)
            else:
                self.status_label.config(text=f"  ✅ 發送完成！已發送 {sent} 位好友", fg=C_GREEN)
                self.friend_label.config(text="")
                # 進度條滿格變綠
                self.bar_fill.place(x=0, y=0, relheight=1, width=self.bar_max_width)
                self.bar_fill.configure(bg=C_GREEN)
                messagebox.showinfo("完成", f"  發送完成！已發送 {sent} 位好友")
                SurveyWindow(source="send_complete", gsheet_logger=self.gsheet_logger)
        self.root.after(0, _finish)

    def run(self):
        self.root.mainloop()


# ==========================================
# 問卷調查視窗
# ==========================================
class SurveyWindow:
    """使用者意見回饋問卷（結果回寫 Google Sheet）"""

    def __init__(self, source="send_complete", gsheet_logger=None):
        self.source = source
        self.gsheet_logger = gsheet_logger
        self.root = tk.Toplevel() if tk._default_root else tk.Tk()
        self.root.overrideredirect(True)
        self.root.geometry("500x620")
        self.root.configure(bg=C_BG)
        self._center()
        self._build_ui()

    def _center(self):
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 500) // 2
        y = (self.root.winfo_screenheight() - 620) // 2
        self.root.geometry(f"+{x}+{y}")

    def _build_ui(self):
        make_title_bar(self.root, "意見回饋", self.root.destroy)

        # 可滾動區域
        canvas = tk.Canvas(self.root, bg=C_BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(self.root, orient='vertical', command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=C_BG)

        scroll_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=scroll_frame, anchor='nw', width=480)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side='left', fill='both', expand=True, padx=(10, 0))
        scrollbar.pack(side='right', fill='y')

        body = scroll_frame
        pad = {'padx': 15}

        tk.Label(body, text="📋 使用回饋問卷",
                 font=("Microsoft JhengHei", 16, "bold"),
                 fg=C_WHITE, bg=C_BG).pack(anchor='w', pady=(10, 3), **pad)
        tk.Label(body, text="花 30 秒填寫，幫助我們做得更好！",
                 font=("Microsoft JhengHei", 9),
                 fg=C_DIM, bg=C_BG).pack(anchor='w', pady=(0, 10), **pad)

        # Q1
        tk.Label(body, text="1. 你的稱呼",
                 font=("Microsoft JhengHei", 11, "bold"),
                 fg=C_WHITE, bg=C_BG).pack(anchor='w', **pad)
        self.q1_name = tk.Entry(body, font=("Microsoft JhengHei", 10),
                                 bg=C_BG_DARK, fg=C_WHITE, insertbackground=C_WHITE, relief='flat')
        self.q1_name.pack(fill='x', ipady=5, pady=(3, 10), **pad)
        self.q1_name.insert(0, "怎麼稱呼你？")
        self.q1_name.config(fg=C_DIM)
        self.q1_name.bind('<FocusIn>', lambda e: self._clear_placeholder(self.q1_name, "怎麼稱呼你？"))
        self.q1_name.bind('<FocusOut>', lambda e: self._set_placeholder(self.q1_name, "怎麼稱呼你？"))

        # Q2
        tk.Label(body, text="2. LINE ID 或 WhatsApp 號碼（方便通知新功能）",
                 font=("Microsoft JhengHei", 11, "bold"),
                 fg=C_WHITE, bg=C_BG).pack(anchor='w', **pad)
        self.q2_contact = tk.Entry(body, font=("Microsoft JhengHei", 10),
                                    bg=C_BG_DARK, fg=C_WHITE, insertbackground=C_WHITE, relief='flat')
        self.q2_contact.pack(fill='x', ipady=5, pady=(3, 10), **pad)
        self.q2_contact.insert(0, "選填")
        self.q2_contact.config(fg=C_DIM)
        self.q2_contact.bind('<FocusIn>', lambda e: self._clear_placeholder(self.q2_contact, "選填"))
        self.q2_contact.bind('<FocusOut>', lambda e: self._set_placeholder(self.q2_contact, "選填"))

        # Q3
        tk.Label(body, text="3. 整體使用體驗如何？",
                 font=("Microsoft JhengHei", 11, "bold"),
                 fg=C_WHITE, bg=C_BG).pack(anchor='w', **pad)
        self.q3_exp = tk.StringVar(value='')
        for opt in ['非常好用', '還不錯', '普通', '需要改進']:
            tk.Radiobutton(body, text=f"  {opt}", variable=self.q3_exp, value=opt,
                          font=("Microsoft JhengHei", 10), fg=C_WHITE, bg=C_BG,
                          selectcolor=C_BG_MID, activebackground=C_BG,
                          activeforeground=C_WHITE).pack(anchor='w', padx=(25, 0))
        tk.Frame(body, bg=C_BG, height=8).pack()

        # Q4
        tk.Label(body, text="4. 最希望新增什麼功能？（可多選）",
                 font=("Microsoft JhengHei", 11, "bold"),
                 fg=C_WHITE, bg=C_BG).pack(anchor='w', **pad)
        self.q4_features = {}
        for feat in ['定時排程發送', '自動帶入對方名字', '報表匯出', '更多訊息格式']:
            var = tk.BooleanVar(value=False)
            self.q4_features[feat] = var
            tk.Checkbutton(body, text=f"  {feat}", variable=var,
                          font=("Microsoft JhengHei", 10), fg=C_WHITE, bg=C_BG,
                          selectcolor=C_BG_MID, activebackground=C_BG,
                          activeforeground=C_WHITE).pack(anchor='w', padx=(25, 0))
        tk.Frame(body, bg=C_BG, height=8).pack()

        # Q5
        tk.Label(body, text="5. 推出月訂閱制（不限使用），你覺得合理月費是？",
                 font=("Microsoft JhengHei", 11, "bold"),
                 fg=C_WHITE, bg=C_BG).pack(anchor='w', **pad)
        price_frame = tk.Frame(body, bg=C_BG)
        price_frame.pack(fill='x', pady=(3, 3), **pad)

        self.q5_currency = tk.StringVar(value='NT$')
        tk.Radiobutton(price_frame, text="NT$", variable=self.q5_currency, value='NT$',
                       font=("Microsoft JhengHei", 10), fg=C_WHITE, bg=C_BG,
                       selectcolor=C_BG_MID).pack(side='left')
        tk.Radiobutton(price_frame, text="RM", variable=self.q5_currency, value='RM',
                       font=("Microsoft JhengHei", 10), fg=C_WHITE, bg=C_BG,
                       selectcolor=C_BG_MID).pack(side='left', padx=(5, 5))

        self.q5_amount = tk.Entry(price_frame, width=8, font=("Microsoft JhengHei", 10),
                                   bg=C_BG_DARK, fg=C_WHITE, insertbackground=C_WHITE,
                                   relief='flat', justify='center')
        self.q5_amount.pack(side='left', ipady=3)
        tk.Label(price_frame, text=" / 月", font=("Microsoft JhengHei", 10),
                 fg=C_LIGHT, bg=C_BG).pack(side='left')

        self.q5_no_pay = tk.BooleanVar(value=False)
        tk.Checkbutton(body, text="  不考慮付費", variable=self.q5_no_pay,
                       font=("Microsoft JhengHei", 10), fg=C_ORANGE, bg=C_BG,
                       selectcolor=C_BG_MID, activebackground=C_BG).pack(anchor='w', padx=(25, 0))
        tk.Frame(body, bg=C_BG, height=8).pack()

        # Q6
        tk.Label(body, text="6. 想對我們說的話（選填）",
                 font=("Microsoft JhengHei", 11, "bold"),
                 fg=C_WHITE, bg=C_BG).pack(anchor='w', **pad)
        self.q6_feedback = tk.Text(body, height=3, font=("Microsoft JhengHei", 10),
                                    bg=C_BG_DARK, fg=C_WHITE, insertbackground=C_WHITE,
                                    relief='flat', padx=8, pady=6)
        self.q6_feedback.pack(fill='x', pady=(3, 10), **pad)
        self.q6_feedback.insert('1.0', "任何建議都歡迎！")
        self.q6_feedback.config(fg=C_DIM)
        self.q6_feedback.bind('<FocusIn>', lambda e: self._clear_text_placeholder(self.q6_feedback, "任何建議都歡迎！"))
        self.q6_feedback.bind('<FocusOut>', lambda e: self._set_text_placeholder(self.q6_feedback, "任何建議都歡迎！"))

        # 送出
        submit_btn = tk.Button(body, text="📤 送出回饋",
                                font=("Microsoft JhengHei", 13, "bold"),
                                bg=C_GREEN, fg=C_WHITE, relief='flat',
                                padx=20, pady=8, command=self._submit)
        submit_btn.pack(pady=(5, 5), **pad)

        self.submit_status = tk.Label(body, text="",
                                       font=("Microsoft JhengHei", 9),
                                       fg=C_DIM, bg=C_BG)
        self.submit_status.pack(**pad)

        make_brand_footer(body)

    def _clear_placeholder(self, entry, placeholder):
        if entry.get() == placeholder:
            entry.delete(0, 'end')
            entry.config(fg=C_WHITE)

    def _set_placeholder(self, entry, placeholder):
        if not entry.get().strip():
            entry.delete(0, 'end')
            entry.insert(0, placeholder)
            entry.config(fg=C_DIM)

    def _clear_text_placeholder(self, text_widget, placeholder):
        if text_widget.get('1.0', 'end-1c') == placeholder:
            text_widget.delete('1.0', 'end')
            text_widget.config(fg=C_WHITE)

    def _set_text_placeholder(self, text_widget, placeholder):
        if not text_widget.get('1.0', 'end-1c').strip():
            text_widget.delete('1.0', 'end')
            text_widget.insert('1.0', placeholder)
            text_widget.config(fg=C_DIM)

    def _get_value(self, entry, placeholder):
        val = entry.get().strip()
        return "" if val == placeholder else val

    def _submit(self):
        name = self._get_value(self.q1_name, "怎麼稱呼你？")
        contact = self._get_value(self.q2_contact, "選填")
        experience = self.q3_exp.get()
        features = ", ".join([f for f, v in self.q4_features.items() if v.get()])

        if self.q5_no_pay.get():
            price = "不考慮付費"
        else:
            amt = self.q5_amount.get().strip()
            if amt:
                price = f"{self.q5_currency.get()}{amt}/月"
            else:
                price = ""

        feedback_text = self.q6_feedback.get('1.0', 'end-1c').strip()
        if feedback_text == "任何建議都歡迎！":
            feedback_text = ""

        timestamp = datetime.now().strftime("%Y/%m/%d %p %I:%M:%S").replace("AM", "上午").replace("PM", "下午")

        if self.gsheet_logger and self.gsheet_logger.connected:
            try:
                row = [timestamp, name, contact, experience,
                       features, price, feedback_text, self.source]
                self.gsheet_logger.log_survey(row)
                self.submit_status.config(text="✅ 感謝回饋！已成功送出", fg=C_GREEN)
                self.root.after(2000, self.root.destroy)
                return
            except Exception:
                self.submit_status.config(text="⚠️ Sheet 寫入失敗，已儲存到本地", fg=C_ORANGE)

        # 本地備份
        try:
            local_file = os.path.join(
                os.environ.get('APPDATA', os.path.expanduser('~')),
                'LINE自動發訊息', 'survey_responses.json'
            )
            responses = []
            if os.path.exists(local_file):
                with open(local_file, 'r', encoding='utf-8') as f:
                    responses = json.load(f)
            responses.append({
                "時間戳記": timestamp, "稱呼": name, "聯絡方式": contact,
                "使用體驗": experience, "希望功能": features,
                "合理月費": price, "回饋意見": feedback_text, "來源": self.source
            })
            with open(local_file, 'w', encoding='utf-8') as f:
                json.dump(responses, f, ensure_ascii=False, indent=2)
            self.submit_status.config(text="✅ 感謝回饋！已儲存到本地", fg=C_GREEN)
        except Exception:
            self.submit_status.config(text="✅ 感謝你的回饋！", fg=C_GREEN)

        self.root.after(2000, self.root.destroy)

    def run(self):
        self.root.mainloop()


# ==========================================
# 主程式入口
# ==========================================
if __name__ == '__main__':
    # 平台檢查
    if sys.platform != 'win32':
        root = tk.Tk(); root.withdraw()
        messagebox.showwarning("系統不支援",
            "此程式為 Windows 版本。\nmacOS 用戶請使用「LINE自動發訊息.app」。")
        sys.exit(0)

    # 授權檢查
    lm = LicenseManager()

    if lm.can_use():
        app = LineAutoSenderApp(lm)
        app.run()
    else:
        expired = ExpiredWindow(lm)
        expired.run()
