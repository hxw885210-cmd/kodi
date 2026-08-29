# -*- coding: utf-8 -*-
"""Play the next queued Douyin video when the current one ends."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("path"))
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
SERVICE_PROP = "plugin.video.douyin.service"

sys.path.insert(0, os.path.join(ADDON_PATH, "resources", "lib"))
from keys import (  # noqa: E402
    PLAYING_PROP,
    SKIP_PROP,
    clear_douyin_playing,
    douyin_keymap_wanted,
    install_play_keymap,
    remove_play_keymap,
)
from library import clear_now_playing, load_now_playing, save_now_playing  # noqa: E402
from pager import extend_playing  # noqa: E402


def _play_url(item):
    if (item.get("kind") == "live") or item.get("room_id") or str(item.get("aweme_id") or "").startswith("live-"):
        query = {
            "action": "play_live",
            "room_id": item.get("room_id") or str(item.get("aweme_id") or "")[5:],
            "auto": "1",
        }
    else:
        query = {
            "action": "play",
            "aweme_id": item.get("aweme_id") or "",
            "video_id": item.get("video_id") or "",
            "title": item.get("title") or "",
            "auto": "1",
        }
    return "plugin://%s/?%s" % (ADDON_ID, urllib.parse.urlencode(query))


def _open(url):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "Player.Open",
        "params": {"item": {"file": url}},
    }
    xbmc.executeJSONRPC(json.dumps(payload, ensure_ascii=False))


class AutoNext(xbmc.Player):
    def __init__(self):
        super(AutoNext, self).__init__()
        self._ended = False
        self._last = 0.0
        self._keymap_on = False

    def onPlayBackStarted(self):
        self._sync_keymap()

    def onAVStarted(self):
        self._sync_keymap()

    def onPlayBackEnded(self):
        self._ended = True
        now = time.time()
        if now - self._last < 1.5:
            return
        self._last = now
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        if playlist.size() > max(playlist.getposition(), 0) + 1:
            return
        xbmc.sleep(250)
        self._play_next()

    def onPlayBackStopped(self):
        skipping = xbmc.getInfoLabel("Window(10000).Property(%s)" % SKIP_PROP) == "1"
        if skipping:
            xbmcgui.Window(10000).clearProperty(SKIP_PROP)
            return
        clear_douyin_playing()
        self._sync_keymap()
        if self._ended:
            self._ended = False
            return
        clear_now_playing(PROFILE)

    def onPlayBackError(self):
        self._ended = False
        self._play_next()

    def _sync_keymap(self):
        want = douyin_keymap_wanted()
        if want and not self._keymap_on:
            install_play_keymap()
            self._keymap_on = True
        elif not want and self._keymap_on:
            remove_play_keymap()
            self._keymap_on = False
        elif not want:
            remove_play_keymap()
            self._keymap_on = False

    def _play_next(self):
        state = load_now_playing(PROFILE)
        if not state.get("active"):
            return
        items = state.get("items") or []
        try:
            idx = int(state.get("index") or 0) + 1
        except (TypeError, ValueError):
            idx = 1
        if idx >= len(items):
            try:
                from plugin import client

                xbmcgui.Dialog().notification("抖音", "正在加载下一页", xbmcgui.NOTIFICATION_INFO, 2000)
                items, idx, _source = extend_playing(PROFILE, state, client())
            except Exception:
                clear_now_playing(PROFILE)
                return
            if idx < 0 or idx >= len(items):
                clear_now_playing(PROFILE)
                return
        nxt = items[idx]
        if not nxt.get("aweme_id"):
            clear_now_playing(PROFILE)
            return
        save_now_playing(PROFILE, items, idx)
        _open(_play_url(nxt))


if __name__ == "__main__":
    xbmcgui.Window(10000).setProperty(SERVICE_PROP, "1")
    xbmcgui.Window(10000).clearProperty(SKIP_PROP)
    if xbmcgui.Window(10000).getProperty(PLAYING_PROP) != "1":
        remove_play_keymap()
    player = AutoNext()
    player._sync_keymap()
    monitor = xbmc.Monitor()
    try:
        while not monitor.abortRequested():
            monitor.waitForAbort(1)
            player._sync_keymap()
    finally:
        clear_douyin_playing()
        remove_play_keymap()
        xbmcgui.Window(10000).clearProperty(SERVICE_PROP)
