# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from api import DouyinAPI
from auth import has_session, load_session, parse_cookie_text, save_session
from library import is_followed, is_liked

ADDON = xbmcaddon.Addon()
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("path"))
def handle():
    return int(sys.argv[1])


def base_url():
    return sys.argv[0]
ICON = os.path.join(ADDON_PATH, "resources", "media", "icon.png")
FANART = os.path.join(ADDON_PATH, "resources", "media", "fanart.png")
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
PLAY_UA = (
    "com.ss.android.ugc.aweme/190500 "
    "(Linux; U; Android 13; zh_CN; Pixel 7; Build/TQ3A; Cronet/58.0.2991.0)"
)


def ensure_device_id():
    device_id = ADDON.getSetting("device_id")
    if not device_id:
        import random

        device_id = str(random.randint(10**14, 10**15 - 1))
        ADDON.setSetting("device_id", device_id)
    return device_id


def session():
    if not os.path.isdir(PROFILE):
        xbmcvfs.mkdirs(PROFILE)
    sess = load_session(PROFILE)
    raw = ADDON.getSetting("cookie") or ""
    pasted = parse_cookie_text(raw)
    saved = dict(sess.get("cookies") or {})
    if has_session(pasted):
        old = saved.get("sessionid") or saved.get("sessionid_ss") or ""
        new = pasted.get("sessionid") or pasted.get("sessionid_ss") or ""
        if new and new != old:
            saved.update(pasted)
            return {"cookies": saved, "user": sess.get("user") or {}}
    if has_session(saved):
        return {"cookies": saved, "user": sess.get("user") or {}}
    if pasted:
        return {"cookies": pasted, "user": sess.get("user") or {}}
    return {"cookies": saved, "user": sess.get("user") or {}}


def persist_session(api, user=None):
    cookies = dict(getattr(api, "cookies", None) or session().get("cookies") or {})
    prev = session().get("user") or {}
    if user:
        prev = dict(user)
    save_session(PROFILE, cookies, prev)
    return {"cookies": cookies, "user": prev}


def client(cookies=None):
    quality = ADDON.getSetting("quality") or "best"
    try:
        count = int(ADDON.getSetting("count") or "20")
    except ValueError:
        count = 20
    sess = session()
    jar = dict(cookies if cookies is not None else (sess.get("cookies") or {}))
    api = DouyinAPI(
        device_id=ensure_device_id(),
        count=count,
        quality=quality,
        cookies=jar,
    )
    return api


def plugin_url(query):
    return base_url() + "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})


def get_params():
    raw = sys.argv[2][1:] if len(sys.argv) > 2 else ""
    parsed = urllib.parse.parse_qs(raw)
    return {k: v[0] for k, v in parsed.items()}


def notify(message, icon=xbmcgui.NOTIFICATION_INFO, ms=4000):
    xbmcgui.Dialog().notification("抖音", message, icon, ms)


def go_plugin_home():
    xbmc.executebuiltin("Container.Update(%s,replace)" % base_url())


def add_home_dir():
    add_dir(
        "回首页",
        {"action": "go_home"},
        is_folder=False,
        plot="回到插件首页；再按返回键就退出到 Kodi",
    )


def add_dir(title, query, icon="", plot="", is_folder=True, menus=None):
    li = xbmcgui.ListItem(label=title, offscreen=True)
    if icon:
        li.setArt({"icon": icon, "thumb": icon})
    else:
        li.setArt({"icon": "DefaultFolder.png", "thumb": "DefaultFolder.png"})
    info = {"title": title}
    if plot:
        info["plot"] = plot
    li.setInfo("video", info)
    if menus:
        li.addContextMenuItems(list(menus), replaceItems=False)
    xbmcplugin.addDirectoryItem(handle(), plugin_url(query), li, is_folder)


def finish(content="videos", succeeded=True, cache=False):
    xbmcplugin.setContent(handle(), content)
    try:
        xbmcplugin.addSortMethod(handle(), xbmcplugin.SORT_METHOD_UNSORTED)
    except Exception:
        pass
    xbmcplugin.endOfDirectory(handle(), succeeded=succeeded, cacheToDisc=cache, updateListing=False)


def add_video(item):
    li = xbmcgui.ListItem(label=item["title"], offscreen=True)
    art = item.get("cover") or ICON
    li.setArt({"icon": art, "thumb": art})
    li.setInfo(
        "video",
        {
            "title": item["title"],
            "plot": item.get("plot") or item["title"],
            "duration": int(item.get("duration") or 0),
            "mediatype": "video",
        },
    )
    li.setProperty("IsPlayable", "true")
    li.setProperty("mimeType", "video/mp4")
    url = plugin_url(
        {
            "action": "play",
            "aweme_id": item.get("aweme_id") or "",
            "video_id": item.get("video_id") or "",
            "title": item.get("title") or "",
        }
    )
    menus = []
    if item.get("sec_uid"):
        menus.append(
            (
                "进入作者主页",
                "Container.Update(%s)"
                % plugin_url(
                    {
                        "action": "author",
                        "sec_uid": item.get("sec_uid") or "",
                        "uid": item.get("uid") or "",
                        "nickname": item.get("author") or "",
                    }
                ),
            )
        )
        followed = is_followed(PROFILE, item.get("sec_uid"))
        menus.append(
            (
                "取消关注" if followed else "关注作者",
                "RunPlugin(%s)"
                % plugin_url(
                    {
                        "action": "toggle_follow",
                        "sec_uid": item.get("sec_uid") or "",
                        "uid": item.get("uid") or "",
                        "nickname": item.get("author") or "",
                        "avatar": item.get("avatar") or "",
                    }
                ),
            )
        )
    liked = is_liked(PROFILE, item.get("aweme_id"))
    menus.append(
        (
            "取消喜欢" if liked else "喜欢此视频",
            "RunPlugin(%s)"
            % plugin_url(
                {
                    "action": "toggle_like",
                    "aweme_id": item.get("aweme_id") or "",
                    "video_id": item.get("video_id") or "",
                    "title": item.get("title") or "",
                    "author": item.get("author") or "",
                    "sec_uid": item.get("sec_uid") or "",
                    "uid": item.get("uid") or "",
                    "cover": item.get("cover") or "",
                    "avatar": item.get("avatar") or "",
                    "duration": str(item.get("duration") or 0),
                }
            ),
        )
    )
    if menus:
        li.addContextMenuItems(menus, replaceItems=False)
    xbmcplugin.addDirectoryItem(handle(), url, li, False)


def add_live(item):
    li = xbmcgui.ListItem(label=item["title"], offscreen=True)
    art = item.get("cover") or item.get("avatar") or ICON
    li.setArt({"icon": art, "thumb": art, "poster": art})
    li.setInfo(
        "video",
        {
            "title": item["title"],
            "plot": item.get("plot") or item["title"],
            "mediatype": "video",
        },
    )
    li.setProperty("IsPlayable", "true")
    url = plugin_url({"action": "play_live", "room_id": item.get("room_id") or ""})
    menus = []
    if item.get("sec_uid") or item.get("uid"):
        menus.append(
            (
                "进入主播首页",
                "Container.Update(%s)"
                % plugin_url(
                    {
                        "action": "author",
                        "sec_uid": item.get("sec_uid") or "",
                        "uid": item.get("uid") or "",
                        "nickname": item.get("author") or "",
                    }
                ),
            )
        )
    if item.get("sec_uid"):
        followed = is_followed(PROFILE, item.get("sec_uid"))
        menus.append(
            (
                "取消关注" if followed else "关注主播",
                "RunPlugin(%s)"
                % plugin_url(
                    {
                        "action": "toggle_follow",
                        "sec_uid": item.get("sec_uid") or "",
                        "uid": item.get("uid") or "",
                        "nickname": item.get("author") or "",
                        "avatar": item.get("avatar") or "",
                    }
                ),
            )
        )
    if menus:
        li.addContextMenuItems(menus, replaceItems=False)
    xbmcplugin.addDirectoryItem(handle(), url, li, False)
