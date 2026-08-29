# -*- coding: utf-8 -*-
"""Cookie session for the Douyin Kodi add-on."""
from __future__ import annotations

import json
import os
import re

SESSION_NAME = "session.json"

LOGIN_KEYS = (
    "sessionid",
    "sessionid_ss",
    "sid_guard",
    "sid_tt",
    "uid_tt",
    "uid_tt_ss",
    "ssid_ucp_v1",
    "odin_tt",
    "passport_csrf_token",
    "ttwid",
    "msToken",
    "s_v_web_id",
)

COOKIE_HELP = """电脑或手机浏览器打开 https://www.douyin.com 并登录。
扫码、扫脸都在网页或抖音 App 里完成，Kodi 里只负责粘贴 Cookie。

复制 Cookie（推荐整段）：
1. 按 F12 打开开发者工具
2. 点「应用程序」或 Application
3. 左侧 Cookies → https://www.douyin.com
4. 找到 sessionid，复制它的值
   也可以在 Network 里点任意 douyin.com 请求，复制整段 Cookie

回到 Kodi：
· 首页「登录抖音账号」→ 粘贴 Cookie / sessionid
· 电视上输入长文本不方便时：把内容存成 U 盘 douyin_cookie.txt，选「从文本文件读取」

登录一次会保存在本机（Kodi 插件目录），下次打开不用再贴。
Cookie 相当于账号密码，不要发给任何人，也不要发到网上。
"""


def _from_json_cookies(data):
    cookies = {}
    if isinstance(data, dict):
        if isinstance(data.get("cookies"), dict):
            data = data["cookies"]
        elif isinstance(data.get("cookies"), list):
            data = data["cookies"]
        elif isinstance(data.get("cookie"), str):
            return parse_cookie_text(data["cookie"])
    if isinstance(data, dict):
        for key, value in data.items():
            if key in ("cookies", "user", "cookie") or value is None:
                continue
            if isinstance(value, dict) and "value" in value:
                cookies[str(key)] = str(value.get("value") or "")
            else:
                cookies[str(key)] = str(value)
        return {k: v for k, v in cookies.items() if k and v}
    if isinstance(data, list):
        for row in data:
            if not isinstance(row, dict):
                continue
            key = str(row.get("name") or row.get("key") or "").strip()
            value = str(row.get("value") or "").strip()
            if key and value:
                cookies[key] = value
        return cookies
    return {}


def parse_cookie_text(text):
    text = (text or "").strip()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return {}
    if text.lower().startswith("cookie:"):
        text = text.split(":", 1)[1].strip()
    if text[:1] in "{[":
        try:
            parsed = _from_json_cookies(json.loads(text))
            if parsed:
                return parsed
        except ValueError:
            pass
    cookies = {}
    compact = text.replace("\n", "; ")
    if "=" in compact:
        for part in re.split(r";\s*", compact):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"')
            if key and key.lower() not in ("path", "domain", "expires", "max-age", "secure", "httponly", "samesite"):
                cookies[key] = value
    elif re.fullmatch(r"[A-Za-z0-9._-]{16,128}", text.strip()):
        cookies["sessionid"] = text.strip()
        cookies["sessionid_ss"] = text.strip()
    if cookies.get("sessionid") and not cookies.get("sessionid_ss"):
        cookies["sessionid_ss"] = cookies["sessionid"]
    if cookies.get("sessionid_ss") and not cookies.get("sessionid"):
        cookies["sessionid"] = cookies["sessionid_ss"]
    return cookies


def has_session(cookies):
    sid = (cookies or {}).get("sessionid") or (cookies or {}).get("sessionid_ss") or (cookies or {}).get("sid_tt") or ""
    return len(str(sid)) >= 16


def session_path(profile_dir):
    return os.path.join(profile_dir, SESSION_NAME)


def load_session(profile_dir):
    path = session_path(profile_dir)
    if not os.path.isfile(path):
        return {"cookies": {}, "user": {}}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"cookies": {}, "user": {}}
    if not isinstance(data, dict):
        return {"cookies": {}, "user": {}}
    cookies = data.get("cookies") if isinstance(data.get("cookies"), dict) else {}
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    return {"cookies": cookies, "user": user}


def save_session(profile_dir, cookies, user=None):
    os.makedirs(profile_dir, exist_ok=True)
    payload = {
        "cookies": dict(cookies or {}),
        "user": dict(user or {}),
    }
    path = session_path(profile_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return payload


def clear_session(profile_dir):
    path = session_path(profile_dir)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def merge_cookies(base, extra):
    out = dict(base or {})
    for key, value in (extra or {}).items():
        if key and value:
            out[key] = value
    return out
