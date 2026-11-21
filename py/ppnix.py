# -*- coding: utf-8 -*-

import json
import re
import time
from urllib.parse import quote, unquote, urljoin

from base.spider import Spider as BaseSpider

HOST = "https://www.ppnix.com"
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/120.0.0.0 Safari/537.36"
)
PAGE_SIZE = 24
HOME_CACHE_SECONDS = 30
SORT_NAMES = {"": "综合", "newstime": "时间", "onclick": "人气", "rating": "评分"}
CLASS_ROWS = (("movie", "电影"), ("tv", "电视剧"))
EXCERPT_FIELDS = {
    "导演": "vod_director",
    "主演": "vod_actor",
    "类型": "vod_class",
    "国家": "vod_area",
    "又名": "vod_en",
    "简介": "vod_content",
}

class Spider(BaseSpider):

    def init(self, extend=""):
        self.host = HOST
        self._filter_data = {}
        self._home_cache = None
        options = extend if isinstance(extend, dict) else {}
        if isinstance(extend, str) and extend.strip():
            try:
                options = json.loads(extend)
            except ValueError:
                options = {}
        if isinstance(options, dict) and str(options.get("host") or "").startswith("http"):
            self.host = str(options["host"]).rstrip("/")

    def getName(self):
        return "PPnix"

    def homeContent(self, filter):
        result = {
            "class": [{"type_id": tid, "type_name": name} for tid, name in CLASS_ROWS],
            "list": self._home_cards(),
        }
        if filter:
            filters = {}
            for tid, _name in CLASS_ROWS:
                rows = self._filters(tid)
                if rows:
                    filters[tid] = rows
            if filters:
                result["filters"] = filters
        return result

    def homeVideoContent(self):
        return {"list": self._home_cards()}

    def categoryContent(self, tid, pg, filter, extend):
        if tid not in dict(CLASS_ROWS):
            raise ValueError("未知分类：%s" % tid)
        pg = self._to_page(pg)
        extend = extend if isinstance(extend, dict) else {}
        segment = "-".join((
            self._segment(extend.get("genre")),
            self._segment(extend.get("area")),
            self._segment(extend.get("year")),
            self._page_slot(pg),
            self._segment(extend.get("sort")),
        ))
        html = self._get(self.host + quote("/cn/%s/%s.html" % (tid, segment), safe="/"))
        cards = self._cards(html)
        if not cards and "lists-content" not in html:
            raise ValueError("列表解析失败")
        return {"page": pg, "pagecount": self._pagecount(html), "limit": PAGE_SIZE, "list": cards}

    def searchContent(self, key, quick, pg="1"):
        pg = self._to_page(pg)
        word = str(key or "").strip().replace("-", " ").replace("/", " ")
        if not word:
            return {"page": pg, "pagecount": 1, "limit": PAGE_SIZE, "list": []}
        path = "/cn/search/%s-%s-.html" % (word, self._page_slot(pg))
        html = self._get(self.host + quote(path, safe="/"))
        cards = self._cards(html)
        if not cards and "搜索结果" not in html:
            raise ValueError("搜索结果解析失败")
        return {"page": pg, "pagecount": self._pagecount(html), "limit": PAGE_SIZE, "list": cards}

    def detailContent(self, ids):
        seq = list(ids) if isinstance(ids, (list, tuple)) else [ids]
        items = [self._detail(str(raw).strip()) for raw in seq if str(raw or "").strip()]
        if not items:
            return {"list": [], "msg": "缺少影片 ID"}
        return {"list": items}

    def playerContent(self, flag, id, vipFlags):
        match = re.fullmatch(r"(\d+)@([0-9A-Za-z]+)", str(id or "").strip())
        if not match:
            return {"parse": 0, "msg": "无效的播放标识"}
        direct = "%s/info/m3u8/%s/%s.m3u8" % (self.host, match.group(1), match.group(2))
        # 走本爬虫代理：输出前把相对 key/分片改写为绝对地址（真机 404 根因）
        return {
            "parse": 0,
            "jx": 0,
            "url": self._media_proxy(direct),
            "format": "application/x-mpegURL",
            "header": {"User-Agent": USER_AGENT},
        }

    def isVideoFormat(self, url):
        return str(url or "").split("?", 1)[0].lower().endswith(".m3u8")

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        args = self._proxy_param(param)
        kind = str(args.get("type") or args.get("do") or "py").lower()
        target = str(args.get("url") or "").strip()
        if not target.startswith("http"):
            return [404, "text/plain; charset=utf-8", "missing url", {}]
        if kind not in ("m3u8", "media", "py", "proxy"):
            return [404, "text/plain; charset=utf-8", "unsupported type", {}]
        # 改写相对 key/分片为绝对地址，避免播放器挂到壳本地地址后 404
        try:
            text = self._get(target, self.host + "/")
        except ValueError as error:
            return [502, "text/plain; charset=utf-8", str(error), {}]
        if "#EXTM3U" not in text:
            return [502, "text/plain; charset=utf-8", "not a playlist", {}]
        rewritten = self._rewrite_playlist(text, target)
        return [200, "application/vnd.apple.mpegurl", rewritten,
                {"Cache-Control": "no-cache", "Access-Control-Allow-Origin": "*"}]

    def proxy(self, param):
        return self.localProxy(param)

    def destroy(self):
        self._filter_data = {}
        self._home_cache = None

    # ---------- 内部实现 ----------

    def _media_proxy(self, target):
        # 播放列表交本爬虫代理改写后再交给播放器，规避相对 key 在壳本地地址下 404
        try:
            root = str(self.getProxyUrl(True))
        except Exception:
            root = "http://127.0.0.1:9978/proxy?do=py"
        sep = "&" if "?" in root else "?"
        return "%s%stype=m3u8&url=%s" % (root, sep, quote(str(target), safe=""))

    @staticmethod
    def _proxy_param(param):
        if isinstance(param, str):
            try:
                param = json.loads(param)
            except ValueError:
                param = {}
        if not isinstance(param, dict):
            return {}
        result = {}
        for key, value in param.items():
            if isinstance(value, (list, tuple)):
                value = value[0] if value else ""
            result[str(key)] = value
        return result

    @staticmethod
    def _rewrite_playlist(text, base):
        # 相对 key（../key）与相对分片按播放列表地址还原为绝对地址
        lines = []
        for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                if "URI=" in line:
                    line = re.sub(r'(URI=")([^"]+)(")',
                                  lambda m: m.group(1) + urljoin(base, m.group(2)) + m.group(3),
                                  line)
                lines.append(line)
            else:
                lines.append(urljoin(base, line))
        return "\n".join(lines) + "\n"

    def _home_cards(self):
        now = time.time()
        if self._home_cache and now - self._home_cache[0] < HOME_CACHE_SECONDS:
            return self._home_cache[1]
        cards = self._cards(self._get(self.host + "/cn/"))
        if not cards:
            raise ValueError("首页解析失败")
        cards = cards[:PAGE_SIZE]
        self._home_cache = (now, cards)
        return cards

    def _get(self, url, referer=None):
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": referer or (self.host + "/"),
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        # 站点偶发超时/502，按现有插件惯例单次重试；其余失败直接抛错
        last = None
        for attempt in range(2):
            try:
                rsp = self.fetch(url, headers=headers, timeout=15)
            except Exception as error:
                last = error
                if attempt == 0:
                    continue
                raise ValueError("请求失败：%s" % last)
            if rsp.status_code in (502, 503) and attempt == 0:
                continue
            if rsp.status_code != 200:
                raise ValueError("HTTP %s" % rsp.status_code)
            text = rsp.text or ""
            if not text.strip():
                raise ValueError("空响应")
            return text
        raise ValueError("请求失败：%s" % last)

    def _cards(self, html):
        tree = self.html(html)
        if tree is None:
            raise ValueError("页面解析失败")
        items, seen = [], set()
        for anchor in tree.xpath('//a[contains(@href, "/cn/movie/") or contains(@href, "/cn/tv/")]'):
            match = re.search(r"/cn/(movie|tv)/(\d+)\.html", anchor.get("href") or "")
            if not match or match.group(2) in seen:
                continue
            imgs = anchor.xpath(".//img")
            name = (imgs[0].get("alt") or "").strip() if imgs else ""
            if not name:
                name = (anchor.get("title") or "").strip() or "".join(anchor.xpath(".//text()")).strip()
            if not name:
                continue
            seen.add(match.group(2))
            item = {
                "vod_id": "%s/%s" % (match.group(1), match.group(2)),
                "vod_name": name,
                "vod_pic": (imgs[0].get("src") or "").strip() if imgs else "",
            }
            cells = anchor.xpath("ancestor::li[1]")
            if cells:
                year = "".join(cells[0].xpath('.//div[contains(@class, "countrie")]//text()')).strip()
                rate = "".join(cells[0].xpath('.//span[contains(@class, "rate")]//text()')).strip()
                if year:
                    item["vod_year"] = year
                if rate:
                    item["vod_remarks"] = rate
            items.append(item)
        return items

    def _detail(self, ident):
        match = re.fullmatch(r"(movie|tv)/(\d+)", ident)
        if not match:
            raise ValueError("无效的影片 ID：%s" % ident)
        kind, num = match.group(1), match.group(2)
        html = self._get(self.host + "/cn/%s/%s.html" % (kind, num))
        tree = self.html(html)
        headings = tree.xpath('//h1[contains(@class, "product-title")]') if tree is not None else []
        if not headings:
            raise ValueError("详情解析失败")
        heading = headings[0]
        plain = "".join(heading.xpath(".//text()"))
        name = (heading.text or "").strip() or plain.strip()
        rates = heading.xpath('.//span[contains(@class, "rate")]/text()')
        pics = tree.xpath('//header[contains(@class, "product-header")]//img/@src')
        params = self._play_params(html)
        if not params:
            raise ValueError("详情缺少播放参数")
        item = {
            "vod_id": ident,
            "vod_name": name,
            "vod_pic": (pics[0] or "").strip() if pics else "",
            "vod_play_from": "PPnix",
            "vod_play_url": "#".join(
                "%s$%s@%s" % (self._episode_label(param), num, param) for param in params
            ),
        }
        year = re.search(r"\((\d{4})\)", plain)
        if year:
            item["vod_year"] = year.group(1)
        if rates and (rates[0] or "").strip():
            item["vod_remarks"] = rates[0].strip()
        for key, value in self._excerpt_fields(tree).items():
            if value:
                item[key] = value
        return item

    @classmethod
    def _excerpt_fields(cls, tree):
        fields = {}
        for cell in tree.xpath('//div[contains(@class, "product-excerpt")]'):
            label = (cell.text or "").strip().rstrip("：:").strip()
            key = EXCERPT_FIELDS.get(label)
            if not key:
                continue
            spans = cell.xpath(".//span")
            if not spans:
                continue
            value = " ".join("".join(span.itertext()).strip() for span in spans).strip()
            if value:
                fields[key] = value
        return fields

    @staticmethod
    def _play_params(html):
        found = re.search(r"m3u8=\[([^\]]*)\]", html or "")
        if not found:
            return []
        return [a or b for a, b in re.findall(r"'([^']*)'|\"([^\"]*)\"", found.group(1))]

    @staticmethod
    def _episode_label(param):
        if param == "1080P":
            return "正片"
        if param.isdigit():
            return "第%s集" % param
        return param

    def _filters(self, kind):
        if kind in self._filter_data:
            data = self._filter_data[kind]
        else:
            data = self._extract_filters(kind) or []
            self._filter_data[kind] = data
        if not data:
            return []
        years = sorted(data["year"], key=lambda v: int(v) if v.isdigit() else 0, reverse=True)
        return [
            {"key": "sort", "name": "排序", "init": "", "value": [
                {"n": SORT_NAMES.get(value, value), "v": value} for value in data["sort"]
            ]},
            {"key": "genre", "name": "类型", "init": "", "value": self._options(data["genre"])},
            {"key": "area", "name": "地区", "init": "", "value": self._options(data["area"])},
            {"key": "year", "name": "年份", "init": "", "value": self._options(years)},
        ]

    @staticmethod
    def _options(values):
        return [{"n": "全部", "v": ""}] + [{"n": value, "v": value} for value in values]

    def _extract_filters(self, kind):
        try:
            html = self._get(self.host + "/cn/%s/" % kind)
        except ValueError:
            return None
        data = {"sort": [""], "genre": [], "area": [], "year": []}
        seen = {"sort": {""}, "genre": set(), "area": set(), "year": set()}
        fields = (("genre", 0), ("area", 1), ("year", 2), ("sort", 4))
        for href in re.findall(r'href="(/cn/%s/[^"]+\.html)"' % kind, html):
            seg = unquote(href.rsplit("/", 1)[-1])
            if seg.endswith(".html"):
                seg = seg[:-5]
            parts = seg.split("-")
            if len(parts) != 5:
                continue
            for key, index in fields:
                value = parts[index].strip()
                if value and value not in seen[key]:
                    seen[key].add(value)
                    data[key].append(value)
        if not data["genre"] and not data["area"] and not data["year"]:
            return None
        return data

    @staticmethod
    def _pagecount(html):
        html = html or ""
        tail = re.search(r'-(\d+)-\.html"[^>]*>\s*尾页', html)
        if tail:
            return int(tail.group(1)) + 1
        pages = [int(value) for value in re.findall(r'-\d+-\.html">\s*(\d+)\s*</a>', html)]
        active = re.search(r'<li class="active"><span>(\d+)</span>', html)
        if active:
            pages.append(int(active.group(1)))
        return max(pages) if pages else 1

    @staticmethod
    def _page_slot(pg):
        return "" if pg <= 1 else str(pg - 1)

    @staticmethod
    def _to_page(pg):
        try:
            page = int(pg)
        except (TypeError, ValueError):
            page = 1
        return page if page >= 1 else 1

    @staticmethod
    def _segment(value):
        return str(value or "").strip()
