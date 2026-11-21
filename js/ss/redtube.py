# -*- coding: utf-8 -*-
import re
import json
import html as html_lib
import threading
from urllib.parse import quote, quote_plus, unquote, urljoin
import requests
import urllib3
urllib3.disable_warnings()


class Spider:
    def __init__(self):
        self.host = "https://www.redtube.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self.classes = [
            {"type_id": "home", "type_name": "最新推荐"},
            {"type_id": "redtube/amateur", "type_name": "业余自拍"},
            {"type_id": "redtube/verifiedamateurs", "type_name": "验证业余"},
            {"type_id": "redtube/hd", "type_name": "高清"},
            {"type_id": "redtube/teens", "type_name": "少女"},
            {"type_id": "redtube/milf", "type_name": "熟女"},
            {"type_id": "redtube/mature", "type_name": "成熟"},
            {"type_id": "redtube/blonde", "type_name": "金发"},
            {"type_id": "redtube/brunette", "type_name": "褐发"},
            {"type_id": "redtube/asian", "type_name": "亚洲"},
            {"type_id": "redtube/japanese", "type_name": "日本"},
            {"type_id": "redtube/latina", "type_name": "拉丁"},
            {"type_id": "redtube/ebony", "type_name": "黑人"},
            {"type_id": "redtube/anal", "type_name": "肛交"},
            {"type_id": "redtube/blowjob", "type_name": "口交"},
            {"type_id": "redtube/bigtits", "type_name": "巨乳"},
            {"type_id": "redtube/creampie", "type_name": "内射"},
            {"type_id": "redtube/cumshot", "type_name": "颜射"},
            {"type_id": "redtube/interracial", "type_name": "跨种族"},
            {"type_id": "redtube/lesbian", "type_name": "女同"},
            {"type_id": "redtube/pov", "type_name": "第一视角"},
            {"type_id": "redtube/public", "type_name": "公共场合"},
            {"type_id": "redtube/threesome", "type_name": "三人行"},
            {"type_id": "redtube/massage", "type_name": "按摩"},
            {"type_id": "redtube/lingerie", "type_name": "内衣"},
            {"type_id": "redtube/toys", "type_name": "玩具"},
            {"type_id": "redtube/hentai", "type_name": "动漫"},
            {"type_id": "redtube/vintage", "type_name": "经典"},
            {"type_id": "redtube/webcam", "type_name": "摄像头"},
        ]
        self._lock = threading.Lock()
        self._session = None
        self._mcache = {}

    def getName(self):
        return "RedTube"

    def getDependence(self):
        return []

    def init(self, extend=""):
        ext = {}
        try:
            if isinstance(extend, str) and extend.strip().startswith("{"):
                ext = json.loads(extend)
            elif isinstance(extend, dict):
                ext = extend
        except Exception:
            ext = {}
        if isinstance(ext, dict):
            if ext.get("host"):
                self.host = str(ext.get("host")).rstrip("/")
                self.headers["Referer"] = self.host + "/"
            if ext.get("ua"):
                self.headers["User-Agent"] = str(ext.get("ua"))
        try:
            self._mcache.clear()
        except Exception:
            pass
        return None

    @property
    def session(self):
        if self._session is None:
            with self._lock:
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
                            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        s.headers.update({"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"})
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

    def destroy(self):
        try:
            with self._lock:
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
        return None

    def _page_header(self, referer=None):
        try:
            ua = self.headers.get("User-Agent", "")
        except Exception:
            ua = ""
        if not ua:
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ref = str(referer or "").strip()
        if not ref.startswith("http"):
            ref = self.host + "/"
        return {"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Referer": ref}

    def _get(self, url, referer=None):
        hd = self._page_header(referer or self.host + "/")
        for _ in range(2):
            try:
                r = self.session.get(url, headers=hd, timeout=20, verify=False)
                if r.status_code == 200 and r.text:
                    try:
                        r.encoding = r.apparent_encoding or "utf-8"
                    except Exception:
                        r.encoding = "utf-8"
                    return r.text
            except Exception:
                continue
        return ""

    def _fix(self, u):
        if not u:
            return ""
        u = str(u).strip().replace("&amp;", "&")
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host + u
        return u

    @staticmethod
    def _strip_tags(s):
        try:
            return re.sub(r"<.*?>", "", s or "")
        except Exception:
            return str(s or "")

    @staticmethod
    def _unesc(s):
        try:
            return html_lib.unescape(s or "").strip()
        except Exception:
            return str(s or "").strip()

    @staticmethod
    def _dur_fmt(raw):
        try:
            m = re.match(r"PT(\d+)S$", str(raw or "").strip())
            if m:
                sec = int(m.group(1))
                return "%d:%02d" % (sec // 60, sec % 60)
        except Exception:
            pass
        return str(raw or "")

    def _cards(self, html):
        result, seen = [], set()
        if not html:
            return result
        for m in re.finditer(r'data-video-id="(\d+)"', html):
            vid = m.group(1)
            if vid in seen:
                continue
            name = ""
            try:
                tm = re.search(r'<a[^>]*href="/' + vid + r'"[^>]*class="[^"]*video-title-text[^"]*"[^>]*>(.*?)</a>', html, re.S)
                if not tm:
                    tm = re.search(r'<a[^>]*class="[^"]*video-title-text[^"]*"[^>]*href="/' + vid + r'"[^>]*>(.*?)</a>', html, re.S)
                if tm:
                    name = self._unesc(self._strip_tags(tm.group(1)))
                if not name:
                    tm2 = re.search(r'<a[^>]*href="/' + vid + r'"[^>]*title="([^"]{2,200})"', html)
                    if tm2:
                        name = self._unesc(tm2.group(1))
            except Exception:
                name = ""
            if not name or len(name) < 2:
                continue
            if len(name) > 120:
                name = name[:120]
            pic = ""
            try:
                im = re.search(r'<img[^>]*id="img_[^"]*' + vid + r'"[^>]*>', html)
                blob = im.group(0) if im else ""
                if blob:
                    pm = re.search(r'data-src="([^"]+)"', blob) or re.search(r'data-srcset="([^"]+)"', blob) or re.search(r'src="([^"]+)"', blob)
                    if pm:
                        pic = pm.group(1).split(",")[0].split()[0]
            except Exception:
                pic = ""
            pic = self._fix(pic)
            dur = ""
            try:
                dm = re.search(r'tm_video_duration[^>]*>\s*([\d:]+)', html[m.start():m.start() + 8000])
                if dm:
                    dur = dm.group(1).strip()
            except Exception:
                dur = ""
            seen.add(vid)
            result.append({"vod_id": vid, "vod_name": name, "vod_pic": self._proxy_pic_url(pic) if pic.startswith("http") else pic, "vod_remarks": dur})
        return result

    def _has_next(self, html):
        try:
            if 'rel="next"' in (html or ""):
                return True
            if 'id="wp_navNext"' in (html or "") and "NEXT" in (html or ""):
                return True
        except Exception:
            pass
        return False

    def _filters(self):
        order = [
            {"key": "sorting", "name": "排序", "value": [
                {"n": "最新", "v": "newest"},
                {"n": "最多观看", "v": "mostviewed"},
                {"n": "评分最高", "v": "rating"},
                {"n": "最多收藏", "v": "mostfavored"},
                {"n": "时长最长", "v": "longest"},
                {"n": "精选", "v": "featured"},
            ]},
            {"key": "period", "name": "周期", "value": [
                {"n": "全部", "v": ""},
                {"n": "本周", "v": "weekly"},
                {"n": "本月", "v": "monthly"},
                {"n": "总榜", "v": "alltime"},
            ]},
        ]
        return {c["type_id"]: order for c in self.classes}

    def _list_url(self, tid, page, sorting="", period=""):
        tid = str(tid or "home")
        if tid == "home":
            base = self.host + "/"
        else:
            base = self.host + "/" + tid.strip("/")
        parts = []
        if sorting and tid != "home":
            parts.append("sorting=" + quote(str(sorting)))
            if period and str(sorting) in ("mostviewed", "mostfavored", "rating", "longest"):
                parts.append("period=" + quote(str(period)))
        if page > 1:
            parts.append("page=" + str(page))
        if parts:
            return base + ("&" if "?" in base else "?") + "&".join(parts)
        return base

    def homeContent(self, filter=None):
        html = self._get(self.host + "/")
        vods = self._cards(html)
        return {"class": self.classes, "list": vods[:20], "filters": self._filters()}

    def homeVideoContent(self):
        try:
            return {"list": self.homeContent({})["list"]}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        sorting, period = "", ""
        try:
            src = filter if isinstance(filter, dict) else (extend if isinstance(extend, dict) else {})
            sorting = str(src.get("sorting") or "")
            period = str(src.get("period") or "")
        except Exception:
            sorting, period = "", ""
        url = self._list_url(tid, page, sorting, period)
        html = self._get(url)
        vods = self._cards(html)
        pagecount = page + 1 if self._has_next(html) else page
        return {"page": page, "pagecount": pagecount, "limit": len(vods), "total": 0, "list": vods}

    def _media_json(self, token_url, referer):
        try:
            r = self.session.get(token_url, headers={"User-Agent": self.headers.get("User-Agent", ""), "Referer": referer, "Accept": "application/json,*/*"}, timeout=20, verify=False)
            if r.status_code != 200 or not r.text:
                return None
            txt = r.text.strip()
            if txt.startswith("#EXTM3U"):
                return {"_hls": token_url}
            return json.loads(txt)
        except Exception:
            return None

    def _one_detail(self, vid):
        try:
            vid = str(vid).strip()
            if vid.startswith("http"):
                m = re.search(r'redtube\.com/(\d+)', vid)
                if m:
                    vid = m.group(1)
            page_url = self.host + "/" + vid
            html = self._get(page_url)
            if not html:
                return None
            name = ""
            try:
                m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
                if m:
                    name = self._unesc(m.group(1))
            except Exception:
                pass
            if not name:
                try:
                    m = re.search(r"<title>(.*?)</title>", html, re.S)
                    if m:
                        name = self._unesc(self._strip_tags(m.group(1)).split(" - ")[0])
                except Exception:
                    pass
            if not name:
                name = vid
            pic = ""
            try:
                m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                if m:
                    pic = self._fix(m.group(1))
            except Exception:
                pass
            desc = ""
            try:
                m = re.search(r'<meta property="og:description" content="([^"]+)"', html)
                if m:
                    desc = self._unesc(m.group(1))
            except Exception:
                pass
            dur, views, up = "", "", ""
            try:
                m = re.search(r'<meta property="og:video:duration" content="(\d+)"', html)
                if m:
                    sec = int(m.group(1))
                    dur = "%d:%02d" % (sec // 60, sec % 60)
            except Exception:
                pass
            if not dur:
                try:
                    m = re.search(r'"duration":"(PT\d+S)"', html)
                    if m:
                        dur = self._dur_fmt(m.group(1))
                except Exception:
                    pass
            try:
                m = re.search(r'"interactionCount":(\d+)', html)
                if m:
                    views = m.group(1)
            except Exception:
                pass
            try:
                m = re.search(r'"uploadDate":"([^"]+)"', html)
                if m:
                    up = m.group(1)[:10]
            except Exception:
                pass
            uploader = ""
            try:
                m = re.search(r"Uploaded by ([A-Za-z0-9_\-]+)", desc)
                if m:
                    uploader = m.group(1)
            except Exception:
                pass
            cats = []
            try:
                cats = [self._unesc(t) for _, t in re.findall(r'href="(/redtube/[a-z0-9\-]+)"[^>]*>([^<]{2,30})<', html)]
                cats = [c for c in cats if c and len(c) < 24][:8]
            except Exception:
                cats = []
            hls_tok, mp4_tok = "", ""
            try:
                m = re.search(r'"format":"hls","videoUrl":"([^"]+)"', html)
                if m:
                    hls_tok = self._fix(m.group(1).replace("\\/", "/"))
            except Exception:
                pass
            try:
                m = re.search(r'"format":"mp4","videoUrl":"([^"]+)"', html)
                if m:
                    mp4_tok = self._fix(m.group(1).replace("\\/", "/"))
            except Exception:
                pass
            sources, episodes = [], []
            quals = []
            if mp4_tok:
                data = self._media_json(mp4_tok, page_url)
                if isinstance(data, list):
                    for it in data:
                        try:
                            q = str(it.get("quality") or "").strip()
                            u = str(it.get("videoUrl") or "").replace("\\/", "/").replace("&amp;", "&").strip()
                            if u.startswith("//"):
                                u = "https:" + u
                            if u.startswith("http"):
                                quals.append((q, u))
                        except Exception:
                            continue
                    try:
                        quals.sort(key=lambda x: int(re.sub(r"\D", "", x[0]) or "0"), reverse=True)
                    except Exception:
                        pass
            if quals:
                sources.append("RedTube\u00b7\u9ad8\u6e05MP4")
                episodes.append("#".join(["%sP$%s" % (q if q else "MP4", u) for q, u in quals]))
            if hls_tok:
                hls_eps = ""
                try:
                    data = self._media_json(hls_tok, page_url)
                    if isinstance(data, dict) and data.get("_hls"):
                        hls_eps = "\u6d41\u7545\u81ea\u9002\u5e94$" + data["_hls"]
                    elif isinstance(data, list):
                        tmp = []
                        for it in data:
                            try:
                                u = str(it.get("videoUrl") or "").replace("\\/", "/").replace("&amp;", "&").strip()
                                if u.startswith("//"):
                                    u = "https:" + u
                                if not u.startswith("http"):
                                    continue
                                q = str(it.get("quality") or "HLS").strip()
                                tmp.append("%s$%s" % (q, u))
                            except Exception:
                                continue
                        if tmp:
                            hls_eps = "#".join(tmp)
                except Exception:
                    hls_eps = ""
                if not hls_eps:
                    hls_eps = "\u6d41\u7545\u81ea\u9002\u5e94$" + hls_tok
                sources.append("RedTube\u00b7HLS")
                episodes.append(hls_eps)
            if not sources:
                try:
                    m = re.search(r'data-mediabook="([^"]+)"', html)
                    if m:
                        pv = self._fix(m.group(1))
                        if pv.startswith("http"):
                            sources.append("\u9884\u89c8\u901f\u770b")
                            episodes.append("\u9884\u89c8$" + pv)
                except Exception:
                    pass
            if not sources:
                return None
            remarks = dur
            if views:
                remarks = (remarks + " \u00b7 " + views + "\u6b21\u64ad\u653e") if remarks else (views + "\u6b21\u64ad\u653e")
            content = desc
            if up:
                content += "\n\u4e0a\u4f20:" + up
            if cats:
                content += "\n\u5206\u7c7b:" + ",".join(cats)
            vod_pic = self._proxy_pic_url(pic) if pic.startswith("http") else pic
            return {
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": vod_pic,
                "vod_remarks": remarks,
                "vod_year": (up[:4] if up else ""),
                "vod_area": "欧美",
                "vod_actor": uploader,
                "vod_director": "RedTube",
                "vod_content": content,
                "type_name": cats[0] if cats else "",
                "vod_play_from": "$$$".join(sources),
                "vod_play_url": "$$$".join(episodes),
            }
        except Exception:
            return None

    def detailContent(self, ids):
        out = []
        try:
            seq = ids if isinstance(ids, (list, tuple)) else [ids]
        except Exception:
            seq = []
        for i in (seq or []):
            try:
                x = self._one_detail(str(i))
            except Exception:
                x = None
            if x:
                out.append(x)
        return {"list": out}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        kw = str(key or "").strip()
        if not kw:
            return {"list": [], "page": page, "pagecount": 1, "limit": 0, "total": 0}
        url = self.host + "/?search=" + quote_plus(kw)
        if page > 1:
            url += "&page=" + str(page)
        html = self._get(url)
        vods = self._cards(html)
        pagecount = page + 1 if self._has_next(html) else page
        return {"page": page, "pagecount": pagecount, "limit": len(vods), "total": 0, "list": vods}

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
        ref = str(referer or "").strip()
        if ref.startswith("http"):
            u += "&referer=" + quote(ref, safe="")
        return u

    def _proxy_pic_url(self, u, referer=None):
        u = str(u or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            u = "https:" + u
        if u.startswith("/"):
            u = self.host + u
        if not u.startswith("http"):
            return ""
        ref = str(referer or "").strip()
        if not ref.startswith("http"):
            ref = self.host + "/"
        return self._proxy_url(u, "img", ref)

    def _browser_base(self):
        try:
            ua = self.headers.get("User-Agent", "")
        except Exception:
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        if not ua:
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        return {
            "User-Agent": ua,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _media_header(self, url="", referer=""):
        h = self._browser_base()
        try:
            h.pop("Referer", None)
            ref = str(referer or "").strip()
            h["Referer"] = ref if ref.startswith("http") else (self.host + "/")
        except Exception:
            pass
        return h

    def _is_media(self, url):
        low = str(url or "").lower().split("?")[0]
        return low.endswith((".m3u8", ".mp4", ".ts", ".m4s", ".key", ".webm", ".mov")) or ".m3u8" in low or "/media/hls" in low or "/media/mp4" in low

    def _unescape(self, raw):
        u = str(raw or "")
        try:
            if "\\u" in u:
                u = re.sub(r"\\u([0-9a-fA-F]{4})", lambda g: chr(int(g.group(1), 16)), u)
            u = u.replace("\\/", "/").replace("\\", "")
        except Exception:
            pass
        return u

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
        m = re.search(r"#EXT-X-STREAM-INF[^\n]*\n\s*([^\n#]+)", body or "")
        if not m:
            return ""
        path = m.group(1).strip()
        return path if path.startswith("http") else urljoin(url, path)

    def _fetch_m3u8_text(self, url, head, timeout=20):
        last = ""
        for _ in range(3):
            try:
                r = self.session.get(url, headers=dict(head or {}), timeout=timeout, verify=False)
                if r.status_code == 200 and r.text and "#EXTINF" in r.text:
                    return r.text
                if r.status_code == 200 and r.text:
                    last = r.text
            except Exception:
                continue
        return last

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
            try:
                text = self._fetch_m3u8_text(url, head, 20)
            except Exception:
                text = text or ""
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
            try:
                t2 = self._fetch_m3u8_text(sub, head, 20)
            except Exception:
                t2 = t2 or ""
            if not t2 or "#EXTINF" not in t2:
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
        ref = str(referer or "").strip()
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
                    line = re.sub(r'(URI=")([^"]+)(")', _rp, line)
                out.append(line)
                continue
            a = line if line.startswith("http") else urljoin(base, line)
            if ref:
                out.append(root + sep + "type=ts&url=" + quote(a, safe="") + "&referer=" + quote(ref, safe=""))
            else:
                out.append(root + sep + "type=ts&url=" + quote(a, safe=""))
        body = "\n".join(out)
        return body if body.endswith("\n") else body + "\n"

    def playerContent(self, flag, id, vipFlags=None):
        raw = self._unescape(id).replace("&amp;", "&").strip()
        if raw.startswith("//"):
            raw = "https:" + raw
        elif raw.startswith("/"):
            raw = self.host + raw
        if not raw.startswith("http"):
            return {"parse": 0, "url": "", "header": self._media_header(), "msg": "无效播放地址"}
        if ".m3u8" in raw.lower() or "/media/hls" in raw.lower():
            return {"parse": 0, "url": self._proxy_url(raw, "m3u8"), "header": self._media_header(raw), "format": "application/x-mpegURL"}
        if not self._is_media(raw):
            return {"parse": 1, "url": raw, "header": self._media_header(raw)}
        return {"parse": 0, "url": self._proxy_url(raw, "m3u8") if raw.lower().endswith(".m3u8") else raw, "header": self._media_header(raw)}

    def _img_ct(self, data):
        try:
            if not data:
                return "image/jpeg"
            if data[:8] == b"\x89PNG\r\n\x1a\n":
                return "image/png"
            if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                return "image/webp"
            if data[:6] in (b"GIF87a", b"GIF89a"):
                return "image/gif"
            if data[:3] == b"\xff\xd8\xff":
                return "image/jpeg"
            if data[:4] == b"\x00\x00\x00\x18" or (len(data) > 4 and data[4:8] == b"ftyp"):
                return "image/heic"
            if data[:2] == b"BM":
                return "image/bmp"
        except Exception:
            pass
        return "image/jpeg"

    def _img_header(self, referer=""):
        try:
            ua = self.headers.get("User-Agent", "")
        except Exception:
            ua = ""
        if not ua:
            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        h = {"User-Agent": ua, "Accept": "image/webp,image/jpeg,image/png,*/*;q=0.8"}
        ref = str(referer or "").strip()
        if ref.startswith("http"):
            h["Referer"] = ref
        return h

    def _fetch_img(self, url, referer=""):
        ref = str(referer or "").strip()
        if not ref.startswith("http"):
            ref = self.host + "/"
        head = self._img_header(ref)
        for _ in range(3):
            try:
                r = self.session.get(url, headers=head, timeout=20, verify=False)
                if r.status_code != 200 or not r.content or len(r.content) <= 200:
                    continue
                data = r.content
                ct = str(r.headers.get("Content-Type") or "").lower()
                if "image" in ct:
                    return data
                if data[:3] == b"\xff\xd8\xff":
                    return data
                if data[:8] == b"\x89PNG\r\n\x1a\n":
                    return data
                if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                    return data
                if data[:6] in (b"GIF87a", b"GIF89a"):
                    return data
                if data[:2] == b"BM":
                    return data
            except Exception:
                continue
        return b""

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
            kind = str(kind or "").strip().lower()
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
                if ".m3u8" in low_all or "/media/hls" in low_all:
                    kind = "m3u8"
                elif url.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif", ".heic")) or "rdtcdn" in url.lower() or "imageMogr2" in url or "qpic.cn" in url.lower():
                    kind = "img"
                else:
                    kind = "ts"
            if kind == "img":
                try:
                    data = self._fetch_img(url, referer)
                except Exception:
                    data = b""
                if not data:
                    return [404, "text/plain", "Fetch Failed"]
                return [200, self._img_ct(data), data]
            head = self._media_header(url, referer)
            if kind == "m3u8" or ".m3u8" in url.lower() or "/media/hls" in url.lower():
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
                elif body[:3] == b"\xff\xd8\xff":
                    mime = "image/jpeg"
                elif body[:4] == b"\x89PNG":
                    mime = "image/png"
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

    def proxy(self, param):
        return self.localProxy(param)

    def isVideoFormat(self, url):
        try:
            return self._is_media(url)
        except Exception:
            return False

    def manualVideoCheck(self):
        return False

    def liveContent(self, url):
        return ""

    def action(self, action):
        return {}
