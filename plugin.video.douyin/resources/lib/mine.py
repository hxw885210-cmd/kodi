# -*- coding: utf-8 -*-
from __future__ import annotations

import xbmcgui
import xbmcplugin

from api import DouyinError
from auth import has_session
from library import follows, likes, remember, save_queue, toggle_follow, toggle_like, videos_by_author
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
    persist_session,
    session,
)


def show_following():
    rows = follows(PROFILE)
    xbmcplugin.setPluginCategory(handle(), "我的关注")
    add_home_dir()
    if not rows:
        notify("插件里还没有关注。看视频时长按 OK → 关注作者")
        finish(succeeded=True)
        return
    for row in rows:
        add_dir(
            row.get("nickname") or "抖音用户",
            {
                "action": "author",
                "sec_uid": row.get("sec_uid") or "",
                "uid": row.get("uid") or "",
                "nickname": row.get("nickname") or "",
            },
            icon=row.get("avatar") or "",
            plot="点进去看他的视频（插件内关注）",
        )
    finish("files")


def show_hosts():
    rows = follows(PROFILE)
    xbmcplugin.setPluginCategory(handle(), "关注的主播")
    add_home_dir()
    if not rows:
        notify("还没有关注的主播。看直播时长按 OK → 关注主播")
        finish("files")
        return
    live_by_sec = {}
    sess = session()
    if has_session(sess.get("cookies") or {}):
        try:
            for item in client().live_follow() or []:
                sec = str((item or {}).get("sec_uid") or "")
                if sec:
                    live_by_sec[sec] = item
        except DouyinError:
            live_by_sec = {}
    for row in rows:
        sec = str(row.get("sec_uid") or "")
        live = live_by_sec.get(sec)
        if live:
            add_live(live)
            continue
        add_dir(
            row.get("nickname") or "抖音用户",
            {
                "action": "author",
                "sec_uid": sec,
                "uid": row.get("uid") or "",
                "nickname": row.get("nickname") or "",
            },
            icon=row.get("avatar") or "",
            plot="点进去看作品。正在直播时这里会显示直播间",
        )
    finish("files")


def show_account_following(offset="0", min_time="0"):
    xbmcplugin.setPluginCategory(handle(), "账号关注")
    add_home_dir()
    sess = session()
    user = sess.get("user") or {}
    if not has_session(sess.get("cookies")):
        notify("先登录才能同步抖音账号的关注")
        finish(succeeded=True)
        return
    try:
        offset_i = int(offset or 0)
    except (TypeError, ValueError):
        offset_i = 0
    try:
        min_time_i = int(min_time or 0)
    except (TypeError, ValueError):
        min_time_i = 0
    api = client()
    if not (user.get("sec_uid") or user.get("uid")):
        try:
            user = api.me()
            persist_session(api, user)
        except DouyinError as exc:
            notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
            finish(succeeded=False)
            return
    try:
        rows, has_more, next_min, next_off = api.following_list_page(
            sec_uid=user.get("sec_uid") or "",
            uid=user.get("uid") or "",
            offset=offset_i,
            min_time=min_time_i,
        )
    except DouyinError as exc:
        notify(str(exc), xbmcgui.NOTIFICATION_ERROR)
        finish(succeeded=False)
        return
    if not rows:
        notify("账号关注是空的，或 Cookie 已失效，请到「已登录」里检查登录")
        finish(succeeded=True)
        return
    for row in rows:
        add_dir(
            row.get("nickname") or "抖音用户",
            {
                "action": "author",
                "sec_uid": row.get("sec_uid") or "",
                "uid": row.get("uid") or "",
                "nickname": row.get("nickname") or "",
            },
            icon=row.get("avatar") or "",
            plot="抖音账号关注的人",
        )
    if offset_i > 0:
        add_dir("上一页", {"action": "account_following", "off": "0", "min_time": "0"})
    if has_more:
        add_dir(
            "下一页",
            {
                "action": "account_following",
                "off": str(next_off),
                "min_time": str(next_min or 0),
            },
            plot="继续同步账号关注",
        )
    finish("files", cache=True)


def show_favorite():
    items = []
    sess = session()
    user = sess.get("user") or {}
    has_more = False
    next_cursor = 0
    from_account = False
    if has_session(sess.get("cookies")):
        try:
            api = client()
            if not (user.get("sec_uid") or user.get("uid")):
                try:
                    user = api.me()
                    persist_session(api, user)
                except DouyinError:
                    pass
            items, has_more, next_cursor = api.favorite_page(
                sec_uid=user.get("sec_uid") or "", uid=user.get("uid") or "", max_cursor=0
            )
            from_account = bool(items)
        except DouyinError:
            items = []
    if not items:
        items = likes(PROFILE)
        has_more = False
        next_cursor = 0
        from_account = False
    xbmcplugin.setPluginCategory(handle(), "我喜欢")
    add_home_dir()
    if not items:
        notify("还没有喜欢。登录后看账号喜欢，或看视频时长按 OK → 喜欢此视频")
        finish(succeeded=True)
        return
    remember(PROFILE, items)
    save_queue(
        PROFILE,
        items,
        {
            "kind": "favorite",
            "sec_uid": (user or {}).get("sec_uid") or "",
            "uid": (user or {}).get("uid") or "",
            "max_cursor": next_cursor,
            "has_more": bool(has_more),
        }
        if from_account
        else {"kind": "likes"},
    )
    for item in items:
        add_video(item)
    finish(cache=True)


def show_author(sec_uid, user_id="", nickname="", aweme_id=""):
    try:
        _show_author(sec_uid, user_id, nickname, aweme_id)
    except Exception as exc:
        notify("打不开这个作者主页：%s" % exc, xbmcgui.NOTIFICATION_ERROR)
        try:
            finish(succeeded=False)
        except Exception:
            pass


def _show_author(sec_uid, user_id="", nickname="", aweme_id=""):
    sec_uid = str(sec_uid or "").strip()
    user_id = str(user_id or "").strip()
    aweme_id = str(aweme_id or "").strip()
    xbmcplugin.setPluginCategory(handle(), nickname or "作者主页")
    add_home_dir()
    api = client()
    if (not sec_uid or not user_id) and aweme_id:
        try:
            detail = api.detail(aweme_id)
            sec_uid = sec_uid or str(detail.get("sec_uid") or "")
            user_id = user_id or str(detail.get("uid") or "")
            nickname = nickname or detail.get("author") or ""
        except DouyinError:
            pass
    if not sec_uid and not user_id:
        notify("这条没有作者信息，换一条再进")
        finish(succeeded=True)
        return
    cached = videos_by_author(PROFILE, sec_uid) if sec_uid else []
    fresh = []
    has_more = False
    next_cursor = 0
    err = ""
    try:
        fresh, has_more, next_cursor = api.user_posts_page(sec_uid, user_id, 0)
    except DouyinError as exc:
        err = str(exc)
        fresh = []
    items = []
    seen = set()
    for row in list(fresh) + list(cached):
        aid = str((row or {}).get("aweme_id") or "")
        if not aid or aid in seen:
            continue
        seen.add(aid)
        items.append(row)
    if not items:
        if err:
            notify("作者主页被抖音限了一下，过几秒再进。推荐里进主页更稳")
        else:
            notify("抖音暂时没返回这个作者的作品。搜索刚结束时容易被限，过几秒再进，不用重启")
        finish(succeeded=True)
        return
    remember(PROFILE, items)
    save_queue(
        PROFILE,
        items,
        {
            "kind": "author",
            "sec_uid": sec_uid or "",
            "uid": user_id or "",
            "max_cursor": int(next_cursor or 0),
            "has_more": bool(has_more),
        },
    )
    for item in items:
        add_video(item)
    finish(cache=True)


def do_toggle_like(params):
    item = {
        "aweme_id": params.get("aweme_id") or "",
        "video_id": params.get("video_id") or "",
        "title": params.get("title") or "",
        "author": params.get("author") or "",
        "sec_uid": params.get("sec_uid") or "",
        "uid": params.get("uid") or "",
        "cover": params.get("cover") or "",
        "avatar": params.get("avatar") or "",
        "duration": int(params.get("duration") or 0),
        "plot": params.get("title") or "",
    }
    liked = toggle_like(PROFILE, item)
    notify("已喜欢" if liked else "已取消喜欢")
    xbmcplugin.endOfDirectory(handle(), succeeded=True)


def do_toggle_follow(params):
    item = {
        "sec_uid": params.get("sec_uid") or "",
        "uid": params.get("uid") or "",
        "author": params.get("nickname") or "",
        "avatar": params.get("avatar") or "",
    }
    followed = toggle_follow(PROFILE, item)
    notify("已关注 %s" % (item.get("author") or "作者") if followed else "已取消关注")
    xbmcplugin.endOfDirectory(handle(), succeeded=True)
