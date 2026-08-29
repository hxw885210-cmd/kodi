# -*- coding: utf-8 -*-
"""Local likes / follows stored on this Kodi box."""
from __future__ import annotations

import json
import os
import time

LIKES_NAME = "likes.json"
FOLLOWS_NAME = "follows.json"
QUEUE_NAME = "queue.json"
SOURCE_NAME = "queue_source.json"
SEEN_NAME = "seen.json"
NOW_NAME = "now_playing.json"
HISTORY_NAME = "search_history.json"
SEARCH_CACHE_NAME = "search_cache.json"

SEARCH_CACHE_TTL = 30
SEARCH_CACHE_VER = "1.5.15"
SEARCH_SORTS = (("0", "综合"), ("1", "最多点赞"), ("2", "最新发布"))
SEARCH_PUBS = (("0", "时间不限"), ("1", "最近一天"), ("7", "最近一周"), ("180", "最近半年"))


def _path(profile_dir, name):
    return os.path.join(profile_dir, name)


_LIST_CACHE = {}


def _load_list(profile_dir, name):
    path = _path(profile_dir, name)
    if not os.path.isfile(path):
        return []
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    hit = _LIST_CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = []
    if not isinstance(data, list):
        data = []
    _LIST_CACHE[path] = (mtime, data)
    return data


def _save_list(profile_dir, name, rows):
    os.makedirs(profile_dir, exist_ok=True)
    path = _path(profile_dir, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False)
    os.replace(tmp, path)
    _LIST_CACHE.pop(path, None)


def likes(profile_dir):
    return _load_list(profile_dir, LIKES_NAME)


def is_liked(profile_dir, aweme_id):
    aweme_id = str(aweme_id or "")
    return any(str(row.get("aweme_id") or "") == aweme_id for row in likes(profile_dir))


def toggle_like(profile_dir, item):
    aweme_id = str((item or {}).get("aweme_id") or "")
    if not aweme_id:
        return False
    rows = [row for row in likes(profile_dir) if str(row.get("aweme_id") or "") != aweme_id]
    liked = len(rows) != len(likes(profile_dir))
    if liked:
        _save_list(profile_dir, LIKES_NAME, rows)
        return False
    row = dict(item)
    row["saved_at"] = int(time.time())
    rows.insert(0, row)
    _save_list(profile_dir, LIKES_NAME, rows[:400])
    return True


def follows(profile_dir):
    return _load_list(profile_dir, FOLLOWS_NAME)


def is_followed(profile_dir, sec_uid):
    sec_uid = str(sec_uid or "")
    return any(str(row.get("sec_uid") or "") == sec_uid for row in follows(profile_dir))


def toggle_follow(profile_dir, item):
    sec_uid = str((item or {}).get("sec_uid") or "")
    if not sec_uid:
        return False
    rows = [row for row in follows(profile_dir) if str(row.get("sec_uid") or "") != sec_uid]
    followed = len(rows) != len(follows(profile_dir))
    if followed:
        _save_list(profile_dir, FOLLOWS_NAME, rows)
        return False
    rows.insert(
        0,
        {
            "sec_uid": sec_uid,
            "uid": str((item or {}).get("uid") or ""),
            "nickname": (item or {}).get("author") or (item or {}).get("nickname") or "抖音用户",
            "avatar": (item or {}).get("avatar") or "",
            "saved_at": int(time.time()),
        },
    )
    _save_list(profile_dir, FOLLOWS_NAME, rows[:200])
    return True


def search_filter_choices():
    out = []
    for sort_key, sort_label in SEARCH_SORTS:
        for pub_key, pub_label in SEARCH_PUBS:
            out.append((sort_key, pub_key, "%s · %s" % (sort_label, pub_label)))
    return out


def search_filter_label(sort="0", pub="0"):
    sort_label = dict(SEARCH_SORTS).get(str(sort or "0"), "综合")
    pub_label = dict(SEARCH_PUBS).get(str(pub or "0"), "时间不限")
    return "筛选：%s · %s" % (sort_label, pub_label)


def save_queue(profile_dir, items, source=None):
    rows = [slim_play_item(item) for item in (items or []) if str((item or {}).get("aweme_id") or "")]
    _save_list(profile_dir, QUEUE_NAME, rows)
    if source is not None:
        save_queue_source(profile_dir, source)


def save_queue_source(profile_dir, source):
    os.makedirs(profile_dir, exist_ok=True)
    path = _path(profile_dir, SOURCE_NAME)
    tmp = path + ".tmp"
    payload = source if isinstance(source, dict) else {}
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    os.replace(tmp, path)


def load_queue_source(profile_dir):
    path = _path(profile_dir, SOURCE_NAME)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_queue(profile_dir):
    return _load_list(profile_dir, QUEUE_NAME)


def slim_play_item(item):
    item = item or {}
    return {
        "aweme_id": str(item.get("aweme_id") or ""),
        "video_id": str(item.get("video_id") or ""),
        "title": item.get("title") or "",
        "author": item.get("author") or "",
        "sec_uid": str(item.get("sec_uid") or ""),
        "uid": str(item.get("uid") or ""),
        "cover": item.get("cover") or "",
        "duration": int(item.get("duration") or 0),
        "likes": int(item.get("likes") or 0),
        "create_time": int(item.get("create_time") or 0),
        "kind": item.get("kind") or "",
        "room_id": str(item.get("room_id") or ""),
        "hls": item.get("hls") or "",
        "flv": item.get("flv") or "",
        "viewers": int(item.get("viewers") or 0),
        "plot": item.get("plot") or "",
    }


def queue_index(items, aweme_id):
    aid = str(aweme_id or "")
    if not aid:
        return -1
    for i, item in enumerate(items or []):
        if str((item or {}).get("aweme_id") or "") == aid:
            return i
    return -1


def save_now_playing(profile_dir, items, index, source=None):
    rows = [slim_play_item(item) for item in (items or []) if str((item or {}).get("aweme_id") or "")]
    if source is None:
        prev = load_now_playing(profile_dir)
        if isinstance(prev, dict) and prev.get("source"):
            source = prev.get("source")
    payload = {"active": True, "index": int(index or 0), "items": rows}
    if source:
        payload["source"] = source
    os.makedirs(profile_dir, exist_ok=True)
    path = _path(profile_dir, NOW_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    os.replace(tmp, path)
    return payload


def load_now_playing(profile_dir):
    path = _path(profile_dir, NOW_NAME)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def clear_now_playing(profile_dir):
    path = _path(profile_dir, NOW_NAME)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def remember(profile_dir, items):
    if not items:
        return
    seen = _load_list(profile_dir, SEEN_NAME)
    index = {str(row.get("aweme_id") or ""): i for i, row in enumerate(seen)}
    for item in reversed(items):
        aweme_id = str(item.get("aweme_id") or "")
        if not aweme_id:
            continue
        if aweme_id in index:
            seen.pop(index[aweme_id])
            index = {str(row.get("aweme_id") or ""): i for i, row in enumerate(seen)}
        seen.insert(0, item)
    _save_list(profile_dir, SEEN_NAME, seen[:800])


def sort_videos(items, sort):
    rows = list(items or [])
    sort = str(sort or "0")
    if sort in ("1", "hot", "likes"):
        rows.sort(key=lambda x: int(x.get("likes") or x.get("viewers") or 0), reverse=True)
    elif sort in ("2", "new", "time"):
        rows.sort(key=lambda x: int(x.get("create_time") or 0), reverse=True)
    return rows


def filter_by_publish(items, pub):
    pub = str(pub or "0")
    days = {"1": 1, "7": 7, "180": 180}.get(pub)
    if not days:
        return list(items or [])
    cutoff = int(time.time()) - days * 86400
    return [row for row in (items or []) if int(row.get("create_time") or 0) >= cutoff]


def save_named_list(profile_dir, name, items):
    _save_list(profile_dir, name, items or [])


def load_named_list(profile_dir, name):
    return _load_list(profile_dir, name)


def search_history(profile_dir):
    rows = _load_list(profile_dir, HISTORY_NAME)
    out = []
    for row in rows:
        if isinstance(row, str) and row.strip():
            out.append(row.strip())
        elif isinstance(row, dict) and (row.get("q") or "").strip():
            out.append(row.get("q").strip())
    return out


def add_search_history(profile_dir, query):
    query = (query or "").strip()
    if not query:
        return search_history(profile_dir)
    rows = [query] + [item for item in search_history(profile_dir) if item != query]
    _save_list(profile_dir, HISTORY_NAME, rows[:30])
    return rows[:30]


def remove_search_history(profile_dir, query):
    query = (query or "").strip()
    rows = [item for item in search_history(profile_dir) if item != query]
    _save_list(profile_dir, HISTORY_NAME, rows)
    return rows


def clear_search_history(profile_dir):
    _save_list(profile_dir, HISTORY_NAME, [])


def save_search_cache(profile_dir, query, sort, pub, items, offset=0, has_more=False, search_id="", next_offset=0):
    os.makedirs(profile_dir, exist_ok=True)
    payload = {
        "q": query or "",
        "sort": str(sort or "0"),
        "pub": str(pub or "0"),
        "offset": int(offset or 0),
        "has_more": bool(has_more),
        "search_id": search_id or "",
        "next_offset": int(next_offset or 0),
        "items": items or [],
        "ts": int(time.time()),
        "ver": SEARCH_CACHE_VER,
    }
    path = _path(profile_dir, SEARCH_CACHE_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    os.replace(tmp, path)


def load_search_cache(profile_dir, query, sort, pub, offset=0):
    path = _path(profile_dir, SEARCH_CACHE_NAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if str(data.get("ver") or "") != SEARCH_CACHE_VER:
        return None
    try:
        ts = int(data.get("ts") or 0)
    except (TypeError, ValueError):
        ts = 0
    if ts and int(time.time()) - ts > SEARCH_CACHE_TTL:
        return None
    if (data.get("q") or "") != (query or ""):
        return None
    if str(data.get("sort") or "0") != str(sort or "0"):
        return None
    if str(data.get("pub") or "0") != str(pub or "0"):
        return None
    try:
        cached_off = int(data.get("offset") or 0)
    except (TypeError, ValueError):
        cached_off = 0
    if cached_off != int(offset or 0):
        return None
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return None
    return data


def videos_by_author(profile_dir, sec_uid):
    sec_uid = str(sec_uid or "")
    if not sec_uid:
        return []
    out = []
    seen = set()
    for row in likes(profile_dir) + load_queue(profile_dir) + _load_list(profile_dir, SEEN_NAME):
        if str(row.get("sec_uid") or "") != sec_uid:
            continue
        aweme_id = str(row.get("aweme_id") or "")
        if not aweme_id or aweme_id in seen:
            continue
        seen.add(aweme_id)
        out.append(row)
    return out
