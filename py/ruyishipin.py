import re
import os
import json
import time
import threading
import urllib.parse
from urllib.parse import quote, unquote, urljoin
import importlib.util

import requests
import urllib3
urllib3.disable_warnings()

# 只有存在 Brotli 解码器时才声明 br，否则响应体无法解压
_ACCEPT_ENCODING = "gzip, deflate"
if importlib.util.find_spec("brotli") is not None or importlib.util.find_spec("brotlicffi") is not None:
    _ACCEPT_ENCODING += ", br"

class Spider:

    _TIMEOUT = 20
    _PAGE_SIZE = 24
    # 线路名与 chapters.resource_url 的 key：1=普快线路，21=超快线路
    _SOURCES = [("普快线路", "1"), ("超快线路", "21")]
    _SORTS = [("最新", "new"), ("人气", "hot"), ("评分", "score")]
    _FILTER_FIELDS = [("tag", "类型"), ("area", "地区"), ("year", "年代"),
                      ("source", "线路"), ("status", "状态")]
    _CHANNELS = [("2", "电视剧"), ("1", "电影"), ("3", "综艺"),
                 ("4", "动漫"), ("32", "纪录片")]
    _AREA_NAMES = ("国产", "欧美", "日本", "香港", "韩国", "泰国",
                   "台湾", "英国", "东南亚", "其它", "其他")
    _UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")

    def __init__(self):
        self.host = "https://rysp.tv"
        self.ua = self._UA
        self.headers = {
            "User-Agent": self.ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": _ACCEPT_ENCODING,
            "Accept-Priority": "u=0, i",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="154", "Google Chrome";v="154"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Referer": self.host + "/",
        }
        self.categories = [{"type_id": cid, "type_name": name} for cid, name in self._CHANNELS]
        self.filters = {cid: [] for cid, _ in self._CHANNELS}
        self._cookie_lock = threading.Lock()
        self._session = None
        self._sess = None
        self._filter_cache_file = None
        self._filter_cache_data = None
        self._hot_data = None
        self._mcache = {}

    # ---------- 基础接口 ----------
    def getName(self):
        return "如意视频"

    def getDependence(self):
        return []

    def init(self, extend=""):
        ext = {}
        try:
            if isinstance(extend, str) and extend.strip()[:1] == "{":
                ext = json.loads(extend)
            elif isinstance(extend, dict):
                ext = extend
        except Exception:
            ext = {}
        if not isinstance(ext, dict):
            ext = {}
        if ext.get("host"):
            try:
                self.host = str(ext.get("host")).rstrip("/")
                self.headers["Referer"] = self.host + "/"
            except Exception:
                pass
        if ext.get("ua"):
            try:
                self.ua = str(ext.get("ua"))
                self.headers["User-Agent"] = self.ua
            except Exception:
                pass
        self.s = self.session
        self.session = self.sess = self.s
        try:
            self._mcache.clear()
        except Exception:
            pass
        try:
            self._filter_cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                   ".rysp_filter_cache.json")
        except Exception:
            self._filter_cache_file = None
        return None

    # ---------- 会话 ----------
    @property
    def session(self):
        if self._session is None:
            with self._cookie_lock:
                if self._session is None:
                    s = requests.Session()
                    try:
                        s.headers.clear()
                    except Exception:
                        pass
                    try:
                        ua = ""
                        try:
                            ua = self.headers.get("User-Agent", "")
                        except Exception:
                            ua = ""
                        if not ua:
                            ua = self._UA
                        s.headers.update({"User-Agent": ua, "Accept-Language": "zh-CN,zh;q=0.9"})
                    except Exception:
                        pass
                    try:
                        s.verify = False
                    except Exception:
                        pass
                    self._session = s
        return self._session

    @session.setter
    def session(self, value):
        self._session = value

    @property
    def sess(self):
        return self.session

    @sess.setter
    def sess(self, value):
        self._session = value

    def _page_header(self, referer=None):
        try:
            ua = self.headers.get("User-Agent", "")
        except Exception:
            ua = ""
        if not ua:
            ua = self._UA
        ref = str(referer or "").strip()
        if not ref.startswith("http"):
            ref = self.host + "/"
        return {"User-Agent": ua, "Accept-Language": "zh-CN,zh;q=0.9", "Referer": ref}

    def _get(self, path, referer=None, xhr=False):
        hd = self._page_header(referer or (self.host + "/video/list?channel_id=1"))
        if xhr:
            hd["X-Requested-With"] = "XMLHttpRequest"
            hd["Accept"] = "application/json, text/javascript, */*; q=0.01"
            hd["Sec-Fetch-Dest"] = "empty"
            hd["Sec-Fetch-Mode"] = "cors"
            hd["Sec-Fetch-Site"] = "same-origin"
        last = None
        for attempt in range(3):
            try:
                r = self.session.get(self.host + path, headers=hd, timeout=self._TIMEOUT, verify=False)
                r.raise_for_status()
                try:
                    r.encoding = r.apparent_encoding or "utf-8"
                except Exception:
                    r.encoding = "utf-8"
                return r.text
            except Exception as e:
                last = e
                try:
                    time.sleep(0.6 * (attempt + 1))
                except Exception:
                    pass
        raise last

    def _json(self, path, referer=None):
        return json.loads(self._get(path, referer, xhr=True))

    def _cate_json(self, **params):
        q = {"page_num": 1, "page_size": self._PAGE_SIZE, "sort": "new", "sorttype": "desc",
             "channel_id": "", "tag": "", "area": "", "year": "", "source": "", "status": ""}
        try:
            q.update(params or {})
            data = self._json("/video/refresh-cate?" + urllib.parse.urlencode(q, doseq=True))
            if isinstance(data, dict) and isinstance(data.get("data"), dict):
                return data["data"]
            return {}
        except Exception:
            raise

    # ---------- 筛选器 ----------
    def _read_filter_box(self, search_box):
        box = {}
        try:
            if not isinstance(search_box, (list, tuple)):
                return {}
            for grp in search_box:
                try:
                    if not isinstance(grp, dict):
                        continue
                    field = grp.get("field")
                    if not field or field == "sort" or field in box:
                        continue
                    lst = grp.get("list")
                    if not isinstance(lst, (list, tuple)):
                        continue
                    vals = []
                    for x in lst:
                        try:
                            if not isinstance(x, dict):
                                continue
                            if x.get("display") == "全部":
                                continue
                            vals.append({"n": str(x.get("display") or ""), "v": str(x.get("value") if x.get("value") is not None else "")})
                        except Exception:
                            continue
                    box[field] = vals
                except Exception:
                    continue
        except Exception:
            return box
        return box

    def _build_filters(self):
        try:
            data = self._cate_json(page_size=1) or {}
        except Exception:
            data = {}
        box = self._read_filter_box((data or {}).get("search_box") or [])
        out = {}
        for cid, _ in self._CHANNELS:
            groups = [{"key": "sort", "name": "排序", "value":
                       [{"n": n, "v": v} for n, v in self._SORTS]}]
            for field, label in self._FILTER_FIELDS:
                try:
                    values = box.get(field) or []
                    if not values:
                        try:
                            d2 = self._cate_json(channel_id=cid, page_size=1) or {}
                            values = self._read_filter_box(d2.get("search_box") or []).get(field) or []
                        except Exception:
                            values = []
                    if values:
                        groups.append({"key": field, "name": label, "value": values})
                except Exception:
                    continue
            out[cid] = groups
        return out

    def _load_filters(self):
        if self._filter_cache_data is not None:
            return self._filter_cache_data
        path = self._filter_cache_file
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("date") == time.strftime("%Y%m%d") and isinstance(data.get("filters"), dict):
                    self._filter_cache_data = data["filters"]
                    return self._filter_cache_data
            except Exception:
                pass
        out = self._build_filters()
        self._filter_cache_data = out
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"date": time.strftime("%Y%m%d"), "filters": out}, f, ensure_ascii=False)
            except Exception:
                pass
        return out

    # ---------- 首页 ----------
    def homeContent(self, filter=None):
        try:
            self.filters = self._load_filters()
        except Exception:
            self.filters = {cid: [] for cid, _ in self._CHANNELS}
        try:
            hot = self.homeVideoContent().get("list") or []
        except Exception:
            hot = []
        return {"class": self.categories, "list": hot, "filters": self.filters}

    def homeVideoContent(self):
        try:
            if self._hot_data is None:
                data = self._cate_json(page_size=24, sort="hot")
                self._hot_data = (data or {}).get("list") or []
            return {"list": self._cards(self._hot_data or [])}
        except Exception:
            return {"list": []}

    # ---------- 分类列表 ----------
    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        if not isinstance(extend, dict):
            extend = dict()
        page = self._safe_page(pg, 1)
        tid = str(tid or "").strip()
        try:
            data = self._cate_json(channel_id=tid, page_num=page,
                                   sort=self._ext(extend, "sort") or "new",
                                   tag=self._ext(extend, "tag"), area=self._ext(extend, "area"),
                                   year=self._ext(extend, "year"), source=self._ext(extend, "source"),
                                   status=self._ext(extend, "status"))
        except Exception:
            return {"page": page, "pagecount": 1,
                    "limit": self._PAGE_SIZE, "total": 0, "list": []}
        try:
            cards = self._cards((data or {}).get("list") or [])
        except Exception:
            cards = []
        data = data or {}
        total = data.get("total_count") or 0
        try:
            cur = int(data.get("current_page") or page)
        except Exception:
            cur = page
        try:
            pcount = int(data.get("total_page") or 1)
        except Exception:
            pcount = 1
        if pcount < 1:
            pcount = 1
        return {"page": cur, "pagecount": pcount,
                "limit": self._PAGE_SIZE, "total": total,
                "list": cards}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick=False, pg="1"):
        key = "" if key is None else str(key)
        page = self._safe_page(pg, 1)
        if not key.strip():
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": self._PAGE_SIZE, "total": 0}
        q = urllib.parse.urlencode({"keyword": key, "page_num": page,
                                    "page_size": self._PAGE_SIZE, "sort": "new",
                                    "sorttype": "desc", "type": ""})
        try:
            html = self._get("/video/refresh-video?" + q, xhr=True,
                             referer=self.host + "/video/search-result?keyword=" + urllib.parse.quote(key))
        except Exception:
            return {"list": [], "page": page, "pagecount": 1,
                    "limit": self._PAGE_SIZE, "total": 0}
        try:
            cards = self._cards_from_html(html)
        except Exception:
            cards = []
        return {"list": cards, "page": page, "pagecount": page + (1 if cards else 0),
                "limit": self._PAGE_SIZE, "total": len(cards)}

    # ---------- 详情 ----------
    def _empty_vod(self, vid):
        return {"vod_id": vid, "vod_name": "", "vod_pic": "",
                "vod_remarks": "", "type_name": "", "vod_class": "",
                "vod_year": "", "vod_area": "", "vod_actor": "",
                "vod_director": "", "vod_content": "",
                "vod_play_from": "", "vod_play_url": ""}

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            vid = str(ids[0]) if ids and ids[0] is not None else ""
        else:
            vid = "" if ids is None else str(ids)
        vid = vid.split("$$")[0].strip()
        if not vid:
            return {"list": [self._empty_vod("")]}
        try:
            page = self._get("/video/detail?video_id=" + urllib.parse.quote(vid))
        except Exception:
            return {"list": [self._empty_vod(vid)]}
        try:
            info = self._info_of(page, vid)
        except Exception:
            info = {"name": vid, "pic": "", "score": "", "types": "",
                    "year": "", "area": "", "actor": "", "director": "", "intro": ""}
        try:
            chapters = self._chapters_of(page)
        except Exception:
            chapters = []
        if not isinstance(chapters, list):
            chapters = []
        names = []
        groups = []
        for name, key in self._SOURCES:
            eps = []
            for idx, ch in enumerate(chapters, 1):
                if not isinstance(ch, dict):
                    continue
                try:
                    ru = ch.get("resource_url") or {}
                    if not isinstance(ru, dict):
                        continue
                    url = ru.get(key)
                except Exception:
                    continue
                if url:
                    try:
                        eps.append("%s$%s" % (self._ep_name(ch, idx), str(url).strip()))
                    except Exception:
                        continue
            if eps:
                names.append(name)
                groups.append("#".join(eps))
        return {"list": [{
            "vod_id": vid,
            "vod_name": info.get("name", ""),
            "vod_pic": info.get("pic", ""),
            "vod_remarks": info.get("score", ""),
            "type_name": info.get("types", ""),
            "vod_class": info.get("types", ""),
            "vod_year": info.get("year", ""),
            "vod_area": info.get("area", ""),
            "vod_actor": info.get("actor", ""),
            "vod_director": info.get("director", ""),
            "vod_content": info.get("intro", ""),
            "vod_play_from": "$$$".join(names),
            "vod_play_url": "$$$".join(groups),
        }]}

    def _chapters_of(self, page):
        try:
            if not isinstance(page, str) or not page:
                return []
            # 详情页内嵌完整章节数组：// console.log([{...}])
            i = page.find("// console.log([{")
            if i < 0:
                return []
            start = page.index("[", i)
            end = self._match_bracket(page, start)
            if end <= start:
                return []
            data = json.loads(page[start:end + 1])
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _match_bracket(self, s, start):
        try:
            if not isinstance(s, str) or not isinstance(start, int):
                return -1
            if start < 0 or start >= len(s):
                return -1
            depth = 0
            in_str = False
            esc = False
            for k in range(start, len(s)):
                c = s[k]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                    continue
                if c == '"':
                    in_str = True
                elif c in "[{":
                    depth += 1
                elif c in "]}":
                    depth -= 1
                    if depth == 0:
                        return k
            return -1
        except Exception:
            return -1

    def _info_of(self, page, vid):
        if not isinstance(page, str):
            page = ""
        if not isinstance(vid, str):
            try:
                vid = str(vid)
            except Exception:
                vid = ""
        try:
            name = ""
            m = re.search(r'<div class="play-name"[^>]*>\s*([^<]{1,80}?)\s*</div>', page)
            if m:
                name = self._text(m.group(1))
            if not name:
                m = re.search(r"<title>\s*(.*?)\s*-\s*如意视频", page, re.S)
                name = self._text(m.group(1)) if m else vid
            tags = []
            m = re.search(r'<div class="GNbox-type"[^>]*>([\s\S]*?)</div>', page)
            if m:
                try:
                    tags = [self._text(x) for x in re.findall(r"<span[^>]*>([\s\S]*?)</span>", m.group(1))]
                except Exception:
                    tags = []
            tags = [t for t in tags if t]
            year = next((t for t in tags if re.fullmatch(r"\d{4}", t or "")), "")
            area = ""
            cls = []
            for t in tags:
                if t == year:
                    continue
                if t in self._AREA_NAMES:
                    area = t
                else:
                    cls.append(t)
            pic = ""
            m = re.search(r'<div class="GNbox-xq-img"[\s\S]{0,400}?originalSrc="([^"]+)"', page)
            if m:
                try:
                    pic = self._fix_url(m.group(1))
                except Exception:
                    pic = ""
            score = ""
            m = re.search(r'<div class="GNbox-PF"[^>]*>\s*<span>([\d.]+)</span>', page)
            if m:
                score = m.group(1)
            return {"name": name, "pic": pic, "score": score,
                    "types": " ".join(cls), "year": year, "area": area,
                    "actor": self._field(page, "主演"),
                    "director": self._field(page, "导演"),
                    "intro": self._field(page, "简介")}
        except Exception:
            return {"name": vid, "pic": "", "score": "", "types": "",
                    "year": "", "area": "", "actor": "", "director": "", "intro": ""}

    def _field(self, page, label):
        try:
            if not isinstance(page, str) or not isinstance(label, str):
                return ""
            m = re.search(label + r"[：:]\s*<span>\s*([\s\S]*?)\s*</span>", page)
            return self._text(m.group(1)) if m else ""
        except Exception:
            return ""

    def _ep_name(self, ch, index):
        try:
            if isinstance(ch, dict):
                name = (ch.get("title") or "")
                if not isinstance(name, str):
                    name = str(name)
                name = name.strip()
                if name:
                    return name
        except Exception:
            pass
        try:
            return "第%02d集" % int(index)
        except Exception:
            return "正片"

    # ---------- 播放 ----------
    def getProxyUrl(self, local=True):
        try:
            from com.github.catvod import Proxy as _CatProxy
            try:
                return str(_CatProxy.getUrl(local)) + "?do=py"
            except Exception:
                return str(_CatProxy.getUrl()) + "?do=py"
        except Exception:
            pass
        return "http://127.0.0.1:9978/proxy?do=py"

    def _proxy_root(self):
        try:
            u = self.getProxyUrl(True)
            if u:
                return str(u)
        except Exception:
            pass
        return "http://127.0.0.1:9978/proxy?do=py"

    def _proxy_url(self, url, kind="media", referer=None):
        root = self._proxy_root()
        sep = "&" if "?" in root else "?"
        u = root + sep + "type=" + kind + "&url=" + quote(str(url or ""), safe="")
        try:
            ref = "" if referer is None else str(referer).strip()
        except Exception:
            ref = ""
        if ref.startswith("http"):
            u += "&referer=" + quote(ref, safe="")
        return u

    def _browser_base(self):
        try:
            ua = self.headers.get("User-Agent", "")
        except Exception:
            ua = ""
        if not ua:
            ua = self._UA
        return {"User-Agent": ua, "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9"}

    def _media_header(self, url="", referer=""):
        try:
            h = self._browser_base()
        except Exception:
            h = {"User-Agent": self._UA, "Accept": "*/*"}
        try:
            h["Origin"] = self.host
            ref = "" if referer is None else str(referer).strip()
            h["Referer"] = ref if ref.startswith("http") else (self.host + "/")
        except Exception:
            pass
        return h

    def _fetch_bin(self, url, head, timeout=15):
        for _ in range(3):
            try:
                r = self.session.get(url, headers=head, timeout=timeout, verify=False)
                if r.status_code == 200 and r.content:
                    return r
            except Exception:
                continue
        return None

    def _sub_url(self, url, body):
        try:
            m = re.search(r'#EXT-X-STREAM-INF[^\n]*\n\s*([^\n#]+)', body or "")
            if not m:
                return ""
            path = m.group(1).strip()
            return path if path.startswith("http") else urljoin(url, path)
        except Exception:
            return ""

    def _playlist(self, url, head):
        r = self._fetch_bin(url, head, 20)
        base = url
        if r is None:
            return url, ""
        try:
            text = r.text
        except Exception:
            text = ""
        if not text or "#EXTINF" not in text:
            return base, (text or "")
        if "#EXT-X-STREAM-INF" not in text:
            return base, text
        sub = self._sub_url(base, text)
        if not sub:
            return base, text
        r2 = self._fetch_bin(sub, head, 20)
        try:
            t2 = r2.text if r2 is not None else ""
        except Exception:
            t2 = ""
        if r2 is None or "#EXTINF" not in t2:
            return base, text
        try:
            self._mcache[url] = sub
            self._mcache[base] = sub
        except Exception:
            pass
        return sub, t2

    def _rewrite_m3u8(self, text, base, referer=""):
        root = self._proxy_root()
        sep = "&" if "?" in root else "?"
        try:
            ref = "" if referer is None else str(referer).strip()
        except Exception:
            ref = ""
        if not ref.startswith("http"):
            ref = ""
        out = []
        for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = raw.strip()
            if not line:
                out.append("")
                continue
            if line.startswith("#"):
                if "URI=" in line:
                    def _rp(m):
                        v = m.group(2)
                        if not v.startswith("http"):
                            v = urljoin(base, v)
                        if ref:
                            return m.group(1) + self._proxy_url(v, "media", ref) + m.group(3)
                        return m.group(1) + self._proxy_url(v, "media") + m.group(3)
                    try:
                        line = re.sub(r'(URI=")([^"]+)(")', _rp, line)
                    except Exception:
                        pass
                out.append(line)
                continue
            a = line if line.startswith("http") else urljoin(base, line)
            if ref:
                out.append(root + sep + "type=ts&url=" + quote(a, safe="") + "&referer=" + quote(ref, safe=""))
            else:
                out.append(root + sep + "type=ts&url=" + quote(a, safe=""))
        body = "\n".join(out)
        return body if body.endswith("\n") else body + "\n"

    def _play(self, raw):
        try:
            real = str(raw or "").strip()
        except Exception:
            real = ""
        if not real:
            return {"parse": 1, "jx": 0, "playUrl": "", "url": "", "header": self._media_header()}
        if not self._is_media(real):
            return {"parse": 1, "jx": 0, "playUrl": "", "url": real, "header": self._media_header()}
        return {"parse": 0, "jx": 0, "playUrl": "", "url": self._proxy_url(real, "m3u8"), "header": self._media_header(real), "format": "application/x-mpegURL"}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            url = "" if id is None else str(id)
        except Exception:
            url = ""
        url = url.strip()
        if url.startswith("//"):
            url = "https:" + url
        try:
            media = self._is_media(url)
        except Exception:
            media = False
        if not media:
            return {"parse": 1, "jx": 0, "playUrl": "", "url": url, "header": self._media_header()}
        try:
            base, body = self._playlist(url, self._media_header(url))
        except Exception:
            base, body = url, ""
        if body and "#EXTINF" in body:
            try:
                data = self._rewrite_m3u8(body, base, self.host + "/")
            except Exception:
                data = ""
            if data:
                return {"parse": 0, "jx": 0, "playUrl": "", "url": self._proxy_url(base, "m3u8"), "header": self._media_header(base), "format": "application/x-mpegURL"}
        return self._play(url)

    def localProxy(self, param):
        try:
            if isinstance(param, str):
                try:
                    param = json.loads(param)
                except Exception:
                    param = dict()
            if not isinstance(param, dict):
                param = dict()
            else:
                param = dict(param)
            kind = param.get("type") or param.get("action") or param.get("do") or ""
            if isinstance(kind, list):
                kind = kind[0] if kind else ""
            try:
                kind = str(kind or "").strip().lower()
            except Exception:
                kind = ""
            url = param.get("url") or ""
            if isinstance(url, list):
                url = url[0] if url else ""
            referer = param.get("referer") or param.get("ref") or ""
            if isinstance(referer, list):
                referer = referer[0] if referer else ""
            try:
                url = unquote(str(url or "")).replace("\\/", "/").strip()
            except Exception:
                url = str(url or "").replace("\\/", "/").strip()
            try:
                referer = unquote(str(referer or "")).strip()
            except Exception:
                referer = str(referer or "").strip()
            if not url:
                return [404, "text/plain", "Not Found"]
            if url.startswith("//"):
                url = "https:" + url
            if not url.startswith("http"):
                return [404, "text/plain", "Unsupported"]
            if not kind or kind in ("py", "proxy", "media"):
                low_all = (url + " " + referer).lower()
                if ".m3u8" in low_all or "m3u8" in low_all:
                    kind = "m3u8"
                else:
                    kind = "ts"
            head = self._media_header(url, referer)
            if kind == "m3u8" or ".m3u8" in url.lower():
                try:
                    base, body = self._playlist(url, head)
                except Exception:
                    base, body = url, ""
                if not body:
                    return [404, "text/plain", "Fetch Failed"]
                try:
                    data = self._rewrite_m3u8(body, base, referer)
                except Exception:
                    try:
                        data = str(body or "")
                    except Exception:
                        data = "Fetch Failed"
                if not data:
                    return [404, "text/plain", "Fetch Failed"]
                return [200, "application/vnd.apple.mpegurl", data]
            try:
                r = self._fetch_bin(url, head, 20)
            except Exception:
                r = None
            if r is None:
                return [404, "text/plain", "Fetch Failed"]
            try:
                body = r.content
            except Exception:
                body = b""
            if not body:
                return [404, "text/plain", "Fetch Failed"]
            mime = "application/octet-stream"
            try:
                if body[:1] == b"\x47":
                    mime = "video/mp2t"
            except Exception:
                mime = "application/octet-stream"
            try:
                if not isinstance(body, (bytes, bytearray)):
                    body = str(body or "").encode("utf-8")
                else:
                    body = bytes(body)
            except Exception:
                return [404, "text/plain", "Fetch Failed"]
            return [200, mime, body]
        except Exception:
            return [500, "text/plain", "proxy error"]

    def _is_media(self, url):
        try:
            low = "" if url is None else str(url).lower()
        except Exception:
            return False
        return ".m3u8" in low or ".mp4" in low or ".flv" in low or ".ts" in low

    def isVideoFormat(self, url):
        return self._is_media(url)

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return dict()

    def destroy(self):
        try:
            with self._cookie_lock:
                if self._session is not None:
                    try:
                        self._session.close()
                    except Exception:
                        pass
                    self._session = None
        except Exception:
            self._session = None
        try:
            self._mcache.clear()
        except Exception:
            pass
        self._filter_cache_data = None
        self._hot_data = None
        return None

    # ---------- 辅助 ----------
    def _fix_url(self, url):
        try:
            if url is None:
                return ""
            if not isinstance(url, str):
                url = str(url)
            url = url.strip()
            if not url:
                return ""
            if url.startswith("//"):
                return "https:" + url
            if url.startswith("/"):
                return self.host.rstrip("/") + url
            return url
        except Exception:
            return ""

    def _safe_page(self, pg, default=1):
        try:
            return max(int(str(pg if pg is not None else default).strip() or default), 1)
        except Exception:
            return default

    def _ext(self, extend, key):
        try:
            v = (extend or {}).get(key, "")
        except Exception:
            return ""
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            v = v[0] if v else ""
        return str(v).strip()

    def liveContent(self, url):
        return ""

    def proxy(self, param):
        return self.localProxy(param)

    def _text(self, s):
        if s is None:
            return ""
        if not isinstance(s, str):
            try:
                s = str(s)
            except Exception:
                return ""
        s = re.sub(r"<[^>]+>", " ", s or "")
        s = s.replace("&nbsp;", " ").replace("&amp;", "&")
        s = s.replace(chr(38) + "quot;", '"').replace("&#39;", "'")
        s = s.replace("&lt;", "<").replace("&gt;", ">")
        return re.sub(r"\s+", " ", s).strip()

    def _cards(self, items):
        out = []
        seen = set()
        try:
            if not isinstance(items, (list, tuple)):
                return []
            for it in items:
                try:
                    if not isinstance(it, dict):
                        continue
                    vid = it.get("video_id")
                    vid = "" if vid is None else str(vid).strip()
                    if not vid or vid in seen:
                        continue
                    seen.add(vid)
                    remark = it.get("score")
                    remark = "" if remark is None else str(remark).strip()
                    hot = it.get("play_times")
                    hot = "" if hot is None else str(hot).strip()
                    out.append({
                        "vod_id": vid,
                        "vod_name": self._text(it.get("video_name") or ""),
                        "vod_pic": self._fix_url(it.get("cover") or ""),
                        "vod_remarks": ("评分%s" % remark) if remark else hot,
                        "vod_class": self._text(it.get("category") or ""),
                        "vod_year": "",
                        "vod_area": "",
                        "vod_actor": self._text(it.get("artist") or "").replace("演员:", "").strip()[:120],
                        "vod_director": self._text(it.get("director") or "").replace("导演:", "").strip()[:60],
                        "vod_content": self._text(it.get("intro") or ""),
                    })
                except Exception:
                    continue
        except Exception:
            return out
        return out

    def _cards_from_html(self, html):
        out = []
        seen = set()
        try:
            if not isinstance(html, str) or not html:
                return []
            blocks = html.split('<li class="Movie-list">')[1:]
            if not blocks:
                try:
                    blocks = re.findall(r'<li[^>]*class="[^"]*Movie-list[^"]*"[\s\S]{0,4000}?</li>', html)
                except Exception:
                    blocks = []
            for blk in blocks:
                try:
                    if not isinstance(blk, str) or not blk:
                        continue
                    vid = re.search(r'video_id=(\d+)', blk)
                    if not vid:
                        continue
                    if vid.group(1) in seen:
                        continue
                    seen.add(vid.group(1))
                    name = re.search(r'Movie-name01[^>]*>\s*([^<]+)', blk)
                    pic = re.search(r'(?:originalSrc|data-src|src)="(https?://[^"]+\.(?:jpg|jpeg|png|webp|gif))"', blk)
                    score = re.search(r'class="oth-time"[\s\S]{0,160}?>\s*([\d.]+)\s*<', blk)
                    cat = re.search(r'<ul[^>]*class="[^"]*Movie-type[^"]*"[\s\S]*?</ul>', blk)
                    actor = re.search(r'Movie-star[\s\S]{0,2000}?主演[：:]\s*([\s\S]{0,600}?)</div>', blk)
                    intro = re.search(r'Movie-content[\s\S]{0,2400}?简介[：:]\s*([\s\S]{0,900}?)</span>', blk)
                    hot = re.search(r'热度[：:]\s*([\d.]+)', blk)
                    out.append({
                        "vod_id": vid.group(1),
                        "vod_name": self._text(name.group(1)) if name else "",
                        "vod_pic": self._fix_url(pic.group(1)) if pic else "",
                        "vod_remarks": ("评分%s" % score.group(1)) if score else (("热度%s" % hot.group(1)) if hot else ""),
                        "vod_class": self._text(cat.group(0)) if cat else "",
                        "vod_year": "",
                        "vod_area": "",
                        "vod_actor": self._text(actor.group(1))[:120] if actor else "",
                        "vod_director": "",
                        "vod_content": self._text(intro.group(1))[:400] if intro else "",
                    })
                except Exception:
                    continue
        except Exception:
            return out
        return out
