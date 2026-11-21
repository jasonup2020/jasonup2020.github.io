import re
import sys
import threading
import requests
from Crypto.Hash import MD5
sys.path.append("..")
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from urllib.parse import quote, unquote, urlparse, urljoin
from base64 import b64encode, b64decode
import json
import time
from base.spider import Spider


class Spider(Spider):

    def getName(self):
        return "MiFun"

    def getDependence(self):
        return []

    def init(self, extend=""):
        try:
            if isinstance(extend, dict) and extend.get("host"):
                self.host = str(extend.get("host")).rstrip("/")
            else:
                self.host = self.gethost()
        except Exception:
            if not getattr(self, "host", ""):
                self.host = "https://getcn.mymifun.com"
        try:
            self.did = self.getdid()
        except Exception:
            self.did = self.md5(str(int(time.time())))
        return None

    def isVideoFormat(self, url):
        try:
            low = str(url or "").lower().split("?")[0]
            return low.endswith((".m3u8", ".mp4", ".ts", ".m4s", ".key")) or ".m3u8" in low
        except Exception:
            return False

    def manualVideoCheck(self):
        return False

    def action(self, action):
        return {}

    def destroy(self):
        return None

    def homeContent(self, filter=None):
        try:
            data = self.getdata("/api.php/getappapi.index/initV119")
        except Exception:
            return {"class": [], "filters": {}, "list": []}
        dy = {"class": "类型", "area": "地区", "lang": "语言", "year": "年份", "letter": "字母", "by": "排序", "sort": "排序"}
        filters = {}
        classes = []
        homedata = []
        try:
            type_list = data.get("type_list", []) if isinstance(data, dict) else []
        except Exception:
            type_list = []
        for item in type_list:
            try:
                if not isinstance(item, dict):
                    continue
                tname = str(item.get("type_name", "")).strip()
                tid = item.get("type_id", "")
                if tname == "全部":
                    continue
                rec = item.get("recommend_list", []) or []
                if rec:
                    homedata.extend(rec)
                classes.append({"type_name": tname, "type_id": tid})
                # 优先用 filter_type_list构建筛选，兼容 type_extend
                built = []
                try:
                    ftl = item.get("filter_type_list", []) or []
                    for f in ftl:
                        if not isinstance(f, dict):
                            continue
                        fkey = str(f.get("name", "")).strip()
                        if fkey not in dy:
                            continue
                        vals = f.get("list", []) or []
                        arr = []
                        for v in vals:
                            v = str(v).strip()
                            if v:
                                arr.append({"n": v, "v": v})
                        if arr:
                            built.append({"key": fkey, "name": dy[fkey], "value": arr})
                except Exception:
                    built = []
                if not built:
                    try:
                        raw_ext = item.get("type_extend", "") or ""
                        jsontype_extend = json.loads(raw_ext) if isinstance(raw_ext, str) else (raw_ext if isinstance(raw_ext, dict) else {})
                    except Exception:
                        jsontype_extend = {}
                    if isinstance(jsontype_extend, dict):
                        if "sort" not in jsontype_extend:
                            jsontype_extend["sort"] = "最新,最热,最赞"
                        for dkey in jsontype_extend:
                            try:
                                if dkey in dy and str(jsontype_extend[dkey] or "").strip() != "":
                                    values = str(jsontype_extend[dkey]).split(",")
                                    value_array = [{"n": value.strip(), "v": value.strip()} for value in values if value.strip() != ""]
                                    if value_array:
                                        built.append({"key": dkey, "name": dy[dkey], "value": value_array})
                            except Exception:
                                continue
                if built:
                    filters[str(tid)] = built
            except Exception:
                continue
        return {"class": classes, "filters": filters, "list": homedata[:30]}
    def homeVideoContent(self):
        try:
            lst = self.homeContent({}).get("list", []) or []
            return {"list": lst[:20]}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg=1, filter=None, extend=None):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        try:
            ex = {}
            if isinstance(extend, dict):
                ex = extend
            elif isinstance(filter, dict):
                ex = filter
            body = {"area": str(ex.get("area", "全部")), "year": str(ex.get("year", "全部")), "type_id": tid, "page": page,
                    "sort": str(ex.get("sort", "最新")), "lang": str(ex.get("lang", "全部")),
                    "class": str(ex.get("class", "全部"))}
            data = self.getdata("/api.php/getappapi.index/typeFilterVodList", body)
            lst = data.get("recommend_list", []) or [] if isinstance(data, dict) else []
        except Exception:
            return {"list": [], "page": 1, "pagecount": 1, "limit": 0, "total": 0}
        try:
            limit = len(lst)
            # 站点已分页：满页则预留下一页，不虚构 total
            pagecount = page + 1 if limit >= 30 else page
            return {"list": lst, "page": page, "pagecount": pagecount, "limit": limit, "total": 0}
        except Exception:
            return {"list": lst, "page": page, "pagecount": page, "limit": len(lst), "total": 0}
    def detailContent(self, ids):
        try:
            seq = ids if isinstance(ids, (list, tuple)) else [ids]
            vid = str(seq[0]) if seq else ""
        except Exception:
            vid = ""
        if not vid:
            return {"list": []}
        try:
            data = self.getdata("/api.php/getappapi.index/vodDetail", f"vod_id={vid}")
        except Exception:
            return {"list": []}
        try:
            if not isinstance(data, dict):
                return {"list": []}
            vod = data.get("vod", {}) or {}
            play_list = data.get("vod_play_list", []) or []
            play = []
            names = []
            direct_flags = []
            for idx, itt in enumerate(play_list):
                try:
                    if not isinstance(itt, dict):
                        continue
                    pinfo = itt.get("player_info", {}) or {}
                    urls = itt.get("urls", []) or []
                    # 服务端 show 已被公告覆盖，用 from 映射中文名（APK 内无映射，见验证说明）
                    try:
                        first_from = str(((urls[0] if urls else {}) or {}).get("from", "") or "").strip()
                    except Exception:
                        first_from = ""
                    try:
                        from_cn = {"dyttm3u8": "电影天堂", "ffm3u8": "非凡影视", "1080zyk": "1080资源库", "toutiao": "头条", "tkyun": "天空云", "file": "文件"}
                    except Exception:
                        from_cn = {}
                    try:
                        show_raw = str(pinfo.get("show", "") or "").strip()
                    except Exception:
                        show_raw = ""
                    if "请先更新" not in show_raw and show_raw:
                        show = show_raw
                    else:
                        show = from_cn.get(first_from, first_from) or ("线路" + str(idx + 1))
                    # 去除分隔符，保持唯一
                    show = show.replace("$$$", "").replace("#", "").replace("$", "")
                    try:
                        first_u = urls[0] if urls else {}
                        line_direct = str((first_u or {}).get("url", "") or "").strip().startswith("http")
                    except Exception:
                        line_direct = False
                    a = []
                    frm = ""
                    for it in urls:
                        try:
                            if not isinstance(it, dict):
                                continue
                            if not frm:
                                frm = str(it.get("from", "")).strip()
                            item = dict(it)
                            item["user_agent"] = pinfo.get("user_agent", "")
                            item["parse"] = pinfo.get("parse", "")
                            nm = str(item.get("name", "")).strip().replace("$$$", "").replace("#", "").replace("$", "") or "正片"
                            a.append(nm + "$" + self.e64(json.dumps(item, ensure_ascii=False)))
                        except Exception:
                            continue
                    if not a:
                        continue
                    # 同名冲突后缀序号
                    base_show = show
                    suffix = 2
                    while show in names:
                        show = base_show + str(suffix)
                        suffix += 1
                    names.append(show)
                    play.append("#".join(a))
                    direct_flags.append(line_direct)
                except Exception:
                    continue
            if not play:
                return {"list": []}
            try:
                order = sorted(range(len(names)), key=lambda i: (not direct_flags[i], i))
                names = [names[i] for i in order]
                play = [play[i] for i in order]
            except Exception:
                pass
            vod["vod_play_from"] = "$$$".join(names)
            vod["vod_play_url"] = "$$$".join(play)
            return {"list": [vod]}
        except Exception:
            return {"list": []}
    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        try:
            kw = str(key or "").strip()
            if not kw:
                return {"list": [], "page": page, "pagecount": 1, "limit": 0, "total": 0}
            data = self.getdata("/api.php/getappapi.index/searchList", {"keywords": kw, "type_id": 0, "page": page})
            lst = data.get("search_list", []) or [] if isinstance(data, dict) else []
        except Exception:
            return {"list": [], "page": page, "pagecount": 1, "limit": 0, "total": 0}
        try:
            limit = len(lst)
            pagecount = page + 1 if limit >= 20 else page
            if pagecount < 1:
                pagecount = 1
            return {"list": lst, "page": page, "pagecount": pagecount, "limit": limit, "total": 0}
        except Exception:
            return {"list": lst, "page": page, "pagecount": page, "limit": len(lst), "total": 0}
    def playerContent(self, flag, id, vipFlags=None):
        try:
            raw = self.d64(id) if isinstance(id, str) else ""
            ids = json.loads(raw) if raw else {}
        except Exception:
            ids = {}
        if not isinstance(ids, dict):
            ids = {}
        ua = ids.get("user_agent", "") or "okhttp/3.14.9"
        h = {"User-Agent": ua}
        url = ""
        parse_flag = 0
        try:
            parse_api_url = str(ids.get("parse_api_url", "") or "")
            vurl = str(ids.get("url", "") or "")
            token = str(ids.get("token", "") or "")
            parse_api = str(ids.get("parse", "") or "")
            try:
                vurl_s = vurl.strip()
            except Exception:
                vurl_s = ""
            if vurl_s.startswith("http"):
                try:
                    direct = self.isVideoFormat(vurl_s)
                except Exception:
                    direct = False
                if direct:
                    return {"parse": 0, "url": vurl_s, "header": {"User-Agent": ua, "Referer": (getattr(self, "host", "") or "") + "/"}}
            if parse_api_url and parse_api_url.strip().startswith("http"):
                try:
                    data = self.fetch(parse_api_url.strip(), headers=h, timeout=10).json()
                    if isinstance(data, dict):
                        url = str(data.get("url", "") or "")
                        if not url and isinstance(data.get("data"), dict):
                            url = str(data["data"].get("url", "") or "")
                        if not url and isinstance(data.get("data"), str):
                            url = data["data"]
                except Exception as e:
                    print("解析接口异常:", e)
                    url = ""
            elif vurl:
                if not parse_api:
                    parse_api = parse_api_url.replace(vurl, "") if parse_api_url else ""
                try:
                    body = {"parse_api": parse_api, "url": self.aes(vurl, True), "token": token}
                    resp = self.getdata("/api.php/getappapi.index/vodParse", body)
                    b = resp.get("json", "") if isinstance(resp, dict) else ""
                    if isinstance(b, dict):
                        url = str(b.get("url", "") or "")
                    elif isinstance(b, str) and b.strip():
                        try:
                            url = str(json.loads(b).get("url", "") or "")
                        except Exception:
                            url = ""
                    else:
                        url = ""
                    if isinstance(url, str) and "error" in url:
                        raise ValueError("解析失败: " + url)
                except Exception as e:
                    print("错误信息:", e)
                    url = ""
            # 服务端占位视频统一视为解析失败，避免播错片
            try:
                if isinstance(url, str) and ("mifun.tv/down/" in url or "366ba6b8dbaf45a68d3af837af6ade59" in url):
                    url = ""
            except Exception:
                pass
            if url:
                parse_flag = 0
            else:
                return {"parse": 1, "url": "", "header": h}
        except Exception as e:
            print("错误信息:", e)
            try:
                url = str(ids.get("url", "") or "")
            except Exception:
                url = ""
            parse_flag = 1
        try:
            if isinstance(url, str) and re.search(r"\.jpg|\.png|\.jpeg|\.webp", url, re.IGNORECASE) and url.startswith("http"):
                url = self.Mproxy(url)
        except Exception:
            pass
        if not url:
            return {"parse": 1, "url": "", "header": h}
        return {"parse": parse_flag, "url": url, "header": h}
    def localProxy(self, param):
        try:
            if isinstance(param, str):
                try:
                    param = json.loads(param)
                except Exception:
                    param = {}
            if not isinstance(param, dict):
                param = {}
            else:
                param = dict(param)
            kind = param.get("type", "") or param.get("action", "") or ""
            if isinstance(kind, list):
                kind = kind[0] if kind else ""
            kind = str(kind or "").strip().lower()
            url = param.get("url", "")
            if isinstance(url, list):
                url = url[0] if url else ""
            url = str(url or "").strip()
            # url 可能是 base64后的 m3u8 链接
            if url and not url.startswith("http"):
                try:
                    dec = self.d64(url)
                    if dec and dec.strip().startswith("http"):
                        url = dec.strip()
                except Exception:
                    pass
            try:
                url = unquote(url).strip()
            except Exception:
                pass
            if not url:
                return [404, "text/plain", "Not Found"]
            if url.startswith("//"):
                url = "https:" + url
            if not url.startswith("http"):
                return [404, "text/plain", "Unsupported"]
            if not kind or kind in ("py", "proxy", "media"):
                low = url.lower()
                if ".m3u8" in low or "m3u8" in low:
                    kind = "m3u8"
                elif low.split("?")[0].endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")):
                    kind = "img"
                else:
                    kind = "m3u8"
            if kind == "img":
                try:
                    r = self.fetch(url, headers={"User-Agent": "okhttp/3.14.9", "Referer": getattr(self, "host", "") + "/"}, timeout=15)
                    data = r.content if isinstance(r.content, (bytes, bytearray)) else str(r.content or "").encode("utf-8")
                    if not data:
                        return [404, "text/plain", "Fetch Failed"]
                    ct = "image/jpeg"
                    try:
                        if data[:4] == b"\x89PNG":
                            ct = "image/png"
                        elif data[:3] == b"\xff\xd8\xff":
                            ct = "image/jpeg"
                        elif data[:4] == b"GIF8":
                            ct = "image/gif"
                        elif data[:4] == b"RIFF":
                            ct = "image/webp"
                    except Exception:
                        ct = "image/jpeg"
                    return [200, ct, bytes(data)]
                except Exception:
                    return [404, "text/plain", "Fetch Failed"]
            return self.Mlocal({"url": self.e64(url)}, header={"User-Agent": "okhttp/3.14.9", "Referer": getattr(self, "host", "") + "/"})
        except Exception:
            return [500, "text/plain", "proxy error"]

    def proxy(self, param):
        return self.localProxy(param)

    def liveContent(self, url):
        return ""

    def gethost(self):
        default_host = "https://getcn.mymifun.com"
        try:
            headers = {"User-Agent": "okhttp/3.14.9"}
            response = self.fetch("https://miget-1313189639.cos.ap-guangzhou.myqcloud.com/mifun.txt", headers=headers, timeout=10).text
            host = self.host_late(str(response or "").splitlines())
            if host and host.startswith("http"):
                return host.rstrip("/")
        except Exception:
            pass
        return default_host
    def host_late(self, url_list):
        try:
            if isinstance(url_list, str):
                urls = [u.strip() for u in url_list.replace("\r", "\n").split("\n")]
            elif isinstance(url_list, (list, tuple)):
                urls = []
                for u in url_list:
                    try:
                        for part in str(u or "").replace("\r", "\n").split("\n"):
                            part = part.strip().rstrip("/")
                            if part:
                                urls.append(part)
                    except Exception:
                        continue
            else:
                urls = []
            # 去重并过滤非 http 项
            seen = []
            for u in urls:
                u = str(u or "").strip()
                if u.startswith("http") and u not in seen:
                    seen.append(u)
            urls = seen
            if not urls:
                return "https://getcn.mymifun.com"
            if len(urls) == 1:
                return urls[0]
        except Exception:
            return "https://getcn.mymifun.com"
        results = {}
        threads = []
        def test_host(url):
            try:
                url = str(url or "").strip()
                start_time = time.time()
                response = requests.head(url, timeout=3.0, allow_redirects=False)
                delay = (time.time() - start_time) * 1000
                if response.status_code >= 500:
                    delay = float("inf")
                results[url] = delay
            except Exception:
                results[url] = float("inf")
        for url in urls:
            t = threading.Thread(target=test_host, args=(url,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        try:
            best = min(results.items(), key=lambda x: x[1])[0]
            if results.get(best, float("inf")) == float("inf"):
                return urls[0]
            return best
        except Exception:
            return urls[0]
    def getdid(self):
        try:
            did = self.getCache("did")
        except Exception:
            did = ""
        try:
            if not did:
                t = str(int(time.time()))
                did = self.md5(t)
                try:
                    self.setCache("did", did)
                except Exception:
                    pass
        except Exception:
            did = self.md5(str(int(time.time())))
        return did
    def aes(self, text, b=None):
        key = b"GETMIFUNGEIMIFUN"
        cipher = AES.new(key, AES.MODE_CBC, key)
        if b:
            ct_bytes = cipher.encrypt(pad(text.encode("utf-8"), AES.block_size))
            ct = b64encode(ct_bytes).decode("utf-8")
            return ct
        else:
            pt = unpad(cipher.decrypt(b64decode(text)), AES.block_size)
            return pt.decode("utf-8")

    def header(self):
        t = str(int(time.time()))
        header = {"Referer": self.host,
                  "User-Agent": "okhttp/3.14.9", "app-version-code": "516", "app-ui-mode": "light",
                  "app-api-verify-time": t, "app-user-device-id": self.did,
                  "app-api-verify-sign": self.aes(t, True),
                  "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        return header

    def getdata(self, path, data=None):
        try:
            rsp = self.post(f"{self.host}{path}", headers=self.header(), data=data, timeout=10).json()
        except Exception as e:
            raise ValueError("网络请求失败: " + str(e))
        try:
            if not isinstance(rsp, dict):
                raise ValueError("接口返回异常")
            if rsp.get("code", 1) == 0:
                raise ValueError(str(rsp.get("msg", "接口返回错误")) or "接口返回错误")
            vdata = rsp.get("data", "")
            if isinstance(vdata, list):
                raise ValueError("接口返回错误")
            if not isinstance(vdata, str) or not vdata:
                raise ValueError("接口返回为空")
            plain = self.aes(vdata)
            return json.loads(plain)
        except ValueError:
            raise
        except Exception as e:
            raise ValueError("解密失败: " + str(e))
    def Mproxy(self, url):
        return f"{self.getProxyUrl()}&url={self.e64(url)}&type=m3u8"

    def Mlocal(self, param, header=None, headers=None):
        try:
            if isinstance(param, str):
                try:
                    param = json.loads(param)
                except Exception:
                    param = {}
            if not isinstance(param, dict):
                return [404, "text/plain", "Not Found"]
            raw = param.get("url", "")
            if isinstance(raw, list):
                raw = raw[0] if raw else ""
            raw = str(raw or "").strip()
            if not raw:
                return [404, "text/plain", "Not Found"]
            url = raw if raw.startswith("http") else self.d64(raw)
            url = str(url or "").strip()
            try:
                url = unquote(url)
            except Exception:
                pass
            if url.startswith("//"):
                url = "https:" + url
            if not url.startswith("http"):
                return [404, "text/plain", "Unsupported"]
            head = {}
            try:
                if isinstance(headers, dict):
                    head.update(headers)
                if isinstance(header, dict):
                    head.update(header)
            except Exception:
                head = {}
            try:
                if not head.get("User-Agent"):
                    head["User-Agent"] = "okhttp/3.14.9"
                if not head.get("Referer") and getattr(self, "host", ""):
                    head["Referer"] = self.host + "/"
            except Exception:
                pass
            try:
                ydata = self.fetch(url, headers=head, timeout=15, allow_redirects=False)
            except Exception:
                return [404, "text/plain", "Fetch Failed"]
            try:
                loc = ydata.headers.get("Location", "") if hasattr(ydata, "headers") else ""
            except Exception:
                loc = ""
            if loc:
                url = urljoin(url, str(loc).strip())
                try:
                    ydata = self.fetch(url, headers=head, timeout=15)
                except Exception:
                    return [404, "text/plain", "Fetch Failed"]
            try:
                raw_body = ydata.content
            except Exception:
                raw_body = b""
            if not raw_body:
                return [404, "text/plain", "Fetch Failed"]
            if isinstance(raw_body, (bytes, bytearray)):
                raw_body = bytes(raw_body)
            else:
                raw_body = str(raw_body or "").encode("utf-8")
            try:
                data = raw_body.decode("utf-8")
            except Exception:
                try:
                    data = raw_body.decode("utf-8", errors="ignore")
                except Exception:
                    return [404, "text/plain", "Fetch Failed"]
            if not data or "#EXTM3U" not in data:
                # 非 m3u8 直接按 ts 二进制返回
                mime = "video/mp2t"
                try:
                    if raw_body[:1] == b"\x47":
                        mime = "video/mp2t"
                except Exception:
                    mime = "application/octet-stream"
                return [200, mime, raw_body]
            lines = data.strip().splitlines()
            out = []
            for string in lines:
                s = str(string or "").strip()
                if not s:
                    continue
                if s.startswith("#") or s.startswith("http"):
                    # #EXT-X-KEY 中的 URI 也要绝对化
                    if s.startswith("#") and "URI=" in s:
                        try:
                            m = re.search(r'URI="([^"]+)"', s)
                            if m:
                                u = m.group(1).strip()
                                if u and not u.startswith("http"):
                                    abs_u = urljoin(url, u)
                                    s = s.replace(u, abs_u)
                        except Exception:
                            pass
                    out.append(s)
                    continue
                out.append(urljoin(url, s))
            data = "\n".join(out)
            if not data:
                return [404, "text/plain", "Fetch Failed"]
            return [200, "application/vnd.apple.mpegurl", data]
        except Exception:
            return [500, "text/plain", "proxy error"]
    def e64(self, text):
        try:
            text_bytes = text.encode('utf-8')
            encoded_bytes = b64encode(text_bytes)
            return encoded_bytes.decode('utf-8')
        except Exception as e:
            print(f"Base64编码错误: {str(e)}")
            return ""

    def d64(self, encoded_text):
        try:
            encoded_bytes = encoded_text.encode('utf-8')
            decoded_bytes = b64decode(encoded_bytes)
            return decoded_bytes.decode('utf-8')
        except Exception as e:
            print(f"Base64解码错误: {str(e)}")
            return ""

    def md5(self, text):
        h = MD5.new()
        h.update(text.encode('utf-8'))
        return h.hexdigest()

