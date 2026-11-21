# -*- coding: utf-8 -*-

import html as _html
import json
import re
import threading
from base64 import b64decode
from urllib.parse import quote, unquote, urljoin

import requests
import urllib3

urllib3.disable_warnings()


class Spider:
 def __init__(self):
  self.host = "https://www.yinhuaone.net"
  self.headers = {
   "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
   "Referer": self.host + "/",
   "Accept-Language": "zh-CN,zh;q=0.9",
  }
  self.classes = [
   {"type_id": "1", "type_name": "日本动漫"},
   {"type_id": "2", "type_name": "国产动漫"},
   {"type_id": "3", "type_name": "欧美动漫"},
  ]
  self._lock = threading.Lock()
  self._session = None
  self._mcache = {}

 def getName(self):
  return "樱花动漫"

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
  return {"User-Agent": ua, "Accept-Language": "zh-CN,zh;q=0.9", "Referer": ref}

 def _get(self, url, referer=None):
  hd = self._page_header(referer or self.host + "/")
  for _ in range(2):
   try:
    r = self.session.get(url, headers=hd, timeout=20, verify=False)
    if r.status_code == 200:
     r.encoding = "utf-8"
     return r.text
   except Exception:
    continue
  return ""

 def _suggest(self, key, limit=20):
  for _ in range(2):
   try:
    r = self.session.get(
     self.host + "/index.php/ajax/suggest",
     params={"mid": "1", "wd": str(key), "limit": int(limit)},
     headers=self._page_header(self.host + "/"),
     timeout=20,
     verify=False,
    )
    if r.status_code == 200 and r.text:
     return json.loads(r.text)
   except Exception:
    continue
  return {}

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
 def _clean(s):
  try:
   t = re.sub(r"<[^>]+>", "", str(s or ""))
   t = _html.unescape(t)
   return re.sub(r"\s+", " ", t).strip()
  except Exception:
   return ""

 def _pic(self, inner):
  try:
   for m in re.finditer(r'data-original="([^"]+)"', inner or ""):
    u = m.group(1).strip()
    if u and "load.gif" not in u and "errorpic" not in u:
     return self._fix(u)
   m = re.search(r'<img[^>]+src="([^"]+)"', inner or "")
   if m:
    u = m.group(1).strip()
    if u and "load.gif" not in u and "errorpic" not in u:
     return self._fix(u)
  except Exception:
   pass
  return ""

 def _cards(self, html):
  result, seen = [], set()
  for m in re.finditer(r'<a([^>]*href="/v/(\d+)\.html"[^>]*)>(.*?)</a>', html or "", re.S):
   attrs, vid, inner = m.group(1), m.group(2), m.group(3)
   if vid in seen:
    continue
   name = ""
   try:
    tm = re.search(r'title="([^"]*)"', attrs or "")
    if tm:
     name = tm.group(1).strip()
   except Exception:
    name = ""
   if not name:
    try:
     nm = re.search(r'module-poster-item-title">([^<]+)</div>', inner or "")
     if nm:
      name = nm.group(1).strip()
    except Exception:
     name = ""
   if not name:
    continue
   if re.search(r"<h1", inner or ""):
    continue
   seen.add(vid)
   remark = ""
   try:
    rm = re.search(r'module-item-note">([^<]*)</div>', inner or "")
    if rm:
     remark = rm.group(1).strip()
   except Exception:
    remark = ""
   result.append({"vod_id": vid, "vod_name": name, "vod_pic": self._pic(inner), "vod_remarks": remark})
  return result

 def homeContent(self, filter=None):
  html = self._get(self.host + "/")
  vods = self._cards(html)
  if not vods:
   vods = self._cards(self._get(self.host + "/s/1.html"))
  return {"class": self.classes, "list": vods[:20], "filters": {}}

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
  tid = str(tid or "1").strip() or "1"
  if tid not in ("1", "2", "3"):
   tid = "1"
  if page > 1:
   return {"page": page, "pagecount": 1, "limit": 0, "list": []}
  html = self._get(self.host + "/s/%s.html" % tid)
  vods = self._cards(html)
  if vods:
   return {"page": 1, "pagecount": 1, "limit": len(vods), "total": len(vods), "list": vods}
  return {"page": 1, "pagecount": 1, "limit": 0, "total": 0, "list": []}

 @staticmethod
 def _norm_vid(v):
  try:
   s = str(v or "").strip()
  except Exception:
   return ""
  m = re.search(r"/v/(\d+)", s)
  if m:
   return m.group(1)
  m = re.search(r"(\d+)", s)
  return m.group(1) if m else s

 def _detail_meta(self, html, vid):
  name, pic, desc = vid, "", ""
  year, area, clazz, director, actor, remark = "", "", "", "", "", ""
  try:
   m = re.search(r"<h1[^>]*>(.*?)</h1>", html or "", re.S)
   if m:
    name = self._clean(m.group(1)) or vid
  except Exception:
   name = vid
  try:
   sec = re.search(r'module-info-poster"(.*?)module-info-main', html or "", re.S)
   scope = sec.group(1) if sec else (html or "")
   m = re.search(r'data-original="([^"]+)"', scope)
   if m:
    pic = self._fix(m.group(1))
  except Exception:
   pic = ""
  try:
   m = re.search(r'module-info-introduction-content[^>]*>(.*?)</div>', html or "", re.S)
   if m:
    desc = self._clean(m.group(1))
  except Exception:
   desc = ""
  try:
   m = re.search(r"/w/1-----------(\d{4})\.html", html or "")
   if m:
    year = m.group(1)
  except Exception:
   pass
  try:
   m = re.search(r'/w/1-([^"/]*?)----------\.html', html or "")
   if m and m.group(1):
    area = unquote(m.group(1))
  except Exception:
   pass
  try:
   m = re.search(r'/w/1---([^"/]*?)--------\.html', html or "")
   if m and m.group(1):
    clazz = unquote(m.group(1))
  except Exception:
   pass
  try:
   m = re.search(r"导演：</span>(.*?)</div>", html or "", re.S)
   if m:
    names = [self._clean(x) for x in re.findall(r"<a[^>]*>([^<]+)</a>", m.group(1))]
    director = ",".join([x for x in names if x])
  except Exception:
   director = ""
  try:
   m = re.search(r"主演：</span>(.*?)</div>", html or "", re.S)
   if m:
    names = [self._clean(x) for x in re.findall(r"<a[^>]*>([^<]+)</a>", m.group(1))]
    actor = ",".join([x for x in names if x])
  except Exception:
   actor = ""
  try:
   m = re.search(r"备注：</span>.*?module-info-item-content\">([^<]*)</div>", html or "", re.S)
   if m:
    remark = self._clean(m.group(1))
  except Exception:
   remark = ""
  return name, pic, desc, year, area, clazz, director, actor, remark

 def _detail_lines(self, html, vid):
  try:
   tabs = re.findall(r'data-dropdown-value="([^"]+)"', html or "")
  except Exception:
   tabs = []
  groups, order = {}, []
  try:
   for m in re.finditer(r'href="(/p/(\d+)-(\d+)-(\d+)\.html)"[^>]*>(?:<span>)?([^<]*)', html or ""):
    path, pvid, sid, nid, nm = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    if pvid != str(vid):
     continue
    try:
     nid_i = int(nid)
    except Exception:
     continue
    if sid not in groups:
     groups[sid] = {}
     order.append(sid)
    if nid_i not in groups[sid]:
     groups[sid][nid_i] = (nm or "").strip() or ("第%02d集" % nid_i)
  except Exception:
   groups, order = {}, []
  names, urls = [], []
  for i, sid in enumerate(order):
   eps = sorted(groups[sid].items())
   line = "#".join(
    ["%s$%s" % (t.strip() or ("第%02d集" % n), self.host + "/p/%s-%s-%d.html" % (vid, sid, n)) for n, t in eps]
   )
   if not line:
    continue
   label = tabs[i].strip() if i < len(tabs) and tabs[i].strip() else ("线路%s" % sid)
   names.append(label)
   urls.append(line)
  return names, urls

 def _one_detail(self, vid):
  try:
   vid = str(vid or "").strip()
   if not vid:
    return None
   html = self._get(self.host + "/v/%s.html" % vid)
   if not html or "module-info-heading" not in html:
    return None
   name, pic, desc, year, area, clazz, director, actor, remark = self._detail_meta(html, vid)
   names, urls = self._detail_lines(html, vid)
   if not names:
    return None
   item = {
    "vod_id": vid,
    "vod_name": name,
    "vod_pic": pic,
    "vod_remarks": remark,
    "vod_year": year,
    "vod_area": area,
    "vod_director": director,
    "vod_actor": actor,
    "vod_content": desc,
    "vod_play_from": "$$$".join(names),
    "vod_play_url": "$$$".join(urls),
   }
   if clazz:
    item["type_name"] = clazz
   return item
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
    x = self._one_detail(self._norm_vid(i))
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
  try:
   key = "" if key is None else str(key).strip()
  except Exception:
   key = ""
  if not key:
   return {"list": [], "page": page, "pagecount": page, "limit": 20, "total": 0}
  size = 20
  try:
   data = self._suggest(key, page * size)
  except Exception:
   data = {}
  if not isinstance(data, dict) or int(data.get("code") or 0) != 1:
   return {"list": [], "page": page, "pagecount": page, "limit": size, "total": 0, "msg": "搜索失败"}
  try:
   total = int(data.get("total") or 0)
  except Exception:
   total = 0
  raw = data.get("list") or []
  if not isinstance(raw, list):
   raw = []
  vods = []
  for it in raw:
   try:
    if not isinstance(it, dict):
     continue
    vid = str(it.get("id") or "").strip()
    nm = str(it.get("name") or "").strip()
    if not vid or not nm:
     continue
    vods.append({"vod_id": vid, "vod_name": nm, "vod_pic": self._fix(it.get("pic") or ""), "vod_remarks": ""})
   except Exception:
    continue
  start = (page - 1) * size
  part = vods[start:start + size]
  try:
   pcount = max(1, (total + size - 1) // size) if total else (page if not part else page + 1)
  except Exception:
   pcount = page
  return {"list": part, "page": page, "pagecount": pcount, "limit": size, "total": total}

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
   "Accept-Language": "zh-CN,zh;q=0.9",
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
  return low.endswith((".m3u8", ".mp4", ".ts", ".m4s", ".key")) or ".m3u8" in low

 def _unescape(self, raw):
  u = str(raw or "")
  try:
   if "\\u" in u:
    u = re.sub(r"\\u([0-9a-fA-F]{4})", lambda g: chr(int(g.group(1), 16)), u)
   u = u.replace("\\/", "/").replace("\\", "")
  except Exception:
   pass
  return u

 def _decode_play_url(self, url, enc):
  u = str(url or "").strip().replace("\\/", "/")
  try:
   if str(enc) == "1":
    return unquote(u)
   if str(enc) == "2":
    pad = "=" * (-len(u) % 4)
    return unquote(b64decode(u + pad).decode("utf-8", errors="ignore"))
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

 def _play(self, raw):
  real = self._unescape(raw)
  if not self._is_media(real):
   return {"parse": 1, "url": real, "header": self._media_header()}
  return {
   "parse": 0,
   "url": self._proxy_url(real, "m3u8"),
   "header": self._media_header(real),
   "format": "application/x-mpegURL"
  }

 def playerContent(self, flag, id, vipFlags=None):
  page = self._fix(id)
  if self._is_media(page):
   return self._play(page)
  html = ""
  for _ in range(3):
   html = self._get(page, self.host + "/")
   if html and "player_aaaa" in html:
    break
  if not html:
   return {"parse": 1, "url": page, "header": self._media_header()}
  play_url, enc = "", "0"
  try:
   m = re.search(r"var player_aaaa=\s*(\{.*?\})\s*</script>", html, re.S)
   if m:
    cfg = json.loads(m.group(1))
    play_url = str(cfg.get("url") or "").strip()
    enc = str(cfg.get("encrypt", "0"))
  except Exception:
   play_url = ""
  if not play_url:
   try:
    m2 = re.search(r'"url"\s*:\s*"(https?[^"]+)"', html)
    if m2:
     play_url = m2.group(1).replace("\\/", "/")
   except Exception:
    play_url = ""
  if play_url:
   play_url = self._decode_play_url(play_url, enc)
  if not play_url:
   return {"parse": 1, "url": page, "header": self._media_header()}
  if not play_url.startswith("http"):
   return {"parse": 1, "url": self._fix(play_url), "header": self._media_header()}
  return self._play(play_url)

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

 def _decode_maybe_b64(self, s):
  t = str(s or "").strip()
  if not t or not t.startswith("http"):
   try:
    pad = "=" * (-len(t) % 4)
    raw = b64decode(t + pad)
    txt = raw.decode("utf-8", errors="ignore").strip()
    if txt.startswith("http"):
     return txt
   except Exception:
    pass
  return t

 def _fetch_img(self, url, referer=""):
  head = self._img_header(referer)
  for _ in range(3):
   try:
    r = self.session.get(url, headers=head, timeout=20, verify=False)
    if r.status_code == 200 and r.content and len(r.content) > 200:
     return r.content
   except Exception:
    continue
  if referer:
   head2 = self._img_header("")
   for _ in range(2):
    try:
     r = self.session.get(url, headers=head2, timeout=20, verify=False)
     if r.status_code == 200 and r.content and len(r.content) > 200:
      return r.content
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
    if ".m3u8" in low_all or "m3u8" in low_all:
     kind = "m3u8"
    elif url.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif", ".heic")):
     kind = "img"
    else:
     kind = "ts"
   if kind == "img":
    try:
     raw = self._decode_maybe_b64(url)
     if raw.startswith("//"):
      raw = "https:" + raw
     if not raw.startswith("http"):
      return [404, "text/plain", "Unsupported"]
     data = self._fetch_img(raw, referer)
    except Exception:
     data = b""
    if not data:
     return [404, "text/plain", "Fetch Failed"]
    return [200, self._img_ct(data), data]
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
    elif body[:4] == b"\x89PNG":
     mime = "image/png"
    elif body[:3] == b"\xff\xd8\xff":
     mime = "image/jpeg"
    elif body[:4] == b"RIFF":
     mime = "audio/wav"
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
