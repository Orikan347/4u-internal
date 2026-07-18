#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Sheet 回寫模組 v2.0 — LINE 自動發訊息
Orikan 李泰欣 | 亞洲銷冠系統架構導師

方式：Google Sheet 僅作為可選的發送結果記錄；授權改由成交聯盟共用平台短效 lease API 判斷。

v2.0 新增：
- API Token 安全驗證（所有寫入操作都帶 token）
- LicenseAPIClient：成交聯盟共用平台短效 lease 授權
- log_send_detail()：逐筆發送紀錄（含好友名稱）
- log_batch_summary()：批次摘要紀錄

macOS / Windows 自帶 urllib，不需要額外安裝套件
"""

import os
import json
import platform
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.parse import quote, urlsplit
from urllib.error import URLError


# 記錄服務憑證不可寫入程式；正式平台應提供短效工作階段。
API_TOKEN = os.environ.get("LINE_LOG_API_TOKEN", "")
LICENSE_API_ENV = "DEAL_ALLIANCE_LICENSE_API_URL"


def normalize_license_api_url(raw_url):
    """只接受由正式環境注入的純 HTTPS API origin，絕不 fallback 到 staging。"""
    value = str(raw_url or "").strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        # Accessing port also validates malformed port syntax.
        _ = parsed.port
    except ValueError:
        return ""
    if (parsed.scheme.lower() != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        return ""
    return value.rstrip("/")


class LicenseAPIClient:
    """成交聯盟共用授權 API client；不保存平台 secret。"""

    def __init__(self, api_url):
        self.api_url = normalize_license_api_url(api_url)

    def _post(self, path, payload, bearer_token=""):
        if not self.api_url:
            raise RuntimeError("未設定成交聯盟授權 API")
        headers = {"Content-Type": "application/json"}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        req = Request(
            f"{self.api_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def exchange_authorization_code(self, code, code_verifier, app_id, client_id, release_id,
                                    product_id, redirect_uri, device_id, platform_name, app_version):
        """OAuth V2 code exchange. The verifier is supplied by memory only."""
        return self._post("/api/apps/token", {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "app_id": app_id,
            "client_id": client_id,
            "release_id": release_id,
            "product_id": product_id,
            "redirect_uri": redirect_uri,
            "device_id": device_id,
            "platform": platform_name,
            "app_version": app_version,
        })

    def refresh_authorization(self, refresh_token, app_id, client_id, release_id,
                              product_id, device_id, platform_name, app_version):
        """Refresh only a memory-resident OAuth V2 session before LINE actions."""
        return self._post("/api/apps/token", {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "app_id": app_id,
            "client_id": client_id,
            "release_id": release_id,
            "product_id": product_id,
            "device_id": device_id,
            "platform": platform_name,
            "app_version": app_version,
        })

    def authorize_app(self, access_token, app_id, client_id, release_id,
                      product_id, device_id, platform_name, app_version):
        """The backend remains authoritative for product, device, version and status."""
        return self._post("/api/apps/license", {
            "app_id": app_id,
            "client_id": client_id,
            "release_id": release_id,
            "product_id": product_id,
            "device_id": device_id,
            "platform": platform_name,
            "app_version": app_version,
        }, bearer_token=access_token)


def load_license_api_url():
    """只讀取正式環境注入的授權 API URL；缺值或不合格值一律不連線。"""
    return normalize_license_api_url(os.environ.get(LICENSE_API_ENV, ""))


class GSheetLogger:
    """Google Sheet 發送結果記錄器（透過 Apps Script Web App）"""

    def __init__(self, webapp_url):
        """
        Args:
            webapp_url: Google Apps Script 部署的 Web App 網址
        """
        self.webapp_url = webapp_url.strip()
        self.connected = False
        self.error_msg = ""

    def connect(self):
        """測試連線"""
        if not self.webapp_url:
            self.error_msg = "未設定 Web App 網址"
            return False
        if 'script.google.com' not in self.webapp_url:
            self.error_msg = "網址格式不對，應該是 script.google.com 開頭"
            return False
        try:
            result = self._post({"action": "ping"})
            if result and result.get("status") == "ok":
                self.connected = True
                return True
            self.error_msg = "連線失敗，請確認 Web App 已部署"
            return False
        except Exception as e:
            self.error_msg = f"連線錯誤：{str(e)}"
            return False

    def _post(self, data):
        """
        發送資料到 Web App。
        自動為寫入操作注入 API Token。
        POST 失敗時改用 GET 備援。
        """
        # 自動注入外部記錄 token；授權 API 使用獨立的 LicenseAPIClient。
        action = data.get("action", "")
        if action != "ping" and "token" not in data:
            if not API_TOKEN:
                return {"status": "error", "reason": "missing_external_log_token"}
            data["token"] = API_TOKEN

        json_data = json.dumps(data).encode('utf-8')
        # 方法 1：POST（urllib 會自動處理 Google 的 302 重新導向）
        try:
            req = Request(
                self.webapp_url,
                data=json_data,
                headers={'Content-Type': 'application/json'}
            )
            with urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                if result.get('status') == 'ok':
                    return result
        except Exception:
            pass
        # 方法 2：GET 備援（把 JSON 放在 query string 的 data 參數）
        fallback_url = self.webapp_url + '?data=' + quote(json.dumps(data))
        req = Request(fallback_url)
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))

    # ==========================================
    # 批次 ID
    # ==========================================
    def get_batch_id(self):
        """產生批次 ID"""
        return f"WIN-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # ==========================================
    # 發送紀錄
    # ==========================================
    def log_send(self, batch_id, seq_num, send_type, status, note=""):
        """記錄單筆發送結果（舊版相容）"""
        if not self.connected:
            return False
        try:
            self._post({
                "action": "log_send",
                "sheet": "發送記錄",
                "row": [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    batch_id, str(seq_num), send_type, status, note
                ]
            })
            return True
        except Exception:
            return False

    def log_send_detail(self, batch_id, seq_num, friend_name, send_type, status, msg_summary=""):
        """
        逐筆發送紀錄 v2.0（含好友名稱）
        row 格式：[時間戳記, 批次ID, 序號, 好友名稱, 發送類型, 狀態, 訊息摘要]
        """
        if not self.connected:
            return False
        try:
            self._post({
                "action": "log_send_detail",
                "row": [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    batch_id,
                    str(seq_num),
                    friend_name or "（未知）",
                    send_type,
                    status,
                    msg_summary[:50] if msg_summary else ""
                ]
            })
            return True
        except Exception:
            return False

    def log_batch_summary(self, batch_id, total, sent, stopped):
        """
        批次摘要 v2.0
        row 格式：[時間戳記, 批次ID, "摘要", 成功數/總數, 發送類型, 完成狀態, 備註]
        """
        if not self.connected:
            return False
        try:
            status = "⛔ 中途停止" if stopped else "✅ 全部完成"
            note = f"預計 {total} 位，實際發送 {sent} 位"
            self._post({
                "action": "log_batch_summary",
                "row": [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    batch_id,
                    "📊 摘要",
                    f"{sent}/{total}",
                    "批次統計",
                    status,
                    note
                ]
            })
            return True
        except Exception:
            return False

    def log_summary(self, batch_id, total, sent, stopped):
        """記錄批次摘要（舊版相容，內部呼叫 log_batch_summary）"""
        return self.log_batch_summary(batch_id, total, sent, stopped)

    def log_survey(self, data):
        """記錄問卷回饋"""
        if not self.connected:
            return False
        try:
            self._post({
                "action": "log_send",
                "sheet": "問卷回饋",
                "row": data
            })
            return True
        except Exception:
            return False


# ==========================================
# 設定檔管理
# ==========================================
def get_config_dir():
    if os.environ.get('LINE_FUNCTIONAL_TEST_CHANNEL') == '1':
        configured = os.environ.get('LINE_FUNCTIONAL_TEST_DATA_DIR', '').strip()
        config_dir = configured or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'functional_test_data'
        )
        os.makedirs(config_dir, exist_ok=True)
        return config_dir
    if platform.system() == 'Darwin':
        config_dir = os.path.expanduser('~/Library/Application Support/LINE自動發訊息')
    else:
        config_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'LINE自動發訊息')
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


# 預設 Web App 網址（寫死備援，確保永遠有值）
DEFAULT_WEBAPP_URL = ""


def load_gsheet_config():
    # 優先讀取系統設定目錄
    config_file = os.path.join(get_config_dir(), 'gsheet_config.json')
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 如果讀到的 URL 是空的，用預設值補上
            if not config.get('webapp_url'):
                config['webapp_url'] = DEFAULT_WEBAPP_URL
                config['enabled'] = False
                save_gsheet_config(config)
            config.setdefault('license_api_url', load_license_api_url())
            return config
    except Exception:
        pass
    # 所有設定檔都讀不到時，用預設值
    return {
        'webapp_url': DEFAULT_WEBAPP_URL,
        'license_api_url': load_license_api_url(),
        'enabled': False,
    }


def save_gsheet_config(config):
    config_file = os.path.join(get_config_dir(), 'gsheet_config.json')
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
