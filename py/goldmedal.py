# -*- coding: utf-8 -*-
# @Author  : Doubebly
# @Time    : 2025/5/29 22:07
# 移植自 QuickJS 源《金牌影视.js》：https://www.x8kb9k8.com
# 说明：旧站 m.sdzhgt.com 已失效（DNS 解析失败），本版对齐新站域名与签名方案。

import sys
import html
import time
import json
import hashlib
import re
import requests

sys.path.append('..')
from base.spider import Spider

DEFAULT_HOST = 'https://www.x8kb9k8.com'
SIGN_KEY = 'cb808529bae6b6be45ecfab29a4889bc'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
PAGE_SIZE = 48
ERROR_URL = ('https://sf1-cdn-tos.huoshanstatic.com/obj/media-fe/'
             'xgplayer_doc_video/mp4/xgplayer-demo-720p.mp4')
TAG_RE = re.compile(r'<[^>]*>')


class Spider(Spider):
    def getName(self):
        return "GoldMedal"

    def init(self, extend=''):
        host = DEFAULT_HOST
        if extend:
            cfg = extend
            if isinstance(cfg, str):
                try:
                    cfg = json.loads(cfg) if cfg.strip().startswith('{') else {'host': cfg}
                except Exception:
                    cfg = {'host': extend}
            if isinstance(cfg, dict):
                host = str(cfg.get('host') or cfg.get('ext') or host).strip() or host
        host = host.rstrip('/')
        if host and not host.startswith('http'):
            host = 'http://' + host
        self.home_url = host + '/'
        self.api_base = host + '/api/mw-movie'
        self.ua = UA
        self.device_id = 'jinpai-py-' + hashlib.md5(
            self.home_url.encode('utf-8')).hexdigest()[:16]
        self.error_url = ERROR_URL

    def getDependence(self):
        return []

    def isVideoFormat(self, url):
        u = str(url or '').split('?')[0].split('#')[0].lower()
        return u.endswith('.m3u8') or u.endswith('.mp4') or u.endswith('.mkv') or u.endswith('.flv')

    def manualVideoCheck(self):
        return False

    # ------------------------------------------------------------------
    # 网络与签名
    # ------------------------------------------------------------------
    def _sort_query(self, params):
        return '&'.join('%s=%s' % (k, params[k]) for k in sorted(params.keys()))

    def _api_call(self, path, params, referer=None):
        query = self._sort_query(params)
        ts = str(int(time.time() * 1000))
        source = query + ('&' if query else '') + 'key=' + SIGN_KEY + '&t=' + ts
        md5_hex = hashlib.md5(source.encode('utf-8')).hexdigest()
        sign = hashlib.sha1(md5_hex.encode('utf-8')).hexdigest()
        url = self.api_base + path + (('?' + query) if query else '')
        headers = {
            'User-Agent': self.ua,
            'Accept': 'application/json',
            'Referer': referer or self.home_url,
            'client-type': '1',
            'sign': sign,
            't': ts,
            'deviceId': self.device_id,
        }
        res = requests.get(url, headers=headers, timeout=15, verify=False)
        data = res.json()
        if int(data.get('code') or 0) != 200:
            raise RuntimeError('api %s code=%s msg=%s' % (path, data.get('code'), data.get('msg')))
        return data.get('data') or {}

    # ------------------------------------------------------------------
    # 通用工具
    # ------------------------------------------------------------------
    def _clean_text(self, value):
        text = TAG_RE.sub('', str(value or ''))
        text = html.unescape(text).replace('\u00a0', ' ')
        return text.strip()

    def _safe_name(self, name):
        text = str(name if name not in (None, '') else '正片')
        return text.replace('$', '＄').replace('#', '＃')

    def _remarks(self, item):
        remarks = str(item.get('vodRemarks') or item.get('vodVersion')
                      or item.get('vodSerial') or item.get('remark') or '').strip()
        if not remarks and item.get('vodScore'):
            remarks = str(item.get('vodScore'))
        return remarks

    def _map_item(self, item):
        if not item:
            return None
        vid = str(item.get('vodId') if item.get('vodId') is not None else (item.get('id') or ''))
        if not vid:
            return None
        return {
            'vod_id': vid,
            'vod_name': str(item.get('vodName') or item.get('name') or ''),
            'vod_pic': str(item.get('vodPic') or item.get('img') or ''),
            'vod_remarks': self._remarks(item),
            'vod_year': str(item.get('vodYear') or ''),
            'vod_area': str(item.get('vodArea') or ''),
            'type_name': str(item.get('vodClass') or item.get('typeName') or ''),
        }

    def _map_list(self, items):
        result = []
        for item in items or []:
            mapped = self._map_item(item)
            if mapped:
                result.append(mapped)
        return result

    @staticmethod
    def _to_page(pg):
        """页码归一化：非法或小于 1 一律回 1。"""
        try:
            return max(1, int(pg))
        except Exception:
            return 1

    def _normalize_page(self, data, pg):
        if not isinstance(data, dict):
            data = {'list': data if isinstance(data, list) else []}
        if not isinstance(data.get('list'), list):
            data['list'] = []
        page = self._to_page(pg)
        if not data.get('page'):
            data['page'] = page
        if not data.get('limit'):
            data['limit'] = len(data['list'])
        if not data.get('pagecount'):
            data['pagecount'] = page + 1 if data['list'] else page
        return data

    def _empty_page(self, pg):
        return self._normalize_page({'list': []}, pg)

    @staticmethod
    def _log_err(where, exc):
        """异常不静默吞掉：输出可诊断信息（Chaquopy 下进入应用日志）。"""
        try:
            print('[goldmedal] %s 失败: %s: %s' % (where, type(exc).__name__, exc))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 接口封装
    # ------------------------------------------------------------------
    def _api_category(self, tid, pg, extend):
        params = {
            'clientType': 1,
            'pageNum': self._to_page(pg),
            'pageSize': PAGE_SIZE,
            'type1': str(tid or '1'),
        }
        selected = extend if isinstance(extend, dict) else {}
        # 服务端不接受空字符串过滤值，非空才下发
        mapping = (('type', 'type'), ('class', 'v_class'), ('area', 'area'),
                   ('year', 'year'), ('lang', 'lang'))
        for src_key, api_key in mapping:
            val = str(selected.get(src_key) or '').strip()
            if val:
                params[api_key] = val
        data = self._api_call('/anonymous/video/list', params)
        items = self._map_list(data.get('list'))
        return {
            'list': items,
            'page': int(data.get('pageNum') or params['pageNum']),
            'pagecount': int(data.get('totalPage') or 1),
            'limit': int(data.get('pageSize') or PAGE_SIZE),
            'total': int(data.get('totalCount') or len(items)),
        }

    def _api_detail(self, vid):
        data = self._api_call('/anonymous/video/detail', {'id': str(vid)})
        episodes = data.get('episodeList')
        if not isinstance(episodes, list):
            episodes = []
        parts = []
        for ep in episodes:
            name = self._safe_name(ep.get('name'))
            nid = str(ep.get('nid') or '')
            if not nid:
                continue
            parts.append(name + '$' + str(vid) + '_' + nid)
        play_url = '#'.join(parts)
        if not data.get('vodName') and not play_url:
            return None
        year = str(data.get('vodYear') or data.get('vodPubdate') or '')[:4]
        return {
            'vod_id': str(vid),
            'vod_name': str(data.get('vodName') or ''),
            'vod_pic': str(data.get('vodPic') or ''),
            'vod_actor': str(data.get('vodActor') or ''),
            'vod_director': str(data.get('vodDirector') or ''),
            'vod_content': self._clean_text(data.get('vodContent') or data.get('vodBlurb') or ''),
            'vod_area': str(data.get('vodArea') or ''),
            'vod_lang': str(data.get('vodLang') or ''),
            'vod_year': year,
            'type_name': str(data.get('typeName') or data.get('vodClass') or ''),
            'vod_remarks': str(data.get('vodRemarks') or data.get('vodVersion') or ''),
            'vod_play_from': '金牌影院' if play_url else '',
            'vod_play_url': play_url,
        }

    def _api_search(self, key, pg):
        # 注意：服务端不接受 type='' 与 sourceCode=''，非空才下发
        params = {
            'keyword': str(key),
            'pageNum': self._to_page(pg),
            'pageSize': PAGE_SIZE,
        }
        data = self._api_call('/anonymous/video/searchByWordPageable', params)
        items = self._map_list(data.get('list'))
        return {
            'list': items,
            'page': int(data.get('pageNum') or params['pageNum']),
            'pagecount': int(data.get('totalPage') or 1),
            'limit': int(data.get('pageSize') or PAGE_SIZE),
            'total': int(data.get('totalCount') or len(items)),
        }

    def _api_play(self, vod_id, nid, referer=None):
        data = self._api_call('/anonymous/v2/video/episode/url',
                              {'clientType': 1, 'id': str(vod_id), 'nid': str(nid)},
                              referer=referer)
        items = data.get('list')
        return items if isinstance(items, list) else []

    @staticmethod
    def _playable(item):
        """JS playItem 的判据：flag 为真或无需登录。实测三条线路服务端均可拉取，
        此判据用于「优先挑选」，不作为「是否可取」的硬门槛。"""
        if not item or not item.get('url'):
            return False
        return item.get('flag') is True or item.get('needLogin') is False

    def _select_play(self, items):
        """线路排序：JS 判定优先的线路排前，其余有直链者按原序兜底。

        旧实现直接取 list[0]，会命中 JS 明确标注为需登录/非优先的线路；
        这里改为「优先 + 兜底」，既忠实移植 JS，也保证不因过滤而丢线路。
        """
        valid = [it for it in items if it and it.get('url')]
        if not valid:
            return []
        preferred = [it for it in valid if self._playable(it)]
        others = [it for it in valid if not self._playable(it)]
        ordered = preferred + others
        result = []
        for idx, it in enumerate(ordered):
            name = str(it.get('resolutionName') or '线路%d' % (idx + 1))
            result.append({'n': name, 'v': str(it.get('url'))})
        return result

    # ------------------------------------------------------------------
    # 六壳接口
    # ------------------------------------------------------------------
    def homeContent(self, filter):
        classes = [
            {'type_id': '1', 'type_name': '电影'},
            {'type_id': '2', 'type_name': '电视剧'},
            {'type_id': '3', 'type_name': '综艺'},
            {'type_id': '4', 'type_name': '动漫'},
            {'type_id': '88', 'type_name': '短剧'},
        ]

        def options(values):
            """把取值列表转成 filters 的 value 结构，首项补「全部」。"""
            items = [('全部', '')]
            for one in values:
                if isinstance(one, tuple):
                    items.append(one)
                else:
                    items.append((one, one))
            return [{'n': n, 'v': val} for n, val in items]

        year_full = ['2026', '2025', '2024', '2023', '2022', '2021', '2020', '2019',
                     '2018', '2017', '2016', '2015', '2014', '2013', '2012', '2011', '2010']
        area_all = ['中国大陆', '中国香港', '中国台湾', '美国', '日本', '韩国',
                    '印度', '泰国', '英国', '法国', '其他']

        # 结构：{分类 type_id: [(filters key, 显示名, 取值列表), ...]}
        spec = {
            '1': [
                ('class', '剧情', ['喜剧', '动作', '爱情', '科幻', '悬疑', '奇幻', '剧情',
                                   '恐怖', '犯罪', '动画', '惊悚', '战争', '冒险', '灾难',
                                   '伦理', '其他']),
                ('area', '地区', area_all),
                ('year', '年份', year_full + [('2009~2000', '2009~2000')]),
                ('lang', '语言', ['国语', '英语', '粤语', '韩语', '日语', '其他']),
            ],
            '2': [
                ('type', '类型', [('国产剧', '14'), ('欧美剧', '15'), ('港台剧', '16'),
                                  ('日韩剧', '62'), ('其他剧', '68')]),
                ('class', '剧情', ['古装', '战争', '喜剧', '家庭', '犯罪', '动作', '奇幻',
                                   '剧情', '历史', '短片', '其他']),
                ('area', '地区', area_all),
                ('year', '年份', year_full),
                ('lang', '语言', ['国语', '英语', '粤语', '韩语', '日语', '泰语', '其他']),
            ],
            '3': [
                ('type', '类型', [('国产综艺', '69'), ('港台综艺', '70'),
                                  ('日韩综艺', '72'), ('欧美综艺', '73')]),
                ('class', '剧情', ['真人秀', '音乐', '脱口秀']),
                ('area', '地区', area_all),
                ('year', '年份', year_full[:10]),
                ('lang', '语言', ['国语', '英语', '粤语', '韩语', '日语', '其他']),
            ],
            '4': [
                ('type', '类型', [('国产动漫', '75'), ('日韩动漫', '76'), ('欧美动漫', '77')]),
                ('class', '剧情', ['喜剧', '科幻', '热血', '冒险', '动作', '运动', '战争', '动画']),
                ('area', '地区', ['中国大陆', '日本', '美国', '其他']),
                ('year', '年份', year_full),
                ('lang', '语言', ['国语', '英语', '日语', '其他']),
            ],
            '88': [
                ('type', '类型', [('喜剧', '100'), ('奇幻', '99'), ('惊悚', '98'),
                                  ('悬疑', '97'), ('古装', '96'), ('爱情', '95'), ('剧情', '94')]),
                ('class', '剧情', ['逆袭', '甜宠', '虐恋', '穿越', '重生', '剧情', '科幻',
                                   '武侠', '爱情', '动作', '战争', '冒险', '其他']),
                ('year', '年份', year_full[:8] + [('更早', '更早')]),
            ],
        }
        filters = {}
        for tid, group in spec.items():
            filters[tid] = [
                {'key': key, 'name': name, 'value': options(values)}
                for key, name, values in group
            ]
        return {'class': classes, 'filters': filters}

    def homeVideoContent(self):
        items = []
        try:
            data = self._api_call('/anonymous/home/hotSearch', {})
            if isinstance(data, list):
                items = self._map_list(data)
        except Exception as exc:
            self._log_err('homeVideoContent hotSearch', exc)
        if not items:
            try:
                items = self._api_search('热门', '1').get('list') or []
            except Exception as exc:
                self._log_err('homeVideoContent 后备搜索', exc)
        return {'list': items, 'parse': 0, 'jx': 0}

    def categoryContent(self, tid, pg, filter, extend):
        page = self._to_page(pg)
        try:
            data = self._api_category(tid, page, extend)
        except Exception as exc:
            self._log_err('categoryContent tid=%s pg=%s' % (tid, page), exc)
            return self._empty_page(page)
        return self._normalize_page(data, page)

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, (list, tuple)) and ids else ids or '')
        if not vid:
            return {'list': [], 'parse': 0, 'jx': 0}
        try:
            vod = self._api_detail(vid)
        except Exception as exc:
            self._log_err('detailContent id=%s' % vid, exc)
            vod = None
        if not vod:
            return {'list': [], 'parse': 0, 'jx': 0}
        return {'list': [vod], 'parse': 0, 'jx': 0}

    def searchContent(self, key, quick, pg="1"):
        page = self._to_page(pg)
        word = str(key or '').strip()
        if not word:
            return self._empty_page(page)
        try:
            data = self._api_search(word, page)
        except Exception as exc:
            self._log_err('searchContent key=%s pg=%s' % (word, page), exc)
            return self._empty_page(page)
        return self._normalize_page(data, page)

    def playerContent(self, flag, pid, vipFlags):
        header = {
            'User-Agent': self.ua,
            'Referer': self.home_url,
            'Origin': self.home_url.rstrip('/'),
        }
        raw = str(pid or '')
        parts = raw.split('_')
        vod_id = parts[0].strip() if parts else ''
        nid = parts[1].strip() if len(parts) > 1 else ''
        if not vod_id or not nid or not vod_id.isdigit():
            nums = [x for x in raw.split('/') if x.strip().isdigit()]
            if len(nums) >= 2:
                vod_id, nid = nums[-2], nums[-1]
        if not vod_id or not nid:
            return {'url': self.error_url, 'header': header, 'parse': 0, 'jx': 0}
        referer = '%svod/play/%s/sid/%s' % (self.home_url, vod_id, nid)
        try:
            items = self._api_play(vod_id, nid, referer)
        except Exception as exc:
            self._log_err('playerContent id=%s nid=%s' % (vod_id, nid), exc)
            return {'url': self.error_url, 'header': header, 'parse': 0, 'jx': 0}
        selected = self._select_play(items)
        if not selected:
            self._log_err('playerContent id=%s nid=%s 无可用线路' % (vod_id, nid), 'empty list')
            return {'url': self.error_url, 'header': header, 'parse': 0, 'jx': 0}
        # 契约：url 主线保持单字符串（旧壳只认单值）；可播线路优先排首位
        return {
            'parse': 0,
            'url': selected[0]['v'],
            'header': header,
        }

    def liveContent(self, url):
        return ''

    def action(self, action):
        return {}

    def localProxy(self, params):
        return None

    def destroy(self):
        return '正在Destroy'


if __name__ == '__main__':
    pass
