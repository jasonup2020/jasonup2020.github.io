# -*- coding: utf-8 -*-
import json
import re
from urllib.parse import quote, urljoin
from base.spider import Spider as BaseSpider

# 人人影视排行榜(m.yysub.cc) 官方 JSON API 爬虫
# 数据链路：/api/resource_top 推荐 -> /api/resource 分类 -> /api/search 搜索
#          /api/resource/{id} 详情 -> /api/resource_item 资源列表 -> /api/resource_item_file 磁力链
# 站点为磁力链资源站，播放值传 itemid，playerContent 时再取磁力链，避免详情页 N+1 请求
# 网络：新旧影视兼容 —— 新影视注入 self.net，旧影视不注入，回落 base/spider.py 的 self.fetch
class Spider(BaseSpider):
    PAGE_SIZE = 10

    def __init__(self):
        super().__init__()
        self.host = "https://m.yysub.cc"
        # 磁力转流服务地址（外部部署的 yysub_relay.py）；为空时 playerContent 返回原始磁力链
        self.relay = ""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Referer": "https://m.yysub.cc/",
            "client": "6",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.classes = [
            {"type_id": "", "type_name": "全部"},
            {"type_id": "tv", "type_name": "电视剧"},
            {"type_id": "movie", "type_name": "电影"},
            {"type_id": "openclass", "type_name": "公开课"},
        ]

    def getName(self):
        return "人人影视"

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
            if ext.get("relay"):
                self.relay = str(ext.get("relay")).rstrip("/")
        return None

    # ==================== 网络 ====================
    def _api(self, path, params=None):
        # 官方 JSON API；非 2xx 或无效 JSON 抛出，不做假成功空列表
        url = self.host + "/api/" + path.lstrip("/")
        q = {k: v for k, v in (params or {}).items() if v not in (None, "")} or None
        net = getattr(self, "net", None)
        if net is not None:
            # 新影视：注入 net，走 net.json
            opts = {"headers": self.headers, "timeout": 15000}
            if q:
                opts["params"] = q
            return net.json(url, opts)
        # 旧影视：不注入 net，回落 base/spider.py 的 fetch
        rsp = self.fetch(url, params=q, headers=self.headers, timeout=15)
        code = getattr(rsp, "status_code", 0)
        if not 200 <= int(code) < 300:
            raise ValueError("HTTP %s" % code)
        try:
            return json.loads(rsp.text)
        except Exception:
            raise ValueError("无效 JSON")

    def _pic(self, u):
        if not u:
            return ""
        if u.startswith("http"):
            return u
        # 前端规则：ftpUrl = origin.replace(/^m\./, 'ftp.')/，相对图片路径拼到 ftp 域名
        return urljoin(re.sub(r"^https?://m\.", "https://ftp.", self.host) + "/", u)

    # ==================== 列表 ====================
    def _card(self, i):
        # resource 列表、search 列表与 resource_info 包装共用
        if isinstance(i, dict) and isinstance(i.get("resource_info"), dict):
            i = i["resource_info"]
        rid = i.get("id") or i.get("itemid") or i.get("rid")
        name = (i.get("cnname") or i.get("title") or "").strip()
        poster = i.get("poster") or (i.get("poster_map") or {}).get("b") or i.get("poster_b") or ""
        remark = (i.get("play_status") or "").strip()
        score = i.get("score")
        try:
            if score not in (None, "", 0) and float(score) > 0:
                remark = (remark + " " if remark else "") + str(score) + "分"
        except Exception:
            pass
        vod = {
            "vod_id": str(rid) if rid not in (None, "") else "",
            "vod_name": name,
            "vod_pic": self._pic(poster),
            "vod_remark": remark,
        }
        if i.get("publish_year"):
            vod["vod_year"] = str(i.get("publish_year"))
        if i.get("area"):
            vod["vod_area"] = str(i.get("area"))
        if i.get("category"):
            vod["vod_class"] = str(i.get("category"))
        return vod

    def _page(self, items, pg):
        # 站点已分页，直接回传当页；接口无 total/pagecount，按满页推下一页
        return {
            "page": int(pg),
            "pagecount": int(pg) + 1 if len(items) >= self.PAGE_SIZE else int(pg),
            "limit": self.PAGE_SIZE,
            "list": items,
        }

    # ==================== 首页 ====================
    def homeContent(self, filter):
        return {"class": self.classes}

    def homeVideoContent(self):
        data = self._api("index")
        vods = []
        for i in data.get("resource_hot") or []:
            vod = self._card(i)
            if vod["vod_id"] and vod["vod_name"]:
                vods.append(vod)
        if not vods:
            top = self._api("resource_top", {"channel": "tv_week", "limit": self.PAGE_SIZE})
            for i in top.get("data") or []:
                vod = self._card(i)
                if vod["vod_id"] and vod["vod_name"]:
                    vods.append(vod)
        return {"list": vods[:self.PAGE_SIZE]}

    # ==================== 分类 ====================
    def categoryContent(self, tid, pg, filter, extend):
        # 接口仅支持 p 与 channel，分类/地区/排序等筛选服务端不生效，不透传 extend
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        data = self._api("resource", {"p": pg, "channel": tid})
        raw = data.get("list") or []
        vods = []
        for i in raw:
            vod = self._card(i)
            if vod["vod_id"] and vod["vod_name"]:
                vods.append(vod)
        return self._page(vods, pg)

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        key = (key or "").strip()
        if not key:
            return self._page([], pg)
        data = self._api("search", {"keyword": key, "type": "resource", "p": pg})
        vods = []
        for i in data.get("data") or []:
            vod = self._card(i)
            if vod["vod_id"] and vod["vod_name"]:
                vods.append(vod)
        return self._page(vods, pg)

    # ==================== 详情 ====================
    def _ep_name(self, it, channel):
        season = str(it.get("season") or "0")
        episode = str(it.get("episode") or "0")
        size = (it.get("size") or "").strip()
        if channel == "tv":
            try:
                s, e = int(season), int(episode)
            except Exception:
                s, e = 0, 0
            if e > 0:
                name = "S%02dE%02d" % (s, e)
            else:
                name = ("S%02d " % s if s > 0 else "") + "合集"
        else:
            name = (it.get("format") or "资源").strip()
        if size:
            name += " " + size
        return name

    def detailContent(self, ids):
        rid = str(ids[0]) if ids else ""
        if not rid:
            return {"list": []}
        det = self._api("resource/" + rid)
        data = det.get("data") or {}
        channel = str(data.get("channel") or "")
        vod = {
            "vod_id": rid,
            "vod_name": (data.get("cnname") or "").strip(),
            "vod_pic": self._pic(data.get("poster") or (data.get("poster_map") or {}).get("b") or ""),
            "vod_content": ((data.get("detail") or {}).get("content") or "").strip(),
        }
        if data.get("enname"):
            vod["vod_en"] = str(data.get("enname"))
        if data.get("aliasname"):
            vod["vod_sub"] = str(data.get("aliasname"))
        if data.get("areas"):
            vod["vod_area"] = str(data.get("areas"))
        if data.get("lang"):
            vod["vod_lang"] = str(data.get("lang"))
        if data.get("category"):
            vod["vod_class"] = str(data.get("category"))
        if data.get("publish_year"):
            vod["vod_year"] = str(data.get("publish_year"))
        if data.get("premiere"):
            vod["vod_time"] = str(data.get("premiere"))
        if data.get("play_status"):
            vod["vod_remark"] = str(data.get("play_status"))
        sc = det.get("score") or {}
        if isinstance(sc, dict) and sc.get("score"):
            vod["vod_score"] = str(sc.get("score"))
        actors = [c.get("cnname") for c in det.get("character_list") or [] if c.get("cnname")]
        if actors:
            vod["vod_actor"] = "/".join(actors[:12])

        # 资源列表按格式分线，播放值传 itemid
        items_data = self._api("resource_item", {"rid": rid}).get("data") or {}
        items = items_data.get("item_list") or []
        # 网盘线路：一次批量取回各资源项的网盘地址（顺序与 itemid 一一对应，无地址为空串）
        pan_map = {}
        ids = [str(it.get("id")) for it in items if it.get("id")]
        if ids:
            try:
                pan_data = self._api("resource_link",
                                     {"itemid": ",".join(ids), "way": 9, "action": "batch"}).get("data") or []
                for iid, addr in zip(ids, pan_data):
                    addr = (addr or "").strip()
                    if addr:
                        pan_map[iid] = addr
            except Exception:
                pan_map = {}
        lines = {}
        pan_eps = []
        for it in items:
            if not it.get("id"):
                continue
            fmt = (it.get("format") or "磁力").strip() or "磁力"
            name = self._ep_name(it, channel)
            lines.setdefault(fmt, []).append("%s$%s" % (name, it.get("id")))
            if str(it.get("id")) in pan_map:
                pan_eps.append("%s$quark:%s" % (name, it.get("id")))
        sources = []
        urls = []
        for fmt in sorted(lines.keys()):
            sources.append(fmt + " 磁力")
            urls.append("#".join(lines[fmt]))
        if pan_eps:
            sources.append("夸克网盘")
            urls.append("#".join(pan_eps))
        vod["vod_play_from"] = "$$$".join(sources) if sources else "磁力"
        vod["vod_play_url"] = "$$$".join(urls)
        return {"list": [vod]}

    # ==================== 播放 ====================
    def _magnet_addrs(self, itemid):
        # 取指定资源项的磁力链（链接会过期，不缓存）
        data = self._api("resource_item_file", {"itemid": str(itemid)}).get("data") or []
        addr = ""
        for f in data:
            a = (f.get("address") or "").strip()
            if not a:
                continue
            if str(f.get("way") or "") == "2" and a.startswith("magnet:"):
                addr = a
                break
            if not addr:
                addr = a
        return addr

    def _pan_addr(self, itemid):
        data = self._api("resource_link", {"itemid": str(itemid), "way": 9,
                                           "action": "batch"}).get("data") or []
        for a in data:
            a = (a or "").strip()
            if a:
                return a
        return ""

    def playerContent(self, flag, id, vipFlags):
        pid = str(id)
        # 网盘线路：播放值形如 quark:<itemid>，交壳解析器解析播放
        if pid.startswith("quark:"):
            return {"parse": 1, "url": self._pan_addr(pid[len("quark:"):]),
                    "header": {"User-Agent": self.headers["User-Agent"]}}
        # 磁力线路：id 为 resource_item 的 itemid
        addr = self._magnet_addrs(pid)
        # 配置了外部转流服务时，把磁力指给它（yysub_relay.py），由它边下边读成 http 流
        if self.relay and addr.startswith("magnet:"):
            play_url = self.relay + "/play?link=" + quote(addr, safe="")
        else:
            play_url = addr
        return {"parse": 0, "url": play_url, "header": {"User-Agent": self.headers["User-Agent"]}}

    def localProxy(self, param):
        pass

    def destroy(self):
        pass
