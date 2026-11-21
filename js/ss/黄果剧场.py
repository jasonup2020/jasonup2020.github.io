"""黄果剧场 (huangguo.video) Python 点播爬虫（TVBox / 默影视，Chaquopy）

站点结构（2026-10-04 实测）：
- 列表/分类/搜索：/videos?category=1|2|3|4&tags=N&rating=N&q=xx&page=N，卡片 <article class="video-card">
- 二级筛选：tags（1=都市/2=人妻/4=同人/5=校园/6=职场/7=古风/8=乱伦/40=玄幻），
  rating（1=安全/2=裸露/3=限制级）
- 最新发布：/videos（不带 category）
- 视频详情：/video/xxx，播放地址在 data-hls（.../master.m3u8），海报在 data-poster
- 连续剧详情：/series/xxx，剧集列表在 data-episode-list 区域（"第N集" + /video/xxx）
- 卡片比例：aspect-[9/16] 竖版，style ratio 按站点实际取 0.56
- 播放链路：data-hls 是 master.m3u8（含 480p/720p/1080p 三个 variant，
  variant 地址带 ?n= 时间戳 token）。playerContent 里解析 master 挑最高清晰度 variant。

网络层：HTML 页面用 requests.Session + Chrome TLS 指纹（TLS1.2 密码套件 + X25519 曲线，
绕过 Cloudflare 1020 按指纹拦截）；m3u8 等静态资源用裸 requests（带文档头反而 403）；
单次请求 10s 超时、失败重试 1 次。详情页连续剧不逐集抓 HLS（N+1 改为 1+播放时解析）。
依赖仅限 requirements.txt 白名单（requests 为主）。

配置示例（放进 TVBox 主配置 "sites" 数组，把本文件放到 ./vod/ 目录）：
[
  {
    "key": "huangguo",
    "name": "黄果剧场",
    "type": 3,
    "api": "./vod/huangguo_spider.py",
    "lang": "zh-CN",
    "searchable": 1,
    "quickSearch": 1,
    "filterable": 1,
    "changeable": 0
  }
]
"""

import re
import json
import time
from urllib.parse import quote, urlsplit, unquote, urljoin, parse_qsl

try:
    import requests
except Exception:
    requests = None

try:
    import ssl
except Exception:
    ssl = None

try:
    from base.spider import Spider as BaseSpider
except Exception:  # 独立运行（本机校验）时兜底
    BaseSpider = object

BASE = "https://huangguo.video"
PAGE_SIZE = 20
# 第一个栏目 = 最新发布（映射到 /videos 不带 category）
CATEGORIES = [
    {"type_id": "latest", "type_name": "最新发布"},
    {"type_id": "1", "type_name": "MV音乐剧"},
    {"type_id": "2", "type_name": "短片"},
    {"type_id": "3", "type_name": "连续剧"},
    {"type_id": "4", "type_name": "片段"},
]
# 二级筛选（2026-10-04 实测：各分类情节标签各不相同；latest 取 16 标签并集）
# 尺度分级按用户要求默认全部，不做筛选
# 标签按每行 4 个拆成多个筛选维度：App 每个维度独占一行，超屏标签自然换行，无需横滑
_TAGS_BY_CAT = {
    "latest": [("都市", "1"), ("人妻", "2"), ("衍生", "3"), ("同人", "4"),
               ("校园", "5"), ("职场", "6"), ("古风", "7"), ("乱伦", "8"),
               ("NTR", "9"), ("穿越", "39"), ("玄幻", "40"), ("露出", "42"),
               ("女同", "55"), ("男同", "56"), ("欧美", "57"), ("二次元", "59")],
    "1": [("都市", "1"), ("人妻", "2"), ("校园", "5"), ("职场", "6"),
          ("NTR", "9"), ("露出", "42"), ("欧美", "57")],
    "2": [("都市", "1"), ("人妻", "2"), ("同人", "4"), ("校园", "5"),
          ("职场", "6"), ("古风", "7"), ("乱伦", "8"), ("NTR", "9"),
          ("穿越", "39"), ("玄幻", "40"), ("女同", "55"), ("男同", "56"),
          ("欧美", "57"), ("二次元", "59")],
    "3": [("都市", "1"), ("人妻", "2"), ("衍生", "3"), ("同人", "4"),
          ("校园", "5"), ("职场", "6"), ("古风", "7"), ("乱伦", "8"),
          ("NTR", "9"), ("穿越", "39"), ("玄幻", "40"), ("女同", "55"),
          ("男同", "56"), ("欧美", "57"), ("二次元", "59")],
    "4": [("都市", "1"), ("人妻", "2"), ("校园", "5"), ("职场", "6"),
          ("古风", "7"), ("乱伦", "8"), ("二次元", "59")],
}
_SORTS = [("最新发布", "newest"), ("最多播放", "views"), ("最多收藏", "favorites")]
_TAG_KEYS = ["tags", "tags2", "tags3", "tags4"]  # 多行标签维度 key，后行覆盖前行

def _chunk(lst, n):
    return [lst[i:i + n] for i in range(0, len(lst), n)]

def _chunk_smart(tags):
    """按用户规则分行：每行4个标签；最后剩余≤5个放一行；剩余6个拆4+2（不留1个孤儿）。"""
    rows = []
    i, n = 0, len(tags)
    while i < n:
        rem = n - i
        if rem <= 5:
            rows.append(tags[i:])
            break
        if rem == 6:
            rows.append(tags[i:i + 4])
            rows.append(tags[i + 4:])
            break
        rows.append(tags[i:i + 4])
        i += 4
    return rows

FILTERS = {}
for _tid, _tags in _TAGS_BY_CAT.items():
    _dims = []
    # 标签多选（App 点已选中可再点取消，不选即全部，故不需要"全部"选项）
    # 分行规则：每行4个；最后剩余≤5个放一行；剩余6个拆4+2（不留1个孤儿）
    _rows = _chunk_smart(_tags)
    for _i, _ck in enumerate(_rows):
        _dims.append({
            "key": _TAG_KEYS[_i] if _i < len(_TAG_KEYS) else "tags%d" % (_i + 1),
            "name": "情节标签",
            "value": [{"n": n, "v": v} for n, v in _ck],
        })
    _dims.append({
        "key": "sort", "name": "排序",
        "value": [{"n": n, "v": v} for n, v in _SORTS],
    })
    FILTERS[_tid] = _dims
del _tid, _tags, _dims, _i, _ck
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# Cloudflare 对 HTML 文档按 TLS 指纹拦截（1020）：Chrome 12 密码套件 + ECDH 曲线组
CHROME_TLS12_CIPHERS = (
    "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:"
    "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:"
    "ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:"
    "ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:AES128-SHA:AES256-SHA"
)
EC_CURVE = "X25519"

CARD_RE = re.compile(r'<article class="(?:video-card|search-content-card)[\s\S]*?</article>')
TITLE_RE = re.compile(r'<p class="[^"]*font-display[^"]*"[^>]*>([^<]*)</p>')
PIC_RE = re.compile(r'<img[^>]*src="([^"]*)"')
REMARK_RE = re.compile(r'bg-black/55[^>]*>([^<]*)<')
TAG_RE = re.compile(r'text-gold-dim[^>]*>([^<]*)<')
HREF_RE = re.compile(r'<a[^>]+href="([^"]*)"')
H1_RE = re.compile(r'<h1[^>]*>([^<]*)</h1>')
DESC_RE = re.compile(r'<meta name="description" content="([^"]*)"')
OGIMG_RE = re.compile(r'<meta property="og:image" content="([^"]*)"')
POSTER_RE = re.compile(r'data-poster="([^"]*)"')
HLS_RE = re.compile(r'data-hls="([^"]*)"')
TOTAL_RE = re.compile(r'(\d+)\s*集')
PAGER_RE = re.compile(r'href="[^"]*page=(\d+)"[^>]*>\s*(\d+)\s*<')
ANCHOR_RE = re.compile(r'<a[^>]+href="/video/([a-z0-9]+)"[\s\S]*?</a>')
STREAM_RE = re.compile(r'#EXT-X-STREAM-INF[^\n]*')

class Spider(BaseSpider):
    def init(self, extend=""):
        if isinstance(extend, dict):
            self.options = extend
        elif extend:
            try:
                self.options = json.loads(extend)
            except Exception:
                self.options = {}
        else:
            self.options = {}
        self._sess = None
        self._bsess = None
        self._last_err = ""
        self._last_ok = 0.0
        self._player_hint = ""
        self._kcache = {}
        self._pcache = {}
        self._mcache = {}
        self._dscache = {}
        self._proxy_root = ""
        self._gw = None

    def getName(self):
        return "黄果剧场"

    # ---------------- 网络层：requests + Chrome TLS 指纹（CF 1020 绕过），fetch 兜底 ----------------
    def _build_session(self):
        if requests is None:
            return None
        s = requests.Session()
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.set_ciphers(CHROME_TLS12_CIPHERS)
            try:
                ctx.set_ecdh_curve(EC_CURVE)
            except Exception:
                pass

            class _FpAdapter(requests.adapters.HTTPAdapter):
                def init_poolmanager(self, connections, maxsize, block=False, **kw):
                    kw["ssl_context"] = ctx
                    super().init_poolmanager(connections, maxsize, block=block, **kw)

            s.mount("https://", _FpAdapter())
        except Exception:
            pass
        s.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
        })
        return s

    def _get_session(self):
        if self._sess is None:
            self._sess = self._build_session()
        return self._sess

    def _get_bare(self):
        # 裸请求专用 Session：仅 UA 默认头（m3u8/ts 带文档头 403）+ keep-alive 复用连接提速
        if getattr(self, "_bsess", None) is not None:
            return self._bsess
        if requests is None:
            return None
        try:
            b = requests.Session()
            b.headers.update({"User-Agent": USER_AGENT})
            b.verify = False
            self._bsess = b
        except Exception:
            self._bsess = None
        return self._bsess

    def _shell_fetch_text(self, url, headers=None, timeout=10):
        try:
            f = getattr(self, "fetch", None)
            if not callable(f):
                return ""
            r = f(url, headers=headers, timeout=timeout)
            if r is not None and getattr(r, "status_code", 0) == 200:
                return getattr(r, "text", "") or ""
        except Exception:
            pass
        return ""

    @staticmethod
    def _ul_get(url, headers=None, timeout=10):
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=headers or {"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode("gbk", errors="ignore")
        except Exception:
            return ""

    @staticmethod
    def _ul_bytes(url, headers=None, timeout=15):
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=headers or {"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception:
            return b""

    @staticmethod
    def _neutral_headers(referer=None):
        """中和指纹 session 默认文档头（Sec-Fetch/UA-CH 会令 m3u8 403），None=删除"""
        h = {"Accept": "*/*"}
        if referer:
            h["Referer"] = referer
        for k in ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
                  "Sec-Fetch-Dest", "Sec-Fetch-Mode", "Sec-Fetch-Site",
                  "Upgrade-Insecure-Requests", "Accept-Language"):
            h[k] = None
        return h

    def _fetch_plain(self, url, referer=None, timeout=10):
        """轻量 GET：裸 Session（keep-alive 提速）优先，回退指纹中和头、壳 fetch、urllib。"""
        h = {"User-Agent": USER_AGENT}
        if referer:
            h["Referer"] = referer
        b = self._get_bare()
        if b is not None:
            try:
                r = b.get(url, headers=h, timeout=timeout, allow_redirects=True)
                if r.status_code == 200:
                    if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
                        r.encoding = "utf-8"
                    return r.text
            except Exception:
                pass
        if requests is not None:
            try:
                r = requests.get(url, headers=h, timeout=timeout, allow_redirects=True)
                if r.status_code == 200:
                    if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
                        r.encoding = "utf-8"
                    return r.text
            except Exception:
                pass
        s = self._get_session()
        if s is not None:
            try:
                r = s.get(url, headers=self._neutral_headers(referer), timeout=timeout,
                          allow_redirects=True)
                if r.status_code == 200:
                    if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
                        r.encoding = "utf-8"
                    return r.text
            except Exception:
                pass
        txt = self._shell_fetch_text(url, h, timeout)
        if txt:
            return txt
        return self._ul_get(url, h, timeout)

    def _get(self, url, referer=None, timeout=10, retries=1):
        """同步 GET 文本：指纹 Session → 壳 fetch → 标准库 urllib 三级兜底。"""
        headers = {}
        if referer:
            headers["Referer"] = referer
        hh = dict(headers)
        hh.setdefault("User-Agent", USER_AGENT)
        last_err = None
        for _attempt in range(retries + 1):
            try:
                s = self._get_session()
                if s is not None:
                    r = s.get(url, headers=headers or None, timeout=timeout,
                              allow_redirects=True)
                    if r.status_code == 200:
                        if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
                            r.encoding = "utf-8"
                        txt = r.text
                        if "you have been blocked" in txt or "Attention Required" in txt:
                            last_err = "cf_blocked"
                        else:
                            self._last_err = ""
                            self._last_ok = time.time()
                            return txt
                    else:
                        last_err = "http_%d" % r.status_code
                elif last_err is None:
                    last_err = "no_requests"
            except Exception as e:
                last_err = type(e).__name__
            txt = self._shell_fetch_text(url, hh, timeout)
            if not txt:
                txt = self._ul_get(url, hh, timeout)
            if txt and "you have been blocked" not in txt and "Attention Required" not in txt:
                self._last_err = ""
                self._last_ok = time.time()
                return txt
        self._last_err = str(last_err)
        return ""

    def _get_master(self, master_url):
        c = self._mcache.get(master_url)
        if c and time.time() - c[0] < 60:
            return c[1]
        txt = ""
        try:
            txt = self._fetch_plain(master_url, referer=BASE + "/")
        except Exception:
            txt = ""
        if txt:
            self._mcache[master_url] = (time.time(), txt)
        return txt

    def _pick_variant(self, master_url, want=0):
        """解析 master.m3u8，挑 variant（want>0 时优先该高度，否则最高）；失败回退 master。"""
        txt = self._get_master(master_url)
        if not txt or "#EXT-X-STREAM-INF" not in txt:
            return master_url
        base_dir = master_url.rsplit("/", 1)[0] + "/"
        lines = txt.splitlines()
        variants = []
        for i, line in enumerate(lines):
            if "#EXT-X-STREAM-INF" not in line:
                continue
            uri = ""
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    uri = lines[j].strip()
                    break
            if not uri:
                continue
            rm = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
            res = int(rm.group(2)) if rm else 0
            bw = re.search(r"BANDWIDTH=(\d+)", line)
            bwv = int(bw.group(1)) if bw else 0
            variants.append((res, bwv, uri))
        if not variants:
            return master_url
        if want:
            exact = [v for v in variants if v[0] == want]
            if exact:
                variants = exact
            else:
                variants.sort(key=lambda x: abs(x[0] - want))
                variants = variants[:1]
        else:
            variants.sort(key=lambda x: (x[0], x[1]), reverse=True)
        uri = variants[0][2]
        if uri.startswith("http://") or uri.startswith("https://"):
            return uri
        if uri.startswith("/"):
            return BASE + uri
        return base_dir + uri

    def _list_variants(self, master_url):
        """返回 master 全部 variant [(height, uri)]，供多线路"""
        out = []
        txt = self._get_master(master_url)
        if not txt or "#EXT-X-STREAM-INF" not in txt:
            return out
        base_dir = master_url.rsplit("/", 1)[0] + "/"
        ls = txt.splitlines()
        for i, line in enumerate(ls):
            if "#EXT-X-STREAM-INF" not in line:
                continue
            uri = ""
            for j in range(i + 1, len(ls)):
                if ls[j].strip():
                    uri = ls[j].strip()
                    break
            if not uri:
                continue
            if uri.startswith("http"):
                pass
            elif uri.startswith("/"):
                uri = BASE + uri
            else:
                uri = base_dir + uri
            rm = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
            out.append((int(rm.group(2)) if rm else 0, uri))
        return out

    def homeContent(self, filter):
        # 六壳契约：class + list + filters（首页需带推荐列表，否则壳首页空白）
        result = {"class": list(CATEGORIES), "filters": dict(FILTERS), "list": []}
        try:
            result["list"] = self.homeVideoContent().get("list") or []
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        # 推荐 = 最新发布列表（不再置空）
        try:
            return {"list": self._list("latest", 1, "", {}).get("list") or []}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        extend = extend if isinstance(extend, dict) else {}
        try:
            ret = self._list(str(tid), pg, "", extend)
            if not ret.get("list"):
                err = str(getattr(self, "_last_err", "") or "")
                ret["msg"] = ("加载失败：" + err) if err else "暂无数据"
            return ret
        except Exception as e:
            return {
                "list": [], "page": 1, "pagecount": 1, "limit": PAGE_SIZE,
                "total": 0, "msg": "分类加载失败：" + type(e).__name__,
            }

    def searchContent(self, key, quick, pg="1"):
        del quick
        try:
            # 全站搜索：站点实际搜索地址 /search?q=（/videos?q= 不是真搜索）
            # 站点要求至少 2 个字符，单字关键词补首字重复凑够长度
            kw = str(key or "").strip()
            if kw and len(kw) < 2:
                kw = kw + kw[0]
            url = "%s/search?q=%s" % (BASE, quote(kw))
            html_text = self._get(url, referer=BASE + "/")
            cards = [self._parse_card(b) for b in CARD_RE.findall(html_text or "")]
            cards = [c for c in cards if c]
            return {
                "list": cards, "page": 1, "pagecount": 1,
                "limit": len(cards), "total": len(cards),
            }
        except Exception as e:
            return {
                "list": [], "page": 1, "pagecount": 1, "limit": PAGE_SIZE,
                "total": 0, "msg": "搜索失败：" + type(e).__name__,
            }

    def _build_url(self, cat, pg, keyword, extend=None):
        extend = extend if isinstance(extend, dict) else {}
        if cat == "latest":
            url = "%s/videos" % BASE
        else:
            url = "%s/videos?category=%s" % (BASE, quote(cat))
        params = []
        # 多行标签多选：合并所有行的非空选择，逗号分隔（网站原生多选，需同时满足）
        # 行1的"全部"仅表示本行未选，不影响其他行
        tag_vals = []
        for k in _TAG_KEYS:
            v = str(extend.get(k, "") or "").strip()
            if v:
                tag_vals.append(v)
        if tag_vals:
            seen = set()
            uniq = []
            for tv in tag_vals:
                for part in tv.split(","):
                    p = part.strip()
                    if p and p not in seen:
                        seen.add(p)
                        uniq.append(p)
            if uniq:
                params.append("tags=" + quote(",".join(uniq)))
        sort = str(extend.get("sort", "") or "").strip()
        if sort and sort != "newest":
            params.append("sort=" + quote(sort))
        if keyword:
            params.append("q=" + quote(keyword))
        page = max(1, int(pg) if str(pg).isdigit() else 1)
        if page > 1:
            params.append("page=%d" % page)
        if params:
            sep = "&" if "?" in url else "?"
            url += sep + "&".join(params)
        return url

    def _list(self, cat, pg, keyword, extend=None):
        url = self._build_url(cat, pg, keyword, extend)
        html_text = self._get(url, referer=BASE + "/")
        cards = [self._parse_card(b) for b in CARD_RE.findall(html_text or "")]
        cards = [c for c in cards if c]
        return {
            "list": cards,
            "page": max(1, int(pg) if str(pg).isdigit() else 1),
            "pagecount": self._pagecount(html_text or ""),
            "limit": PAGE_SIZE,
            "total": len(cards),
        }

    @staticmethod
    def _clean(text):
        # P2：片名/集名里的 $ # 全角化，避免与分隔符冲突
        return str(text or "").replace("$", "＄").replace("#", "＃").strip()

    def _parse_card(self, block):
        href_m = HREF_RE.search(block)
        if not href_m:
            return None
        href = href_m.group(1)
        kind = "series" if href.startswith("/series/") else "video"
        code = href.rstrip("/").split("/")[-1]
        title_m = TITLE_RE.search(block)
        title = self._clean(title_m.group(1)) if title_m else ""
        pic_m = PIC_RE.search(block)
        pic = self._absolute(pic_m.group(1)) if pic_m else ""
        remark_m = REMARK_RE.search(block)
        remark = remark_m.group(1).strip() if remark_m else ""
        tags = TAG_RE.findall(block)[:3]
        return {
            "vod_id": "%s/%s" % (kind, code),
            "vod_name": title,
            "vod_pic": pic,
            "vod_remarks": remark or "/".join(tags),
            "vod_class": "/".join(tags),
            "vod_type": "连续剧" if kind == "series" else "视频",
            # 站点卡片实际为 9/16 竖版，按网站实际取 0.56（P10 意图：比例正确不畸变）
            "style": {"type": "rect", "ratio": 0.56},
        }

    def _pagecount(self, html_text):
        pages = [int(n) for _, n in PAGER_RE.findall(html_text)]
        return max(1, max(pages)) if pages else 1

    def detailContent(self, ids):
        # P1：遍历 ids，不截断
        items = []
        for ident in ids or []:
            try:
                item = self._parse_detail(str(ident))
                if item:
                    items.append(item)
            except Exception:
                continue
        if not items:
            return {"list": [], "msg": "详情加载失败"}
        return {"list": items}

    # 站点 master 固定三档清晰度（实测 480p/720p/1080p），按档位输出多线路
    _QUALITIES = [(1080, "1080P"), (720, "720P"), (480, "480P")]

    @staticmethod
    def _encode_ep(quality, target):
        return "q%d|%s" % (quality, target)

    @staticmethod
    def _decode_play(play_id):
        m = re.match(r"^q(\d+)\|(.+)$", play_id or "")
        if m:
            return int(m.group(1)), m.group(2)
        return 0, play_id

    def _detail_lines(self, item, eps):
        # eps: [(label, target)]，按 _QUALITIES 展开为多线路（$$$ 分隔）
        froms, plays = [], []
        for q, name in self._QUALITIES:
            froms.append(name)
            plays.append("#".join(
                "%s$%s" % (lb, self._encode_ep(q, tg)) for lb, tg in eps
            ))
        item["vod_play_from"] = "$$$".join(froms)
        item["vod_play_url"] = "$$$".join(plays)

    def _parse_detail(self, ident):
        parts = str(ident).split("/")
        kind = parts[0]
        code = parts[1] if len(parts) >= 2 else ident
        item = {
            "vod_id": ident,
            "vod_name": "",
            "vod_pic": "",
            "vod_play_from": "黄果剧场",
            "vod_play_url": "",
        }
        if kind == "series":
            text = self._get("%s/series/%s" % (BASE, code), referer=BASE + "/")
            text = text or ""
            item["vod_name"] = self._clean(self._first(H1_RE, text))
            item["vod_pic"] = self._absolute(
                self._first(OGIMG_RE, text) or self._first(POSTER_RE, text)
            )
            item["vod_content"] = self._first(DESC_RE, text) or ""
            # 剧集只拼 /video/{code}，HLS 解析后移到 playerContent（详情 1 次请求，不再 N+1）
            ep_area = text
            m_area = re.search(r'data-episode-list[\s\S]*', text)
            if m_area:
                ep_area = m_area.group(0)
            urls = []
            seen = set()
            idx = 0
            for am in ANCHOR_RE.finditer(ep_area):
                ep_code = am.group(1)
                if ep_code in seen:
                    continue
                seen.add(ep_code)
                inner = am.group(0)
                lm = re.search(r'第\s*\d+\s*[集话]|正片|预告', inner)
                label = self._clean(lm.group(0).replace(" ", "")) if lm else ("第%d集" % (idx + 1))
                idx += 1
                urls.append((label, "/video/" + ep_code))
            total_m = TOTAL_RE.search(text)
            if total_m:
                item["vod_remark"] = "全%s集" % total_m.group(1)
            # 站点剧集区按最新在前（第9→第1），选集需正序（第1→第9）
            if urls:
                def _ep_num(pair):
                    m2 = re.match(r"第(\d+)", pair[0])
                    return int(m2.group(1)) if m2 else 0
                if all(_ep_num(p) for p in urls):
                    urls.sort(key=_ep_num)
                else:
                    urls.reverse()
            if urls:
                self._detail_lines(item, urls)
            return item
        text = self._get("%s/video/%s" % (BASE, code), referer=BASE + "/")
        text = text or ""
        item["vod_name"] = self._clean(self._first(H1_RE, text)) or "正片"
        item["vod_pic"] = self._absolute(
            self._first(POSTER_RE, text) or self._first(OGIMG_RE, text)
        )
        item["vod_content"] = self._first(DESC_RE, text) or ""
        # 单视频：data-hls 直接从已抓页面提取，不再二次请求
        m = HLS_RE.search(text)
        master = self._absolute(m.group(1)) if m else ""
        if master:
            self._detail_lines(item, [("正片", master)])
        else:
            item["vod_play_url"] = ""
        return item

    def playerContent(self, flag, id, vipFlags):
        del flag, vipFlags
        try:
            # 兼容整串传入（含 $$$/ #）：先取首线路首集，再拆 Name$id
            cur = str(id or "").split("$$$")[0].split("#")[0]
            sep = cur.rfind("$")
            play_id = (cur[sep + 1:] if sep >= 0 else cur).strip()
            if not play_id:
                return {"parse": 0, "jx": 0, "url": "", "msg": "空播放地址"}
            want, play_id = self._decode_play(play_id)
            # /video/xxx → 抓页面取 data-hls（120s 缓存，换线路/重播免二次抓取）
            if "/video/" in play_id and "master.m3u8" not in play_id:
                code = play_id.rstrip("/").split("/")[-1]
                master = self._dscache.get(code, "")
                if not master or time.time() - self._dscache.get(code + "#t", 0) > 120:
                    page = self._get("%s/video/%s" % (BASE, code), referer=BASE + "/")
                    m = HLS_RE.search(page or "")
                    master = self._absolute(m.group(1)) if m else ""
                    if master:
                        self._dscache[code] = master
                        self._dscache[code + "#t"] = time.time()
                if not master:
                    return {"parse": 1, "url": play_id,
                            "header": {"Referer": BASE + "/"}}
            else:
                master = self._absolute(play_id)
            # 按线路（清晰度）挑 variant；无指定时取最高
            playable = self._pick_variant(master, want)
            # 预取媒体 m3u8 与 key 进缓存：代理首跳命中，消除设备端超时（2004）
            self._prefetch_media(playable)
            return {
                "parse": 0,
                "jx": 0,
                "url": self._proxy_url(playable, "m3u8"),
                "header": {"Referer": BASE + "/", "User-Agent": USER_AGENT},
                "format": "application/x-mpegURL",
            }
        except Exception as e:
            return {"parse": 0, "jx": 0, "url": "", "msg": "播放失败：" + type(e).__name__}

    def _prefetch_media(self, url):
        """预取媒体 m3u8（master 先解析 variant）与 AES key，写入 60s 缓存"""
        try:
            c = self._pcache.get(url)
            if c and time.time() - c[0] < 60:
                return
            body = self._fetch_plain(url, referer=BASE + "/")
            base = str(url or "")
            if body and "#EXT-X-STREAM-INF" in body:
                sub = self._pick_variant(url)
                if sub != url:
                    t2 = self._fetch_plain(sub, referer=BASE + "/")
                    if t2 and "#EXTINF" in t2:
                        base, body = sub, t2
            if body and "#EXT" in body:
                self._pcache[url] = (time.time(), body, base)
                km = re.search(r'URI="([^"]+)"', body)
                if km:
                    ku = km.group(1)
                    if not ku.startswith("http"):
                        ku = urljoin(base or url, ku)
                    self._fetch_key(ku)
        except Exception:
            pass

    # ---------------- 本地代理：m3u8 KEY 改写 + 二进制取回（六壳 localProxy 契约） ----------------
    def getProxyUrl(self, local=True):
        root = getattr(self, "_proxy_root", "")
        if root:
            return root
        if self._is_ds_gateway():
            key = quote("local_py_" + str(self.getName()), safe="")
            root = "http://127.0.0.1:9978/api/" + key + "/proxy?do=py"
            self._proxy_root = root
            return root
        try:
            from com.github.catvod import Proxy as _CatProxy
            try:
                root = str(_CatProxy.getUrl(local)) + "?do=py"
            except Exception:
                root = str(_CatProxy.getUrl()) + "?do=py"
            self._proxy_root = root
            return root
        except Exception:
            pass
        root = "http://127.0.0.1:9978/proxy?do=py"
        self._proxy_root = root
        return root

    def _is_ds_gateway(self):
        cached = getattr(self, "_gw", None)
        if cached is not None:
            return cached
        ok = False
        try:
            r = requests.get("http://127.0.0.1:9978/ping", timeout=2)
            if getattr(r, "status_code", 0) == 200 and "gateway" in str(getattr(r, "text", "") or "").lower():
                ok = True
        except Exception:
            pass
        self._gw = ok
        return ok

    def _proxy_url(self, url, kind="media"):
        root = self.getProxyUrl(True)
        sep = "&" if "?" in root else "?"
        return root + sep + "type=" + kind + "&url=" + quote(str(url or ""), safe="")

    def _rewrite_m3u8(self, text, base):
        # 只改写 KEY 的 URI：相对路径（会被 ExoPlayer 解析到 127.0.0.1 404）改为代理绝对地址
        out = []
        for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = raw.strip()
            if line.startswith("#") and "URI=" in line:
                def _rp(m):
                    v = m.group(2)
                    if not v.startswith("http"):
                        v = urljoin(base, v)
                    return m.group(1) + self._proxy_url(v, "key") + m.group(3)
                line = re.sub(r'(URI=")([^"]+)(")', _rp, line)
                out.append(line)
                continue
            out.append(raw)
        body = "\n".join(out)
        return body if body.endswith("\n") else body + "\n"

    def _fetch_key(self, url):
        # key 端点：裸请求 403，需指纹 Session（裸头）；成功缓存避免重复请求
        cached = self._kcache.get(url)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        s = self._get_session()
        for hdr in (self._neutral_headers(BASE + "/"),
                    {"Referer": BASE + "/"}):
            if s is None:
                break
            try:
                r = s.get(url, headers=hdr, timeout=10)
                if r.status_code == 200 and r.content and len(r.content) <= 64:
                    data = bytes(r.content)
                    self._kcache[url] = (time.time(), data)
                    return data
            except Exception:
                pass
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT, "Referer": BASE + "/"}, timeout=10)
            if r.status_code == 200 and r.content and len(r.content) <= 64:
                data = bytes(r.content)
                self._kcache[url] = (time.time(), data)
                return data
        except Exception:
            pass
        data = self._ul_bytes(url, {"User-Agent": USER_AGENT, "Referer": BASE + "/"}, 10)
        if data and len(data) <= 64:
            self._kcache[url] = (time.time(), data)
            return data
        return b""

    def _fetch_bytes(self, url, referer=None):
        # ts 段/图片：裸 Session（keep-alive）→ 单发裸请求 → 指纹中和头 → urllib → 壳 fetch
        h = {"User-Agent": USER_AGENT}
        if referer:
            h["Referer"] = referer
        b = self._get_bare()
        if b is not None:
            try:
                r = b.get(url, headers=h, timeout=15, allow_redirects=True)
                if r.status_code == 200 and r.content:
                    return bytes(r.content)
            except Exception:
                pass
        if requests is not None:
            try:
                r = requests.get(url, headers=h, timeout=15, allow_redirects=True)
                if r.status_code == 200 and r.content:
                    return bytes(r.content)
            except Exception:
                pass
        s = self._get_session()
        if s is not None:
            try:
                r = s.get(url, headers=self._neutral_headers(referer), timeout=15,
                          allow_redirects=True)
                if r.status_code == 200 and r.content:
                    return bytes(r.content)
            except Exception:
                pass
        data = self._ul_bytes(url, h, 15)
        if data:
            return data
        try:
            r = self.fetch(url, headers=h, timeout=15)
            if r and getattr(r, "status_code", 0) == 200:
                return bytes(r.content)
        except Exception:
            pass
        return b""

    def localProxy(self, param):
        try:
            if isinstance(param, str):
                t = param.strip()
                try:
                    param = json.loads(t)
                except Exception:
                    if "=" in t:
                        param = dict(parse_qsl(t, keep_blank_values=True))
                    else:
                        param = {}
            if not isinstance(param, dict):
                param = {}

            def _one(v):
                if isinstance(v, (list, tuple)):
                    return v[0] if v else ""
                return v
            kind = _one(param.get("type") or param.get("do") or "")
            url = _one(param.get("url") or "")
            kind = str(kind or "").strip().lower()
            url = unquote(str(url or "").strip()).replace("\\/", "/").strip()
            if not url:
                return [404, "text/plain", "Not Found"]
            if url.startswith("//"):
                url = "https:" + url
            if not url.startswith("http"):
                return [404, "text/plain", "Unsupported"]
            if kind in ("", "py", "proxy", "media", "m3u8"):
                kind = "m3u8" if ".m3u8" in url.lower() else "ts"
            if kind == "m3u8":
                base, body = url, ""
                cached = self._pcache.get(url)
                if cached and time.time() - cached[0] < 60:
                    body, base = cached[1], cached[2]
                for _ in range(2):
                    if body and "#EXT" in body:
                        break
                    body = self._fetch_plain(url, referer=BASE + "/")
                if not body:
                    return [404, "text/plain", "Fetch Failed"]
                if "#EXT-X-STREAM-INF" in body:
                    sub = self._pick_variant(url)
                    if sub != url:
                        t2 = self._fetch_plain(sub, referer=BASE + "/")
                        if t2 and "#EXTINF" in t2:
                            base, body = sub, t2
                if "#EXT-X-STREAM-INF" in body:
                    return [200, "application/vnd.apple.mpegurl", body]
                try:
                    data = self._rewrite_m3u8(body, base)
                except Exception:
                    data = body
                return [200, "application/vnd.apple.mpegurl", data]
            if kind == "key":
                data = self._fetch_key(url)
                if not data:
                    return [404, "text/plain", "Key Fetch Failed"]
                return [200, "application/octet-stream", data]
            data = self._fetch_bytes(url, referer=BASE + "/")
            if not data:
                return [404, "text/plain", "Fetch Failed"]
            mime = "video/mp2t" if data[:1] == b"\x47" else "application/octet-stream"
            return [200, mime, data]
        except Exception:
            return [500, "text/plain", "proxy error"]

    def proxy(self, param):
        return self.localProxy(param)

    def manualVideoCheck(self):
        return False

    def isVideoFormat(self, url):
        return str(url or "").split("?")[0].lower().endswith(
            (".m3u8", ".mpd", ".mp4", ".mkv", ".flv")
        )

    def destroy(self):
        try:
            if getattr(self, "_sess", None) is not None:
                self._sess.close()
        except Exception:
            pass
        self._sess = None
        self.options = {}
        for k in ("_kcache", "_pcache", "_mcache", "_dscache"):
            try:
                getattr(self, k).clear()
            except Exception:
                pass
        try:
            for att in ("_bsess",):
                s2 = getattr(self, att, None)
                if s2 is not None:
                    s2.close()
                setattr(self, att, None)
        except Exception:
            pass

    @staticmethod
    def _absolute(url):
        v = str(url or "").strip()
        if not v:
            return ""
        if v.startswith("http://") or v.startswith("https://"):
            return v
        if v.startswith("/"):
            return BASE + v
        return v

    @staticmethod
    def _first(regex, text):
        m = regex.search(text)
        return m.group(1) if m else ""
