/*
@header({
  类型: '影视',
  title: '金牌影视',
  lang: 'ds',
  searchable: 2,
  filterable: 0,
  quickSearch: 0
})
*/
var rule = {
  类型: '影视',
  title: '金牌影视',
  version: '1.0.1',
  host: 'https://www.sizhengxt.com',
  homeUrl: '/',
  url: '/vod/show/id/fyclass',
  searchUrl: '/vod/search/**',
  detailUrl: '/detail/fyid',
  searchable: 2,
  quickSearch: 0,
  filterable: 0,
  headers: {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.x8kb9k8.com/',
    'Accept': 'text/html,application/xhtml+xml'
  },
  timeout: 15000,
  class_name: '电影&电视剧&综艺&动漫&短剧',
  class_url: '1&2&3&4&88',
  double: false,
  limit: 48,
  play_parse: true,
  play_json: [],

  _jpStr: function(v) { return v == null ? '' : String(v); },
  _jpStrip: function(s) {
    s = s == null ? '' : String(s);
    return s.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
  },
  _jpResp: function(r) {
    if (r == null) return '';
    if (typeof r === 'string') return r;
    if (typeof r === 'object') {
      if (typeof r.content === 'string') return r.content;
      if (typeof r.data === 'string') return r.data;
    }
    return String(r);
  },
  _jpFlight: function(html) {
    var src = String(html || '');
    var re = /self\.__next_f\.push\(\[1,([\s\S]*?)\]\)<\/script>/g;
    var parts = [], m;
    while ((m = re.exec(src)) !== null) {
      var c = m[1];
      try { c = JSON.parse(c); }
      catch (e) {
        try { c = JSON.parse('[' + c + ']')[1]; }
        catch (e2) { c = String(c).split('\\\\n').join('\n').split('\\\\\"').join('\"'); }
      }
      if (typeof c !== 'string') c = String(c);
      parts.push(c);
    }
    return parts.join('\n');
  },
  _jpBalanced: function(s, start) {
    var open = s[start];
    var close = open === '{' ? '}' : ']';
    var depth = 0, inStr = false, esc = false;
    for (var i = start; i < s.length; i++) {
      var ch = s[i];
      if (inStr) {
        if (esc) esc = false;
        else if (ch === '\\\\') esc = true;
        else if (ch === '\"') inStr = false;
      } else {
        if (ch === '\"') inStr = true;
        else if (ch === open) depth++;
        else if (ch === close) { depth--; if (depth === 0) return s.slice(start, i + 1); }
      }
    }
    return '';
  },
  _jpByKey: function(text, key) {
    var pat = '\"' + key + '\"';
    var idx = text.indexOf(pat);
    while (idx >= 0) {
      var j = idx + pat.length;
      while (j < text.length && /\s/.test(text[j])) j++;
      if (text[j] === ':') {
        j++;
        while (j < text.length && /\s/.test(text[j])) j++;
        if (text[j] === '{' || text[j] === '[') {
          var sub = rule._jpBalanced(text, j);
          if (sub) { try { return JSON.parse(sub); } catch (e) {} }
        }
      }
      idx = text.indexOf(pat, idx + 1);
    }
    return null;
  },
  _jpMap: function(o) {
    if (!o) return null;
    var vodId = rule._jpStr(o.vodId != null ? o.vodId : o.id);
    if (!vodId) return null;
    var remarks = rule._jpStr(o.vodRemarks || o.vodVersion || o.vodSerial || o.remark || '');
    if (!remarks && o.vodScore) remarks = rule._jpStr(o.vodScore);
    var name = rule._jpStr(o.vodName || o.name || '');
    if (!name) return null;
    var pic = rule._jpStr(o.vodPic || o.img || '');
    return {
      title: name, vod_name: name,
      pic_url: pic, vod_pic: pic,
      desc: remarks, content: remarks, vod_remarks: remarks,
      url: vodId, vod_id: vodId,
      vod_year: rule._jpStr(o.vodYear || ''),
      vod_area: rule._jpStr(o.vodArea || ''),
      type_name: rule._jpStr(o.vodClass || o.typeName || '')
    };
  },
  _jpCards: function(html) {
    var src = String(html || '');
    var re = /<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/g;
    var list = [], m, seen = {};
    while ((m = re.exec(src)) !== null) {
      var href = m[1] || '';
      if (href.indexOf('/detail/') < 0) continue;
      var idm = /(\d{4,})/.exec(href);
      if (!idm) continue;
      var vodId = idm[1];
      if (seen[vodId]) continue;
      var inner = m[2] || '';
      if (inner.length > 4000) continue;
      var name = '';
      var tm = /title="([^"]+)"/.exec(m[0]);
      if (tm) name = tm[1].trim();
      if (!name) {
        var h = /<[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)<\/[^>]+>/.exec(inner);
        if (h) name = rule._jpStrip(h[1]);
      }
      if (!name || name.length > 60) continue;
      if (/更多|查看|全部|首页|排序|播放器/.test(name)) continue;
      seen[vodId] = 1;
      list.push({ title: name, vod_name: name, pic_url: '', vod_pic: '', desc: '', content: '', vod_remarks: '', url: vodId, vod_id: vodId });
      if (list.length >= 24) break;
    }
    return list;
  },
  _jpCatUrl: function(tid, pg, extend) {
    extend = extend || {};
    var url = rule.host + '/vod/show/id/' + encodeURIComponent(rule._jpStr(tid || '1'));
    var t = rule._jpStr(extend.type || '').trim();
    var c = rule._jpStr(extend.class || '').trim();
    var a = rule._jpStr(extend.area || '').trim();
    var y = rule._jpStr(extend.year || '').trim();
    var l = rule._jpStr(extend.lang || '').trim();
    if (t) url += '/type/' + encodeURIComponent(t);
    if (c) url += '/class/' + encodeURIComponent(c);
    if (a) url += '/area/' + encodeURIComponent(a);
    if (y) url += '/year/' + encodeURIComponent(y);
    if (l) url += '/lang/' + encodeURIComponent(l);
    var page = parseInt(pg, 10) || 1;
    if (page > 1) url += '/page/' + page;
    return url;
  },

  推荐: async function() {
    var url = this.input || (rule.host + '/');
    try {
      var html = rule._jpResp(await request(url, { headers: rule.headers }));
      var ft = rule._jpFlight(html);
      var keys = ['homeNewMoviePageData', 'homeBroadcastPageData', 'newestTvPageData', 'newestVarietyPageData', 'newestCartoonPageData', 'newestShortTvPageData', 'homeManagerPageData', 'homeTrailerPageData'];
      var list = [], seen = {};
      for (var i = 0; i < keys.length; i++) {
        var o = rule._jpByKey(ft, keys[i]);
        var arr = o && o.list ? o.list : null;
        if (arr) {
          for (var k = 0; k < arr.slice(0, 6).length; k++) {
            var it = rule._jpMap(arr[k]);
            if (it && !seen[it.vod_id]) { seen[it.vod_id] = 1; list.push(it); }
          }
        }
        if (list.length >= 12) break;
      }
      if (!list.length) list = rule._jpCards(html);
      return setResult(list.slice(0, 24));
    } catch (e) { return setResult([]); }
  },

  一级: async function(tid, pg, filter, extend) {
    var myTid = tid || this.MY_CATE || '1';
    var myPg = parseInt(pg || this.MY_PAGE || 1, 10) || 1;
    var ext = extend || filter || this.MY_FL || {};
    if (typeof ext === 'string') { try { ext = JSON.parse(ext); } catch (e) { ext = {}; } }
    var url = rule._jpCatUrl(myTid, myPg, ext);
    try {
      var html = rule._jpResp(await request(url, { headers: rule.headers }));
      var ft = rule._jpFlight(html);
      var vd = rule._jpByKey(ft, 'videoList');
      var data = vd && vd.data ? vd.data : vd;
      if (data && Array.isArray(data.list) && data.list.length) {
        var list = [];
        for (var i = 0; i < data.list.length; i++) {
          var m = rule._jpMap(data.list[i]);
          if (m) list.push(m);
        }
        return setResult(list);
      }
      var fb = rule._jpCards(html);
      return setResult(fb);
    } catch (e) { return setResult([]); }
  },

  二级: async function(ids) {
    var raw = Array.isArray(ids) ? ids[0] : ids;
    var s = rule._jpStr(raw);
    var mm = /(\d{4,})/.exec(s);
    var vid = mm ? mm[1] : s.trim();
    var url = this.input;
    if (!url || url.indexOf('/detail/') < 0) url = rule.host + '/detail/' + vid;
    try {
      var html = rule._jpResp(await request(url, { headers: rule.headers }));
      var ft = rule._jpFlight(html);
      var get = function(k) {
        var rx = new RegExp('\"' + k + '\":\"(.*?)\"');
        var m1 = rx.exec(ft);
        if (m1) { try { return JSON.parse('\"' + m1[1] + '\"'); } catch (e) { return m1[1]; } }
        var rx2 = new RegExp('\"' + k + '\":([^,}\\]]+)');
        var m2 = rx2.exec(ft);
        return m2 ? m2[1].replace(/^"|"$/g, '') : '';
      };
      var vodName = get('vodName');
      if (!vodName && ft.indexOf('episodeList') < 0) return null;
      var vodId = get('vodId') || vid;
      var pic = get('vodPic');
      var actor = get('vodActor');
      var director = get('vodDirector');
      var contentRaw = get('vodContent') || get('vodBlurb');
      var area = get('vodArea');
      var lang = get('vodLang');
      var year = get('vodYear') || get('vodPubdate');
      var ym = /(\d{4})/.exec(rule._jpStr(year));
      if (ym) year = ym[1]; else year = rule._jpStr(year);
      var vclass = get('vodClass') || get('typeName');
      var remarks = rule._jpStr(get('vodRemarks') || get('vodVersion') || get('vodSerial'));
      var serial = get('vodSerial'), total = get('vodTotal');
      if (!remarks) { if (serial && total) remarks = '(' + serial + '/' + total + ')'; else if (serial) remarks = '(' + serial + ')'; }
      var eps = rule._jpByKey(ft, 'episodeList');
      if (!Array.isArray(eps)) eps = [];
      var parts = [];
      for (var i = 0; i < eps.length; i++) {
        var nid = rule._jpStr(eps[i].nid || '');
        var nm = rule._jpStr(eps[i].name || '正片').replace(/\$/g, '＄').replace(/#/g, '＃');
        if (!nid) continue;
        parts.push(nm + '$' + rule._jpStr(vodId) + '_' + nid);
      }
      var playUrl = parts.join('#');
      return {
        vod_id: rule._jpStr(vodId), vod_name: vodName || ('ID_' + rule._jpStr(vodId)),
        vod_pic: pic, vod_actor: actor, vod_director: director,
        vod_content: rule._jpStrip(contentRaw), vod_area: area, vod_lang: lang,
        vod_year: rule._jpStr(year), type_name: vclass, vod_remarks: remarks,
        vod_play_from: playUrl ? '金牌影院' : '', vod_play_url: playUrl
      };
    } catch (e) { return null; }
  },

  搜索: async function(wd, quick, pg) {
    var keyword = '';
    if (typeof wd === 'string' && wd) keyword = wd;
    else if (this.KEY) keyword = this.KEY;
    keyword = rule._jpStr(keyword).trim();
    var page = parseInt(pg || this.MY_PAGE || 1, 10) || 1;
    if (!keyword) return setResult([]);
    try {
      var url = rule.host + '/vod/search/' + encodeURIComponent(keyword);
      if (page > 1) url += '?page=' + page;
      var html = rule._jpResp(await request(url, { headers: rule.headers }));
      var ft = rule._jpFlight(html);
      var rs = rule._jpByKey(ft, 'result');
      if (rs && rs.list && rs.list.length) {
        var list = [];
        for (var i = 0; i < rs.list.length; i++) { var a = rule._jpMap(rs.list[i]); if (a) list.push(a); }
        return setResult(list);
      }
      var vd = rule._jpByKey(ft, 'videoList');
      var data = vd && vd.data ? vd.data : null;
      if (data && data.list && data.list.length) {
        var list2 = [];
        for (var j = 0; j < data.list.length; j++) { var b = rule._jpMap(data.list[j]); if (b) list2.push(b); }
        return setResult(list2);
      }
      return setResult(rule._jpCards(html));
    } catch (e) { return setResult([]); }
  },

  lazy: async function(flag, id) {
    var s = rule._jpStr(id || this.input || '');
    var vodId = '', nid = '';
    var m = /(\d+)_(\d+)/.exec(s);
    if (m) { vodId = m[1]; nid = m[2]; }
    else {
      var nums = s.match(/\d+/g) || [];
      if (nums.length >= 2) { vodId = nums[nums.length - 2]; nid = nums[nums.length - 1]; }
    }
    var playPage = s;
    if (vodId && nid) playPage = rule.host + '/vod/play/' + vodId + '/sid/' + nid;
    else if (s.indexOf('http') === 0) playPage = s;
    var PH = { 'User-Agent': rule.headers['User-Agent'], 'Referer': rule.host + '/', 'Origin': rule.host };
    try {
      var html = rule._jpResp(await request(playPage, { headers: rule.headers }));
      var all = rule._jpFlight(html) + '\n' + rule._jpStr(html);
      var m3 = /(https?:[^"'\\\s<>]+\.m3u8[^"'\\\s<>]*)/i.exec(all);
      if (m3) return { parse: 0, url: m3[1], header: PH };
      var mp4 = /(https?:[^"'\\\s<>]+\.mp4[^"'\\\s<>]*)/i.exec(all);
      if (mp4) return { parse: 0, url: mp4[1], header: PH };
      return { parse: 1, url: playPage, header: rule.headers };
    } catch (e) { return { parse: 1, url: playPage, header: rule.headers }; }
  }
};
