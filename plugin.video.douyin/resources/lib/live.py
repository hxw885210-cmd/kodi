# -*- coding: utf-8 -*-
from __future__ import annotations

import xbmc
import xbmcgui
import xbmcplugin

from api import DouyinError
from auth import has_session
from library import load_named_list, save_named_list, save_queue, sort_videos
from plugin import PROFILE, add_dir, add_home_dir, add_live, client, finish, handle, notify, plugin_url, session


def live_home():
    xbmcplugin.setPluginCategory(handle(), "直播")
    add_home_dir()
    add_dir("搜索直播", {"action": "live_search"}, plot="按关键词找直播间")
    if has_session((session().get("cookies") or {})):
        add_dir("关注的直播", {"action": "live_follow"}, plot="正在开播的关注主播")
    add_dir("推荐", {"action": "live_list", "partition": "0", "sort": "0"}, plot="直播广场")
    from api import LIVE_CATEGORIES

    for name, partition in LIVE_CATEGORIES:
        if partition == "0":
            continue
        add_dir(name, {"action": "live_list", "partition": partition, "sort": "0"})
    finish("files")


def show_live_list(partition="0", sort="0", refresh=""):
    partition = str(partition or "0")
    sort = str(sort or "0")
    cache_name = "cache_live_%s.json" % partition
    title = "直播"
    for name, pid in client().live_categories():
        if pid == partition:
            title = "直播 · %s" % name
            break
    xbmcplugin.setPluginCategory(handle(), title)
    add_home_dir()
    if refresh:
        try:
            items = client().live_feed(partition)
        except DouyinError as exc:
            notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
            finish(succeeded=False)
            return
        save_named_list(PROFILE, cache_name, items)
        xbmc.executebuiltin("Container.Refresh")
        return
    items = load_named_list(PROFILE, cache_name)
    if not items:
        try:
            items = client().live_feed(partition)
        except DouyinError as exc:
            notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
            finish(succeeded=False)
            return
        save_named_list(PROFILE, cache_name, items)
    items = sort_videos(items, sort)
    if not items:
        notify("这个分类暂时没有直播")
        finish(succeeded=True)
        return
    _sort_bar("live_list", {"partition": partition}, sort)
    add_dir(
        "换一批",
        {"action": "live_refresh", "partition": partition, "sort": sort},
        is_folder=False,
        plot="重新拉取直播，不点就不会刷新",
    )
    save_queue(PROFILE, items, {"kind": "live", "partition": partition, "has_more": True})
    for item in items:
        add_live(item)
    finish("videos", cache=True)


def do_live_refresh(partition="0", sort="0"):
    partition = str(partition or "0")
    cache_name = "cache_live_%s.json" % partition
    try:
        items = client().live_feed(partition)
        save_named_list(PROFILE, cache_name, items)
        notify("已换一批直播")
    except DouyinError as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        return
    xbmc.executebuiltin("Container.Refresh")


def do_live_search(query=None):
    from browse import keyboard

    if not query:
        query = keyboard("搜索直播间 / 主播")
        if not query:
            finish(succeeded=False)
            return
        xbmc.executebuiltin(
            "Container.Update(%s,replace)" % plugin_url({"action": "live_search", "q": query})
        )
        return
    xbmcplugin.setPluginCategory(handle(), "直播搜索：%s" % query)
    add_home_dir()
    try:
        items = client().live_search(query)
    except DouyinError as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        finish(succeeded=False)
        return
    if not items:
        notify("没搜到直播间")
        finish(succeeded=True)
        return
    save_queue(PROFILE, items, {"kind": "live_search", "q": query})
    for item in items:
        add_live(item)
    finish("videos", cache=True)


def show_live_follow():
    xbmcplugin.setPluginCategory(handle(), "关注的直播")
    add_home_dir()
    try:
        items = client().live_follow()
    except DouyinError as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        finish(succeeded=False)
        return
    if not items:
        notify("关注的人暂时没有在播")
        finish(succeeded=True)
        return
    save_queue(PROFILE, items, {"kind": "live_follow"})
    for item in items:
        add_live(item)
    finish("videos", cache=True)


def _sort_bar(action, extra, current):
    extra = dict(extra or {})
    extra["action"] = action
    marks = (("0", "综合"), ("1", "人气"), ("2", "最新"))
    for key, label in marks:
        prefix = "· " if str(current or "0") == key else ""
        query = dict(extra)
        query["sort"] = key
        add_dir(prefix + label, query, plot="按%s排序" % label)
