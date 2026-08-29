# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import urllib.parse

import xbmc
import xbmcgui
import xbmcplugin

from api import WEB_UA, DouyinError
from keys import douyin_keymap_wanted, install_play_keymap, mark_douyin_playing, remove_play_keymap
from library import (
    load_now_playing,
    load_queue,
    load_queue_source,
    queue_index,
    save_now_playing,
)
from pager import extend_playing
from plugin import FANART, ICON, PLAY_UA, PROFILE, client, finish, handle, notify, plugin_url


def kodi_play_path(url):
    headers = urllib.parse.urlencode({"User-Agent": PLAY_UA, "Referer": "https://www.douyin.com/"})
    return url + "|" + headers


def play_list_url(item, auto=False):
    if (item.get("kind") == "live") or item.get("room_id") or str(item.get("aweme_id") or "").startswith("live-"):
        query = {
            "action": "play_live",
            "room_id": item.get("room_id") or str(item.get("aweme_id") or "")[5:],
        }
    else:
        query = {
            "action": "play",
            "aweme_id": item.get("aweme_id") or "",
            "video_id": item.get("video_id") or "",
            "title": item.get("title") or "",
        }
    if auto:
        query["auto"] = "1"
    return plugin_url(query)


def play_item(aweme_id, video_id="", title="", auto=""):
    try:
        path = client().play_url(video_id=video_id, aweme_id=aweme_id)
    except DouyinError as exc:
        xbmcplugin.setResolvedUrl(handle(), False, xbmcgui.ListItem())
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        return
    li = xbmcgui.ListItem(label=title or "抖音视频", path=kodi_play_path(path), offscreen=True)
    li.setArt({"icon": ICON, "thumb": ICON, "fanart": FANART})
    li.setInfo("video", {"title": title or "抖音视频", "mediatype": "video"})
    li.setMimeType("video/mp4")
    li.setContentLookup(False)
    li.setProperty("IsPlayable", "true")
    xbmcplugin.setResolvedUrl(handle(), True, li)
    mark_douyin_playing()
    install_play_keymap()
    _arm_autonext(aweme_id, auto=bool(auto))


def _arm_autonext(aweme_id, auto=False):
    source = None
    if auto:
        state = load_now_playing(PROFILE)
        items = state.get("items") or []
        source = state.get("source")
    else:
        items = load_queue(PROFILE)
        source = load_queue_source(PROFILE)
    idx = queue_index(items, aweme_id)
    if idx < 0:
        return
    save_now_playing(PROFILE, items, idx, source)
    _playlist_queue(items, idx)


def _playlist_queue(items, idx):
    playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
    if playlist.size() > 1:
        return
    for item in items[idx + 1 :]:
        url = play_list_url(item, auto=True)
        nli = xbmcgui.ListItem(label=item.get("title") or "抖音视频", path=url, offscreen=True)
        nli.setProperty("IsPlayable", "true")
        nli.setInfo("video", {"title": item.get("title") or "抖音视频", "mediatype": "video"})
        nli.setMimeType("video/mp4")
        playlist.add(url, nli)


def play_live(room_id, auto=""):
    room_id = str(room_id or "")
    item = None
    for row in load_queue(PROFILE) + (load_now_playing(PROFILE).get("items") or []):
        if str(row.get("room_id") or "") == room_id or str(row.get("aweme_id") or "") == "live-%s" % room_id:
            item = row
            break
    try:
        path = client().live_play_url(room_id, item=item)
    except DouyinError as exc:
        xbmcplugin.setResolvedUrl(handle(), False, xbmcgui.ListItem())
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        return
    headers = urllib.parse.urlencode({"User-Agent": WEB_UA, "Referer": "https://live.douyin.com/"})
    play_path = path + "|" + headers
    title = (item or {}).get("title") or "抖音直播"
    li = xbmcgui.ListItem(label=title, path=play_path, offscreen=True)
    li.setArt({"icon": ICON, "thumb": ICON, "fanart": FANART})
    li.setInfo("video", {"title": title, "mediatype": "video"})
    if ".m3u8" in path:
        li.setMimeType("application/vnd.apple.mpegurl")
    else:
        li.setMimeType("video/x-flv")
    li.setContentLookup(False)
    li.setProperty("IsPlayable", "true")
    xbmcplugin.setResolvedUrl(handle(), True, li)
    mark_douyin_playing()
    install_play_keymap()
    _arm_autonext("live-%s" % room_id, auto=bool(auto))


def do_open():
    from browse import keyboard

    text = keyboard("粘贴抖音分享链接或口令")
    if text is None:
        finish(succeeded=False)
        return
    if not text:
        notify("没有输入内容")
        finish(succeeded=False)
        return
    try:
        item = client().from_share(text)
    except DouyinError as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        finish(succeeded=False)
        return
    play_item(item.get("aweme_id") or "", item.get("video_id") or "", item.get("title") or "")


def skip_next():
    _skip(1)


def skip_prev():
    _skip(-1)


def _skip(delta):
    if not douyin_keymap_wanted():
        remove_play_keymap()
        return
    xbmcgui.Window(10000).setProperty("plugin.video.douyin.skipping", "1")
    state = load_now_playing(PROFILE)
    items = state.get("items") if state.get("active") else None
    if not items:
        items = load_queue(PROFILE)
        idx = 0
    else:
        try:
            idx = int(state.get("index") or 0)
        except (TypeError, ValueError):
            idx = 0
    nxt = idx + int(delta)
    if nxt < 0:
        xbmcgui.Window(10000).clearProperty("plugin.video.douyin.skipping")
        notify("已经是第一条")
        return
    if not items or nxt >= len(items):
        if int(delta) <= 0:
            xbmcgui.Window(10000).clearProperty("plugin.video.douyin.skipping")
            notify("已经是第一条")
            return
        notify("正在加载下一页")
        try:
            items, nxt, _source = extend_playing(
                PROFILE,
                {
                    "items": items or [],
                    "source": (state or {}).get("source") or load_queue_source(PROFILE),
                },
                client(),
            )
        except Exception as exc:  # noqa: BLE001
            xbmcgui.Window(10000).clearProperty("plugin.video.douyin.skipping")
            notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
            return
        if nxt < 0:
            xbmcgui.Window(10000).clearProperty("plugin.video.douyin.skipping")
            notify("没有下一条了")
            return
    save_now_playing(PROFILE, items, nxt)
    url = play_list_url(items[nxt], auto=True)
    if not url.startswith("plugin://"):
        url = "plugin://plugin.video.douyin/?" + url.split("?", 1)[-1]
    xbmc.executeJSONRPC(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "Player.Open",
                "params": {"item": {"file": url}},
            },
            ensure_ascii=False,
        )
    )
