"""歪比巴卜 (wbbb1.com) TVBox Python Spider — 六壳契约 (TVBox/fongmi/默影视/影视仓/OK影视/PickTV)

站点实测 (2026-10-07, MacCMS + mxtheme 主题):
- 分类: GET /show/{tid}--------{page}---.html (12 段路由, 第9段=页码, 尾页链接给出 pagecount)
  段位: [1]tid [2]地区 [4]类别 [5]语言 [6]字母 [12]年份
- 卡片: a.module-poster-item[href^=/detail/], title=片名, img[data-original]=封面,
  .module-item-note=备注
- 搜索: GET /search/{kw}-------------.html — 实测服务端强制验证码 (系统安全验证,
  4位数字PNG, POST /index.php/ajax/verify_check?type=search); suggest 403、
  ajax/data 500、采集 API closed, 均无可用搜索路径 -> searchContent 显式抛错。
- 详情: GET /detail/{id}.html
  线路 tab: y-playList 区 .module-tab-item[data-dropdown-value]=线路名 (首个 tab 含 active)
  选集面板: 多个 id 均重复为 "panel1", 只能按文档顺序与 tab 一一对应
  每集: a.module-play-list-link[href=/vplay/{id}-{sid}-{nid}.html]
- 播放: GET /vplay/{id}-{sid}-{nid}.html
   1) 页内 var player_aaaa={...,"url":"<TOKEN>","link_next":...}
   2) iframe src={PLAYER}/player/?url=<TOKEN>&next=<下一集>&title=...
   3) POST {PLAYER}/api.php (同源相对路径, 需 Referer/Origin)
      body: url=urlencode(TOKEN+"&next="+next) & key & vkey & ckey
      三 key 为混淆 JS(jsjiami v7)动态计算, 服务端校验 (改 key 即 404):
        urlValueurl = TOKEN + "&next=" + next(解码后, //开头)
        key  = RC4(calculate(urlValueurl), md5(urlValueurl + "stray"))  -> b64
        vkey = RC4(calculate(urlValueurl), str(time) + md5(calculate(urlValueurl) + "stray")) -> b64
        ckey = RC4(calculate(urlValueurl), md5(播放器域名 + "stray"))   -> b64
        calculate(x) = (md5(x) + " P")[-22:]
        time = int(Date.now()/1000) (秒)
      响应 {"code":200,"url":"<b64密文>","type":"m3u8","aes_key":"<b64>","aes_iv":"<b64>",...}
   4) 解密: aes_key/aes_iv 先 RC4 还原(deplay) -> AES-128-CBC(url密文, key, iv) -> m3u8
      m3u8 含时效签名 (网易 CDN 分片), 必须每次播放实时解析, 不缓存。
"""

import base64
import json
import re
from urllib.parse import quote, urlsplit

from base.spider import Spider as BaseSpider

SITE = "https://wbbb1.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
TIMEOUT_MS = 15000

# 播放器混淆 JS 三处盐常量 (jsjiami 混淆 _0x47996d 求值实测, 均为 "stray")
_SALT = "stray"
# 播放器页 document.domain (ckey 明文输入, 实测 = 播放器域名, 与 ckey 无关的常量)


def _md5_hex(s):
    import hashlib
    return hashlib.md5(str(s).encode("utf-8")).hexdigest()


def _calculate(x):
    """播放器 calculate(x) = (md5(x) + " P")[-22:]"""
    return (_md5_hex(x) + " P")[-22:]


def _rc4(key, data):
    """RC4 加解密 (aesplay), data 为 bytes, 返回 bytes。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    if isinstance(key, str):
        key = key.encode("utf-8")
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) % 256
        s[i], s[j] = s[j], s[i]
    i = j = 0
    out = bytearray()
    for b in data:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        out.append(b ^ s[(s[i] + s[j]) % 256])
    return bytes(out)


def _enplay(plain, url):
    """播放器 enplay(x): RC4(calculate(url), x) -> base64"""
    return base64.b64encode(_rc4(_calculate(url), plain)).decode("ascii")


def _deplay(b64, url):
    """播放器 deplay: base64 解码后 RC4(calculate(url), ...) 还原明文"""
    return _rc4(_calculate(url), base64.b64decode(b64)).decode("utf-8", "replace")

CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "剧集"},
    {"type_id": "3", "type_name": "动漫"},
    {"type_id": "4", "type_name": "综艺"},
]

# ---- 筛选 (实测自 /show/{tid}-----------.html 各分类筛选区) ----
# show 12 段路由, 0-based 段位: [0]tid [1]地区 [3]类别 [4]语言 [5]字母 [8]页码 [11]年份
SEG_AREA, SEG_CLASS, SEG_LANG, SEG_LETTER, SEG_PAGE, SEG_YEAR = 1, 3, 4, 5, 8, 11
_AREAS = ["大陆", "港台", "美国", "韩国", "日本", "泰国", "印度", "法国", "英国"]
_LANGS = ["国语", "粤语", "韩语", "日语", "英语", "泰语"]
_LETTERS = [chr(c) for c in range(ord("A"), ord("Z") + 1)] + ["0-9"]
_YEARS_ALL = [str(y) for y in range(2026, 2009, -1)]       # 2026..2010
_YEARS_MOVIE = [str(y) for y in range(2025, 2009, -1)]      # 电影页筛选从 2025 起
_CATE = {
    "1": ["喜剧", "爱情", "恐怖", "动作", "科幻", "剧情", "战争", "警匪", "犯罪",
          "动画", "奇幻", "武侠", "冒险"],
    "2": ["爱情", "言情", "都市", "家庭", "战争", "喜剧", "古装", "武侠", "偶像",
          "历史", "悬疑", "科幻", "冒险", "惊悚", "犯罪", "运动", "恐怖", "剧情",
          "奇幻", "纪录片", "灾难", "动作"],
    "3": ["情感", "科幻", "热血", "推理", "搞笑", "冒险", "萝莉", "校园", "动作",
          "机战", "运动", "战争", "少年", "少女", "社会", "原创", "亲子"],
    "4": ["真人秀", "音乐", "喜剧", "脱口秀", "文化", "美食"],
}

VERIFY_MARK = "系统安全验证"


# ---------------------------------------------------------------- AES 解密
_SBOX = (
    99, 124, 119, 123, 242, 107, 111, 197, 48, 1, 103, 43, 254, 215, 171, 118,
    186, 202, 130, 201, 125, 250, 89, 71, 240, 173, 212, 162, 175, 156, 164, 114,
    192, 183, 253, 147, 38, 54, 63, 247, 204, 52, 165, 229, 241, 113, 216, 49,
    21, 4, 199, 35, 195, 24, 150, 5, 154, 7, 18, 128, 226, 235, 39, 178, 117,
    9, 131, 44, 26, 27, 110, 90, 160, 82, 59, 214, 179, 41, 227, 47, 132, 83,
    209, 0, 237, 32, 252, 177, 91, 106, 203, 190, 57, 74, 76, 88, 207, 208, 239,
    170, 251, 67, 77, 51, 133, 69, 249, 2, 127, 80, 60, 159, 168, 81, 163, 64,
    143, 146, 157, 56, 245, 188, 182, 218, 33, 16, 255, 243, 210, 205, 12, 19,
    236, 95, 151, 68, 23, 196, 167, 126, 61, 100, 93, 25, 115, 96, 129, 79, 220,
    34, 42, 144, 136, 70, 238, 184, 20, 222, 94, 11, 219, 224, 50, 58, 10, 73,
    6, 36, 92, 194, 211, 172, 98, 145, 149, 228, 121, 231, 200, 55, 109, 141,
    213, 78, 169, 108, 86, 244, 234, 101, 122, 174, 8, 186, 120, 37, 46, 28, 166,
    180, 198, 232, 221, 116, 31, 75, 189, 139, 138, 112, 62, 181, 102, 72, 3,
    246, 14, 97, 53, 87, 185, 134, 193, 29, 158, 225, 248, 152, 17, 105, 217,
    142, 148, 155, 30, 135, 233, 206, 85, 40, 223, 140, 161, 137, 13, 191, 230,
    66, 104, 65, 153, 45, 15, 176, 84, 187, 22,
)
_RCON = (0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


def _pure_aes128_cbc_decrypt(data, key, iv):
    """纯 Python AES-128-CBC 解密 + PKCS7 去填充；壳内无 Crypto 库时兜底。"""
    sbox = _SBOX
    sbox_rev = [0] * 256
    for i, v in enumerate(sbox):
        sbox_rev[v] = i

    def xtime(a):
        return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else (a << 1) & 0xFF

    def expand(k):
        w = list(k)
        for i in range(4, 44):
            t = w[(i - 1) * 4:i * 4]
            if i % 4 == 0:
                t = [sbox[t[1]] ^ _RCON[i // 4], sbox[t[2]], sbox[t[3]], sbox[t[0]]]
            for j in range(4):
                w.append(w[(i - 4) * 4 + j] ^ t[j])
        return w

    def round_key(w, rnd):
        return w[rnd * 16:(rnd + 1) * 16]

    def sub_shift(state, inv):
        if not inv:
            for i in range(16):
                state[i] = sbox[state[i]]
            # 行移位: r 行左移 r 列
            for r in range(1, 4):
                row = [state[r + 4 * c] for c in range(4)]
                row = row[r:] + row[:r]
                for c in range(4):
                    state[r + 4 * c] = row[c]
        else:
            for r in range(1, 4):
                row = [state[r + 4 * c] for c in range(4)]
                row = row[4 - r:] + row[:4 - r]
                for c in range(4):
                    state[r + 4 * c] = row[c]
            for i in range(16):
                state[i] = sbox_rev[state[i]]

    def mix(inv):
        if not inv:
            return
        pass

    def mix_columns(state, inv):
        for c in range(4):
            col = [state[4 * c + r] for r in range(4)]
            if not inv:
                a = col
                state[4 * c + 0] = xtime(a[0]) ^ xtime(a[1]) ^ a[1] ^ a[2] ^ a[3]
                state[4 * c + 1] = a[0] ^ xtime(a[1]) ^ xtime(a[2]) ^ a[2] ^ a[3]
                state[4 * c + 2] = a[0] ^ a[1] ^ xtime(a[2]) ^ xtime(a[3]) ^ a[3]
                state[4 * c + 3] = xtime(a[0]) ^ a[0] ^ a[1] ^ a[2] ^ xtime(a[3])
            else:
                a = col

                def mul(x, n):
                    r = 0
                    for _ in range(4):
                        if n & 1:
                            r ^= x
                        hi = x & 0x80
                        x = (x << 1) & 0xFF
                        if hi:
                            x ^= 0x1B
                        n >>= 1
                    return r

                state[4 * c + 0] = mul(a[0], 14) ^ mul(a[1], 11) ^ mul(a[2], 13) ^ mul(a[3], 9)
                state[4 * c + 1] = mul(a[0], 9) ^ mul(a[1], 14) ^ mul(a[2], 11) ^ mul(a[3], 13)
                state[4 * c + 2] = mul(a[0], 13) ^ mul(a[1], 9) ^ mul(a[2], 14) ^ mul(a[3], 11)
                state[4 * c + 3] = mul(a[0], 11) ^ mul(a[1], 13) ^ mul(a[2], 9) ^ mul(a[3], 14)

    def add_round(state, rk):
        for i in range(16):
            state[i] ^= rk[i]

    rk = expand(key)
    if len(data) % 16:
        data = data[:len(data) - len(data) % 16]
    out = bytearray()
    prev = list(iv[:16])
    for off in range(0, len(data), 16):
        block = list(data[off:off + 16])
        orig = block[:]
        add_round(block, round_key(rk, 10))
        for rnd in range(9, 0, -1):
            sub_shift(block, True)
            mix_columns(block, True)
            add_round(block, round_key(rk, rnd))
        sub_shift(block, True)
        add_round(block, round_key(rk, 0))
        for i in range(16):
            out.append(block[i] ^ prev[i])
        prev = orig
    pad = out[-1] if out else 0
    if 1 <= pad <= 16 and len(out) >= pad:
        out = out[:-pad]
    return bytes(out)


def aes_decrypt(b64_cipher, key, iv):
    """AES-128-CBC 解密 (key/iv 为 ASCII 串, 来自 deplay(响应 aes_key/aes_iv))。"""
    if isinstance(key, str):
        key = key.encode("utf-8")
    if isinstance(iv, str):
        iv = iv.encode("utf-8")
    raw = base64.b64decode(b64_cipher)
    try:
        from Crypto.Cipher import AES as _CA
        pt = _CA.new(key, _CA.MODE_CBC, iv).decrypt(raw)
    except Exception:
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
            pt = d.update(raw) + d.finalize()
        except Exception:
            pt = _pure_aes128_cbc_decrypt(raw, key, iv)
    pad = pt[-1] if pt else 0
    if 1 <= pad <= 16 and len(pt) >= pad:
        pt = pt[:-pad]
    return pt.decode("utf-8", "replace")


class Spider(BaseSpider):
    def init(self, extend=""):
        self.site = SITE

    def getName(self):
        return "歪比巴卜"

    # ------------------------------------------------------------ helpers
    def _call_net(self, url, options=None):
        """统一网络出口: 优先 App 注入的 self.net.req, 否则用 base.spider 的 fetch/post
        (FongMi com.fongmi.chaquo.Spider 5.1.6 实测不注入 net, 只有 requests 封装)。
        返回 {code, content} 或 {error}, timeout 选项为毫秒。"""
        opts = dict(options or {})
        net = getattr(self, "net", None)
        if net is not None and hasattr(net, "req"):
            return net.req(url, opts)
        headers = opts.get("headers") or {}
        timeout = (opts.get("timeout") or TIMEOUT_MS) / 1000.0
        method = str(opts.get("method") or "GET").upper()
        try:
            if method == "POST":
                rsp = self.post(url, data=opts.get("body"), headers=headers,
                                timeout=timeout)
            else:
                rsp = self.fetch(url, headers=headers, timeout=timeout)
            return {"code": rsp.status_code, "content": rsp.text}
        except Exception as e:
            return {"error": "%s: %s" % (type(e).__name__, e)}

    def _req(self, url, options=None):
        """统一请求；网络错误 / 非 2xx / 验证码页 / 429 直接抛错，不伪装成功。"""
        opts = {"timeout": TIMEOUT_MS}
        if options:
            opts.update(options)
        headers = opts.setdefault("headers", {})
        # 站点要求完整浏览器头, 缺 Accept/sec-ch-ua 会 403 (实测)
        headers.setdefault("User-Agent", UA)
        headers.setdefault("Accept",
                           "text/html,application/xhtml+xml,application/xml;"
                           "q=0.9,image/avif,image/webp,*/*;q=0.8")
        headers.setdefault("Accept-Language", "zh-CN,zh;q=0.9")
        headers.setdefault("sec-ch-ua",
                           '"Chromium";v="124", "Google Chrome";v="124", '
                           '"Not-A.Brand";v="99"')
        headers.setdefault("sec-ch-ua-mobile", "?0")
        headers.setdefault("sec-ch-ua-platform", '"Windows"')
        headers.setdefault("Upgrade-Insecure-Requests", "1")
        headers.setdefault("Referer", self.site + "/")
        r = self._call_net(url, opts)
        if r.get("error"):
            raise ValueError("请求失败: %s" % r["error"])
        code = r.get("code", 0)
        if code == 429:
            raise ValueError("站点限流 (429)，请稍后再试")
        if not 200 <= code < 300:
            raise ValueError("HTTP %s" % code)
        html = r.get("content") or ""
        if VERIFY_MARK in html[:4000]:
            raise ValueError("站点要求验证码验证，当前无法获取该数据")
        return html

    @staticmethod
    def _cards(html, limit=0):
        """列表卡片: a.module-poster-item -> (id, name, pic, note)"""
        out, seen = [], set()
        for m in re.finditer(
            r'<a[^>]+href="(/detail/(\d+)\.html)"[^>]+title="([^"]*)"[^>]*class="module-poster-item[^"]*"',
            html,
        ):
            href, vid, name = m.group(1), m.group(2), m.group(3)
            if vid in seen:
                continue
            seen.add(vid)
            seg = html[m.start():m.start() + 900]
            pic = re.search(r'data-original="([^"]+)"', seg)
            note = re.search(r'class="module-item-note">([^<]*)<', seg)
            out.append({
                "vod_id": vid,
                "vod_name": name.strip(),
                "vod_pic": pic.group(1) if pic else "",
                "vod_remarks": (note.group(1).strip() if note else ""),
            })
            if limit and len(out) >= limit:
                break
        if not out:
            # class 属性在 title 前的兜底
            for m in re.finditer(
                r'<a[^>]+class="module-poster-item[^"]*"[^>]+href="(/detail/(\d+)\.html)"[^>]+title="([^"]*)"',
                html,
            ):
                vid, name = m.group(2), m.group(3)
                if vid in seen:
                    continue
                seen.add(vid)
                seg = html[m.start():m.start() + 900]
                pic = re.search(r'data-original="([^"]+)"', seg)
                note = re.search(r'class="module-item-note">([^<]*)<', seg)
                out.append({
                    "vod_id": vid,
                    "vod_name": name.strip(),
                    "vod_pic": pic.group(1) if pic else "",
                    "vod_remarks": (note.group(1).strip() if note else ""),
                })
                if limit and len(out) >= limit:
                    break
        return out

    @staticmethod
    def _pagecount(html, tid=""):
        """分页区尾页链接 -> pagecount (只取真实分页链接, 不碰筛选/年份链接)"""
        for label in ("尾页", "末页"):
            m = re.search(
                r'<a href="(/show/[^"]+)"[^>]*>\s*' + label + r'\s*</a>', html)
            if m:
                name = m.group(1).split("/")[-1]
                if name.endswith(".html"):
                    name = name[:-5]
                # 页码 = 最后一个 <1900 的纯数字段 (年份>=2010 排除;
                # letter=0-9 含 dash 会使段数偏移, 逐段扫描兼容)
                page_no = 0
                for tok in name.split("-"):
                    if tok.isdigit() and int(tok) < 1900:
                        page_no = int(tok)
                if page_no:
                    return max(1, page_no)
        # 无分页控件(如空结果页)
        return 1

    # ------------------------------------------------------------ 接口
    @staticmethod
    def _filter_rows(tid):
        """分类筛选行 (值直接拼入 show 路由段)"""
        years = _YEARS_MOVIE if tid == "1" else _YEARS_ALL
        return [
            {"key": "cate", "name": "剧情",
             "value": [{"n": "全部", "v": ""}] + [{"n": v, "v": v} for v in _CATE[tid]]},
            {"key": "area", "name": "地区",
             "value": [{"n": "全部", "v": ""}] + [{"n": v, "v": v} for v in _AREAS]},
            {"key": "lang", "name": "语言",
             "value": [{"n": "全部", "v": ""}] + [{"n": v, "v": v} for v in _LANGS]},
            {"key": "letter", "name": "字母",
             "value": [{"n": "全部", "v": ""}] + [{"n": v, "v": v} for v in _LETTERS]},
            {"key": "year", "name": "年份",
             "value": [{"n": "全部", "v": ""}] + [{"n": v, "v": v} for v in years]},
        ]

    def homeContent(self, filter):
        result = {"class": list(CLASSES)}
        if filter:
            result["filters"] = {c["type_id"]: self._filter_rows(c["type_id"])
                                 for c in CLASSES}
        return result

    def homeVideoContent(self):
        html = self._req(self.site + "/")
        items = self._cards(html, limit=18)
        return {"list": items}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if str(pg).isdigit() and int(pg) > 0 else 1
        # 12 段路由: 段值来自筛选, 页码在第 9 段(1-based)
        segs = [""] * 12
        segs[0] = str(tid)
        if isinstance(extend, dict):
            for key, seg in (("area", SEG_AREA), ("cate", SEG_CLASS),
                             ("lang", SEG_LANG), ("letter", SEG_LETTER),
                             ("year", SEG_YEAR)):
                v = str(extend.get(key) or "").strip()
                if v and v != "全部":
                    segs[seg] = quote(v, safe="")
        segs[SEG_PAGE] = str(page)
        url = "%s/show/%s.html" % (self.site, "-".join(segs))
        html = self._req(url)
        items = self._cards(html)
        if not items and page > 1:
            raise ValueError("分类第 %d 页无数据" % page)
        return {
            "list": items,
            "page": page,
            "pagecount": self._pagecount(html, tid),
            "limit": len(items) or 36,
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if str(pg).isdigit() and int(pg) > 0 else 1
        kw = quote(str(key or "").strip(), safe="")
        if not kw:
            raise ValueError("搜索关键字为空")
        # 实测: /search/* 服务端强制验证码(系统安全验证), suggest 403。
        # _req 检出验证码页会抛错, 不会伪装成成功空列表; 分页格式被拦截未验证。
        url = "%s/search/%s-------------.html" % (self.site, kw)
        html = self._req(url)
        items = self._cards(html)
        if not items and page > 1:
            raise ValueError("搜索第 %d 页无数据" % page)
        return {
            "list": items,
            "page": page,
            "pagecount": self._pagecount(html) if items else 1,
            "limit": len(items) or 20,
        }

    def detailContent(self, ids):
        vid = str(ids[0] if ids else "").split("/")[-1]
        if not vid.isdigit():
            raise ValueError("无效的影片 ID")
        html = self._req("%s/detail/%s.html" % (self.site, vid))
        name = re.search(r'<h1[^>]*>\s*<a[^>]*>([^<]+)</a>', html) or re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        title = name.group(1).strip() if name else ""
        pic = re.search(r'class="module-item-pic"[^>]*>\s*<img[^>]+data-original="([^"]+)"', html) or \
            re.search(r'<img[^>]+class="[^"]*lazy[^"]*"[^>]+data-original="([^"]+)"', html)
        content = re.search(
            r'class="module-info-introduction-content[^"]*"[^>]*>\s*<p>([\s\S]*?)</p>', html) or \
            re.search(r'class="module-info-content"[\s\S]*?<p>([\s\S]*?)</p>', html)
        # 备注取详情区「集数:」值 (module-item-note 在本页只属于「相关推荐」卡片)
        ep = re.search(r'集数：</span>\s*<div class="module-info-item-content">([^<]*)<', html)
        if not ep:
            ep = re.search(r'集数：</span>\s*<p class="module-info-item-content">([^<]*)<', html)
        # 年份/地区: h1 下 module-info-tag-link (href 为 URL 编码, 取链接文本)
        tag_year, tag_area = None, None
        for tm in re.finditer(
                r'<a[^>]+href="/show/\d-([^-"]*)-[^"]*"[^>]*>\s*([^<]+)</a>', html):
            txt = tm.group(2).strip()
            if not txt:
                continue
            if txt.isdigit() and len(txt) == 4:
                if not tag_year:
                    tag_year = txt
            elif not tag_area:
                tag_area = txt
            if tag_year and tag_area:
                break

        # 线路 tab (首个 tab class 带 active, 按 y-playList 区顺序)
        tabs = re.findall(
            r'class="module-tab-item tab-item[^"]*"[^>]+data-dropdown-value="([^"]+)"', html)
        # 选集面板: 所有面板 id 均重复为 "panel1", 按文档顺序切分
        panels, last = [], None
        for pm in re.finditer(r'<div class="module-list[^"]*"\s+id="panel\d+"', html):
            if last is not None:
                panels.append(html[last:pm.start()])
            last = pm.end()
        if last is not None:
            panels.append(html[last:])
        lines_by_panel = []
        for seg in panels:
            eps = []
            for em in re.finditer(
                r'<a class="module-play-list-link"\s+href="(/vplay/[^"]+)"[^>]*>([\s\S]*?)</a>',
                seg,
            ):
                ep_name = re.sub(r"<[^>]+>", "", em.group(2)).strip()
                if not ep_name:
                    continue
                eps.append((ep_name, em.group(1)))
            if eps:
                lines_by_panel.append(eps)
        if not lines_by_panel:
            raise ValueError("详情页未找到播放选集")

        flags, lines = [], []
        for i, eps in enumerate(lines_by_panel):
            flag = tabs[i] if i < len(tabs) else ("线路%d" % (i + 1))
            flags.append(self._safe(flag))
            lines.append("#".join(
                "%s$%s" % (self._safe(ep), href) for ep, href in eps
            ))

        item = {
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic.group(1) if pic else "",
            "vod_remarks": ep.group(1).strip() if ep else "",
            "vod_content": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", content.group(1))).strip() if content else "",
            "vod_play_from": "$$$".join(flags),
            "vod_play_url": "$$$".join(lines),
        }
        if tag_year:
            item["vod_year"] = tag_year
        if tag_area and tag_area != tag_year:
            item["vod_area"] = tag_area
        return {"list": [item]}

    def playerContent(self, flag, id, vipFlags):
        import time as _time
        from urllib.parse import unquote, urlencode
        path = str(id or "")
        if not path.startswith("/vplay/"):
            path = "/vplay/" + path.lstrip("/")
        html = self._req(self.site + path)

        # 1) 播放页 var player_aaaa (含嵌套 vod_data, 用括号配对截取 JSON)
        m = re.search(r"var player_aaaa=", html)
        if not m:
            raise ValueError("播放页缺少 player_aaaa")
        start = html.find("{", m.end())
        depth, end, in_str, esc = 0, -1, False, False
        for i in range(start, len(html)):
            c = html[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end < 0:
            raise ValueError("播放页 player_aaaa 结构不完整")
        try:
            pa = json.loads(html[start:end])
        except Exception:
            raise ValueError("播放页 player_aaaa 解析失败")
        token = pa.get("url") or ""
        if not token:
            raise ValueError("播放页缺少 url 令牌")
        link_next = pa.get("link_next") or ""

        # 2) 播放器地址 (parse.js 硬编码域名; 不可信 iframe 可能被动态构造)
        fm = re.search(r'src="(https://[^"]+/player/\?[^"]*)"', html)
        if fm:
            iframe = fm.group(1).replace("&amp;", "&")
            player_base = iframe.split("?")[0]
        else:
            pm = re.search(r'(https://[^\s"\']+/player/\?url=)', html)
            if not pm:
                # parse.js 运行时构造, 落盘 HTML 无 iframe: 抓 parse.js 提取
                js = self._req(self.site + "/static/player/parse.js")
                pm = re.search(r'src="(https://[^"]+/player/\?url=)', js)
            if not pm:
                raise ValueError("未找到播放器地址")
            player_base = pm.group(1).split("?")[0]
        # 统一单尾斜杠, 避免 player//api.php
        player_base = player_base.rstrip("/") + "/"
        player_host = urlsplit(player_base).hostname or ""

        # 3) urlValueurl = token + &next= + next (parse.js: "//" + document.domain + link_next)
        url_value = token
        if link_next:
            site_host = urlsplit(self.site).hostname or "wbbb1.com"
            nxt = unquote(link_next)
            if not nxt.startswith("//"):
                nxt = "//" + site_host + ("/" + nxt.lstrip("/") if nxt else "")
            url_value += "&next=" + nxt

        # 4) 三 key 动态计算 (服务端校验, 见文档头)
        calc = _calculate(url_value)
        ts = int(_time.time())
        key = _enplay(_md5_hex(url_value + _SALT), url_value)
        vkey = _enplay(str(ts) + _md5_hex(calc + _SALT), url_value)
        ckey = _enplay(_md5_hex(player_host + _SALT), url_value)

        # Referer = 播放器页真实地址 (parse.js 拼出的 iframe src)
        referer = player_base + "?url=" + quote(token, safe="")
        if link_next:
            referer += "&next=" + unquote(link_next)
        referer += "&title="

        # 5) POST api.php (同源相对路径, 需 Referer/Origin/X-Requested-With)
        body = urlencode({"url": url_value, "key": key, "vkey": vkey, "ckey": ckey})
        r = self._call_net(player_base + "api.php", {
            "timeout": TIMEOUT_MS,
            "method": "POST",
            "headers": {
                "User-Agent": UA,
                "Referer": referer,
                "Origin": player_base.rsplit("/", 2)[0],
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            "body": body,
        })
        if r.get("error"):
            raise ValueError("解析请求失败: %s" % r["error"])
        if not 200 <= r.get("code", 0) < 300:
            raise ValueError("解析 HTTP %s" % r.get("code"))
        try:
            data = json.loads(r.get("content") or "{}")
        except Exception:
            raise ValueError("解析响应不是 JSON")
        if data.get("code") != 200 or not data.get("url"):
            raise ValueError("解析失败: %s" % (data.get("msg") or data.get("code")))
        if (data.get("type") or "") not in ("m3u8", "mp4", ""):
            raise ValueError("不支持的播放类型: %s" % data.get("type"))

        # 6) aes_key/aes_iv 经 RC4(deplay) 还原 -> AES-CBC 解 url -> m3u8
        aes_key = data.get("aes_key") or ""
        aes_iv = data.get("aes_iv") or ""
        if not aes_key or not aes_iv:
            raise ValueError("响应缺少 aes_key/aes_iv")
        k = _deplay(aes_key, url_value)
        iv = _deplay(aes_iv, url_value)
        media = aes_decrypt(data["url"], k, iv)
        if not media.startswith("http"):
            raise ValueError("解密结果不是有效地址")
        return {
            "parse": 0,
            "jx": 0,
            "url": media,
            "header": {"User-Agent": UA, "Referer": self.site + "/"},
        }

    def isVideoFormat(self, url):
        path = urlsplit(str(url or "")).path.lower()
        return path.endswith(".m3u8") or path.endswith(".mp4")

    def destroy(self):
        pass

    @staticmethod
    def _safe(name):
        return str(name or "").replace("$", "＄").replace("#", "＃").strip()
