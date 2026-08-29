# -*- coding: utf-8 -*-
"""Load the next page of a Douyin list while a video is playing."""
from __future__ import annotations

from api import DouyinError
from library import (
    filter_by_publish,
    load_named_list,
    load_queue_source,
    save_named_list,
    save_now_playing,
    save_queue,
    save_search_cache,
    sort_videos,
)

MAX_KEEP = 240


def merge_unique(existing, extra):
    seen = {str((row or {}).get("aweme_id") or "") for row in existing or []}
    seen.discard("")
    added = []
    for row in extra or []:
        aweme_id = str((row or {}).get("aweme_id") or "")
        if not aweme_id or aweme_id in seen:
            continue
        seen.add(aweme_id)
        added.append(row)
    return added


def load_feed_page(profile_dir, api, page):
    try:
        page = max(int(page or 1), 1)
    except (TypeError, ValueError):
        page = 1
    cache_name = "cache_feed_%s.json" % page
    items = load_named_list(profile_dir, cache_name)
    if page == 1 and not items:
        items = load_named_list(profile_dir, "cache_feed.json")
    if items:
        return items
    items = api.feed(pull_type=0 if page == 1 else 1) or []
    seen = set()
    for prev in range(1, page):
        for row in load_named_list(profile_dir, "cache_feed_%s.json" % prev):
            seen.add(str((row or {}).get("aweme_id") or ""))
    items = [row for row in items if str((row or {}).get("aweme_id") or "") not in seen]
    save_named_list(profile_dir, cache_name, items)
    if page == 1:
        save_named_list(profile_dir, "cache_feed.json", items)
    return items


def fetch_more(profile_dir, source, api):
    source = dict(source or {})
    kind = str(source.get("kind") or "")
    if not kind:
        return [], source
    try:
        if kind == "feed":
            return _more_feed(profile_dir, source, api)
        if kind == "search":
            return _more_search(profile_dir, source, api)
        if kind == "follow":
            return _more_follow(source, api)
        if kind == "author":
            return _more_author(source, api)
        if kind == "favorite":
            return _more_favorite(source, api)
        if kind == "live":
            return _more_live(profile_dir, source, api)
    except DouyinError:
        return [], source
    return [], source


def extend_playing(profile_dir, state, api):
    items = list((state or {}).get("items") or [])
    source = (state or {}).get("source") or load_queue_source(profile_dir)
    added = []
    for _attempt in range(3):
        more, source = fetch_more(profile_dir, source, api)
        added = merge_unique(items, more)
        if added:
            break
        if not more or (source and source.get("has_more") is False):
            break
    if not added:
        if source:
            source = dict(source)
            source["has_more"] = False
        return items, -1, source
    items = items + added
    idx = len(items) - len(added)
    if len(items) > MAX_KEEP:
        cut = len(items) - MAX_KEEP
        items = items[cut:]
        idx -= cut
    save_queue(profile_dir, items, source)
    save_now_playing(profile_dir, items, idx, source)
    return items, idx, source


def _more_feed(profile_dir, source, api):
    try:
        page = int(source.get("page") or 1) + 1
    except (TypeError, ValueError):
        page = 2
    items = load_feed_page(profile_dir, api, page)
    source["page"] = page
    source["has_more"] = bool(items)
    return items, source


def _more_search(profile_dir, source, api):
    if source.get("has_more") is False:
        return [], source
    query = source.get("q") or ""
    sort = str(source.get("sort") or "0")
    pub = str(source.get("pub") or "0")
    try:
        offset = int(source.get("next_offset") or 0)
    except (TypeError, ValueError):
        offset = 0
    sid = str(source.get("sid") or "")
    items, has_more, next_offset, next_sid = api.search_page(
        query, sort_type=sort, publish_time=pub, offset=offset, search_id=sid
    )
    items = filter_by_publish(sort_videos(items, sort), pub)
    source["offset"] = offset
    source["has_more"] = bool(has_more)
    source["next_offset"] = int(next_offset or 0)
    source["sid"] = str(next_sid or sid)
    save_search_cache(
        profile_dir,
        query,
        sort,
        pub,
        items,
        offset=offset,
        has_more=has_more,
        search_id=next_sid,
        next_offset=next_offset,
    )
    return items, source


def _more_follow(source, api):
    items = api.follow_feed() or []
    source["has_more"] = bool(items)
    return items, source


def _more_author(source, api):
    if source.get("has_more") is False:
        return [], source
    try:
        cursor = int(source.get("max_cursor") or 0)
    except (TypeError, ValueError):
        cursor = 0
    items, has_more, next_cursor = api.user_posts_page(
        source.get("sec_uid") or "", source.get("uid") or "", cursor
    )
    source["has_more"] = bool(has_more)
    source["max_cursor"] = int(next_cursor or 0)
    return items or [], source


def _more_favorite(source, api):
    if source.get("has_more") is False:
        return [], source
    try:
        cursor = int(source.get("max_cursor") or 0)
    except (TypeError, ValueError):
        cursor = 0
    items, has_more, next_cursor = api.favorite_page(
        source.get("sec_uid") or "", source.get("uid") or "", cursor
    )
    source["has_more"] = bool(has_more)
    source["max_cursor"] = int(next_cursor or 0)
    return items or [], source


def _more_live(profile_dir, source, api):
    partition = str(source.get("partition") or "0")
    items = api.live_feed(partition) or []
    save_named_list(profile_dir, "cache_live_%s.json" % partition, items)
    source["has_more"] = bool(items)
    return items, source
