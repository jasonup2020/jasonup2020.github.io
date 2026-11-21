# coding=utf-8
# !/usr/bin/python

"""
花都影院 (huaduys.org) —— TVBox / 默影视 / 影视仓 / OK影视 / PickTV 五壳通用 Spider

站点为 feifeicms(stui 模板)：
  分类页 /vodshow/{tid}--------{page}---.html
  搜索页 /vodsearch/-------------.html?wd={关键词}
  详情页 /voddetail/{id}.html
  播放页 /vodplay/{id}-{线路}-{集数}.html
播放地址为双层编码：base64 解码后得到 percent-encoded 的 m3u8，
需先 base64 解码再 unquote。

多地址轮换：默认 7 个域名，任一失效自动切换；extend 可用
{"host": "https://a.com,https://b.com"} 或 {"hosts": ["https://a.com"]} 覆盖。
"""

import re
import html
import json
import time
import base64
import requests
from urllib.parse import quote, unquote

DEFAULT_HOSTS = [
    "https://rb.huaduys.org",
    "https://www.huaduys.org",
    "https://long.huaduys.org",
    "https://ww.huaduys.org",
    "https://rb1.huaduys.org",
    "https://rb2.huaduys.org",
    "https://rb3.huaduys.org",
]

UA_PC = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0")

PLAY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36"
}

HOSTS_FILE = "huaduys_hosts.txt"


class Spider:
    def __init__(self):
        self.hosts = list(DEFAULT_HOSTS)
        self.host = self.hosts[0]
        self.sess = None

    # ---------------- 基础 ----------------
    def getName(self):
        return "花都影院"

    def init(self, extend=""):
        if extend:
            try:
                o = json.loads(extend)
            except Exception:
                o = None
            if isinstance(o, dict):
                raw = o.get("hosts") or o.get("host") or o.get("url")
                if isinstance(raw, list):
                    picked = [str(x).strip().rstrip("/") for x in raw if str(x).strip()]
                    if picked:
                        self.hosts = picked
                elif isinstance(raw, str) and raw.strip():
                    picked = [x.strip().rstrip("/") for x in raw.split(",") if x.strip()]
                    if picked:
                        self.hosts = picked
        else:
            try:
                with open(HOSTS_FILE, "r", encoding="utf-8") as f:
                    lines = [x.strip().rstrip("/") for x in f if x.strip() and not x.startswith("#")]
                if lines:
                    self.hosts = lines
            except Exception:
                pass
        self.host = self.hosts[0]
        self.sess = requests.Session()
        self.sess.headers.update({
            "User-Agent": UA_PC,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self._warm()

    def _warm(self):
        for _ in range(len(self.hosts)):
            try:
                self.sess.get(self.host, timeout=10)
                return
            except Exception:
                self._rotate()

    def _rotate(self):
        if len(self.hosts) > 1:
            self.host = self.hosts[(self.hosts.index(self.host) + 1) % len(self.hosts)]
        return self.host

    def _get(self, path, timeout=15, min_len=0, attempts=3):
        """按当前域名抓取；正文过短视为无效页，换域名继续尝试。"""
        absolute = path.startswith("http")
        last = ""
        for _ in range(len(self.hosts)):
            for i in range(attempts):
                url = path if absolute else self.host + path
                try:
                    r = self.sess.get(url, timeout=timeout)
                    r.encoding = "utf-8"
                    text = r.text or ""
                    last = text
                    if r.status_code == 200 and text and len(text) >= min_len:
                        return text
                except Exception:
                    pass
                if absolute:
                    break
                if i + 1 < attempts:
                    time.sleep(0.7)
            if absolute:
                break
            self._rotate()
        return last

    def _abs(self, u):
        u = str(u or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return self.host + u
        return u

    @staticmethod
    def _attr(fragment, key):
        m = re.search(key + r'="([^"]*)"', fragment or "")
        return html.unescape(m.group(1)).strip() if m else ""

    # ---------------- 列表解析 ----------------
    def _cards(self, text):
        out = []
        seen = set()
        if not text:
            return out
        pat = re.compile(
            r'<a class="stui-vodlist__thumb[^"]*?"([^>]*)href="(/voddetail/(\d+)\.html)"([^>]*)>(.*?)</a>',
            re.S)
        for m in pat.finditer(text):
            vid = m.group(3)
            if vid in seen:
                continue
            inner = html.unescape(m.group(5))
            title = self._attr(m.group(1) + m.group(4), "title") or self._attr(inner, "alt")
            name = re.sub(r"\s+", " ", title).strip()
            if not name:
                continue
            pic = self._abs(self._attr(inner, "data-original") or self._attr(inner, "src"))
            if pic.endswith("/hdys/img/load.gif"):
                pic = ""
            tags = re.findall(r'<span class="pic-tag[^"]*"[^>]*>(.*?)</span>', inner, re.S)
            tags = [re.sub(r"<[^>]+>", "", html.unescape(t)).strip() for t in tags]
            remarks = ""
            for t in tags:
                plain = t.replace(":", "").replace("：", "").strip()
                if t and plain and not plain.isdigit() and "次" not in t and "\U0001f44d" not in t:
                    remarks = t
                    break
            if not remarks and tags:
                remarks = tags[-1]
            seen.add(vid)
            out.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": remarks,
            })
        return out

    # ---------------- 主接口 ----------------
    def homeContent(self, filter):
        text = self._get("/")
        classes = []
        for m in re.finditer(r'<a href="(/vodtype/(\d+)\.html)"[^>]*>(.*?)</a>', text or "", re.S):
            tid = m.group(2)
            name = re.sub(r"<[^>]+>", "", html.unescape(m.group(3))).strip()
            if not name or len(name) > 12:
                continue
            if any(c["type_id"] == tid for c in classes):
                continue
            classes.append({"type_id": tid, "type_name": name})
        return {
            "class": classes,
            "list": self._cards(text),
            "filters": {c["type_id"]: [{"n": c["type_name"], "v": c["type_id"]}] for c in classes},
        }

    def homeVideoContent(self):
        return {"list": self._cards(self._get("/"))}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg or 1)
        if page <= 1:
            url = "/vodshow/%s-----------.html" % tid
        else:
            url = "/vodshow/%s--------%d---.html" % (tid, page)
        text = self._get(url, min_len=20000)
        pages = [int(x) for x in
                 re.findall(r"/vodshow/%s-+(\d+)---\.html" % re.escape(str(tid)), text or "")]
        pagecount = max(pages) if pages else 1
        return {
            "page": page,
            "pagecount": pagecount,
            "limit": 40,
            "total": pagecount * 40,
            "list": self._cards(text),
        }

    def detailContent(self, ids):
        vid = str(ids[0]) if ids else ""
        if not vid:
            return {"list": []}
        text = html.unescape(self._get("/voddetail/%s.html" % vid, min_len=8000))
        if not text:
            return {"list": []}

        def label(key):
            m = re.search(r'label-width">' + key + r'[：:]</strong><span class="detail-content">(.*?)</span>',
                          text, re.S)
            if not m:
                return ""
            v = re.sub(r"<[^>]+>", " ", m.group(1))
            return re.sub(r"\s+", " ", v).strip()

        name = label("名称") or label("标题")
        if not name:
            m = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.S)
            name = re.sub(r"<[^>]+>", "", html.unescape(m.group(1))).strip() if m else vid

        pic = ""
        m = re.search(r'<a class="stui-vodlist__thumb[^>]*?href="/vodplay/%s-[^"]*"[^>]*>(.*?)</a>'
                      % re.escape(vid), text, re.S)
        if not m:
            m = re.search(r'<a class="stui-vodlist__thumb[^>]*>(.*?)</a>', text, re.S)
        if m:
            pic = self._abs(self._attr(m.group(1), "data-original") or self._attr(m.group(1), "src"))
            if pic.endswith("/hdys/img/load.gif"):
                pic = ""

        play = ""
        m = re.search(r'/vodplay/%s-\d+-\d+\.html' % re.escape(vid), text)
        if m:
            play = self._abs(m.group(0))

        return {"list": [{
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_actor": label("演员"),
            "vod_director": "",
            "vod_year": (label("日期") or "")[:10],
            "vod_area": label("分类"),
            "vod_remarks": label("类别"),
            "vod_content": label("标题") or label("名称"),
            "vod_play_from": "花都" if play else "暂无",
            "vod_play_url": ("播放$" + play) if play else "暂无$",
        }]}

    def playerContent(self, flag, id, vipFlags):
        pid = str(id or "")
        if pid.startswith("播放"):
            pid = pid.split("$")[-1]
        if not pid.startswith("http"):
            pid = self._abs(pid)
        text = self._get(pid, min_len=2000)
        url = ""
        m = re.search(r'"","url":"([^"]+)"', text or "")
        if m:
            raw = m.group(1).replace("\\", "")
            try:
                decoded = base64.b64decode(raw).decode("utf-8", "ignore")
            except Exception:
                decoded = ""
            if decoded:
                url = unquote(decoded)
        if not url.startswith("http"):
            m = re.search(r'(https?[^"\'\s\\]+\.m3u8[^"\'\s\\]*)', text or "")
            url = m.group(1) if m else ""
        if not url.startswith("http"):
            return {"parse": 1, "url": pid, "header": PLAY_HEADERS}
        return {"parse": 0, "playUrl": "", "url": url, "header": PLAY_HEADERS}

    def searchContent(self, key, quick, pg="1"):
        text = self._get("/vodsearch/-------------.html?wd=" + quote(str(key or "")),
                         min_len=6000)
        items = self._cards(text)
        return {"list": items, "page": 1, "pagecount": 1,
                "limit": len(items) or 20, "total": len(items)}

    def searchContentPage(self, key, quick, pg):
        return self.searchContent(key, quick, pg)

    def isVideoFormat(self, url):
        u = (url or "").lower().split("?")[0]
        return u.endswith((".m3u8", ".mp4", ".flv", ".ts", ".m4v", ".webm", ".mov"))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None

    def getDependence(self):
        return []

    def destroy(self):
        try:
            if self.sess:
                self.sess.close()
        except Exception:
            pass
        return None