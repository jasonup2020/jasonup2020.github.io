#coding=utf-8
#!/usr/bin/python
# 以原可用 Douban 脚本为骨架，合并解密自 20260808163114spider_decrypted.jar 的
# Douban 爬虫逻辑（分类/榜单 tid 与 frodo 接口分支）。保留 TVBox 认可的返回结构。
import sys
import json
import re
import urllib.parse
from datetime import date
sys.path.append('..')
from base.spider import Spider

# 全部分组: key -> (接口路径, 数据key)。已在 2026-08-08 联网逐一验证。
# tv_hot/show_hot 的子分类(tv_domestic/tv_american/...)同样是 subject_collection 形态, 归一化复用
GROUPS = {
    "hot_gaia": ("movie/hot_gaia", "items"),
    "tv_hot": ("subject_collection/tv_hot/items", "subject_collection_items"),
    "tv_domestic": ("subject_collection/tv_domestic/items", "subject_collection_items"),
    "tv_american": ("subject_collection/tv_american/items", "subject_collection_items"),
    "tv_japanese": ("subject_collection/tv_japanese/items", "subject_collection_items"),
    "tv_korean": ("subject_collection/tv_korean/items", "subject_collection_items"),
    "tv_animation": ("subject_collection/tv_animation/items", "subject_collection_items"),
    "anime_hot": ("subject_collection/tv_animation/items", "subject_collection_items"),
    "show_hot": ("subject_collection/show_hot/items", "subject_collection_items"),
    "show_domestic": ("subject_collection/show_domestic/items", "subject_collection_items"),
    "show_foreign": ("subject_collection/show_foreign/items", "subject_collection_items"),
    "movie": ("movie/recommend", "items"),
    "tv": ("tv/recommend", "items"),
    "movie_real_time_hotest": ("subject_collection/movie_real_time_hotest/items", "subject_collection_items"),
    "movie_weekly_best": ("subject_collection/movie_weekly_best/items", "subject_collection_items"),
    "movie_top250": ("subject_collection/movie_top250/items", "subject_collection_items"),
    "tv_real_time_hotest": ("subject_collection/tv_real_time_hotest/items", "subject_collection_items"),
    "tv_chinese_best_weekly": ("subject_collection/tv_chinese_best_weekly/items", "subject_collection_items"),
    "tv_global_best_weekly": ("subject_collection/tv_global_best_weekly/items", "subject_collection_items"),
    "show_chinese_best_weekly": ("subject_collection/show_chinese_best_weekly/items", "subject_collection_items"),
    "show_global_best_weekly": ("subject_collection/show_global_best_weekly/items", "subject_collection_items"),
}
DOUBAN_API = "https://frodo.douban.com/api/v2"
API_KEY = "0ac44ae016490db2204ce0a042db2916"
USER_AGENT = "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.143 Safari/537.36 MicroMessenger/7.0.9.501 NetType/WIFI MiniProgramEnv/Windows WindowsWechat"
REFERER = "https://servicewechat.com/wx2f9b06c1de1ccfca/84/page-frame.html"
PIC_SUFFIX = '@Referer=https://api.douban.com/@User-Agent=Mozilla/5.0%20(Windows%20NT%2010.0;%20Win64;%20x64)%20AppleWebKit/537.36%20(KHTML,%20like%20Gecko)%20Chrome/122.0.0.0%20Safari/537.36'
TODAY = date.today().isoformat()


class Spider(Spider):
    def getName(self):
        return "豆瓣"

    def init(self, extend=""):
        print("============{0}============".format(extend))
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def _fetchJo(self, url):
        return json.loads(self.fetch(url, headers=self.header, timeout=15).text)

    def _localPort(self):
        try:
            from com.github.catvod import Proxy as P
            return int(P.getPort())
        except Exception:
            pass
        return 9978

    def _fireSearch(self, word):
        try:
            word = (word or "").strip()
            if not word:
                return False
            q = urllib.parse.quote(word, safe="")
            ports = [self._localPort()]
            if 9978 not in ports:
                ports.append(9978)
            for port in ports:
                try:
                    r = self.fetch(f"http://127.0.0.1:{port}/action?do=search&word={q}", timeout=3)
                    if r is not None and getattr(r, "status_code", 200) == 200:
                        return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    def _fireSearchAsync(self, word, delay=0.8):
        try:
            import threading
            import time as _time
            w = (word or "").strip()
            if not w:
                return False
            def _run():
                try:
                    _time.sleep(delay)
                    self._fireSearch(w)
                except Exception:
                    pass
            t = threading.Thread(target=_run, daemon=True)
            t.start()
            return True
        except Exception:
            try:
                return self._fireSearch(word)
            except Exception:
                return False

    def action(self, act):
        try:
            act = (act or "").strip()
            if act.startswith("search:"):
                word = act[7:].strip()
                if word:
                    self._fireSearchAsync(word, delay=0.8)
                    return {}
            return {}
        except Exception:
            return {}

    def _autoPages(self, firstJo, data_key, need, fetchNext):
        acc = list(firstJo.get(data_key) or [])
        total = firstJo.get("total") or 0
        tries = 0
        while len(acc) < need and tries < 3:
            nxt = fetchNext(len(acc))
            if not nxt:
                break
            chunk = nxt.get(data_key) or []
            if not chunk:
                break
            acc.extend(chunk)
            total = nxt.get("total") or total
            if len(chunk) < need:
                break
            tries += 1
        return acc, total

    # 判断是否已上映: 优先 is_released 字段, 兼容 release_date/date
    def isReleased(self, item):
        if "is_released" in item and item["is_released"] is not None:
            return bool(item["is_released"])
        if item.get("release_date"):
            return item["release_date"] <= TODAY
        if item.get("date"):
            return item["date"] <= TODAY
        return True

    def _pic(self, item):
        pic = item.get("pic") or {}
        if pic.get("normal"):
            return pic["normal"] + PIC_SUFFIX
        if item.get("cover_url"):
            return str(item["cover_url"]).split("?")[0] + PIC_SUFFIX
        photos = item.get("photos") or []
        if photos and isinstance(photos[0], str) and photos[0].startswith("http"):
            return photos[0].split("?")[0] + PIC_SUFFIX
        return ""

    # 构建标准 vod(对齐 jar Douban:pic 加防盗链、评分备注;保留 vod_year)
    # 兼容三种形态:列表 subject(pic+card_subtitle) / 首页 real_hot(cover_url+is_released) / 搜索 target(cover_url+year)
    # 点击即搜:每个卡片带 action="search:片名", 点海报直调 Spider.action -> 本地 do=search
    def buildVod(self, item):
        rawType = ((item.get("type") or item.get("subtype") or item.get("target_type") or "")).strip().lower()
        typeName = "电影" if "movie" in rawType else ("剧集" if "tv" in rawType else "")
        card_subtitle = item.get("card_subtitle", "") or ""
        year = ""
        region = ""
        m = re.match(r"^(\d{4})\s*/\s*([^/]+)", card_subtitle)
        if m:
            year, region = m.group(1), m.group(2).strip()
        if not year and item.get("year"):
            year = str(item.get("year"))
        rating_val = "暂无"
        rating = item.get("rating")
        if rating and rating.get("value", 0) != 0:
            rating_val = str(rating["value"])
        remarks = f"{typeName}评分 {rating_val}" if typeName else f"评分 {rating_val}"
        ep = (item.get("episodes_info") or "").strip()
        if ep:
            remarks = f"{remarks}·{ep}"
        title = item.get("title", "")
        return {
            "vod_id": str(item.get("id", "")),
            "vod_name": title,
            "vod_pic": self._pic(item),
            "vod_remarks": remarks,
            "vod_year": f"{year}{region}" if year else "",
            "action": f"search:{title}" if title else "",
        }

    def _buildList(self, items, skipTypeCheck=False):
        videos = []
        seen = set()
        for item in items or []:
            try:
                if not isinstance(item, dict):
                    continue
                # movie/recommend 混入 chart/doulist/ad 卡片:只收 subject
                if not skipTypeCheck and "card" in item and item.get("card") not in (None, "subject"):
                    if item.get("type") not in ("movie", "tv"):
                        continue
                if not skipTypeCheck and item.get("type", "") not in ["movie", "tv"] and "target_type" not in item:
                    if item.get("type"):
                        continue
                if not self.isReleased(item):
                    continue
                vod = self.buildVod(item)
                if not vod["vod_id"] or vod["vod_id"] in seen:
                    continue
                if not vod["vod_pic"]:
                    continue
                seen.add(vod["vod_id"])
                videos.append(vod)
            except Exception:
                continue
        return videos

    def homeContent(self, filter):
        # 全部分组作为一级分类（anime_hot 走 tv_animation）
        cateManual = {
            "热门电影": "hot_gaia",
            "热播剧集": "tv_hot",
            "热门动漫": "tv_animation",
            "热播综艺": "show_hot",
            "电影筛选": "movie",
            "电视筛选": "tv",
            "电影榜单": "rank_list_movie",
            "电视剧榜单": "rank_list_tv",
            "豆瓣电影Top250": "movie_top250",
            "院线口碑榜": "movie_weekly_best",
        }
        classes = [{'type_name': k, 'type_id': v} for k, v in cateManual.items()]
        result = {'class': classes}
        if filter:
            result['filters'] = self.config['filter']
        return result

    # 推荐:协议本身无 pg 参数,无法真翻页。这里一次拉 3 个榜单合并去重,
    # 一屏条数从 18 涨到 50+,等效“自动下一页”的观感。只做显示,不拼播放。
    def homeVideoContent(self):
        try:
            jobs = [
                ("subject_collection/subject_real_time_hotest/items", {"apikey": API_KEY, "count": 20}),
                ("movie/hot_gaia", {"apikey": API_KEY, "sort": "recommend", "area": "全部", "start": 0, "count": 20}),
                ("subject_collection/tv_hot/items", {"apikey": API_KEY, "start": 0, "count": 20}),
            ]
            items = []
            for path, params in jobs:
                try:
                    jo = self._fetchJo(f"{DOUBAN_API}/{path}?{urllib.parse.urlencode(params)}")
                    items.extend(jo.get("subject_collection_items") or jo.get("items") or [])
                except Exception:
                    continue
            return {"list": self._buildList(items, skipTypeCheck=True)}
        except Exception:
            return {"list": []}

    # 分类/榜单(基于已验证的 GROUPS 映射):pagecount 由 total 动态计算, 空页自动拉下一页
    def categoryContent(self, tid, pg, filter, extend):
        extend = extend or {}
        pg = int(pg)
        result = {"list": [], "page": pg, "pagecount": 9999, "limit": 20, "total": 999999}
        try:
            sort = extend.get("sort") or "T"
            tags = ",".join(str(v) for k, v in extend.items() if k != "sort" and k != "榜单" and k != "type" and str(v).strip())
            count = 20
            start = (pg - 1) * count

            # tv_hot/show_hot 子分类切换具体 collection
            if tid in ("tv_hot", "show_hot", "tv_animation", "anime_hot"):
                sub = (extend.get("type") or "").strip()
                if sub and sub in GROUPS:
                    tid = sub

            # 榜单类按所选榜单切换具体 collection
            rank_map = {
                "rank_list_movie": "movie_real_time_hotest",
                "rank_list_tv": "tv_real_time_hotest",
            }
            if tid in rank_map:
                tid = (extend.get("榜单") or "").strip() or rank_map[tid]

            if tid in GROUPS:
                path, data_key = GROUPS[tid]
            else:
                path, data_key = GROUPS["movie"]

            def _url(off):
                u = f"{DOUBAN_API}/{path}?apikey={API_KEY}&start={off}&count={count}"
                if tid in ("movie", "tv"):
                    u = f"{DOUBAN_API}/{path}?apikey={API_KEY}&sort={urllib.parse.quote(sort)}&tags={urllib.parse.quote(tags)}&start={off}&count={count}"
                elif tid == "hot_gaia":
                    s = extend.get("sort") or "recommend"
                    area = extend.get("area") or "全部"
                    u = f"{DOUBAN_API}/{path}?apikey={API_KEY}&sort={urllib.parse.quote(s)}&area={urllib.parse.quote(area)}&start={off}&count={count}"
                return u

            jo = self._fetchJo(_url(start))
            items = list(jo.get(data_key) or [])
            total = jo.get("total") or 0
            # 自动下一页:过滤后不足 5 条且还有剩余, 自动顺延拉下一页补足(最多追 3 页)
            if total and start + count < total:
                guard = 0
                while len(self._buildList(items)) < 5 and guard < 3:
                    start += count
                    if start >= total:
                        break
                    try:
                        jo2 = self._fetchJo(_url(start))
                    except Exception:
                        break
                    chunk = jo2.get(data_key) or []
                    if not chunk:
                        break
                    items.extend(chunk)
                    total = jo2.get("total") or total
                    guard += 1
                    if len(chunk) < count:
                        break
            videos = self._buildList(items)
            result["list"] = videos
            result["limit"] = count
            if total:
                result["total"] = total
                result["pagecount"] = max(1, (total + count - 1) // count)
            return result
        except Exception:
            return result

    # 只做显示+点击跳转搜索:详情不拼可播线路,只给一条“搜片名”入口。
    # 点击详情集数 -> playerContent(id=片名) 同样 fire 本地 do=search, 双保险。
    def _detailOne(self, sid):
        for kind in ("movie", "tv"):
            try:
                jo = self._fetchJo(f"{DOUBAN_API}/{kind}/{urllib.parse.quote(str(sid))}?apikey={API_KEY}")
                if jo and jo.get("title"):
                    return jo
            except Exception:
                continue
        return None

    def detailContent(self, array):
        try:
            sid = str((array or [""])[0]).strip()
            if not sid:
                return {"list": []}
            jo = self._detailOne(sid)
            if not jo:
                return {"list": []}
            pic = jo.get("pic") or {}
            pic_url = pic.get("large") or pic.get("normal") or ""
            if pic_url:
                pic_url = pic_url.split("?")[0] + PIC_SUFFIX
            rating = jo.get("rating") or {}
            rating_val = str(rating.get("value", "")) if rating.get("value") else "暂无"
            genres = " ".join(jo.get("genres") or [])
            countries = "/".join(jo.get("countries") or [])
            year = str(jo.get("year") or "")
            directors = "/".join([d.get("name", "") for d in jo.get("directors", []) if d.get("name")])
            actors = "/".join([a.get("name", "") for a in jo.get("actors", [])[:8] if a.get("name")])
            title = jo.get("title", "")
            remark = f"{rating_val}分·{genres}".strip("·")
            return {"list": [{
                "vod_id": sid,
                "vod_name": title,
                "vod_pic": pic_url,
                "type_name": "电影" if jo.get("type") == "movie" else "剧集",
                "vod_year": year,
                "vod_area": countries,
                "vod_remarks": remark,
                "vod_actor": actors,
                "vod_director": directors,
                "vod_content": (jo.get("intro") or "").strip(),
                "vod_play_from": "搜片名",
                "vod_play_url": f"搜索${title}",
            }]}
        except Exception:
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg) if str(pg).isdigit() else 1
            count = 20
            start = (pg - 1) * count
            url = f"{DOUBAN_API}/search?apikey={API_KEY}&q={urllib.parse.quote(key)}&count={count}&start={start}"
            jo = self._fetchJo(url)
            subs = (jo.get("subjects") or {}).get("items") or []
            videos = []
            seen = set()
            for wrap in subs:
                try:
                    if (wrap.get("layout") or "") != "subject":
                        continue
                    # 类型在外层 wrap.target_type(WARN:target 内无 target_type, 以外层为准)
                    wtype = (wrap.get("target_type") or (wrap.get("target") or {}).get("target_type") or "")
                    if wtype not in ("movie", "tv"):
                        continue
                    t = wrap.get("target") or {}
                    if not t.get("id") or t["id"] in seen:
                        continue
                    seen.add(t["id"])
                    item = dict(t)
                    item["type"] = wtype
                    if not item.get("pic") and t.get("cover_url"):
                        item["cover_url"] = t["cover_url"]
                    if not item.get("card_subtitle") and t.get("year"):
                        item["year"] = t["year"]
                    vod = self.buildVod(item)
                    if vod["vod_pic"]:
                        videos.append(vod)
                except Exception:
                    continue
            return {"list": videos, "page": pg}
        except Exception:
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        try:
            word = (id or "").strip()
            if word:
                self._fireSearchAsync(word, delay=0.8)
            return {"parse": 0, "url": "", "header": {}}
        except Exception:
            return {}

    header = {
        "Host": "frodo.douban.com",
        "Connection": "Keep-Alive",
        "Referer": REFERER,
        "User-Agent": USER_AGENT,
    }

    def localProxy(self, param):
        return [200, "video/MP2T", b"", ""]
    config = {
        "player": {},
        "filter": {
            "hot_gaia": [
                {"key": "sort", "name": "排序", "value": [
                    {"n": "热度", "v": "recommend"}, {"n": "最新", "v": "time"}, {"n": "评分", "v": "rank"},
                ]},
                {"key": "area", "name": "地区", "value": [
                    {"n": "全部", "v": "全部"}, {"n": "华语", "v": "华语"}, {"n": "欧美", "v": "欧美"},
                    {"n": "韩国", "v": "韩国"}, {"n": "日本", "v": "日本"},
                ]},
            ],
            "tv_hot": [
                {"key": "type", "name": "分类", "value": [
                    {"n": "综合", "v": "tv_hot"}, {"n": "国产剧", "v": "tv_domestic"}, {"n": "欧美剧", "v": "tv_american"},
                    {"n": "日剧", "v": "tv_japanese"}, {"n": "韩剧", "v": "tv_korean"}, {"n": "动画", "v": "tv_animation"},
                ]},
            ],
            "anime_hot": [
                {"key": "type", "name": "分类", "value": [
                    {"n": "热门动画", "v": "tv_animation"},
                ]},
            ],
            "show_hot": [
                {"key": "type", "name": "分类", "value": [
                    {"n": "综合", "v": "show_hot"}, {"n": "国内", "v": "show_domestic"}, {"n": "国外", "v": "show_foreign"},
                ]},
            ],
            "movie": [
                {"key": "类型", "name": "类型", "value": [
                    {"n": "全部类型", "v": ""}, {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"},
                    {"n": "动作", "v": "动作"}, {"n": "科幻", "v": "科幻"}, {"n": "动画", "v": "动画"},
                    {"n": "悬疑", "v": "悬疑"}, {"n": "犯罪", "v": "犯罪"}, {"n": "惊悚", "v": "惊悚"},
                    {"n": "冒险", "v": "冒险"}, {"n": "音乐", "v": "音乐"}, {"n": "历史", "v": "历史"},
                    {"n": "奇幻", "v": "奇幻"}, {"n": "恐怖", "v": "恐怖"}, {"n": "战争", "v": "战争"},
                    {"n": "传记", "v": "传记"}, {"n": "歌舞", "v": "歌舞"}, {"n": "武侠", "v": "武侠"},
                    {"n": "情色", "v": "情色"}, {"n": "灾难", "v": "灾难"}, {"n": "西部", "v": "西部"},
                    {"n": "纪录片", "v": "纪录片"}, {"n": "短片", "v": "短片"},
                ]},
                {"key": "地区", "name": "地区", "value": [
                    {"n": "全部地区", "v": ""}, {"n": "华语", "v": "华语"}, {"n": "欧美", "v": "欧美"},
                    {"n": "韩国", "v": "韩国"}, {"n": "日本", "v": "日本"}, {"n": "中国大陆", "v": "中国大陆"},
                    {"n": "美国", "v": "美国"}, {"n": "中国香港", "v": "中国香港"}, {"n": "中国台湾", "v": "中国台湾"},
                    {"n": "英国", "v": "英国"}, {"n": "法国", "v": "法国"}, {"n": "德国", "v": "德国"},
                    {"n": "意大利", "v": "意大利"}, {"n": "西班牙", "v": "西班牙"}, {"n": "印度", "v": "印度"},
                    {"n": "泰国", "v": "泰国"}, {"n": "俄罗斯", "v": "俄罗斯"}, {"n": "加拿大", "v": "加拿大"},
                    {"n": "澳大利亚", "v": "澳大利亚"}, {"n": "爱尔兰", "v": "爱尔兰"}, {"n": "瑞典", "v": "瑞典"},
                    {"n": "巴西", "v": "巴西"}, {"n": "丹麦", "v": "丹麦"},
                ]},
                {"key": "sort", "name": "排序", "value": [
                    {"n": "近期热度", "v": "T"}, {"n": "首映时间", "v": "R"}, {"n": "高分优先", "v": "S"},
                ]},
                {"key": "年代", "name": "年代", "value": [
                    {"n": "全部年代", "v": ""}, {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"},
                    {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"},
                    {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"},
                    {"n": "2010年代", "v": "2010年代"}, {"n": "2000年代", "v": "2000年代"}, {"n": "90年代", "v": "90年代"},
                    {"n": "80年代", "v": "80年代"}, {"n": "70年代", "v": "70年代"}, {"n": "60年代", "v": "60年代"},
                    {"n": "更早", "v": "更早"},
                ]},
            ],
            "tv": [
                {"key": "类型", "name": "类型", "value": [
                    {"n": "不限", "v": ""}, {"n": "电视剧", "v": "电视剧"}, {"n": "综艺", "v": "综艺"},
                ]},
                {"key": "电视剧形式", "name": "电视剧形式", "value": [
                    {"n": "不限", "v": ""}, {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"},
                    {"n": "悬疑", "v": "悬疑"}, {"n": "动画", "v": "动画"}, {"n": "武侠", "v": "武侠"},
                    {"n": "古装", "v": "古装"}, {"n": "家庭", "v": "家庭"}, {"n": "犯罪", "v": "犯罪"},
                    {"n": "科幻", "v": "科幻"}, {"n": "恐怖", "v": "恐怖"}, {"n": "历史", "v": "历史"},
                    {"n": "战争", "v": "战争"}, {"n": "动作", "v": "动作"}, {"n": "冒险", "v": "冒险"},
                    {"n": "传记", "v": "传记"}, {"n": "剧情", "v": "剧情"}, {"n": "奇幻", "v": "奇幻"},
                    {"n": "惊悚", "v": "惊悚"}, {"n": "灾难", "v": "灾难"}, {"n": "歌舞", "v": "歌舞"},
                    {"n": "音乐", "v": "音乐"},
                ]},
                {"key": "综艺形式", "name": "综艺形式", "value": [
                    {"n": "不限", "v": ""}, {"n": "真人秀", "v": "真人秀"}, {"n": "脱口秀", "v": "脱口秀"},
                    {"n": "音乐", "v": "音乐"}, {"n": "歌舞", "v": "歌舞"},
                ]},
                {"key": "地区", "name": "地区", "value": [
                    {"n": "全部地区", "v": ""}, {"n": "华语", "v": "华语"}, {"n": "欧美", "v": "欧美"},
                    {"n": "国外", "v": "国外"}, {"n": "韩国", "v": "韩国"}, {"n": "日本", "v": "日本"},
                    {"n": "中国大陆", "v": "中国大陆"}, {"n": "中国香港", "v": "中国香港"}, {"n": "美国", "v": "美国"},
                    {"n": "英国", "v": "英国"}, {"n": "泰国", "v": "泰国"}, {"n": "中国台湾", "v": "中国台湾"},
                    {"n": "意大利", "v": "意大利"}, {"n": "法国", "v": "法国"}, {"n": "德国", "v": "德国"},
                    {"n": "西班牙", "v": "西班牙"}, {"n": "俄罗斯", "v": "俄罗斯"}, {"n": "瑞典", "v": "瑞典"},
                    {"n": "巴西", "v": "巴西"}, {"n": "丹麦", "v": "丹麦"}, {"n": "印度", "v": "印度"},
                    {"n": "加拿大", "v": "加拿大"}, {"n": "爱尔兰", "v": "爱尔兰"}, {"n": "澳大利亚", "v": "澳大利亚"},
                ]},
                {"key": "sort", "name": "排序", "value": [
                    {"n": "近期热度", "v": "T"}, {"n": "首播时间", "v": "R"}, {"n": "高分优先", "v": "S"},
                ]},
                {"key": "年代", "name": "年代", "value": [
                    {"n": "全部", "v": ""}, {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"},
                    {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"},
                    {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"},
                    {"n": "2010年代", "v": "2010年代"}, {"n": "2000年代", "v": "2000年代"}, {"n": "90年代", "v": "90年代"},
                    {"n": "80年代", "v": "80年代"}, {"n": "70年代", "v": "70年代"}, {"n": "60年代", "v": "60年代"},
                    {"n": "更早", "v": "更早"},
                ]},
                {"key": "平台", "name": "平台", "value": [
                    {"n": "全部", "v": ""}, {"n": "腾讯视频", "v": "腾讯视频"}, {"n": "爱奇艺", "v": "爱奇艺"},
                    {"n": "优酷", "v": "优酷"}, {"n": "湖南卫视", "v": "湖南卫视"}, {"n": "Netflix", "v": "Netflix"},
                    {"n": "HBO", "v": "HBO"}, {"n": "BBC", "v": "BBC"}, {"n": "NHK", "v": "NHK"},
                    {"n": "CBS", "v": "CBS"}, {"n": "NBC", "v": "NBC"}, {"n": "tvN", "v": "tvN"},
                ]},
            ],
            "rank_list_movie": [
                {"key": "榜单", "name": "榜单", "value": [
                    {"n": "实时热门电影", "v": "movie_real_time_hotest"}, {"n": "一周口碑电影榜", "v": "movie_weekly_best"}, {"n": "豆瓣电影Top250", "v": "movie_top250"},
                ]},
            ],
            "rank_list_tv": [
                {"key": "榜单", "name": "榜单", "value": [
                    {"n": "实时热门电视", "v": "tv_real_time_hotest"}, {"n": "华语口碑剧集榜", "v": "tv_chinese_best_weekly"}, {"n": "全球口碑剧集榜", "v": "tv_global_best_weekly"},
                    {"n": "国内口碑综艺榜", "v": "show_chinese_best_weekly"}, {"n": "国外口碑综艺榜", "v": "show_global_best_weekly"},
                ]},
            ],
        },
    }
