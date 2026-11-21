# -*- coding: utf-8 -*-
"""
TVBox / Hipy / T4 / DrPy 爬虫源
站点: 欧乐影院  https://www.olevod.one/
语言: Python (100%)
"""

import sys
import re
import json
from urllib.parse import quote, unquote

import requests

sys.path.append('..')

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


class Spider(BaseSpider):

    host = 'https://www.olevod.one'

    UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.UA,
            'Referer': self.host + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })

    def getName(self):
        return "欧乐影院"

    def init(self, extend=''):
        self.__init__()

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass

    def isVideoFormat(self, url):
        if not url:
            return False
        u = url.lower()
        return '.m3u8' in u or '.mp4' in u or '.flv' in u or '.ts' in u

    def manualVideoCheck(self):
        return False

    # ------------------------------------------------------------------ #
    # 通用工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _attr(tag, name):
        if not tag:
            return ''
        p = re.search(r'(?:^|\s)' + re.escape(name) + r'\s*=\s*["\']([^"\']*)["\']',
                      tag, re.I)
        if p:
            return p.group(1).strip()
        p = re.search(re.escape(name) + r'\s*=\s*["\']([^"\']*)["\']', tag, re.I)
        return p.group(1).strip() if p else ''

    def abs_url(self, url):
        if not url:
            return ''
        url = url.strip().replace('&amp;', '&')
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('http://') or url.startswith('https://'):
            return url
        if url.startswith('/'):
            return self.host + url
        return self.host + '/' + url

    def norm_id(self, url):
        if not url:
            return ''
        u = url.strip()
        if u.startswith('http://') or u.startswith('https://'):
            u = re.sub(r'^https?://[^/]+', '', u)
        return u if u.startswith('/') else '/' + u

    def fetch(self, url, headers=None, timeout=15):
        h = dict(self.session.headers)
        if headers:
            h.update(headers)
        try:
            r = self.session.get(url, headers=h, timeout=timeout)
            r.encoding = 'utf-8'
            return r.text if r.text else ''
        except Exception:
            return ''

    @staticmethod
    def _strip(html_text):
        if not html_text:
            return ''
        t = re.sub(r'<script[\s\S]*?</script>', '', html_text, flags=re.I)
        t = re.sub(r'<style[\s\S]*?</style>', '', t, flags=re.I)
        t = re.sub(r'<[^>]+>', '', t)
        t = t.replace('&nbsp;', ' ').replace('\xa0', ' ').replace('\u2003', ' ')
        t = t.replace('&amp;', '&').replace('&quot;', '"')
        t = t.replace('&lt;', '<').replace('&gt;', '>')
        t = re.sub(r'[\ue000-\uf8ff]', '', t)
        return t.strip()

    # ------------------------------------------------------------------ #
    # 解析：影视卡片（首页 / 分类 / 搜索 通用）
    # ------------------------------------------------------------------ #
    def parse_vodlist(self, html):
        res = []
        if not html:
            return res
        seen = set()
        pattern = re.compile(
            r'<li[^>]*class="[^"]*vodlist_item[^"]*"[^>]*>([\s\S]*?)</li>', re.I)
        blocks = pattern.findall(html)
        if not blocks:
            blocks = re.findall(r'(<a[^>]*vodlist_thumb[\s\S]*?</a>)', html, re.I)

        for block in blocks:
            tag_m = re.search(r'<a[^>]*vodlist_thumb[^>]*>', block, re.I)
            if not tag_m:
                tag_m = re.search(r'<a[^>]*href="[^"]*/vod/[^"]*"[^>]*>', block, re.I)
            if not tag_m:
                continue
            tag = tag_m.group(0)

            href = self._attr(tag, 'href')
            if not href or '/vod/' not in href:
                continue

            pic = (self._attr(tag, 'data-original')
                   or self._attr(tag, 'data-src')
                   or self._attr(tag, 'src'))
            if pic and ('load.gif' in pic or 'loading' in pic.lower()):
                pic = self._attr(tag, 'data-src') or self._attr(tag, 'data-original')

            name = self._attr(tag, 'title')
            if not name:
                t = re.search(r'<p[^>]*class="[^"]*vodlist_title[^"]*"[^>]*>'
                              r'[\s\S]*?<a[^>]*>([\s\S]*?)</a>', block, re.I)
                if t:
                    name = self._strip(t.group(1))
            if not name:
                t = re.search(r'title="([^"]+)"', block)
                if t:
                    name = t.group(1).strip()

            remark = ''
            r = re.search(r'<span[^>]*class="[^"]*text_right text_dy[^"]*"[^>]*>'
                          r'([\s\S]*?)</span>', block, re.I)
            if r:
                remark = self._strip(r.group(1))
                if remark.lower() == 'none':
                    remark = ''
            if not remark:
                r = re.search(r'<span[^>]*class="[^"]*pic_text[^"]*"[^>]*>'
                              r'([\s\S]*?)</span>', block, re.I)
                if r:
                    remark = self._strip(r.group(1))
            if not remark:
                r = re.search(r'<p[^>]*class="[^"]*vodlist_sub[^"]*"[^>]*>'
                              r'([\s\S]*?)</p>', block, re.I)
                if r:
                    remark = self._strip(r.group(1))[:30]

            vid = self.norm_id(href)
            if vid in seen:
                continue
            seen.add(vid)

            res.append({
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': self.abs_url(pic),
                'vod_remarks': remark,
            })
        return res

    # ------------------------------------------------------------------ #
    # 首页
    # ------------------------------------------------------------------ #
    def homeContent(self, filter):
        classes = [
            {"type_name": "连续剧", "type_id": "/type/tv"},
            {"type_name": "电影", "type_id": "/type/movie"},
            {"type_name": "综艺", "type_id": "/type/show"},
            {"type_name": "动漫", "type_id": "/type/anime"},
        ]

        year_values = [{"n": "全部", "v": ""}]
        for y in range(2026, 2019, -1):
            year_values.append({"n": str(y), "v": str(y)})

        filters = {
            "/type/tv": [
                {"key": "genre", "name": "剧情", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "国产剧", "v": "cn"},
                    {"n": "欧美剧", "v": "west"},
                    {"n": "港台剧", "v": "hk_tw"},
                    {"n": "日韩剧", "v": "jp_kr"},
                ]},
                {"key": "year", "name": "年份", "value": year_values},
            ],
            "/type/movie": [
                {"key": "genre", "name": "剧情", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "动作片", "v": "action"},
                    {"n": "喜剧片", "v": "comedy"},
                    {"n": "爱情片", "v": "romance"},
                    {"n": "科幻片", "v": "scifi"},
                    {"n": "恐怖片", "v": "horror"},
                    {"n": "剧情片", "v": "feature"},
                    {"n": "战争片", "v": "war"},
                ]},
                {"key": "year", "name": "年份", "value": year_values},
            ],
            "/type/show": [
                {"key": "genre", "name": "剧情", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "美食节目", "v": "food"},
                    {"n": "搞笑节目", "v": "funny"},
                    {"n": "音乐节目", "v": "music"},
                    {"n": "脱口秀", "v": "talk"},
                    {"n": "真人秀", "v": "reality"},
                ]},
                {"key": "year", "name": "年份", "value": year_values},
            ],
            "/type/anime": [
                {"key": "genre", "name": "地区", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "日本", "v": "jp"},
                    {"n": "国产", "v": "cn"},
                    {"n": "欧美", "v": "west"},
                ]},
                {"key": "year", "name": "年份", "value": year_values},
            ],
        }

        # ★ 首页推荐 = 直接抓首页的 ul.vodlist > li.vodlist_item 卡片
        #   （不要用 ul.hom_mob_list > a.mob_btn，那是顶部导航按钮）
        home_list = []
        try:
            html = self.fetch(self.host + '/')
            home_list = self.parse_vodlist(html)
        except Exception:
            home_list = []

        return {
            'class': classes,
            'list': home_list,
            'filters': filters,
        }

    # ------------------------------------------------------------------ #
    # 分类
    # ------------------------------------------------------------------ #
    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg)
        except Exception:
            page = 1

        path = tid if tid else '/type/tv'
        if path.startswith('/type/') and not path.startswith('/type/filter/'):
            path = path.replace('/type/', '/type/filter/', 1)

        params = []
        if extend and isinstance(extend, dict):
            for k, v in extend.items():
                if v is None:
                    continue
                v = str(v).strip()
                if v == '' or v.lower() == 'all':
                    continue
                params.append('%s=%s' % (k, quote(v)))

        if page > 1:
            params.append('page=%d' % page)

        url = self.host + path
        if params:
            url += ('&' if '?' in url else '?') + '&'.join(params)

        html = self.fetch(url, headers={'Referer': self.host + '/'})
        vod_list = self.parse_vodlist(html)

        return {
            'page': page,
            'pagecount': 99,
            'limit': 20,
            'total': 999,
            'list': vod_list,
        }

    # ------------------------------------------------------------------ #
    # 详情
    # ------------------------------------------------------------------ #
    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, list) else ids
        url = self.abs_url(vod_id)
        html = self.fetch(url, headers={'Referer': self.host + '/'})

        vod = {
            'vod_id': vod_id,
            'vod_name': '',
            'vod_pic': '',
            'type_name': '',
            'vod_year': '',
            'vod_area': '',
            'vod_remarks': '',
            'vod_actor': '',
            'vod_director': '',
            'vod_content': '',
            'vod_play_from': '',
            'vod_play_url': '',
        }

        if not html:
            return {'list': [vod]}

        # ---------- 1. 片名 ----------
        m = re.search(r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>([\s\S]*?)</h1>',
                      html, re.I)
        if m:
            a = re.search(r'<a[^>]*>([\s\S]*?)</a>', m.group(1), re.I)
            raw = a.group(1) if a else m.group(1)
            name = self._strip(raw)
            name = re.sub(r'[\s\u3000]+(简介|详情|剧情简介|正片|HD国语|TC国语|抢先版|HDTC)\s*$',
                          '', name).strip()
            vod['vod_name'] = name
        if not vod['vod_name']:
            m = re.search(r'<title>([\s\S]*?)</title>', html, re.I)
            if m:
                vod['vod_name'] = re.split(r'[\s\-–—|]+',
                                           self._strip(m.group(1)))[0].strip()

        # ---------- 2. 封面 ----------
        pic = ''
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                      html, re.I)
        if m:
            cand = m.group(1)
            if re.search(r'\.(jpg|jpeg|png|webp)(\?|$)', cand, re.I):
                pic = cand
        if not pic:
            m = re.search(r'<div[^>]*class="[^"]*(?:detail_pic|content_pic|pic_box|pic)[^"]*"'
                          r'[^>]*>[\s\S]*?<img[^>]*>', html, re.I)
            if m:
                pic = (self._attr(m.group(0), 'data-original')
                       or self._attr(m.group(0), 'data-src')
                       or self._attr(m.group(0), 'src'))
        if not pic:
            mm = re.search(r'/vod/(\d+)', url)
            if mm:
                pic = '/wpimg/th/%s.jpg' % mm.group(1)
        vod['vod_pic'] = self.abs_url(pic)

        # ---------- 3. li.data 汇总 ----------
        data_texts = []
        for li in re.findall(r'<li[^>]*class="[^"]*data[^"]*"[^>]*>([\s\S]*?)</li>',
                             html, re.I):
            t = self._strip(li)
            t = re.sub(r'[\s\u3000]+', ' ', t)
            if t:
                data_texts.append(t)
        data_all = ' '.join(data_texts)

        LABELS = ['主演', '演员', '导演', '编剧', '类型', '分类', '地区',
                  '国家', '产地', '年份', '年代', '上映', '语言', '状态',
                  '更新', '集数', '片长', '别名', '频道', '评分']
        kv = {}
        if data_all:
            parts = re.split(r'(' + '|'.join(LABELS) + r')\s*[：:]', data_all)
            for i in range(1, len(parts) - 1, 2):
                key = parts[i]
                val = parts[i + 1].strip(' ,;，；')
                if val and key not in kv:
                    kv[key] = val

        def pick(*keys):
            for k in keys:
                if k in kv and kv[k]:
                    return kv[k]
            return ''

        vod['vod_actor'] = pick('主演', '演员')
        vod['vod_director'] = pick('导演')
        vod['type_name'] = pick('类型', '分类', '频道')
        vod['vod_area'] = pick('地区', '国家', '产地')
        vod['vod_year'] = pick('年份', '年代', '上映')
        vod['vod_remarks'] = pick('状态', '更新', '集数', '片长')

        # ---------- 4. nstem 兜底 ----------
        if not vod['vod_year'] or not vod['vod_area']:
            m = re.search(r'<p[^>]*class="[^"]*nstem[^"]*"[^>]*>([\s\S]*?)</p>',
                          html, re.I)
            if m:
                for sp in re.findall(r'<span[^>]*>([\s\S]*?)</span>',
                                     m.group(1), re.I):
                    txt = self._strip(sp)
                    if not txt:
                        continue
                    if re.match(r'^(19|20)\d{2}$', txt) and not vod['vod_year']:
                        vod['vod_year'] = txt
                    elif (not re.match(r'^\d+(\.\d+)?$', txt)
                          and txt.lower() != 'none'
                          and not vod['vod_area']):
                        vod['vod_area'] = txt

        # ---------- 5. play_content 兜底 ----------
        if not (vod['vod_actor'] and vod['vod_director']):
            m = re.search(r'<div[^>]*class="[^"]*(?:play_content|content_detail|content_box)'
                          r'[^"]*"[^>]*>([\s\S]*?)</div>', html, re.I)
            if m:
                block = m.group(1)
                for p in re.findall(r'<p[^>]*>([\s\S]*?)</p>', block, re.I):
                    txt = self._strip(p)
                    if not txt:
                        continue
                    if re.match(r'^导演\s*[：:]', txt) and not vod['vod_director']:
                        vod['vod_director'] = re.sub(
                            r'^导演\s*[：:]\s*', '', txt).strip()
                    elif re.match(r'^主演\s*[：:]', txt) and not vod['vod_actor']:
                        vod['vod_actor'] = re.sub(
                            r'^主演\s*[：:]\s*', '', txt).strip()

        # ---------- 6. 简介 ----------
        content = ''
        m = re.search(r'<li[^>]*class="[^"]*desc[^"]*"[^>]*>([\s\S]*?)</li>',
                      html, re.I)
        if m:
            content = self._strip(m.group(1))
        if not content:
            m = re.search(r'<div[^>]*class="[^"]*(?:content_desc|detail_desc|introduction)'
                          r'[^"]*"[^>]*>([\s\S]*?)</div>', html, re.I)
            if m:
                content = self._strip(m.group(1))
        if not content:
            m = re.search(r'<div[^>]*class="[^"]*play_content[^"]*"[^>]*>([\s\S]*?)</div>',
                          html, re.I)
            if m:
                best = ''
                for p in re.findall(r'<p[^>]*>([\s\S]*?)</p>', m.group(1), re.I):
                    txt = self._strip(p)
                    if re.match(r'^(导演|主演)\s*[：:]', txt):
                        continue
                    if len(txt) > len(best):
                        best = txt
                content = best
        if not content:
            m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
                          html, re.I)
            if m:
                content = self._strip(m.group(1))
        content = re.sub(r'^\s*(简介|剧情简介|详细介绍)\s*[：:]\s*', '', content)
        vod['vod_content'] = content

        # ---------- 7. 线路名 ----------
        line_name = '欧乐官方播放器'
        m_ln = re.search(r'<ul[^>]*class="[^"]*title_nav[^"]*"[^>]*>([\s\S]*?)</ul>',
                         html, re.I)
        if m_ln:
            t = re.search(r'<a[^>]*>([\s\S]*?)</a>', m_ln.group(1), re.I)
            if t:
                ln = self._strip(t.group(1))
                if ln:
                    line_name = ln

        # ---------- 8. 播放列表 ----------
        eps = []
        m_pl = re.search(
            r'<div[^>]*class="[^"]*playlist_full[^"]*"[^>]*>\s*'
            r'<ul[^>]*class="[^"]*content_playlist[^"]*"[^>]*>([\s\S]*?)</ul>',
            html, re.I)
        if m_pl:
            for a in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>',
                                 m_pl.group(1), re.I):
                href = a.group(1).strip().replace('&amp;', '&')
                if not href or 'javascript' in href:
                    continue
                label = self._strip(a.group(2))
                eps.append((label, self.abs_url(href)))

        if not eps:
            mm = re.search(r'/vod/(\d+)', url)
            cur_id = mm.group(1) if mm else ''
            seen = set()
            if cur_id:
                pat = (r'<a[^>]*href="([^"]*/vod/' + re.escape(cur_id) +
                       r'/play/[^"]*)"[^>]*>([\s\S]*?)</a>')
                for a in re.finditer(pat, html, re.I):
                    href = a.group(1).strip().replace('&amp;', '&')
                    if href in seen:
                        continue
                    seen.add(href)
                    label = self._strip(a.group(2))
                    eps.append((label, self.abs_url(href)))

        if eps:
            parts = []
            for i, (name, href) in enumerate(eps):
                if not name:
                    name = '第%d集' % (i + 1)
                parts.append('%s$%s' % (name, href))
            vod['vod_play_from'] = line_name
            vod['vod_play_url'] = '#'.join(parts)

        return {'list': [vod]}

    # ------------------------------------------------------------------ #
    # 播放
    # ------------------------------------------------------------------ #
    def playerContent(self, flag, id, vipFlags):
        base_headers = {
            'User-Agent': self.UA,
            'Referer': self.host + '/',
        }

        play_url = id if isinstance(id, str) else (id[0] if id else '')
        if not play_url:
            return {'parse': 1, 'playUrl': '', 'url': '', 'header': base_headers}

        if not play_url.startswith('http'):
            play_url = self.abs_url(play_url)

        mm = re.search(r'/vod/(\d+)/play/([^/?&#]+)', play_url)
        if not mm:
            return {'parse': 1, 'playUrl': '', 'url': play_url, 'header': base_headers}

        vod_id = mm.group(1)
        src_flag = mm.group(2)
        em = re.search(r'[?&]ep=([^&#]+)', play_url)
        ep = unquote(em.group(1)) if em else ''

        keys = []
        for k in (ep, src_flag, 'zheng_pian'):
            if k and k not in keys:
                keys.append(k)

        for k in keys:
            api = '%s/_olevod_lazy/%s-%s' % (self.host, vod_id, k)
            txt = self.fetch(api, headers={
                'Referer': play_url,
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
            })
            if not txt:
                continue

            try:
                data = json.loads(txt)
            except Exception:
                data = None

            if isinstance(data, dict):
                plays = data.get('video_plays') or []
                for p in plays:
                    if not isinstance(p, dict):
                        continue
                    purl = p.get('play_data') or p.get('url') or ''
                    if not purl:
                        continue
                    purl = purl.strip()
                    if purl.startswith('//'):
                        purl = 'https:' + purl
                    elif purl.startswith('/'):
                        purl = self.host + purl

                    if '.m3u8' in purl or '.mp4' in purl or '.flv' in purl:
                        return {
                            'parse': 0,
                            'playUrl': '',
                            'url': purl,
                            'header': {
                                'User-Agent': self.UA,
                                'Referer': self.host + '/',
                            },
                        }
                    return {
                        'parse': 1,
                        'playUrl': '',
                        'url': purl,
                        'header': {
                            'User-Agent': self.UA,
                            'Referer': self.host + '/',
                        },
                    }

            m2 = re.search(r'(https?://[^\s"\'<>\\]+?\.m3u8[^\s"\'<>\\]*)', txt)
            if m2:
                return {
                    'parse': 0,
                    'playUrl': '',
                    'url': m2.group(1),
                    'header': {
                        'User-Agent': self.UA,
                        'Referer': self.host + '/',
                    },
                }

        return {
            'parse': 1,
            'playUrl': '',
            'url': play_url,
            'header': base_headers,
        }

    # ------------------------------------------------------------------ #
    # 搜索
    # ------------------------------------------------------------------ #
    def _searchContent_raw(self, key, quick, pg="1"):
        result = []
        if not key:
            return {'list': result}

        try:
            urls = [
                self.host + '/search.html?wd=' + quote(key),
                self.host + '/vodsearch/-------------.html?wd=' + quote(key),
                self.host + '/index.php/vod/search.html?wd=' + quote(key),
            ]
            for u in urls:
                html = self.fetch(u, headers={'Referer': self.host + '/'})
                if not html:
                    continue
                lst = self.parse_vodlist(html)
                if lst:
                    result = lst
                    break
        except Exception:
            pass

        return {'list': result}

    def searchContent(self, key, quick, pg="1"):
        data = self._searchContent_raw(key, quick)
        return self._normalize_page(data, pg)

    def _normalize_page(self, data, pg):
        if not isinstance(data, dict):
            data = {"list": data if isinstance(data, list) else []}
        if not isinstance(data.get("list"), list):
            data["list"] = []
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        if not data.get("page"):
            data["page"] = page
        if not data.get("limit"):
            data["limit"] = len(data["list"])
        if not data.get("pagecount"):
            data["pagecount"] = page + 1 if data["list"] else page
        return data