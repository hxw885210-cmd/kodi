# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

import xbmcaddon
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("path"))
sys.path.insert(0, os.path.join(ADDON_PATH, "resources", "lib"))

from plugin import get_params, go_plugin_home  # noqa: E402


def router():
    params = get_params()
    action = params.get("action") or ""
    if action == "go_home":
        go_plugin_home()
        return
    if action == "skip_next":
        from player import skip_next

        skip_next()
        return
    if action == "skip_prev":
        from player import skip_prev

        skip_prev()
        return
    if action in ("", "home"):
        from browse import home

        home()
        return
    if action == "feed":
        from browse import show_feed

        show_feed(params.get("sort") or "0", params.get("page") or "1")
        return
    if action == "feed_refresh":
        from browse import do_feed_refresh

        do_feed_refresh(params.get("sort") or "0")
        return
    if action == "follow_feed":
        from browse import show_follow_feed

        show_follow_feed()
        return
    if action == "hot":
        from browse import show_hot

        show_hot()
        return
    if action == "hot_videos":
        from browse import show_hot_videos

        show_hot_videos(params.get("word") or "", params.get("sentence_id") or "")
        return
    if action == "search":
        from browse import do_search

        do_search(
            params.get("q"),
            params.get("sort") or "0",
            params.get("pub") or "0",
            params.get("off") or "0",
            params.get("sid") or "",
        )
        return
    if action == "search_input":
        from browse import do_search_input

        do_search_input()
        return
    if action == "search_del":
        from browse import do_search_del

        do_search_del(params.get("q") or "")
        return
    if action == "search_clear":
        from browse import do_search_clear

        do_search_clear()
        return
    if action == "search_filter":
        from browse import do_search_filter

        do_search_filter(params.get("q") or "", params.get("sort") or "0", params.get("pub") or "0")
        return
    if action == "live":
        from live import live_home

        live_home()
        return
    if action == "live_list":
        from live import show_live_list

        show_live_list(params.get("partition") or "0", params.get("sort") or "0", params.get("refresh") or "")
        return
    if action == "live_refresh":
        from live import do_live_refresh

        do_live_refresh(params.get("partition") or "0", params.get("sort") or "0")
        return
    if action == "live_search":
        from live import do_live_search

        do_live_search(params.get("q"))
        return
    if action == "live_follow":
        from live import show_live_follow

        show_live_follow()
        return
    if action == "open":
        from player import do_open

        do_open()
        return
    if action == "play":
        from player import play_item

        play_item(
            params.get("aweme_id") or "",
            params.get("video_id") or "",
            params.get("title") or "",
            auto=params.get("auto") or "",
        )
        return
    if action == "play_live":
        from player import play_live

        play_live(params.get("room_id") or "", auto=params.get("auto") or "")
        return
    if action == "following":
        from mine import show_following

        show_following()
        return
    if action == "hosts":
        from mine import show_hosts

        show_hosts()
        return
    if action == "account_following":
        from mine import show_account_following

        show_account_following(params.get("off") or "0", params.get("min_time") or "0")
        return
    if action == "favorite":
        from mine import show_favorite

        show_favorite()
        return
    if action == "author":
        from mine import show_author

        show_author(params.get("sec_uid") or "", params.get("uid") or "", params.get("nickname") or "")
        return
    if action == "toggle_like":
        from mine import do_toggle_like

        do_toggle_like(params)
        return
    if action == "toggle_follow":
        from mine import do_toggle_follow

        do_toggle_follow(params)
        return
    if action == "login":
        from account import do_login

        do_login()
        return
    if action == "account":
        from account import show_account

        show_account()
        return
    if action == "check_login":
        from account import do_check_login

        do_check_login()
        return
    if action == "logout":
        from account import do_logout

        do_logout()
        return
    from browse import home

    home()


if __name__ == "__main__":
    try:
        router()
    except Exception as exc:
        try:
            import xbmc
            import xbmcgui
            from plugin import finish, notify

            xbmc.log("[plugin.video.douyin] %s" % exc, xbmc.LOGERROR)
            notify("出错了：%s" % exc, xbmcgui.NOTIFICATION_ERROR)
            try:
                finish(succeeded=False)
            except Exception:
                pass
        except Exception:
            pass

