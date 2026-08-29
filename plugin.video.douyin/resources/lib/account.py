# -*- coding: utf-8 -*-
"""Cookie login / logout for the Douyin add-on."""
from __future__ import annotations

import os

import xbmc
import xbmcgui
import xbmcvfs

from api import DouyinError
from auth import COOKIE_HELP, clear_session, has_session, parse_cookie_text, save_session
from plugin import ADDON, PROFILE, add_dir, add_home_dir, client, finish, notify, persist_session, session


def show_account():
    add_home_dir()
    sess = session()
    user = sess.get("user") or {}
    if has_session(sess.get("cookies")):
        nick = user.get("nickname") or "已登录"
        uid = user.get("uid") or ""
        plot = "UID %s" % uid if uid else "登录已保存在本机"
        add_dir("当前账号 · %s" % nick, {"action": "account"}, plot=plot)
        add_dir("检查登录状态", {"action": "check_login"}, plot="向抖音确认 Cookie 是否还有效")
        add_dir("重新登录", {"action": "login"}, plot="粘贴新的 Cookie")
        add_dir("退出登录", {"action": "logout"}, plot="删除本机保存的 Cookie")
    else:
        add_dir("登录抖音账号", {"action": "login"}, plot="粘贴 Cookie，登录一次会记住")
    finish("files")


def do_login():
    choice = xbmcgui.Dialog().select(
        "登录抖音",
        ["查看说明", "粘贴 Cookie / sessionid", "从文本文件读取", "使用插件设置里的 Cookie"],
    )
    if choice < 0:
        finish(succeeded=False)
        return
    if choice == 0:
        xbmcgui.Dialog().textviewer("怎么登录", COOKIE_HELP)
        finish(succeeded=True)
        return
    raw = ""
    if choice == 1:
        raw = _keyboard("粘贴 sessionid 或整段 Cookie")
        if raw is None:
            finish(succeeded=False)
            return
    elif choice == 2:
        raw = _read_cookie_file()
        if raw is None:
            finish(succeeded=False)
            return
    else:
        raw = ADDON.getSetting("cookie") or ""
        if not raw.strip():
            notify("插件设置里还没有 Cookie")
            finish(succeeded=False)
            return
    cookies = parse_cookie_text(raw)
    if not has_session(cookies):
        notify("没有找到 sessionid。请复制登录后的 Cookie", xbmcgui.NOTIFICATION_ERROR)
        finish(succeeded=False)
        return
    sess = session()
    merged = dict(sess.get("cookies") or {})
    merged.update(cookies)
    try:
        api = client(cookies=merged)
        user = api.me()
    except DouyinError as exc:
        save_session(PROFILE, merged, sess.get("user") or {})
        ADDON.setSetting("cookie", raw.strip() if len(raw.strip()) < 4000 else "")
        notify("已保存 Cookie，但校验失败：%s" % exc, xbmcgui.NOTIFICATION_WARNING, ms=6000)
        _refresh()
        finish(succeeded=True)
        return
    persist_session(api, user)
    ADDON.setSetting("cookie", "")
    notify("登录成功 · %s" % (user.get("nickname") or "抖音用户"))
    _refresh()
    finish(succeeded=True)


def do_check_login():
    sess = session()
    if not has_session(sess.get("cookies")):
        notify("还没有登录")
        finish(succeeded=True)
        return
    try:
        api = client()
        user = api.me()
        persist_session(api, user)
        notify("登录有效 · %s" % (user.get("nickname") or "抖音用户"))
    except DouyinError as exc:
        notify("登录已失效：%s" % exc, xbmcgui.NOTIFICATION_ERROR, ms=6000)
    finish(succeeded=True)


def do_logout():
    if not xbmcgui.Dialog().yesno("抖音", "退出登录并删除本机保存的 Cookie？"):
        finish(succeeded=False)
        return
    clear_session(PROFILE)
    ADDON.setSetting("cookie", "")
    notify("已退出登录")
    _refresh()
    finish(succeeded=True)


def _keyboard(heading):
    kb = xbmc.Keyboard("", heading, False)
    kb.doModal()
    if not kb.isConfirmed():
        return None
    return (kb.getText() or "").strip()


def _read_cookie_file():
    path = xbmcgui.Dialog().browse(1, "选择 douyin_cookie.txt", "files", ".txt|.json", False, False, "")
    if not path:
        return None
    raw = ""
    try:
        if xbmcvfs.exists(path):
            fh = xbmcvfs.File(path)
            try:
                raw = fh.read()
            finally:
                fh.close()
    except Exception:
        raw = ""
    if not raw and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            raw = ""
    if not (raw or "").strip():
        notify("文件是空的，或读不到这个路径", xbmcgui.NOTIFICATION_ERROR)
        return ""
    return raw


def _refresh():
    xbmc.executebuiltin("Container.Refresh")
