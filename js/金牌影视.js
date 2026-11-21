/**
 * 发布页 https://www.jpyy.com/
 */

const baseUrl = 'https://www.x8kb9k8.com';
const API_BASE = baseUrl + '/api/mw-movie';
const API_SIGN_KEY = 'cb808529bae6b6be45ecfab29a4889bc';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36';
const HEADERS = { 'User-Agent': UA, 'Referer': baseUrl + '/', 'Accept': 'text/html' };
const API_HEADERS = { 'User-Agent': UA, 'Referer': baseUrl + '/', 'Accept': 'application/json' };
const PLAY_HEADERS = { 'User-Agent': UA, 'Referer': baseUrl + '/', 'Origin': baseUrl };

async function init(cfg) { return {}; }
function destroy() { return {}; }
function live(u) { return JSON.stringify([]); }
function proxy(p) { return [404, 'text/plain', 'no proxy']; }
function sniffer() { return false; }
function isVideo(url) {
  const u = String(url || '').split(/[?#]/)[0].toLowerCase();
  return ['.m3u8', '.mp4', '.mkv', '.flv'].some(function (s) { return u.endsWith(s); });
}
async function action(v) { return JSON.stringify({ msg: 'ok' }); }
function output(v) { return JSON.stringify(v); }
function str(v) { return v == null ? '' : String(v); }
function deviceId() { return 'jinpai-web-' + str(stableUuid()); }
function stableUuid() { return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) { var r = Math.random() * 16 | 0; var v = c === 'x' ? r : (r & 0x3 | 0x8); return v.toString(16); }); }
function stableQuery(params) { return Object.keys(params).sort().map(function (k) { return k + '=' + str(params[k]); }).join('&'); }
function md5Text(value) { return md5X(value); }
function rotateLeft(value, amount) { return (value << amount) | (value >>> (32 - amount)); }
function sha1Text(value) {
  const source = str(value);
  const bytes = [];
  for (let index = 0; index < source.length; index++) {
    let code = source.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff && index + 1 < source.length) {
      const next = source.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        code = 0x10000 + ((code - 0xd800) << 10) + (next - 0xdc00);
        index++;
      }
    }
    if (code < 0x80) bytes.push(code);
    else if (code < 0x800) bytes.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f));
    else if (code < 0x10000) bytes.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));
    else bytes.push(0xf0 | (code >> 18), 0x80 | ((code >> 12) & 0x3f), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));
  }
  const bitLength = bytes.length * 8;
  bytes.push(128);
  while (bytes.length % 64 !== 56) bytes.push(0);
  const high = Math.floor(bitLength / 0x100000000);
  const low = bitLength >>> 0;
  bytes.push((high >>> 24) & 255, (high >>> 16) & 255, (high >>> 8) & 255, high & 255);
  bytes.push((low >>> 24) & 255, (low >>> 16) & 255, (low >>> 8) & 255, low & 255);
  let h0 = 0x67452301;
  let h1 = 0xefcdab89;
  let h2 = 0x98badcfe;
  let h3 = 0x10325476;
  let h4 = 0xc3d2e1f0;
  for (let offset = 0; offset < bytes.length; offset += 64) {
    const words = [];
    for (let index = 0; index < 16; index++) {
      const position = offset + index * 4;
      words[index] = ((bytes[position] << 24) | (bytes[position + 1] << 16) | (bytes[position + 2] << 8) | bytes[position + 3]) >>> 0;
    }
    for (let index = 16; index < 80; index++) words[index] = rotateLeft(words[index - 3] ^ words[index - 8] ^ words[index - 14] ^ words[index - 16], 1);
    let a = h0, b = h1, c = h2, d = h3, e = h4;
    for (let index = 0; index < 80; index++) {
      let f, k;
      if (index < 20) { f = (b & c) | (~b & d); k = 0x5a827999; }
      else if (index < 40) { f = b ^ c ^ d; k = 0x6ed9eba1; }
      else if (index < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8f1bbcdc; }
      else { f = b ^ c ^ d; k = 0xca62c1d6; }
      const next = (rotateLeft(a, 5) + (f >>> 0) + e + k + words[index]) >>> 0;
      e = d;
      d = c;
      c = rotateLeft(b, 30);
      b = a;
      a = next;
    }
    h0 = (h0 + a) >>> 0;
    h1 = (h1 + b) >>> 0;
    h2 = (h2 + c) >>> 0;
    h3 = (h3 + d) >>> 0;
    h4 = (h4 + e) >>> 0;
  }
  return [h0, h1, h2, h3, h4].map(function (value) { return value.toString(16).padStart(8, '0'); }).join('');
}
function signApi(url, params, referer) {
  var query = stableQuery(params);
  var t = Date.now().toString();
  var source = query + (query ? '&' : '') + 'key=' + API_SIGN_KEY + '&t=' + t;
  return { url: url + (query ? '?' + query : ''), headers: { 'User-Agent': UA, Accept: 'application/json', Referer: referer || baseUrl + '/', 'client-type': '1', sign: sha1Text(md5Text(source)), t: t, deviceId: deviceId() } };
}
function stripTags(s) { return str(s).replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim(); }

function parseRespText(resp) {
  if (resp == null) return '';
  if (typeof resp === 'string') return resp;
  if (typeof resp === 'object') {
    if (typeof resp.content === 'string') return resp.content;
    if (typeof resp.data === 'string') return resp.data;
  }
  return str(resp);
}
async function apiGet(path, params, referer) {
  const signed = signApi(API_BASE + path, params || {}, referer);
  const response = await req(signed.url, { headers: signed.headers });
  const text = parseRespText(response);
  const data = JSON.parse(text);
  if (Number(data.code) !== 200) throw new Error(str(data.msg || 'API request failed'));
  return data.data || {};
}
function mapApiList(list) {
  const result = [];
  for (const item of list || []) { const mapped = mapVodItem(item); if (mapped) result.push(mapped); }
  return result;
}
async function apiCategory(tid, pg, extend) {
  const params = { clientType: 1, pageNum: parseInt(pg, 10) || 1, pageSize: 48, type1: str(tid || '1') };
  const selected = extend || {};
  const type = str(selected.type || '').trim();
  const cls = str(selected.class || '').trim();
  const area = str(selected.area || '').trim();
  const year = str(selected.year || '').trim();
  const lang = str(selected.lang || '').trim();
  if (type) params.type = type;
  if (cls) params.v_class = cls;
  if (area) params.area = area;
  if (year) params.year = year;
  if (lang) params.lang = lang;
  const data = await apiGet('/anonymous/video/list', params);
  const list = mapApiList(data.list);
  return { list: list, page: Number(data.pageNum) || params.pageNum, pagecount: Number(data.totalPage) || 1, limit: Number(data.pageSize) || 48, total: Number(data.totalCount) || list.length };
}
async function apiDetail(vid) {
  const data = await apiGet('/anonymous/video/detail', { id: str(vid) });
  const episodes = Array.isArray(data.episodeList) ? data.episodeList : [];
  const list = episodes.map(function (episode) {
    const name = str(episode.name || '正片').replace(/\$/g, '＄').replace(/#/g, '＃');
    return name + '$' + str(vid) + '_' + str(episode.nid || '');
  }).join('#');
  return {
    vod_id: str(vid),
    vod_name: str(data.vodName || ''),
    vod_pic: str(data.vodPic || ''),
    vod_actor: str(data.vodActor || ''),
    vod_director: str(data.vodDirector || ''),
    vod_content: stripTags(data.vodContent || data.vodBlurb || ''),
    vod_area: str(data.vodArea || ''),
    vod_lang: str(data.vodLang || ''),
    vod_year: str(data.vodYear || data.vodPubdate || '').slice(0, 4),
    type_name: str(data.typeName || data.vodClass || ''),
    vod_remarks: str(data.vodRemarks || data.vodVersion || ''),
    vod_play_from: list ? '金牌影院' : '',
    vod_play_url: list
  };
}
async function apiSearch(key, page) {
  const data = await apiGet('/anonymous/video/searchByWordPageable', { keyword: str(key), pageNum: parseInt(page, 10) || 1, pageSize: 48, sourceCode: '', type: '' });
  const list = mapApiList(data.list);
  return { list: list, page: Number(data.pageNum) || parseInt(page, 10) || 1, pagecount: Number(data.totalPage) || 1, limit: Number(data.pageSize) || 48, total: Number(data.totalCount) || list.length };
}
async function httpGet(url) {
  const r = await req(url, { headers: HEADERS });
  return parseRespText(r);
}
function flightText(html) {
  const src = str(html || '');
  const re = /self\.__next_f\.push\(\[1,([\s\S]*?)\]\)<\/script>/g;
  const parts = [];
  let m;
  while ((m = re.exec(src)) !== null) {
    let c = m[1];
    try { c = JSON.parse(c); } catch (e) { try { c = JSON.parse('[' + c + ']')[1]; } catch (e2) { c = c.split('\\n').join('\n').split('\\"').join('"'); } }
    if (typeof c !== 'string') c = str(c);
    parts.push(c);
  }
  return parts.join('\n');
}
function extractBalanced(s, start) {
  const open = s[start];
  const close = open === '{' ? '}' : ']';
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < s.length; i++) {
    const ch = s[i];
    if (inStr) {
      if (esc) esc = false;
      else if (ch === '\\') esc = true;
      else if (ch === '"') inStr = false;
    } else {
      if (ch === '"') inStr = true;
      else if (ch === open) depth++;
      else if (ch === close) { depth--; if (depth === 0) return s.slice(start, i + 1); }
    }
  }
  return '';
}
function extractJsonByKey(text, key) {
  const pat = '"' + key + '"';
  let idx = text.indexOf(pat);
  while (idx >= 0) {
    let j = idx + pat.length;
    while (j < text.length && /\s/.test(text[j])) j++;
    if (text[j] === ':') {
      j++;
      while (j < text.length && /\s/.test(text[j])) j++;
      if (text[j] === '{' || text[j] === '[') {
        const sub = extractBalanced(text, j);
        if (sub) { try { return JSON.parse(sub); } catch (e) {} }
      }
    }
    idx = text.indexOf(pat, idx + 1);
  }
  return null;
}
function mapVodItem(o) {
  if (!o) return null;
  const vodId = str(o.vodId != null ? o.vodId : o.id);
  if (!vodId) return null;
  let remarks = str(o.vodRemarks || o.vodVersion || o.vodSerial || o.remark || '');
  if (!remarks && o.vodScore) remarks = str(o.vodScore);
  return {
    vod_id: vodId,
    vod_name: str(o.vodName || o.name || ''),
    vod_pic: str(o.vodPic || o.img || ''),
    vod_remarks: remarks,
    vod_year: str(o.vodYear || ''),
    vod_area: str(o.vodArea || ''),
    type_name: str(o.vodClass || o.typeName || '')
  };
}
function parseCardsFallback(html) {
  const src = str(html || '');
  const re = /<a[^>]*class="[^"]*content-card[^"]*"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/g;
  const list = [];
  let m;
  while ((m = re.exec(src)) !== null) {
    const href = m[1];
    const inner = m[2];
    const idm = /(\d{4,})/.exec(href);
    if (!idm) continue;
    const vodId = idm[1];
    if (list.some(function (x) { return x.vod_id === vodId; })) continue;
    let name = '';
    const tm = /<div[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)<\/div>/.exec(inner);
    if (tm) name = stripTags(tm[1]);
    if (!name) { const am = /alt="([^"]+)"/.exec(inner); if (am) name = am[1]; }
    if (!name) continue;
    let pic = '';
    const imSet = /<img[^>]*srcSet="([^"]+)"/.exec(inner);
    const imSrc = /<img[^>]*src="([^"]+)"/.exec(inner);
    const imOrig = /data-original="([^"]+)"/.exec(inner);
    const bg = /background-image:url\((https?:[^)]+)\)/.exec(inner);
    const cand = (imOrig && imOrig[1]) || (imSet && imSet[1].split(',')[0].split(' ')[0]) || (imSrc && imSrc[1]) || (bg && bg[1]) || '';
    if (cand && cand.indexOf('site_logo') < 0 && cand.indexOf('data:') !== 0) pic = cand;
    let score = '';
    const sm = /<div[^>]*class="[^"]*score[^"]*"[^>]*>(.*?)<\/div>/.exec(inner);
    if (sm) score = stripTags(sm[1]);
    list.push({ vod_id: vodId, vod_name: name, vod_pic: pic, vod_remarks: score });
    if (list.length >= 48) break;
  }
  return list;
}
function v(n, val) { return { n: n, v: val == null ? '' : str(val) }; }

async function home(filter) {
  const classes = [
    { type_id: '1', type_name: '电影' },
    { type_id: '2', type_name: '电视剧' },
    { type_id: '3', type_name: '综艺' },
    { type_id: '4', type_name: '动漫' },
    { type_id: '88', type_name: '短剧' }
  ];
  const filters = {
    '1': [
      { key: 'class', name: '剧情', value: [v('全部', ''), v('喜剧', '喜剧'), v('动作', '动作'), v('爱情', '爱情'), v('科幻', '科幻'), v('悬疑', '悬疑'), v('奇幻', '奇幻'), v('恐怖', '恐怖'), v('剧情', '剧情'), v('犯罪', '犯罪'), v('动画', '动画'), v('惊悚', '惊悚'), v('战争', '战争'), v('冒险', '冒险'), v('灾难', '灾难'), v('伦理', '伦理'), v('其他', '其他')] },
      { key: 'area', name: '地区', value: [v('全部', ''), v('中国大陆', '中国大陆'), v('中国香港', '中国香港'), v('中国台湾', '中国台湾'), v('美国', '美国'), v('日本', '日本'), v('韩国', '韩国'), v('印度', '印度'), v('泰国', '泰国'), v('英国', '英国'), v('法国', '法国'), v('其他', '其他')] },
      { key: 'year', name: '年份', value: [v('全部', ''), v('2026', '2026'), v('2025', '2025'), v('2024', '2024'), v('2023', '2023'), v('2022', '2022'), v('2021', '2021'), v('2020', '2020'), v('2019', '2019'), v('2018', '2018'), v('2017', '2017'), v('2016', '2016'), v('2015', '2015'), v('2014', '2014'), v('2013', '2013'), v('2012', '2012'), v('2011', '2011'), v('2010', '2010'), v('2009~2000', '2009~2000')] },
      { key: 'lang', name: '语言', value: [v('全部', ''), v('国语', '国语'), v('英语', '英语'), v('粤语', '粤语'), v('韩语', '韩语'), v('日语', '日语'), v('其他', '其他')] }
    ],
    '2': [
      { key: 'type', name: '类型', value: [v('全部', ''), v('国产剧', '14'), v('欧美剧', '15'), v('港台剧', '16'), v('日韩剧', '62'), v('其他剧', '68')] },
      { key: 'class', name: '剧情', value: [v('全部', ''), v('古装', '古装'), v('战争', '战争'), v('喜剧', '喜剧'), v('家庭', '家庭'), v('犯罪', '犯罪'), v('动作', '动作'), v('奇幻', '奇幻'), v('剧情', '剧情'), v('历史', '历史'), v('短片', '短片'), v('其他', '其他')] },
      { key: 'area', name: '地区', value: [v('全部', ''), v('中国大陆', '中国大陆'), v('中国香港', '中国香港'), v('中国台湾', '中国台湾'), v('日本', '日本'), v('韩国', '韩国'), v('美国', '美国'), v('泰国', '泰国'), v('其他', '其他')] },
      { key: 'year', name: '年份', value: [v('全部', ''), v('2026', '2026'), v('2025', '2025'), v('2024', '2024'), v('2023', '2023'), v('2022', '2022'), v('2021', '2021'), v('2020', '2020'), v('2019', '2019'), v('2018', '2018'), v('2017', '2017'), v('2016', '2016'), v('2015', '2015'), v('2014', '2014'), v('2013', '2013'), v('2012', '2012'), v('2011', '2011'), v('2010', '2010')] },
      { key: 'lang', name: '语言', value: [v('全部', ''), v('国语', '国语'), v('英语', '英语'), v('粤语', '粤语'), v('韩语', '韩语'), v('日语', '日语'), v('泰语', '泰语'), v('其他', '其他')] }
    ],
    '3': [
      { key: 'type', name: '类型', value: [v('全部', ''), v('国产综艺', '69'), v('港台综艺', '70'), v('日韩综艺', '72'), v('欧美综艺', '73')] },
      { key: 'class', name: '剧情', value: [v('全部', ''), v('真人秀', '真人秀'), v('音乐', '音乐'), v('脱口秀', '脱口秀')] },
      { key: 'area', name: '地区', value: [v('全部', ''), v('中国大陆', '中国大陆'), v('中国香港', '中国香港'), v('中国台湾', '中国台湾'), v('日本', '日本'), v('韩国', '韩国'), v('美国', '美国'), v('其他', '其他')] },
      { key: 'year', name: '年份', value: [v('全部', ''), v('2026', '2026'), v('2025', '2025'), v('2024', '2024'), v('2023', '2023'), v('2022', '2022'), v('2021', '2021'), v('2020', '2020')] },
      { key: 'lang', name: '语言', value: [v('全部', ''), v('国语', '国语'), v('英语', '英语'), v('粤语', '粤语'), v('韩语', '韩语'), v('日语', '日语'), v('其他', '其他')] }
    ],
    '4': [
      { key: 'type', name: '类型', value: [v('全部', ''), v('国产动漫', '75'), v('日韩动漫', '76'), v('欧美动漫', '77')] },
      { key: 'class', name: '剧情', value: [v('全部', ''), v('喜剧', '喜剧'), v('科幻', '科幻'), v('热血', '热血'), v('冒险', '冒险'), v('动作', '动作'), v('运动', '运动'), v('战争', '战争'), v('动画', '动画')] },
      { key: 'area', name: '地区', value: [v('全部', ''), v('中国大陆', '中国大陆'), v('日本', '日本'), v('美国', '美国'), v('其他', '其他')] },
      { key: 'year', name: '年份', value: [v('全部', ''), v('2026', '2026'), v('2025', '2025'), v('2024', '2024'), v('2023', '2023'), v('2022', '2022'), v('2021', '2021'), v('2020', '2020'), v('2019', '2019'), v('2018', '2018'), v('2017', '2017'), v('2016', '2016'), v('2015', '2015'), v('2014', '2014'), v('2013', '2013'), v('2012', '2012'), v('2011', '2011'), v('2010', '2010')] },
      { key: 'lang', name: '语言', value: [v('全部', ''), v('国语', '国语'), v('英语', '英语'), v('日语', '日语'), v('其他', '其他')] }
    ],
    '88': [
      { key: 'type', name: '类型', value: [v('全部', ''), v('喜剧', '100'), v('奇幻', '99'), v('惊悚', '98'), v('悬疑', '97'), v('古装', '96'), v('爱情', '95'), v('剧情', '94')] },
      { key: 'class', name: '剧情', value: [v('全部', ''), v('逆袭', '逆袭'), v('甜宠', '甜宠'), v('虐恋', '虐恋'), v('穿越', '穿越'), v('重生', '重生'), v('剧情', '剧情'), v('科幻', '科幻'), v('武侠', '武侠'), v('爱情', '爱情'), v('动作', '动作'), v('战争', '战争'), v('冒险', '冒险'), v('其他', '其他')] },
      { key: 'year', name: '年份', value: [v('全部', ''), v('2026', '2026'), v('2025', '2025'), v('2024', '2024'), v('2023', '2023'), v('2022', '2022'), v('2021', '2021'), v('2020', '2020'), v('更早', '更早')] }
    ]
  };
  return output({ class: classes, filters: filters });
}

async function homeVod() {
  try {
    const html = await httpGet(baseUrl + '/');
    const ft = flightText(html);
    const keys = ['homeNewMoviePageData', 'homeBroadcastPageData', 'newestTvPageData', 'newestVarietyPageData', 'newestCartoonPageData', 'newestShortTvPageData'];
    let list = [];
    const seen = {};
    for (const k of keys) {
      const o = extractJsonByKey(ft, k);
      const arr = o && o.list ? o.list : null;
      if (arr) {
        for (const it of arr.slice(0, 6)) { const m = mapVodItem(it); if (m && !seen[m.vod_id]) { seen[m.vod_id] = 1; list.push(m); } }
      }
      if (list.length >= 12) break;
    }
    if (!list.length) list = parseCardsFallback(html);
    return output({ list: list.slice(0, 24) });
  } catch (e) {
    return output({ list: await apiHomeList() });
  }
}
async function apiHomeList() {
  const data = await apiGet('/anonymous/v1/movie/recommend', { clientType: 1, modulesType: '1', pageNum: 1 });
  return mapApiList(data.list);
}

function buildCategoryUrl(tid, pg, extend) {
  extend = extend || {};
  let url = baseUrl + '/vod/show/id/' + encodeURIComponent(str(tid || '1'));
  const t = str(extend.type || '').trim();
  const c = str(extend.class || '').trim();
  const a = str(extend.area || '').trim();
  const y = str(extend.year || '').trim();
  const l = str(extend.lang || '').trim();
  if (t) url += '/type/' + encodeURIComponent(t);
  if (c) url += '/class/' + encodeURIComponent(c);
  if (a) url += '/area/' + encodeURIComponent(a);
  if (y) url += '/year/' + encodeURIComponent(y);
  if (l) url += '/lang/' + encodeURIComponent(l);
  const page = parseInt(pg, 10) || 1;
  if (page > 1) url += '/page/' + page;
  return { url: url, page: page };
}

async function category(tid, pg, filter, extend) {
  const page = parseInt(pg, 10) || 1;
  try {
    const data = await apiCategory(tid, page, extend);
    return output(data);
  } catch (e) {
    const built = buildCategoryUrl(tid, page, extend);
    const html = await httpGet(built.url);
    const ft = flightText(html);
    const vd = extractJsonByKey(ft, 'videoList');
    const source = vd && vd.data ? vd.data : vd;
    if (source && Array.isArray(source.list) && source.list.length) {
      const list = mapApiList(source.list);
      return output({ list: list, page: Number(source.pageNum) || page, pagecount: Number(source.totalPage) || 1, limit: Number(source.pageSize) || 48, total: Number(source.totalCount) || list.length });
    }
    const list = parseCardsFallback(html);
    return output({ list: list, page: page, pagecount: list.length ? page + 1 : 1, limit: 48, total: list.length ? 9999 : 0 });
  }
}

function detailId(v) { const m = /(\d{4,})/.exec(str(v)); return m ? m[1] : str(v).trim(); }

async function detail(id) {
  const vid = detailId(id);
  try {
    const vod = await apiDetail(vid);
    if (!vod.vod_name && !vod.vod_play_url) return output({ list: [] });
    return output({ list: [vod] });
  } catch (e) {
    const html = await httpGet(baseUrl + '/detail/' + vid);
    const ft = flightText(html);
    const get = function (k) {
      const m = new RegExp('"' + k + '":"(.*?)"').exec(ft);
      return m ? m[1] : '';
    };
    const eps = extractJsonByKey(ft, 'episodeList') || [];
    const list = eps.map(function (ep) { return str(ep.name || '正片') + '$' + vid + '_' + str(ep.nid || ''); }).join('#');
    return output({ list: [{ vod_id: vid, vod_name: get('vodName'), vod_pic: get('vodPic'), vod_actor: get('vodActor'), vod_director: get('vodDirector'), vod_content: stripTags(get('vodContent') || get('vodBlurb')), vod_area: get('vodArea'), vod_lang: get('vodLang'), vod_year: get('vodYear') || get('vodPubdate'), type_name: get('typeName') || get('vodClass'), vod_remarks: get('vodRemarks') || get('vodVersion'), vod_play_from: list ? '金牌影院' : '', vod_play_url: list }] });
  }
}

async function search(key, quick, pg) {
  const page = parseInt(pg, 10) || 1;
  const wd = str(key || '').trim();
  if (!wd) return output({ list: [], page: page, pagecount: 1, limit: 48, total: 0 });
  try {
    return output(await apiSearch(wd, page));
  } catch (e) {
    const html = await httpGet(baseUrl + '/vod/search/' + encodeURIComponent(wd) + (page > 1 ? '?page=' + page : ''));
    const ft = flightText(html);
    const result = extractJsonByKey(ft, 'result') || extractJsonByKey(ft, 'videoList');
    const data = result && result.data ? result.data : result;
    if (data && Array.isArray(data.list) && data.list.length) {
      const list = mapApiList(data.list);
      return output({ list: list, page: Number(data.pageNum) || page, pagecount: Number(data.totalPage) || 1, limit: Number(data.pageSize) || 48, total: Number(data.totalCount) || list.length });
    }
    const list = parseCardsFallback(html);
    return output({ list: list, page: page, pagecount: list.length ? page + 1 : 1, limit: 48, total: list.length ? 9999 : 0 });
  }
}

async function apiPlay(vodId, nid, referer) {
  const data = await apiGet('/anonymous/v2/video/episode/url', { clientType: 1, id: str(vodId), nid: str(nid) }, referer);
  return Array.isArray(data.list) ? data.list : [];
}
function playItem(item) {
  const url = str(item && item.url);
  return url && item && (item.flag === true || item.needLogin === false) ? item : null;
}
function selectPlayItem(list) {
  for (const item of list || []) { const selected = playItem(item); if (selected) return selected; }
  return null;
}
async function play(flag, id, vipFlags) {
  const s = str(id || '');
  let vodId = '', nid = '';
  const m = /(\d+)_(\d+)/.exec(s);
  if (m) { vodId = m[1]; nid = m[2]; }
  else { const nums = s.match(/\d+/g) || []; if (nums.length >= 2) { vodId = nums[nums.length - 2]; nid = nums[nums.length - 1]; } }
  const playPage = vodId && nid ? baseUrl + '/vod/play/' + vodId + '/sid/' + nid : s;
  if (vodId && nid) {
    const list = await apiPlay(vodId, nid, playPage);
    const selected = selectPlayItem(list);
    if (selected) return output({ parse: 0, url: selected.url, header: PLAY_HEADERS });
    throw new Error('播放线路不可用');
  }
  if (s.indexOf('http') === 0 && /\.m3u8(?:[?#]|$)/i.test(s)) return output({ parse: 0, url: s, header: PLAY_HEADERS });
  const html = await httpGet(playPage);
  const all = flightText(html) + '\n' + str(html);
  const m3 = /(https?:[^"'\\s<>]+\.m3u8[^"'\\s<>]*)/i.exec(all);
  if (m3) return output({ parse: 0, url: m3[1], header: PLAY_HEADERS });
  const mp4 = /(https?:[^"'\\s<>]+\.mp4[^"'\\s<>]*)/i.exec(all);
  if (mp4) return output({ parse: 0, url: mp4[1], header: PLAY_HEADERS });
  throw new Error('播放地址不可用');
}

async function homeContent(filter) { return home(filter); }
async function homeVideoContent() { return homeVod(); }
async function categoryContent(tid, pg, filter, extend) { return category(tid, pg, filter, extend); }
async function detailContent(ids) { const id = Array.isArray(ids) ? ids[0] : ids; return detail(id); }
async function searchContent(key, quick, pg) { return search(key, quick, pg); }
async function playerContent(flag, id, vipFlags) { return play(flag, id, vipFlags); }

export default { init, home, homeVod, category, detail, search, play, live, proxy, action, sniffer, isVideo, destroy, homeContent, homeVideoContent, categoryContent, detailContent, searchContent, playerContent };