# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import xbmc
import xbmcgui
import xbmcplugin

from api import DouyinError
from auth import has_session
from library import (
    add_search_history,
    clear_search_history,
    filter_by_publish,
    load_search_cache,
    remember,
    remove_search_history,
    save_named_list,
    save_queue,
    save_search_cache,
    search_filter_choices,
    search_filter_label,
    search_history,
    sort_videos,
)
from pager import load_feed_page
from plugin import (
    handle,
    PROFILE,
    add_dir,
    add_home_dir,
    add_live,
    add_video,
    client,
    finish,
    notify,
    plugin_url,
    session,
)


def list_videos(title, loader, empty_msg, add=True, source=None):
    xbmcplugin.setPluginCategory(handle(), title)
    add_home_dir()
    try:
        items = loader()
    except DouyinError as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        finish(succeeded=False)
        return
    if not items:
        notify(empty_msg)
        finish(succeeded=True)
        return
    remember(PROFILE, items)
    save_queue(PROFILE, items, source)
    if add:
        for item in items:
            add_video(item)
    return items


def home():
    add_home_dir()
    sess = session()
    user = sess.get("user") or {}
    if has_session(sess.get("cookies")):
        nick = user.get("nickname") or "已登录"
        add_dir("已登录 · %s" % nick, {"action": "account"}, plot="检查登录、重新登录或退出")
        add_dir("关注动态", {"action": "follow_feed"}, plot="关注的人更新的视频（需要有效 Cookie）")
        add_dir("账号关注", {"action": "account_following"}, plot="和抖音账号里的关注同步")
    else:
        add_dir("登录抖音账号", {"action": "login"}, plot="粘贴 Cookie，登录一次会记住")
    add_dir("推荐", {"action": "feed", "sort": "0"}, plot="刷推荐。返回不会自动换一批")
    add_dir("直播", {"action": "live"}, plot="直播广场、分类、搜索直播间")
    add_dir("关注的主播", {"action": "hosts"}, plot="长按直播点关注的主播，可进主页看作品")
    add_dir("搜索", {"action": "search"}, plot="搜视频、用户。点筛选可选排序和发布时间，需登录 Cookie")
    add_dir("我的关注", {"action": "following"}, plot="只保存在这台 Kodi 上，长按视频点的关注")
    add_dir("我喜欢", {"action": "favorite"}, plot="登录后看账号喜欢；未登录则用本机喜欢")
    add_dir("热搜榜", {"action": "hot"}, plot="今日热搜")
    add_dir("打开链接", {"action": "open"}, plot="粘贴 v.douyin.com 链接播放")
    finish("files")


def show_feed(sort="0", page="1"):
    sort = str(sort or "0")
    try:
        page = max(int(page or 1), 1)
    except (TypeError, ValueError):
        page = 1
    xbmcplugin.setPluginCategory(handle(), "推荐" if page == 1 else "推荐 · 第%s页" % page)
    add_home_dir()
    try:
        items = load_feed_page(PROFILE, client(), page)
    except DouyinError as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        finish(succeeded=False)
        return
    if not items:
        notify("暂时没有拉到推荐，点「换一批」或「下一页」试试")
        finish(succeeded=True)
        return
    add_dir(
        "换一批",
        {"action": "feed_refresh", "sort": sort},
        is_folder=False,
        plot="只有点这里才会重新拉推荐",
    )
    remember(PROFILE, items)
    save_queue(PROFILE, items, {"kind": "feed", "page": page, "has_more": True})
    for item in items:
        add_video(item)
    if page > 1:
        add_dir("上一页", {"action": "feed", "sort": sort, "page": str(page - 1)})
    add_dir("下一页", {"action": "feed", "sort": sort, "page": str(page + 1)}, plot="再刷一页推荐")
    finish(cache=True)


def do_feed_refresh(sort="0"):
    try:
        items = client().feed(pull_type=0)
        save_named_list(PROFILE, "cache_feed_1.json", items)
        save_named_list(PROFILE, "cache_feed.json", items)
        for prev in range(2, 40):
            path = os.path.join(PROFILE, "cache_feed_%s.json" % prev)
            if os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        notify("已换一批")
    except DouyinError as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        return
    xbmc.executebuiltin("Container.Refresh")


def show_follow_feed():
    items = list_videos(
        "关注动态",
        lambda: client().follow_feed(),
        "暂时没有关注动态。先登录，或确认 Cookie 仍有效",
        add=False,
        source={"kind": "follow", "has_more": True},
    )
    if items:
        add_dir("换一批", {"action": "follow_feed", "t": str(xbmc.getInfoLabel("System.Time"))}, plot="再刷一页")
        for item in items:
            add_video(item)
        finish(cache=False)


def show_hot():
    xbmcplugin.setPluginCategory(handle(), "热搜榜")
    add_home_dir()
    try:
        words = client().hot_words()
    except DouyinError as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        finish(succeeded=False)
        return
    labels = {0: "", 1: "新", 3: "热"}
    for word in words:
        tag = labels.get(word.get("label") or 0, "")
        prefix = "%02d. " % word["rank"]
        if tag:
            prefix += "[%s] " % tag
        add_dir(
            prefix + word["word"],
            {"action": "hot_videos", "word": word["word"], "sentence_id": word.get("sentence_id") or ""},
            icon=word.get("cover") or "",
            plot="热度 %s" % (word.get("hot_value") or "-"),
        )
    finish("files")


def show_hot_videos(word, sentence_id=""):
    items = list_videos(
        word or "热搜视频",
        lambda: client().hot_videos(word, sentence_id),
        "这个热搜暂时没有可播视频",
        source={"kind": "hot", "word": word or "", "sentence_id": sentence_id or ""},
    )
    if items:
        finish(cache=False)


def keyboard(heading, default=""):
    kb = xbmc.Keyboard(default, heading, False)
    kb.doModal()
    if not kb.isConfirmed():
        return None
    return (kb.getText() or "").strip()


def show_search_hub():
    xbmcplugin.setPluginCategory(handle(), "搜索")
    add_home_dir()
    add_dir("输入关键词搜索", {"action": "search_input"}, plot="搜视频、用户，或粘贴分享链接")
    rows = search_history(PROFILE)
    if rows:
        add_dir("—— 搜索历史 ——", {"action": "search"}, plot="长按可删除其中一条")
        for query in rows:
            add_dir(
                query,
                {"action": "search", "q": query, "sort": "0", "pub": "0", "off": "0"},
                plot="点进去按这个词搜索",
                menus=[
                    (
                        "删除这条历史",
                        "RunPlugin(%s)" % plugin_url({"action": "search_del", "q": query}),
                    )
                ],
            )
        add_dir("清空全部搜索历史", {"action": "search_clear"}, is_folder=False)
    finish("files")


def do_search_input():
    query = keyboard("搜索抖音 / 粘贴分享链接")
    if query is None:
        finish(succeeded=False)
        return
    if not query:
        notify("请输入关键词或链接")
        finish(succeeded=False)
        return
    add_search_history(PROFILE, query)
    xbmc.executebuiltin(
        "Container.Update(%s,replace)"
        % plugin_url({"action": "search", "q": query, "sort": "0", "pub": "0", "off": "0"})
    )


def do_search(query=None, sort="0", pub="0", offset="0", search_id=""):
    query = (query or "").strip()
    if not query:
        show_search_hub()
        return
    sort = str(sort or "0")
    pub = str(pub or "0")
    try:
        offset = int(offset or 0)
    except (TypeError, ValueError):
        offset = 0
    search_id = str(search_id or "")
    xbmcplugin.setPluginCategory(handle(), "搜索：%s" % query if offset <= 0 else "搜索：%s · 续" % query)
    add_home_dir()
    cached = load_search_cache(PROFILE, query, sort, pub, offset)
    if cached is None:
        try:
            items, has_more, next_offset, next_sid = client().search_page(
                query, sort_type=sort, publish_time=pub, offset=offset, search_id=search_id
            )
        except DouyinError as exc:
            notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
            finish(succeeded=False)
            return
        except Exception as exc:
            notify("搜索出错了：%s" % exc, xbmcgui.NOTIFICATION_ERROR)
            finish(succeeded=False)
            return
        save_search_cache(
            PROFILE,
            query,
            sort,
            pub,
            items,
            offset=offset,
            has_more=has_more,
            search_id=next_sid,
            next_offset=next_offset,
        )
    else:
        items = cached.get("items") or []
        has_more = bool(cached.get("has_more"))
        next_offset = int(cached.get("next_offset") or (offset + len(items)))
        next_sid = cached.get("search_id") or search_id
    special = [row for row in items if (row or {}).get("kind") in ("user", "live") or (row or {}).get("room_id")]
    videos = [row for row in items if row not in special]
    if sort not in ("0", ""):
        videos = sort_videos(videos, sort)
    videos = filter_by_publish(videos, pub)
    items = special + videos
    if not items:
        notify("这一页没有视频了" if offset else "没搜到视频，换个词、改筛选，或确认已登录")
        _search_filter_item(query, sort, pub)
        if offset > 0:
            add_dir("上一页", {"action": "search", "q": query, "sort": sort, "pub": pub, "off": "0"})
        finish(succeeded=True)
        return
    _search_filter_item(query, sort, pub)
    playable = [row for row in items if (row or {}).get("kind") != "user" and ((row or {}).get("aweme_id") or (row or {}).get("room_id"))]
    remember(PROFILE, playable)
    save_queue(
        PROFILE,
        playable,
        {
            "kind": "search",
            "q": query,
            "sort": sort,
            "pub": pub,
            "offset": offset,
            "has_more": bool(has_more),
            "next_offset": int(next_offset if next_offset > offset else offset + len(videos)),
            "sid": next_sid or "",
        },
    )
    for item in items:
        kind = (item or {}).get("kind") or ""
        if kind == "user":
            add_dir(
                item.get("title") or item.get("author") or "抖音用户",
                {
                    "action": "author",
                    "sec_uid": item.get("sec_uid") or "",
                    "uid": item.get("uid") or "",
                    "nickname": item.get("author") or item.get("nickname") or "",
                },
                icon=item.get("avatar") or item.get("cover") or "",
                plot=item.get("plot") or "进入作者主页看作品",
            )
        elif kind == "live" or item.get("room_id"):
            add_live(item)
        else:
            add_video(item)
    if offset > 0:
        prev = max(offset - max(len(videos), int(client().count or 20)), 0)
        add_dir("上一页", {"action": "search", "q": query, "sort": sort, "pub": pub, "off": str(prev), "sid": search_id})
    if has_more:
        add_dir(
            "下一页",
            {
                "action": "search",
                "q": query,
                "sort": sort,
                "pub": pub,
                "off": str(next_offset if next_offset > offset else offset + len(videos)),
                "sid": next_sid or "",
            },
            plot="继续往后翻",
        )
    finish(cache=True)


def do_search_del(query):
    remove_search_history(PROFILE, query)
    notify("已删除这条搜索")
    xbmc.executebuiltin("Container.Refresh")


def do_search_clear():
    if not xbmcgui.Dialog().yesno("抖音", "清空全部搜索历史？"):
        return
    clear_search_history(PROFILE)
    notify("已清空搜索历史")
    xbmc.executebuiltin("Container.Refresh")


def _search_filter_item(query, sort, pub):
    add_dir(
        search_filter_label(sort, pub),
        {"action": "search_filter", "q": query, "sort": sort, "pub": pub},
        is_folder=False,
        plot="点这里弹出列表，一次选排序和发布时间",
    )


def do_search_filter(query="", sort="0", pub="0"):
    query = (query or "").strip()
    if not query:
        return
    choices = search_filter_choices()
    labels = [row[2] for row in choices]
    current = 0
    for i, (sort_key, pub_key, _label) in enumerate(choices):
        if sort_key == str(sort or "0") and pub_key == str(pub or "0"):
            current = i
            break
    dialog = xbmcgui.Dialog()
    try:
        idx = dialog.select("选择排序和发布时间", labels, 0, current)
    except TypeError:
        idx = dialog.select("选择排序和发布时间", labels)
    if idx < 0 or idx >= len(choices):
        return
    sort_key, pub_key, _label = choices[idx]
    xbmc.executebuiltin(
        "Container.Update(%s,replace)"
        % plugin_url({"action": "search", "q": query, "sort": sort_key, "pub": pub_key, "off": "0"})
    )
