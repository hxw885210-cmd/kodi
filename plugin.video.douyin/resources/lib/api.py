# -*- coding: utf-8 -*-
"""Douyin client for Kodi. stdlib only. Cookie login, feed, play."""
from __future__ import annotations

import gzip
import io
import json
import random
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from auth import has_session

APP_UA = (
    "com.ss.android.ugc.aweme/190500 "
    "(Linux; U; Android 13; zh_CN; Pixel 7; Build/TQ3A; Cronet/58.0.2991.0)"
)
WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HOSTS = (
    "https://aweme.snssdk.com",
    "https://aweme-hl.snssdk.com",
    "https://api5-normal-c-lq.amemv.com",
)
PLAY_BASES = (
    "https://aweme.snssdk.com/aweme/v1/play/",
    "https://www.iesdouyin.com/aweme/v1/play/",
    "https://aweme-hl.snssdk.com/aweme/v1/play/",
)
WEB_ORIGIN = "https://www.douyin.com"
LIVE_CATEGORIES = (
    ("推荐", "0"),
    ("游戏", "103"),
    ("聊天", "101"),
    ("音乐", "102"),
    ("舞蹈", "105"),
    ("射击游戏", "1"),
    ("竞技游戏", "2"),
    ("王者荣耀", "1010045"),
    ("和平精英", "1010032"),
    ("英雄联盟", "1010014"),
    ("无畏契约", "1010017"),
    ("CSGO", "1010003"),
    ("永劫无间", "1010016"),
    ("第五人格", "1010041"),
)

_CTX = ssl.create_default_context()
try:
    _CTX_INSECURE = ssl._create_unverified_context()
except Exception:  # noqa: BLE001
    _CTX_INSECURE = None


class DouyinError(Exception):
    pass


class DouyinAPI:
    def __init__(self, device_id=None, count=20, quality="best", cookies=None):
        self.device_id = device_id or _new_device_id()
        self.count = max(6, min(int(count or 20), 40))
        self.quality = quality if quality in ("最高", "best", "1080p", "720p") else "best"
        self.cookies = dict(cookies or {})
        self._user = None
        self._ensure_guest_cookies()

    def common_params(self):
        return {
            "aid": "1128",
            "app_name": "aweme",
            "version_code": "190500",
            "version_name": "19.5.0",
            "device_id": self.device_id,
            "iid": self.device_id,
            "os_api": "29",
            "os_version": "13",
            "device_type": "Pixel 7",
            "device_brand": "google",
            "language": "zh",
            "resolution": "1080*2400",
            "dpi": "420",
            "count": str(self.count),
        }

    def web_params(self):
        return {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "pc_client_type": "1",
            "version_code": "190500",
            "version_name": "19.5.0",
            "cookie_enabled": "true",
            "screen_width": "1920",
            "screen_height": "1080",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Chrome",
            "browser_version": "131.0.0.0",
            "browser_online": "true",
            "engine_name": "Blink",
            "engine_version": "131.0.0.0",
            "os_name": "Windows",
            "os_version": "10",
            "platform": "PC",
            "webcast_language": "zh-CN",
            "webid": str(self.device_id),
        }

    def logged_in(self):
        return has_session(self.cookies)

    def me(self):
        data = self._request_json(
            WEB_ORIGIN + "/passport/web/account/info/",
            headers=self._headers("web"),
            allow_error=True,
        )
        payload = data.get("data") if isinstance(data.get("data"), dict) else {}
        ok = data.get("message") == "success" or bool(payload.get("user_id") or payload.get("user_id_str"))
        if not ok:
            msg = payload.get("description") or data.get("status_msg") or "Cookie 无效或已过期，请重新登录"
            raise DouyinError(str(msg))
        user = {
            "uid": str(payload.get("user_id") or payload.get("user_id_str") or ""),
            "nickname": (payload.get("screen_name") or payload.get("nickname") or "").strip(),
            "avatar": payload.get("avatar_url") or "",
            "sec_uid": str(payload.get("sec_user_id") or payload.get("sec_uid") or ""),
        }
        try:
            extra = self._web_json("/aweme/v1/web/user/profile/self/", self.web_params(), allow_error=True)
            pu = extra.get("user") if isinstance(extra.get("user"), dict) else {}
            if pu.get("sec_uid"):
                user["sec_uid"] = str(pu.get("sec_uid"))
            if pu.get("uid"):
                user["uid"] = str(pu.get("uid"))
            if (pu.get("nickname") or "").strip():
                user["nickname"] = pu.get("nickname").strip()
            avatar = _first_url(pu.get("avatar_thumb") or pu.get("avatar_medium") or {})
            if avatar:
                user["avatar"] = avatar
        except DouyinError:
            pass
        if not user.get("nickname"):
            user["nickname"] = "抖音用户"
        self._user = user
        return user

    def feed(self, pull_type=0, pages=2):
        try:
            out = self._app_feed(pull_type, pages=max(1, min(int(pages or 2), 3)))
            if out:
                return out
        except DouyinError:
            pass
        return self._tab_feed()

    def follow_feed(self):
        if not self.logged_in():
            raise DouyinError("先登录才能看关注动态")
        items = []
        try:
            data = self._web_json(
                "/aweme/v1/web/follow/feed/",
                dict(self.web_params(), count=str(self.count), refresh_index="1", pull_type="0"),
                allow_error=True,
            )
            items = _aweme_rows(data)
        except DouyinError:
            items = []
        if not items:
            try:
                data = self._get_json("/aweme/v1/follow/feed/", self.common_params(), allow_error=True)
                items = _aweme_rows(data)
            except DouyinError:
                items = []
        out = [_normalize(item) for item in items if _is_video(item)]
        if not out:
            raise DouyinError("暂时没有关注动态。确认 Cookie 有效，并且账号关注过作者")
        return out

    def following_list(self, sec_uid="", uid=""):
        rows, _more, _min_time, _offset = self.following_list_page(sec_uid=sec_uid, uid=uid)
        return rows

    def following_list_page(self, sec_uid="", uid="", offset=0, min_time=0):
        if not self.logged_in():
            return [], False, 0, 0
        try:
            offset = int(offset or 0)
        except (TypeError, ValueError):
            offset = 0
        try:
            min_time = int(min_time or 0)
        except (TypeError, ValueError):
            min_time = 0
        params = dict(
            self.web_params(),
            user_id=str(uid or "0"),
            sec_user_id=str(sec_uid or ""),
            count="20",
            offset=str(offset),
            min_time=str(min_time),
            source_type="1",
            gps_access="0",
            address_book_access="0",
        )
        try:
            data = self._web_json("/aweme/v1/web/user/following/list/", params, allow_error=True)
        except DouyinError:
            return [], False, min_time, offset
        if data.get("status_code") not in (0, None):
            return [], False, min_time, offset
        rows = data.get("followings") or data.get("data") or []
        if isinstance(rows, dict):
            rows = rows.get("followings") or rows.get("list") or []
        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            user = row.get("user") if isinstance(row.get("user"), dict) else row
            sec = str(user.get("sec_uid") or user.get("sec_user_id") or "")
            if not sec:
                continue
            out.append(
                {
                    "sec_uid": sec,
                    "uid": str(user.get("uid") or ""),
                    "nickname": (user.get("nickname") or "抖音用户").strip(),
                    "avatar": _first_url(user.get("avatar_thumb") or user.get("avatar_medium") or {}),
                }
            )
        has_more = bool(data.get("has_more"))
        next_min = data.get("min_time")
        try:
            next_min = int(next_min)
        except (TypeError, ValueError):
            next_min = min_time
        next_offset = offset + len(out)
        if has_more is False and len(out) >= 20:
            has_more = True
        return out, bool(has_more or len(out) >= 20), next_min, next_offset

    def favorite(self, sec_uid="", uid=""):
        items, _more, _cursor = self.favorite_page(sec_uid=sec_uid, uid=uid, max_cursor=0)
        return items

    def favorite_page(self, sec_uid="", uid="", max_cursor=0):
        if not self.logged_in():
            raise DouyinError("先登录才能看账号喜欢")
        try:
            max_cursor = int(max_cursor or 0)
        except (TypeError, ValueError):
            max_cursor = 0
        data = None
        items = []
        if sec_uid:
            try:
                data = self._web_json(
                    "/aweme/v1/web/aweme/favorite/",
                    dict(
                        self.web_params(),
                        sec_user_id=str(sec_uid),
                        max_cursor=str(max_cursor),
                        min_cursor="0",
                        count=str(self.count),
                    ),
                    allow_error=True,
                )
                items = _aweme_rows(data)
            except DouyinError:
                data = None
                items = []
        if not items and uid:
            try:
                params = self.common_params()
                params.update({"user_id": str(uid), "max_cursor": str(max_cursor), "count": str(self.count)})
                data = self._get_json("/aweme/v1/aweme/favorite/", params, allow_error=True)
                items = _aweme_rows(data)
            except DouyinError:
                data = None
                items = []
        out = [_normalize(item) for item in items if _is_video(item)]
        has_more, next_cursor = _page_cursor(data, max_cursor, len(out), self.count)
        return out, has_more, next_cursor

    def user_posts(self, sec_uid, user_id=""):
        items, _more, _cursor = self.user_posts_page(sec_uid, user_id, 0)
        return items

    def user_posts_page(self, sec_uid, user_id="", max_cursor=0):
        try:
            max_cursor = int(max_cursor or 0)
        except (TypeError, ValueError):
            max_cursor = 0
        sec_uid = str(sec_uid or "").strip()
        user_id = str(user_id or "").strip()
        last_data = None
        items = []
        if sec_uid:
            for attempt in range(2):
                try:
                    data = self._web_json(
                        "/aweme/v1/web/aweme/post/",
                        dict(
                            self.web_params(),
                            sec_user_id=sec_uid,
                            max_cursor=str(max_cursor),
                            count=str(min(self.count, 20)),
                            locate_query="false",
                            show_live_replay_strategy="1",
                            need_time_list="1",
                            time_list_query="0",
                        ),
                        allow_error=True,
                        referer="%s/user/%s" % (WEB_ORIGIN, urllib.parse.quote(sec_uid)),
                        timeout=15,
                    )
                except DouyinError:
                    data = None
                if isinstance(data, dict):
                    last_data = data
                    code = data.get("status_code")
                    if code in (0, None):
                        items = _aweme_rows(data)
                        if items:
                            break
                    if attempt == 0:
                        time.sleep(0.7)
                        continue
                elif attempt == 0:
                    time.sleep(0.5)
        if not items and sec_uid:
            ies_items, ies_data = self._ies_user_posts(sec_uid, max_cursor)
            if ies_items:
                items = ies_items
                last_data = ies_data or last_data
        if not items and not user_id and sec_uid:
            user_id = self._uid_from_profile(sec_uid)
        if not items and user_id:
            try:
                params = self.common_params()
                params.update({"user_id": user_id, "max_cursor": str(max_cursor)})
                data = self._get_json("/aweme/v1/aweme/post/", params, allow_error=True)
                if isinstance(data, dict):
                    last_data = data
                    items = _aweme_rows(data)
            except DouyinError:
                items = items or []
        out = []
        for item in items:
            if not _is_search_video(item):
                continue
            row = _safe_normalize(item)
            if row:
                out.append(row)
        has_more, next_cursor = _page_cursor(last_data, max_cursor, len(out), self.count)
        return out, has_more, next_cursor

    def _uid_from_profile(self, sec_uid):
        sec_uid = str(sec_uid or "").strip()
        if not sec_uid:
            return ""
        try:
            data = self._web_json(
                "/aweme/v1/web/user/profile/other/",
                dict(
                    self.web_params(),
                    sec_user_id=sec_uid,
                    publish_video_strategy_type="2",
                    personal_center_strategy="1",
                ),
                allow_error=True,
                referer="%s/user/%s" % (WEB_ORIGIN, urllib.parse.quote(sec_uid)),
                timeout=12,
            )
        except DouyinError:
            return ""
        user = {}
        if isinstance(data, dict):
            if isinstance(data.get("user"), dict):
                user = data.get("user")
            elif isinstance(data.get("user_info"), dict):
                user = data.get("user_info")
        return str(user.get("uid") or user.get("id") or "")

    def _ies_user_posts(self, sec_uid, max_cursor=0):
        sec_uid = str(sec_uid or "").strip()
        if not sec_uid:
            return [], None
        query = urllib.parse.urlencode(
            {
                "sec_uid": sec_uid,
                "count": str(min(self.count, 20)),
                "max_cursor": str(int(max_cursor or 0)),
                "aid": "1128",
            }
        )
        try:
            data = self._request_json(
                "https://www.iesdouyin.com/web/api/v2/aweme/post/?" + query,
                headers=self._headers("web", referer="https://www.iesdouyin.com/"),
                allow_error=True,
                timeout=15,
            )
        except DouyinError:
            return [], None
        if not isinstance(data, dict):
            return [], None
        if data.get("status_code") not in (0, None):
            return [], None
        return _aweme_rows(data), data

    def hot_words(self):
        words = self._hot_words_web()
        if words:
            return words
        return self._hot_words_app()

    def _hot_words_web(self):
        try:
            data = self._request_json(
                WEB_ORIGIN + "/aweme/v1/web/hot/search/list/",
                headers=self._headers("web"),
                allow_error=True,
            )
        except DouyinError:
            return []
        return _parse_hot_words(data)

    def _hot_words_app(self):
        try:
            data = self._get_json("/aweme/v1/hot/search/list/", self.common_params(), allow_error=True)
        except DouyinError:
            return []
        return _parse_hot_words(data)

    def hot_videos(self, word, sentence_id=""):
        params = self.common_params()
        if word:
            params["hotword"] = word
        if sentence_id:
            params["sentence_id"] = sentence_id
        data = self._get_json("/aweme/v1/hot/search/video/list/", params)
        return [_normalize(item) for item in _aweme_rows(data) if _is_video(item)]

    def hot_mix(self, limit=24):
        words = self.hot_words()[:6]
        seen = set()
        out = []
        for word in words:
            try:
                items = self.hot_videos(word["word"], word.get("sentence_id") or "")
            except DouyinError:
                continue
            for item in items:
                if item["aweme_id"] in seen:
                    continue
                seen.add(item["aweme_id"])
                out.append(item)
                if len(out) >= limit:
                    return out
        return out

    def search(self, keyword, sort_type="0", publish_time="0"):
        items, _has_more, _offset, _sid = self.search_page(keyword, sort_type, publish_time, 0, "")
        return items

    def search_page(self, keyword, sort_type="0", publish_time="0", offset=0, search_id=""):
        keyword = (keyword or "").strip()
        if not keyword:
            return [], False, 0, ""
        sort_type = str(sort_type or "0")
        publish_time = str(publish_time or "0")
        try:
            offset = int(offset or 0)
        except (TypeError, ValueError):
            offset = 0
        search_id = str(search_id or "")
        lowered = keyword.lower()
        if "douyin.com" in lowered or "iesdouyin.com" in lowered or "v.douyin" in lowered:
            item = self.from_share(keyword)
            return ([item] if item else []), False, offset, ""

        videos = []
        users = []
        lives = []
        has_more = False
        next_offset = offset
        next_sid = search_id
        used_web = False
        login_err = None

        try:
            videos, users, lives, has_more, next_offset, next_sid, login_err = self._web_search(
                keyword,
                sort_type=sort_type,
                publish_time=publish_time,
                offset=offset,
                search_id=search_id,
            )
            used_web = bool(videos or users or lives)
        except DouyinError as exc:
            login_err = exc
            videos, users, lives = [], [], []

        if offset == 0:
            try:
                extra_users = self._user_search(keyword)
            except DouyinError:
                extra_users = []
            users = _merge_users(users, extra_users)
            users = _merge_users(users, self._users_from_following(keyword))

        # 搜到用户就先展示卡片，不要立刻去拉每个人的主页，否则搜索后再进作者会被限流。
        if not videos and offset == 0 and users and not self.logged_in():
            videos = self._videos_from_users(users[:2])

        if not videos and offset == 0:
            try:
                videos = self.hot_videos(keyword)
            except DouyinError:
                videos = []
            if videos:
                has_more = len(videos) >= min(self.count, 15)
                next_offset = len(videos)

        if not videos and offset == 0:
            videos = self._search_via_hot_words(keyword)
            if videos:
                has_more = False
                next_offset = offset + len(videos)

        if not videos and offset == 0:
            videos = self._search_via_suggest(keyword)
            if videos:
                has_more = False
                next_offset = offset + len(videos)

        if not used_web:
            videos = _filter_pub(videos, publish_time)
            videos = _sort_items(videos, sort_type)
        elif publish_time not in ("0", ""):
            kept = _filter_pub(videos, publish_time)
            if kept or not videos:
                videos = kept

        items = []
        if offset == 0:
            items.extend(users)
            items.extend(lives)
        items.extend(videos)

        if not items:
            if login_err and ("登录" in str(login_err) or "cookie" in str(login_err).lower()):
                raise DouyinError("搜索需要有效登录 Cookie。请重新登录后再搜，热搜词也可先去热搜榜")
            return [], False, int(next_offset or 0), str(next_sid or "")
        return items, bool(has_more), int(next_offset or 0), str(next_sid or "")

    def _search_referer(self, keyword, kind="video"):
        tab = "user" if kind == "user" else "video"
        return "%s/search/%s?type=%s" % (WEB_ORIGIN, urllib.parse.quote(keyword or ""), tab)

    def _search_params(self, keyword, sort_type, publish_time, offset, search_id, channel, source):
        filtered = sort_type not in ("0", "") or publish_time not in ("0", "")
        count = "15"
        params = dict(
            self.web_params(),
            keyword=keyword,
            search_channel=channel,
            count=count,
            offset=str(offset),
            sort_type=str(sort_type or "0"),
            publish_time=str(publish_time or "0"),
            search_source=source,
            query_correct_type="1",
            is_filter_search="1" if filtered else "0",
            from_group_id="",
            need_filter_settings="1",
            list_type="multi",
            enable_history="1",
            publish_video_strategy_type="2",
            cpu_core_num="8",
            device_memory="8",
            downlink="10",
            effective_type="4g",
            round_trip_time="50",
        )
        ms_token = (self.cookies.get("msToken") or "").strip()
        if ms_token:
            params["msToken"] = ms_token
        if search_id:
            params["search_id"] = search_id
        params["filter_selected"] = json.dumps(
            {"sort_type": str(sort_type or "0"), "publish_time": str(publish_time or "0")},
            separators=(",", ":"),
        )
        return params

    def _web_search(self, keyword, sort_type="0", publish_time="0", offset=0, search_id=""):
        sort_type = str(sort_type or "0")
        publish_time = str(publish_time or "0")
        try:
            offset = int(offset or 0)
        except (TypeError, ValueError):
            offset = 0
        search_id = str(search_id or "")
        attempts = (
            ("/aweme/v1/web/general/search/single/", "aweme_general", "tab_search"),
            ("/aweme/v1/web/general/search/single/", "aweme_general", "normal_search"),
            ("/aweme/v1/web/search/item/", "aweme_video_web", "tab_search"),
            ("/aweme/v1/web/search/item/", "aweme_video_web", "normal_search"),
        )
        last = None
        login_err = None
        for path, channel, source in attempts:
            params = self._search_params(keyword, sort_type, publish_time, offset, search_id, channel, source)
            try:
                data = self._web_json(
                    path,
                    params,
                    allow_error=True,
                    referer=self._search_referer(keyword, "video"),
                    timeout=15,
                    sign=True,
                )
            except DouyinError as exc:
                last = exc
                continue
            if not isinstance(data, dict) or not data:
                continue
            code = data.get("status_code")
            msg = str(data.get("status_msg") or "")
            if code in (2483, 2154, 5, 8) or ("登录" in msg):
                login_err = DouyinError(msg or "搜索需要先登录")
                last = login_err
                continue
            if code not in (0, None):
                last = DouyinError(msg or ("错误码 %s" % code))
                continue
            videos = []
            for item in _search_awemes(data):
                if not _is_search_video(item):
                    continue
                row = _safe_normalize(item)
                if row:
                    videos.append(row)
            users = _search_users(data)
            lives = []
            for room in _live_search_rooms(data):
                item = _normalize_live(room)
                if item:
                    lives.append(item)
            extra = data.get("extra") if isinstance(data.get("extra"), dict) else {}
            next_sid = str(data.get("search_id") or extra.get("search_id") or extra.get("logid") or search_id or "")
            cursor = data.get("cursor")
            if cursor is None:
                cursor = extra.get("cursor")
            try:
                next_offset = int(cursor)
            except (TypeError, ValueError):
                next_offset = offset + max(len(videos), 1)
            if next_offset <= offset and videos:
                next_offset = offset + max(len(videos), 10)
            has_more = data.get("has_more")
            if has_more is None:
                has_more = extra.get("has_more")
            if has_more is None:
                has_more = len(videos) >= 8
            if videos or users or lives:
                return videos, users, lives, bool(has_more), next_offset, next_sid, None
        if login_err:
            return [], [], [], False, offset, search_id, login_err
        if last:
            return [], [], [], False, offset, search_id, last
        return [], [], [], False, offset, search_id, None

    def _user_search(self, keyword, offset=0):
        keyword = (keyword or "").strip()
        if not keyword:
            return []
        try:
            offset = int(offset or 0)
        except (TypeError, ValueError):
            offset = 0
        attempts = (
            ("/aweme/v1/web/discover/search/", "aweme_user_web", "switch_tab"),
            ("/aweme/v1/web/discover/search/", "aweme_user_web", "normal_search"),
            ("/aweme/v1/web/general/search/single/", "aweme_user_web", "tab_search"),
        )
        users = []
        for path, channel, source in attempts:
            params = dict(
                self.web_params(),
                keyword=keyword,
                search_channel=channel,
                search_source=source,
                query_correct_type="1",
                is_filter_search="0",
                offset=str(offset),
                count="10",
                from_group_id="",
            )
            ms_token = (self.cookies.get("msToken") or "").strip()
            if ms_token:
                params["msToken"] = ms_token
            try:
                data = self._web_json(
                    path,
                    params,
                    allow_error=True,
                    referer=self._search_referer(keyword, "user"),
                    timeout=15,
                    sign=True,
                )
            except DouyinError:
                continue
            if not isinstance(data, dict):
                continue
            code = data.get("status_code")
            if code not in (0, None):
                continue
            found = _search_users(data)
            if found:
                users = _merge_users(users, found)
                break
        if not users:
            users = self._app_user_search(keyword, offset)
        return users

    def _app_user_search(self, keyword, offset=0):
        params = self.common_params()
        params.update(
            {
                "keyword": keyword,
                "count": "10",
                "cursor": str(int(offset or 0)),
                "type": "1",
                "hot_search": "0",
                "search_source": "discover",
            }
        )
        try:
            data = self._get_json("/aweme/v1/discover/search/", params, allow_error=True)
        except DouyinError:
            return []
        if not isinstance(data, dict):
            return []
        code = data.get("status_code")
        if code not in (0, None):
            return []
        return _search_users(data)

    def _users_from_following(self, keyword):
        keyword = (keyword or "").strip()
        if not keyword or not self.logged_in():
            return []
        needle = keyword.lower()
        try:
            rows, _more, _min_time, _offset = self.following_list_page()
        except DouyinError:
            rows = []
        out = []
        for row in rows or []:
            nick = str((row or {}).get("nickname") or (row or {}).get("author") or "")
            if not nick:
                continue
            if needle not in nick.lower() and nick.lower() not in needle:
                continue
            out.append(
                _normalize_user(
                    {
                        "nickname": nick,
                        "sec_uid": (row or {}).get("sec_uid") or "",
                        "uid": (row or {}).get("uid") or "",
                        "avatar_thumb": {"url_list": [(row or {}).get("avatar") or ""]},
                    }
                )
            )
        return [row for row in out if row and row.get("sec_uid")]

    def _videos_from_users(self, users):
        seen = set()
        out = []
        for user in users or []:
            sec = str((user or {}).get("sec_uid") or "")
            uid = str((user or {}).get("uid") or "")
            if not sec and not uid:
                continue
            try:
                posts, _more, _cursor = self.user_posts_page(sec, uid, 0)
            except DouyinError:
                continue
            for item in posts:
                aid = str(item.get("aweme_id") or "")
                if not aid or aid in seen:
                    continue
                seen.add(aid)
                out.append(item)
                if len(out) >= max(self.count, 12):
                    return out
        return out

    def _search_via_hot_words(self, keyword):
        try:
            words = self.hot_words()
        except DouyinError:
            return []
        matches = [w for w in words if keyword in w["word"] or w["word"] in keyword]
        seen = set()
        out = []
        for word in matches[:6]:
            try:
                found = self.hot_videos(word["word"], word.get("sentence_id") or "")
            except DouyinError:
                continue
            for item in found:
                aid = str(item.get("aweme_id") or "")
                if not aid or aid in seen:
                    continue
                seen.add(aid)
                out.append(item)
        return out

    def _search_via_suggest(self, keyword):
        words = self._suggest_words(keyword)
        seen = set()
        out = []
        for word in words[:5]:
            try:
                found = self.hot_videos(word)
            except DouyinError:
                continue
            for item in found:
                aid = str(item.get("aweme_id") or "")
                if not aid or aid in seen:
                    continue
                seen.add(aid)
                out.append(item)
                if len(out) >= max(self.count, 12):
                    return out
        return out

    def _suggest_words(self, keyword):
        keyword = (keyword or "").strip()
        if not keyword:
            return []
        try:
            data = self._web_json(
                "/aweme/v1/web/api/suggest_words/",
                dict(self.web_params(), query=keyword, count="10", business_id="30068", from_group_id=""),
                allow_error=True,
                referer=self._search_referer(keyword, "video"),
            )
        except DouyinError:
            return []
        if not isinstance(data, dict):
            return []
        out = []
        seen = set()
        rows = data.get("data") or data.get("sug_list") or []
        if isinstance(rows, dict):
            rows = [rows]
        for group in rows:
            words = []
            if isinstance(group, dict):
                words = group.get("words") or group.get("sug_list") or group.get("list") or []
                one = (group.get("word") or group.get("name") or group.get("content") or "").strip()
                if one:
                    words = list(words) + [group]
            if not isinstance(words, list):
                continue
            for row in words:
                if isinstance(row, str):
                    word = row.strip()
                elif isinstance(row, dict):
                    word = (row.get("word") or row.get("word_name") or row.get("name") or row.get("content") or "").strip()
                else:
                    word = ""
                if not word or word == keyword or word in seen:
                    continue
                seen.add(word)
                out.append(word)
        return out

    def live_categories(self):
        return list(LIVE_CATEGORIES)

    def live_feed(self, partition="0"):
        partition = str(partition or "0")
        query = urllib.parse.urlencode(
            {
                "aid": "6383",
                "count": str(max(self.count, 12)),
                "req_from": "partition",
                "partition": partition,
            }
        )
        data = self._request_json(
            "https://live.douyin.com/webcast/feed/?" + query,
            headers=self._headers("web"),
            allow_error=True,
        )
        out = []
        for row in data.get("data") or []:
            room = row.get("data") if isinstance(row, dict) else None
            item = _normalize_live(room if isinstance(room, dict) else row)
            if item:
                out.append(item)
        return out

    def live_search(self, keyword):
        keyword = (keyword or "").strip()
        if not keyword:
            return []
        if not self.logged_in():
            raise DouyinError("搜索直播需要先登录")
        data = self._web_json(
            "/aweme/v1/web/live/search/",
            dict(
                self.web_params(),
                keyword=keyword,
                count=str(self.count),
                offset="0",
                search_channel="live",
                search_source="normal_search",
            ),
            allow_error=True,
        )
        code = data.get("status_code")
        if code not in (0, None):
            raise DouyinError(str(data.get("status_msg") or "搜索直播失败"))
        out = []
        for room in _live_search_rooms(data):
            item = _normalize_live(room)
            if item:
                out.append(item)
        return out

    def live_follow(self):
        if not self.logged_in():
            raise DouyinError("先登录才能看关注的直播")
        last = None
        for url in (
            "https://live.douyin.com/webcast/web/feed/follow/?aid=6383&count=" + str(self.count),
            WEB_ORIGIN + "/webcast/web/feed/follow/?" + urllib.parse.urlencode(dict(self.web_params(), count=str(self.count))),
        ):
            try:
                data = self._request_json(url, headers=self._headers("web"), allow_error=True)
            except DouyinError as exc:
                last = exc
                continue
            rows = data.get("data") or []
            if isinstance(rows, dict):
                rows = rows.get("data") or rows.get("list") or []
            out = []
            for row in rows:
                room = row.get("data") or row.get("room") if isinstance(row, dict) else None
                item = _normalize_live(room if isinstance(room, dict) else row)
                if item:
                    out.append(item)
            if out:
                return out
        if last:
            raise last
        return []

    def live_play_url(self, room_id, item=None):
        room_id = str(room_id or "")
        url = _live_stream(item or {})
        if url:
            return url
        if not room_id:
            raise DouyinError("缺少直播间")
        try:
            for room in self.live_feed("0"):
                if room.get("room_id") == room_id:
                    url = _live_stream(room)
                    if url:
                        return url
        except DouyinError:
            pass
        raise DouyinError("这个直播间暂时无法播放，可能已下播")

    def detail(self, aweme_id):
        aweme_id = str(aweme_id or "")
        if not aweme_id:
            raise DouyinError("缺少视频 ID")
        item = None
        try:
            params = self.common_params()
            params["aweme_id"] = aweme_id
            data = self._get_json("/aweme/v1/aweme/detail/", params, allow_error=True)
            item = data.get("aweme_detail") if isinstance(data.get("aweme_detail"), dict) else None
        except DouyinError:
            item = None
        if not item:
            try:
                data = self._web_json(
                    "/aweme/v1/web/aweme/detail/",
                    dict(self.web_params(), aweme_id=aweme_id),
                    allow_error=True,
                )
                item = data.get("aweme_detail") if isinstance(data.get("aweme_detail"), dict) else None
            except DouyinError:
                item = None
        if not item:
            raise DouyinError("视频不存在或已删除")
        row = _safe_normalize(item)
        if not row:
            raise DouyinError("视频解析失败")
        return row

    def from_share(self, text):
        aweme_id = self.resolve_aweme_id(text)
        if not aweme_id:
            raise DouyinError("无法从链接里解析视频 ID，请粘贴 v.douyin.com 或 douyin.com/video 链接")
        try:
            return self.detail(aweme_id)
        except DouyinError:
            return {
                "aweme_id": aweme_id,
                "video_id": "",
                "title": "抖音视频 %s" % aweme_id,
                "plot": "来自分享链接",
                "author": "",
                "uid": "",
                "sec_uid": "",
                "avatar": "",
                "cover": "",
                "duration": 0,
                "width": 0,
                "height": 0,
                "likes": 0,
                "create_time": int(time.time()),
            }

    def resolve_aweme_id(self, text):
        text = (text or "").strip()
        if not text:
            return ""
        patterns = (
            r"douyin.com/video/([0-9]{15,})",
            r"douyin.com/note/([0-9]{15,})",
            r"iesdouyin.com/share/video/([0-9]{15,})",
            r"modal_id=([0-9]{15,})",
            r"aweme_id=([0-9]{15,})",
            r"/([0-9]{19})(?:[/?#]|$)",
        )
        for pat in patterns:
            match = re.search(pat, text)
            if match:
                return match.group(1)
        short = re.search(r"https?://v.douyin.com/[A-Za-z0-9_-]+", text)
        if short:
            final = self._follow(short.group(0))
            for pat in patterns:
                match = re.search(pat, final)
                if match:
                    return match.group(1)
        return ""

    def play_url(self, item=None, video_id="", aweme_id=""):
        vid = video_id or (item or {}).get("video_id") or ""
        if not vid:
            aid = aweme_id or (item or {}).get("aweme_id") or ""
            if aid:
                try:
                    fresh = self.detail(aid)
                    vid = fresh.get("video_id") or ""
                except DouyinError:
                    vid = ""
        if not vid:
            raise DouyinError("没有可播放的视频地址。推荐和热搜可以直接播；分享链接若失败请改用推荐。")
        ratio = play_ratio(self.quality)
        last = ""
        for line in ("0", "1"):
            api_url = self._play_api_url(vid, ratio, line)
            last = api_url
            resolved = self._resolve_media_url(api_url)
            if resolved:
                return resolved
        return last

    def _play_api_url(self, video_id, ratio, line="0"):
        query = urllib.parse.urlencode(
            {
                "video_id": video_id,
                "ratio": ratio,
                "line": str(line or "0"),
                "watermark": "0",
            }
        )
        return PLAY_BASES[0] + "?" + query

    def _resolve_media_url(self, url):
        """Follow Douyin 302 to the CDN mp4 so Kodi keeps headers and Range."""
        headers = {
            "User-Agent": APP_UA,
            "Referer": "https://www.douyin.com/",
            "Accept": "*/*",
        }
        cookie = self._cookie_header()
        if cookie:
            headers["Cookie"] = cookie
        req = urllib.request.Request(url, headers=headers)
        ctx = _CTX_INSECURE if _CTX_INSECURE is not None else _CTX
        try:
            resp = urllib.request.urlopen(req, timeout=12, context=ctx)
        except Exception:
            return ""
        try:
            final = (resp.geturl() or "").strip()
            ctype = (resp.headers.get("Content-Type") or "").lower()
        finally:
            try:
                resp.close()
            except Exception:
                pass
        if not final.startswith("http"):
            return ""
        if ctype and ("video" not in ctype) and ("octet-stream" not in ctype) and ("mp4" not in ctype):
            return ""
        return final

    def _tab_feed(self):
        data = self._web_json(
            "/aweme/v1/web/tab/feed/",
            dict(self.web_params(), count=str(self.count), refresh_index="1", video_type_select="1"),
            allow_error=True,
        )
        return [_normalize(item) for item in _aweme_rows(data) if _is_video(item)]

    def _app_feed(self, pull_type=0, pages=4):
        seen = set()
        out = []
        pages = max(1, min(int(pages or 1), 8))
        last_err = None
        for i in range(pages):
            params = self.common_params()
            params.update(
                {
                    "type": "0",
                    "max_cursor": "0",
                    "min_cursor": "0",
                    "pull_type": "0" if i == 0 and pull_type == 0 else "1",
                    "volume": "0.2",
                    "is_cold_start": "1" if i == 0 else "0",
                }
            )
            try:
                data = self._get_json("/aweme/v1/feed/", params)
            except DouyinError as exc:
                last_err = exc
                continue
            for item in _aweme_rows(data):
                if not _is_video(item):
                    continue
                row = _normalize(item)
                if not row["aweme_id"] or row["aweme_id"] in seen:
                    continue
                seen.add(row["aweme_id"])
                out.append(row)
                if len(out) >= self.count:
                    return out
        if not out and last_err:
            raise last_err
        return out

    def _ensure_guest_cookies(self):
        if not (self.cookies.get("msToken") or "").strip():
            self.cookies["msToken"] = _new_ms_token()

    def _cookie_header(self):
        parts = []
        for key, value in self.cookies.items():
            if key and value:
                parts.append("%s=%s" % (key, value))
        return "; ".join(parts)

    def _headers(self, kind="app", referer=None):
        headers = {
            "User-Agent": APP_UA if kind == "app" else WEB_UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate",
        }
        if kind == "web":
            headers["Referer"] = referer or (WEB_ORIGIN + "/")
            headers["Origin"] = WEB_ORIGIN
            if not (self.cookies.get("ttwid") or "").strip():
                ttwid = _fetch_ttwid()
                if ttwid:
                    self.cookies["ttwid"] = ttwid
            if not (self.cookies.get("msToken") or "").strip():
                self.cookies["msToken"] = _new_ms_token()
        cookie = self._cookie_header()
        if cookie:
            headers["Cookie"] = cookie
        return headers

    def _web_json(self, path, params, allow_error=False, referer=None, timeout=12, sign=False):
        query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        if sign:
            try:
                from abogus import make_a_bogus

                query = query + "&a_bogus=" + urllib.parse.quote(make_a_bogus(query, WEB_UA), safe="")
            except Exception:
                pass
        return self._request_json(
            WEB_ORIGIN + path + "?" + query,
            headers=self._headers("web", referer=referer),
            allow_error=allow_error,
            timeout=timeout,
        )

    def _get_json(self, path, params, allow_error=False):
        query = urllib.parse.urlencode(params)
        last_err = None
        for host in HOSTS:
            try:
                return self._request_json(
                    host + path + "?" + query,
                    headers=self._headers("app"),
                    allow_error=allow_error,
                )
            except DouyinError as exc:
                last_err = exc
                continue
        raise last_err or DouyinError("网络请求失败")

    def _request_json(self, url, headers=None, timeout=10, allow_error=False):
        raw = self._request_bytes(url, headers=headers, timeout=timeout)
        if not raw:
            raise DouyinError("接口返回为空")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", "replace")
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise DouyinError("接口返回不是 JSON") from exc
        if not isinstance(data, dict):
            return data
        if allow_error:
            return data
        code = data.get("status_code")
        if code not in (0, None):
            msg = data.get("status_msg") or ("错误码 %s" % code)
            raise DouyinError(str(msg))
        return data

    def _request_bytes(self, url, headers=None, data=None, timeout=10):
        req = urllib.request.Request(url, data=data, headers=headers or {})
        ctx = _CTX_INSECURE if _CTX_INSECURE is not None else _CTX
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read(1_500_000)
                self._absorb_cookies(resp.headers)
                return _maybe_gunzip(raw, resp.headers)
        except urllib.error.HTTPError as exc:
            body = b""
            try:
                body = exc.read(400) if exc.fp else b""
            except Exception:  # noqa: BLE001
                body = b""
            raise DouyinError("HTTP %s %s" % (exc.code, body[:120])) from exc
        except urllib.error.URLError as exc:
            raise DouyinError("连接失败：%s" % exc.reason) from exc
        except ssl.SSLError as exc:
            raise DouyinError("SSL 失败：%s" % exc) from exc
        except (TimeoutError, OSError) as exc:
            raise DouyinError("连接失败：%s" % exc) from exc

    def _absorb_cookies(self, headers):
        raw_list = []
        getter = getattr(headers, "get_all", None)
        if callable(getter):
            raw_list = getter("Set-Cookie") or []
        elif headers.get("Set-Cookie"):
            raw_list = [headers.get("Set-Cookie")]
        for raw in raw_list:
            first = (raw or "").split(";", 1)[0]
            if "=" not in first:
                continue
            key, value = first.split("=", 1)
            key = key.strip()
            if key and key.lower() not in ("path", "domain", "expires", "max-age", "secure", "httponly", "samesite"):
                self.cookies[key] = value.strip()

    def _follow(self, url):
        class _Capture(urllib.request.HTTPRedirectHandler):
            last = url

            def redirect_request(self, req, fp, code, msg, headers, newurl):
                _Capture.last = newurl
                return urllib.request.HTTPRedirectHandler.redirect_request(
                    self, req, fp, code, msg, headers, newurl
                )

        opener = urllib.request.build_opener(_Capture)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": WEB_UA, "Accept": "text/html,*/*"},
        )
        try:
            with opener.open(req, timeout=15) as resp:
                return resp.geturl() or _Capture.last
        except urllib.error.HTTPError as exc:
            loc = exc.headers.get("Location") if exc.headers else None
            return loc or _Capture.last
        except Exception:
            return _Capture.last


def _fetch_ttwid():
    payload = json.dumps(
        {
            "region": "cn",
            "aid": 1768,
            "needFid": False,
            "service": "www.ixigua.com",
            "migrate_info": {"ticket": "", "source": "node"},
            "cbUrlProtocol": "https",
            "union": True,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://ttwid.bytedance.com/ttwid/union/register/",
        data=payload,
        headers={"User-Agent": WEB_UA, "Content-Type": "application/json", "Accept": "application/json"},
    )
    contexts = [_CTX]
    if _CTX_INSECURE is not None:
        contexts.append(_CTX_INSECURE)
    for ctx in contexts:
        try:
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                getter = getattr(resp.headers, "get_all", None)
                rows = getter("Set-Cookie") if callable(getter) else [resp.headers.get("Set-Cookie") or ""]
                for raw in rows or []:
                    match = re.search(r"\bttwid=([^;]+)", raw or "")
                    if match:
                        return match.group(1).strip()
        except Exception:
            continue
    return ""


def _maybe_gunzip(raw, headers):
    encoding = ""
    if headers is not None:
        encoding = (headers.get("Content-Encoding") or "").lower()
    if encoding == "gzip" or (raw[:2] == b"\x1f\x8b"):
        try:
            return gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        except Exception:
            return raw
    return raw


def _https(url):
    url = str(url or "").strip()
    if url.startswith("http://"):
        return "https://" + url[7:]
    return url


def _live_stream(item):
    if not isinstance(item, dict):
        return ""
    for key in ("hls", "flv"):
        url = _https(item.get(key) or "")
        if url:
            return url
    su = item.get("stream_url") or {}
    if isinstance(su, dict):
        hls_map = su.get("hls_pull_url_map") or {}
        flv_map = su.get("flv_pull_url") or su.get("flv_pull_url_map") or {}
        for key in ("FULL_HD1", "HD1", "SD1", "SD2"):
            url = _https(hls_map.get(key) or flv_map.get(key) or "")
            if url:
                return url
        url = _https(su.get("hls_pull_url") or su.get("rtmp_pull_url") or "")
        if url:
            return url
    return ""


def _normalize_live(room):
    if not isinstance(room, dict):
        return None
    if room.get("room"):
        room = room.get("room")
    owner = room.get("owner") or room.get("anchor") or {}
    if not isinstance(owner, dict):
        owner = {}
    nested = owner.get("user") if isinstance(owner.get("user"), dict) else {}
    nick = (owner.get("nickname") or nested.get("nickname") or "主播").strip()
    title = (room.get("title") or "").strip() or ("%s 的直播" % nick)
    room_id = str(room.get("id_str") or room.get("id") or room.get("room_id") or "")
    if not room_id:
        return None
    su = room.get("stream_url") if isinstance(room.get("stream_url"), dict) else {}
    hls_map = su.get("hls_pull_url_map") or {}
    flv_map = su.get("flv_pull_url") or su.get("flv_pull_url_map") or {}
    hls = ""
    flv = ""
    for key in ("FULL_HD1", "HD1", "SD1", "SD2"):
        if not hls:
            hls = _https(hls_map.get(key) or "")
        if not flv:
            flv = _https(flv_map.get(key) or "")
    if not hls:
        hls = _https(su.get("hls_pull_url") or "")
    viewers = room.get("user_count") or room.get("user_count_str") or 0
    try:
        viewers = int(str(viewers).replace("万", "0000").split(".")[0] or 0)
    except (TypeError, ValueError):
        viewers = 0
    cover = _first_url(room.get("cover") or owner.get("avatar_thumb") or {})
    show = "[直播] %s · %s" % (nick, title)
    if len(show) > 80:
        show = show[:77] + "…"
    return {
        "kind": "live",
        "room_id": room_id,
        "aweme_id": "live-%s" % room_id,
        "video_id": "",
        "title": show,
        "plot": "在线 %s  ·  %s" % (_human(viewers), title),
        "author": nick,
        "uid": str(
            owner.get("id_str")
            or owner.get("uid")
            or owner.get("id")
            or nested.get("id_str")
            or nested.get("uid")
            or ""
        ),
        "sec_uid": str(
            owner.get("sec_uid")
            or owner.get("sec_user_id")
            or nested.get("sec_uid")
            or nested.get("sec_user_id")
            or room.get("sec_uid")
            or ""
        ),
        "avatar": _first_url(owner.get("avatar_thumb") or owner.get("avatar_medium") or nested.get("avatar_thumb") or {}),
        "cover": cover,
        "viewers": viewers,
        "likes": viewers,
        "hls": hls,
        "flv": flv,
        "create_time": int(room.get("create_time") or 0),
        "duration": 0,
    }


def _live_search_rooms(data):
    if not isinstance(data, dict):
        return []
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    rows = []
    for key in ("data", "lives", "live_list", "list", "aweme_list"):
        val = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(val, list):
            rows = val
            break
    if isinstance(data.get("data"), list):
        rows = data.get("data")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        lives = row.get("lives") if isinstance(row.get("lives"), dict) else None
        room = (
            row.get("room")
            or row.get("rawdata")
            or (lives.get("rawdata") if lives else None)
            or row.get("data")
            or row
        )
        if isinstance(room, str):
            try:
                room = json.loads(room)
            except ValueError:
                continue
        if isinstance(room, dict):
            out.append(room)
    return out


def _sort_items(items, sort):
    rows = list(items or [])
    sort = str(sort or "0")
    if sort in ("1", "hot", "likes"):
        rows.sort(key=lambda x: int(x.get("likes") or x.get("viewers") or 0), reverse=True)
    elif sort in ("2", "new", "time"):
        rows.sort(key=lambda x: int(x.get("create_time") or 0), reverse=True)
    return rows


def _page_cursor(data, cursor, nitems, count):
    try:
        cursor = int(cursor or 0)
    except (TypeError, ValueError):
        cursor = 0
    try:
        count = int(count or 0)
    except (TypeError, ValueError):
        count = 0
    if not isinstance(data, dict):
        return nitems >= count and nitems > 0, cursor
    has_more = data.get("has_more")
    next_cursor = data.get("max_cursor")
    if next_cursor is None:
        next_cursor = data.get("min_cursor")
    try:
        next_cursor = int(next_cursor)
    except (TypeError, ValueError):
        next_cursor = cursor
    if has_more is None:
        has_more = nitems >= count and next_cursor != cursor
    else:
        has_more = bool(has_more)
    if next_cursor == cursor and nitems == 0:
        has_more = False
    return has_more, next_cursor


def _filter_pub(items, pub):
    pub = str(pub or "0")
    days = {"1": 1, "7": 7, "180": 180}.get(pub)
    if not days:
        return list(items or [])
    cutoff = int(time.time()) - days * 86400
    return [row for row in (items or []) if int(row.get("create_time") or 0) >= cutoff]


def play_ratio(quality):
    """Map add-on quality setting to Douyin play `ratio`.

    `最高` uses Douyin's `default` rendition: each video's own top encode
    (1080p / 2K / 4K original), not a fixed 1080p cap.
    """
    q = (quality or "").strip()
    if q in ("720p", "1080p"):
        return q
    return "default"


def _new_device_id():
    return str(random.randint(10**14, 10**15 - 1))


def _new_ms_token():
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    return "".join(random.choice(alphabet) for _ in range(128))


def _maybe_json(value):
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in "{[":
            try:
                return json.loads(text)
            except ValueError:
                return value
    return value


def _aweme_rows(data):
    if not isinstance(data, dict):
        return []
    rows = data.get("aweme_list")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    payload = data.get("data")
    if isinstance(payload, dict) and isinstance(payload.get("aweme_list"), list):
        return [row for row in payload.get("aweme_list") if isinstance(row, dict)]
    detail = data.get("aweme_detail")
    if isinstance(detail, dict) and (detail.get("aweme_id") or detail.get("awemeId")):
        return [detail]
    return _search_awemes(data)


def _search_awemes(data):
    out = []
    seen = set()

    def add(item):
        if not isinstance(item, dict):
            return
        aid = str(item.get("aweme_id") or item.get("awemeId") or "")
        if not aid or aid in seen:
            return
        if not (item.get("video") or item.get("author") or item.get("desc") is not None or item.get("statistics")):
            return
        seen.add(aid)
        out.append(item)

    def walk(node, depth=0):
        if depth > 8 or node is None:
            return
        node = _maybe_json(node)
        if isinstance(node, list):
            for row in node:
                walk(row, depth + 1)
            return
        if not isinstance(node, dict):
            return
        add(node)
        for key in (
            "aweme_info",
            "aweme",
            "item_info",
            "item",
            "aweme_detail",
            "rawdata",
            "aweme_list",
            "search_item_list",
            "items",
            "list",
            "data",
            "business_data",
            "card_info",
            "cards",
        ):
            if key in node:
                walk(node.get(key), depth + 1)

    walk(data)
    return out


def _search_users(data):
    out = []
    seen = set()

    def add(user):
        if not isinstance(user, dict):
            return
        for key in ("user_info", "user", "author", "author_info", "authorInfo"):
            nested = user.get(key)
            if isinstance(nested, dict) and (
                nested.get("sec_uid") or nested.get("sec_user_id") or nested.get("secUid") or nested.get("nickname")
            ):
                user = nested
                break
        sec = _pick(user, "sec_uid", "sec_user_id", "secUid")
        if not sec or sec in seen:
            return
        nick = _pick(user, "nickname", "nick_name", "unique_id", "short_id")
        if not nick:
            return
        seen.add(sec)
        row = _normalize_user(user)
        if row:
            out.append(row)

    def walk(node, depth=0):
        if depth > 8 or node is None:
            return
        node = _maybe_json(node)
        if isinstance(node, list):
            for row in node:
                walk(row, depth + 1)
            return
        if not isinstance(node, dict):
            return
        ntype = node.get("type")
        card = str(node.get("card_unique_name") or node.get("card_id") or node.get("card_name") or "").lower()
        userish = (
            ntype in (2, 4, 14, 16, 999, 1005, "2", "4", "14", "16", "999", "1005")
            or "user" in card
            or "star" in card
            or "celeb" in card
            or node.get("user_list")
            or node.get("user_info")
        )
        if userish:
            for key in (
                "user_list",
                "users",
                "user_info",
                "user",
                "common_aladdin",
                "display",
                "star_info",
                "famous_user",
            ):
                val = node.get(key)
                if isinstance(val, list):
                    for row in val:
                        add(row)
                elif isinstance(val, dict):
                    add(val)
        if _pick(node, "sec_uid", "sec_user_id", "secUid") and _pick(node, "nickname", "unique_id"):
            if not node.get("aweme_id") and not node.get("video"):
                add(node)
        for key in (
            "data",
            "user_list",
            "users",
            "business_data",
            "card_info",
            "cards",
            "common_aladdin",
            "display",
        ):
            if key in node:
                walk(node.get(key), depth + 1)

    walk(data)
    return out


def _merge_users(left, right):
    seen = set()
    out = []
    for row in list(left or []) + list(right or []):
        if not isinstance(row, dict):
            continue
        sec = str(row.get("sec_uid") or "")
        if not sec or sec in seen:
            continue
        seen.add(sec)
        out.append(row)
    return out


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _pick(node, *keys):
    if not isinstance(node, dict):
        return ""
    for key in keys:
        val = node.get(key)
        if val is None or isinstance(val, (dict, list, bool)):
            continue
        text = str(val).strip()
        if text:
            return text
    return ""


def _safe_int(value, default=0):
    if value is None or value is False or isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    if isinstance(value, dict):
        for key in ("count", "value", "min"):
            if key in value:
                return _safe_int(value.get(key), default)
        return default
    text = str(value).strip().replace(",", "")
    if not text:
        return default
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return default


def _author_node(item):
    item = _as_dict(item)
    for key in ("author", "author_info", "authorInfo", "user_info", "user"):
        node = item.get(key)
        if isinstance(node, dict) and (
            node.get("sec_uid")
            or node.get("sec_user_id")
            or node.get("secUid")
            or node.get("nickname")
            or node.get("uid")
        ):
            return node
    return {}


def _normalize_user(user):
    user = _as_dict(user)
    nick = _pick(user, "nickname", "nick_name", "unique_id", "short_id") or "抖音用户"
    fans = _safe_int(user.get("follower_count") or user.get("mplatform_followers_count"))
    works = _safe_int(user.get("aweme_count"))
    sig = _pick(user, "signature")
    uid_show = _pick(user, "unique_id", "short_id", "custom_verify")
    plot_bits = []
    if uid_show and uid_show != nick:
        plot_bits.append("抖音号 %s" % uid_show)
    if fans:
        plot_bits.append("粉丝 %s" % _human(fans))
    if works:
        plot_bits.append("作品 %s" % _human(works))
    if sig:
        plot_bits.append(sig)
    avatar = _first_url(
        user.get("avatar_thumb") or user.get("avatar_medium") or user.get("avatar_larger") or user.get("avatar") or {}
    )
    return {
        "kind": "user",
        "sec_uid": _pick(user, "sec_uid", "sec_user_id", "secUid"),
        "uid": _pick(user, "uid", "id", "user_id"),
        "author": nick,
        "title": "[用户] %s" % nick,
        "nickname": nick,
        "avatar": avatar,
        "cover": avatar,
        "plot": "  ·  ".join(plot_bits) or "进入作者主页看作品",
        "aweme_id": "",
        "video_id": "",
        "likes": fans,
        "create_time": _safe_int(time.time()),
        "duration": 0,
    }


def _is_video(item):
    play = _play_node(_as_dict((item or {}).get("video")))
    return _is_search_video(item) and bool(play.get("uri") or (play.get("url_list") or [None])[0])


def _is_search_video(item):
    item = _as_dict(item)
    if not (item.get("aweme_id") or item.get("awemeId")):
        return False
    if item.get("aweme_type") in (2, 68, 101, "2", "68", "101"):
        return False
    if item.get("images") and not _as_dict(item.get("video")):
        return False
    return True


def _play_node(video):
    if not isinstance(video, dict):
        return {}
    h264 = _as_dict(video.get("play_addr_h264"))
    if h264.get("uri") or (h264.get("url_list") or [None])[0]:
        return h264
    for bitrate in video.get("bit_rate") or []:
        if not isinstance(bitrate, dict):
            continue
        if bitrate.get("is_h265") or bitrate.get("is_bytevc1"):
            continue
        node = _as_dict(bitrate.get("play_addr"))
        if node.get("uri") or (node.get("url_list") or [None])[0]:
            return node
    for bitrate in video.get("bit_rate") or []:
        if not isinstance(bitrate, dict):
            continue
        node = _as_dict(bitrate.get("play_addr"))
        if node.get("uri") or (node.get("url_list") or [None])[0]:
            return node
    for key in ("play_addr", "play_addr_h264", "play_addr_bytevc1", "download_addr"):
        node = _as_dict(video.get(key))
        if node.get("uri") or (node.get("url_list") or [None])[0]:
            return node
    return {}


def _first_url(node):
    if isinstance(node, str):
        return node.strip()
    if not isinstance(node, dict):
        return ""
    urls = node.get("url_list") or []
    return urls[0] if urls else ""


def _parse_hot_words(data):
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    rows = (payload.get("word_list") if isinstance(payload, dict) else None) or data.get("word_list") or []
    out = []
    for i, row in enumerate(rows, 1):
        word = (row.get("word") or "").strip()
        if not word:
            continue
        cover = ""
        urls = ((row.get("word_cover") or {}).get("url_list")) or []
        if urls:
            cover = urls[0]
        out.append(
            {
                "rank": int(row.get("position") or i),
                "word": word,
                "hot_value": int(row.get("hot_value") or 0),
                "sentence_id": str(row.get("sentence_id") or ""),
                "video_count": int(row.get("video_count") or 0),
                "cover": cover,
                "label": int(row.get("label") or 0),
            }
        )
    return out


def _safe_normalize(item):
    try:
        row = _normalize(item)
    except Exception:
        return None
    if not row or not row.get("aweme_id"):
        return None
    return row


def _normalize(item):
    item = _as_dict(item)
    author = _author_node(item)
    video = _as_dict(item.get("video"))
    play = _play_node(video)
    cover = video.get("cover") or video.get("origin_cover") or {}
    stats = _as_dict(item.get("statistics"))
    desc = _pick(item, "desc", "description", "title")
    nick = _pick(author, "nickname", "nick_name", "unique_id") or "抖音用户"
    title = desc if desc else ("@%s 的视频" % nick)
    if len(title) > 80:
        title = title[:77] + "…"
    duration_ms = _safe_int(video.get("duration") or item.get("duration"))
    duration = duration_ms // 1000 if duration_ms > 1000 else duration_ms
    likes = _safe_int(stats.get("digg_count"))
    comments = _safe_int(stats.get("comment_count"))
    plot_bits = [desc or title, "@%s" % nick]
    if likes:
        plot_bits.append("赞 %s" % _human(likes))
    if comments:
        plot_bits.append("评 %s" % _human(comments))
    return {
        "aweme_id": _pick(item, "aweme_id", "awemeId"),
        "video_id": str(play.get("uri") or ""),
        "title": title,
        "plot": "  ·  ".join(plot_bits),
        "author": nick,
        "uid": _pick(author, "uid", "id", "user_id") or _pick(item, "uid", "user_id"),
        "sec_uid": _pick(author, "sec_uid", "sec_user_id", "secUid") or _pick(item, "sec_uid", "sec_user_id"),
        "avatar": _first_url(author.get("avatar_thumb") or author.get("avatar_medium") or {}),
        "cover": _first_url(cover),
        "duration": duration,
        "width": _safe_int(video.get("width")),
        "height": _safe_int(video.get("height")),
        "likes": likes,
        "create_time": _safe_int(item.get("create_time"), int(time.time())),
    }



def _human(n):
    n = int(n or 0)
    if n >= 100000000:
        return "%.1f亿" % (n / 100000000.0)
    if n >= 10000:
        return "%.1f万" % (n / 10000.0)
    return str(n)
