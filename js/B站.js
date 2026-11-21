/**
 * @config
 * timeout: 30
 * blockImages: false
 * returnType: dom
 * debug: false
 *
 */

var siteUrl = 'https://www.bilibili.com';
var wvPlayerUrl = 'https://player.bilibili.com/player.html';
var DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';

/* ==================== 共用纯计算 ==================== */
function safeText(v) { return String(v == null ? '' : v).replace(/\s+/g, ' ').trim(); }
function firstId(ids) { return Array.isArray(ids) ? String(ids[0] || '') : String(ids == null ? '' : ids); }
function cleanPlayName(value, fallback) {
    var name = safeText(value || fallback || '').replace(/[$#]/g, ' ');
    return name || '第1集';
}
function packPlayId(data) { return 'bvplay:' + encodeURIComponent(JSON.stringify(data || {})); }
function unpackPlayId(value) {
    var raw = String(value || '');
    if (raw.indexOf('bvplay:') !== 0) return { type: 'url', url: raw };
    var payload = raw.slice(7);
    try { var d = JSON.parse(payload); if (d && typeof d === 'object') return d; } catch (e) {}
    try { var d2 = JSON.parse(decodeURIComponent(payload)); if (d2 && typeof d2 === 'object') return d2; } catch (e2) {}
    return {};
}
function extractBvid(input) {
    var s = String(input || '');
    var m = s.match(/(BV[A-Za-z0-9]{10})/) || s.match(/bvid=([A-Za-z0-9]+)/);
    return m ? m[1] : '';
}
function extractAid(input) {
    var s = String(input || '');
    var m = s.match(/\/video\/av(\d+)/) || s.match(/[?&]aid=(\d+)/) || s.match(/^av(\d+)$/i);
    return m ? m[1] : '';
}
function normalizeCrTid(tid) {
    if (tid && typeof tid === 'object') return String(tid.id || tid.name || '');
    var raw = String(tid || '').trim();
    if (!raw) return '';
    try { raw = decodeURIComponent(raw); } catch (e) {}
    if (raw.charAt(0) === '{' && raw.charAt(raw.length - 1) === '}') {
        try { var d = JSON.parse(raw); raw = String(d.id || d.name || ''); } catch (e2) {}
    }
    return raw;
}
function richLink(name, routeId) {
    var text = safeText(name);
    var id = String(routeId || '').trim();
    if (!text || !id) return text;
    return '[a=cr:' + JSON.stringify({ id: id, name: text }) + '/]' + text + '[/a]';
}

/* ==================== MD5（UTF-8 安全） ==================== */
function md5(s) {
    function utf8Bytes(str) {
        var out = [];
        for (var i = 0; i < str.length; i++) {
            var c = str.charCodeAt(i);
            if (c < 0x80) out.push(c);
            else if (c < 0x800) { out.push(0xC0 | (c >> 6), 0x80 | (c & 0x3F)); }
            else if (c < 0xD800 || c >= 0xE000) { out.push(0xE0 | (c >> 12), 0x80 | ((c >> 6) & 0x3F), 0x80 | (c & 0x3F)); }
            else {
                i++;
                var c2 = str.charCodeAt(i);
                var cp = 0x10000 + (((c & 0x3FF) << 10) | (c2 & 0x3FF));
                out.push(0xF0 | (cp >> 18), 0x80 | ((cp >> 12) & 0x3F), 0x80 | ((cp >> 6) & 0x3F), 0x80 | (cp & 0x3F));
            }
        }
        return out;
    }
    function rl(n, c) { return (n << c) | (n >>> (32 - c)); }
    function au(x, y) { var l = (x & 0xFFFF) + (y & 0xFFFF); var m = (x >> 16) + (y >> 16) + (l >> 16); return (m << 16) | (l & 0xFFFF); }
    function cmn(q, a, b, x, s, t) { return au(rl(au(au(a, q), au(x, t)), s), b); }
    function ff(a, b, c, d, x, s, t) { return cmn((b & c) | ((~b) & d), a, b, x, s, t); }
    function gg(a, b, c, d, x, s, t) { return cmn((b & d) | (c & (~d)), a, b, x, s, t); }
    function hh(a, b, c, d, x, s, t) { return cmn(b ^ c ^ d, a, b, x, s, t); }
    function ii(a, b, c, d, x, s, t) { return cmn(c ^ (b | (~d)), a, b, x, s, t); }
    var bytes = utf8Bytes(s);
    var bl = bytes.length * 8;
    bytes.push(0x80);
    while (bytes.length % 64 !== 56) bytes.push(0);
    for (var b = 0; b < 8; b++) bytes.push((bl >>> (b * 8)) & 0xFF);
    var x = [];
    for (var w = 0; w < bytes.length; w += 4) x.push(bytes[w] | (bytes[w + 1] << 8) | (bytes[w + 2] << 16) | (bytes[w + 3] << 24));
    var a = 1732584193, b2 = -271733879, c = -1732584194, d = 271733878;
    for (var i = 0; i < x.length; i += 16) {
        var oa = a, ob = b2, oc = c, od = d;
        a = ff(a, b2, c, d, x[i] || 0, 7, -680876936); d = ff(d, a, b2, c, x[i + 1] || 0, 12, -389564586); c = ff(c, d, a, b2, x[i + 2] || 0, 17, 606105819); b2 = ff(b2, c, d, a, x[i + 3] || 0, 22, -1044525330);
        a = ff(a, b2, c, d, x[i + 4] || 0, 7, -176418897); d = ff(d, a, b2, c, x[i + 5] || 0, 12, 1200080426); c = ff(c, d, a, b2, x[i + 6] || 0, 17, -1473231341); b2 = ff(b2, c, d, a, x[i + 7] || 0, 22, -45705983);
        a = ff(a, b2, c, d, x[i + 8] || 0, 7, 1770035416); d = ff(d, a, b2, c, x[i + 9] || 0, 12, -1958414417); c = ff(c, d, a, b2, x[i + 10] || 0, 17, -42063); b2 = ff(b2, c, d, a, x[i + 11] || 0, 22, -1990404162);
        a = ff(a, b2, c, d, x[i + 12] || 0, 7, 1804603682); d = ff(d, a, b2, c, x[i + 13] || 0, 12, -40341101); c = ff(c, d, a, b2, x[i + 14] || 0, 17, -1502002290); b2 = ff(b2, c, d, a, x[i + 15] || 0, 22, 1236535329);
        a = gg(a, b2, c, d, x[i + 1] || 0, 5, -165796510); d = gg(d, a, b2, c, x[i + 6] || 0, 9, -1069501632); c = gg(c, d, a, b2, x[i + 11] || 0, 14, 643717713); b2 = gg(b2, c, d, a, x[i] || 0, 20, -373897302);
        a = gg(a, b2, c, d, x[i + 5] || 0, 5, -701558691); d = gg(d, a, b2, c, x[i + 10] || 0, 9, 38016083); c = gg(c, d, a, b2, x[i + 15] || 0, 14, -660478335); b2 = gg(b2, c, d, a, x[i + 4] || 0, 20, -405537848);
        a = gg(a, b2, c, d, x[i + 9] || 0, 5, 568446438); d = gg(d, a, b2, c, x[i + 14] || 0, 9, -1019803690); c = gg(c, d, a, b2, x[i + 3] || 0, 14, -187363961); b2 = gg(b2, c, d, a, x[i + 8] || 0, 20, 1163531501);
        a = gg(a, b2, c, d, x[i + 13] || 0, 5, -1444681467); d = gg(d, a, b2, c, x[i + 2] || 0, 9, -51403784); c = gg(c, d, a, b2, x[i + 7] || 0, 14, 1735328473); b2 = gg(b2, c, d, a, x[i + 12] || 0, 20, -1926607734);
        a = hh(a, b2, c, d, x[i + 5] || 0, 4, -378558); d = hh(d, a, b2, c, x[i + 8] || 0, 11, -2022574463); c = hh(c, d, a, b2, x[i + 11] || 0, 16, 1839030562); b2 = hh(b2, c, d, a, x[i + 14] || 0, 23, -35309556);
        a = hh(a, b2, c, d, x[i + 1] || 0, 4, -1530992060); d = hh(d, a, b2, c, x[i + 4] || 0, 11, 1272893353); c = hh(c, d, a, b2, x[i + 7] || 0, 16, -155497632); b2 = hh(b2, c, d, a, x[i + 10] || 0, 23, -1094730640);
        a = hh(a, b2, c, d, x[i + 13] || 0, 4, 681279174); d = hh(d, a, b2, c, x[i] || 0, 11, -358537222); c = hh(c, d, a, b2, x[i + 3] || 0, 16, -722521979); b2 = hh(b2, c, d, a, x[i + 6] || 0, 23, 76029189);
        a = hh(a, b2, c, d, x[i + 9] || 0, 4, -640364487); d = hh(d, a, b2, c, x[i + 12] || 0, 11, -421815835); c = hh(c, d, a, b2, x[i + 15] || 0, 16, 530742520); b2 = hh(b2, c, d, a, x[i + 2] || 0, 23, -995338651);
        a = ii(a, b2, c, d, x[i] || 0, 6, -198630844); d = ii(d, a, b2, c, x[i + 7] || 0, 10, 1126891415); c = ii(c, d, a, b2, x[i + 14] || 0, 15, -1416354905); b2 = ii(b2, c, d, a, x[i + 5] || 0, 21, -57434055);
        a = ii(a, b2, c, d, x[i + 12] || 0, 6, 1700485571); d = ii(d, a, b2, c, x[i + 3] || 0, 10, -1894986606); c = ii(c, d, a, b2, x[i + 10] || 0, 15, -1051523); b2 = ii(b2, c, d, a, x[i + 1] || 0, 21, -2054922799);
        a = ii(a, b2, c, d, x[i + 8] || 0, 6, 1873313359); d = ii(d, a, b2, c, x[i + 15] || 0, 10, -30611744); c = ii(c, d, a, b2, x[i + 6] || 0, 15, -1560198380); b2 = ii(b2, c, d, a, x[i + 13] || 0, 21, 1309151649);
        a = ii(a, b2, c, d, x[i + 4] || 0, 6, -145523070); d = ii(d, a, b2, c, x[i + 11] || 0, 10, -1120210379); c = ii(c, d, a, b2, x[i + 2] || 0, 15, 718787259); b2 = ii(b2, c, d, a, x[i + 9] || 0, 21, -343485551);
        a = au(a, oa); b2 = au(b2, ob); c = au(c, oc); d = au(d, od);
    }
    function hex(n) { var s = ''; for (var i = 0; i < 4; i++) s += ('0' + ((n >> (i * 8)) & 0xFF).toString(16)).slice(-2); return s; }
    return (hex(a) + hex(b2) + hex(c) + hex(d)).toLowerCase();
}

/* ==================== Wbi 签名 ==================== */
var _wbiCache = { imgKey: '', subKey: '', ts: 0 };
function _mixinKeyEncTab() {
    return [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
        33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
        26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
        20, 34, 44, 52];
}
function _getMixinKey(orig) {
    var tab = _mixinKeyEncTab();
    var s = '';
    for (var i = 0; i < tab.length; i++) s += orig.charAt(tab[i]);
    return s.slice(0, 32);
}
async function getWbiKeys() {
    var now = Date.now();
    if (_wbiCache.imgKey && _wbiCache.subKey && now - _wbiCache.ts < 1200 * 1000) {
        return { imgKey: _wbiCache.imgKey, subKey: _wbiCache.subKey };
    }
    try {
        var res = await fetch('https://api.bilibili.com/x/web-interface/nav', {
            headers: { 'User-Agent': DESKTOP_UA, 'Referer': 'https://www.bilibili.com/' }
        });
        var data = await res.json();
        if (data && data.code === 0 && data.data && data.data.wbi_img) {
            var img = String(data.data.wbi_img.img_url || '').split('/').pop().split('.')[0];
            var sub = String(data.data.wbi_img.sub_url || '').split('/').pop().split('.')[0];
            _wbiCache = { imgKey: img, subKey: sub, ts: now };
            return { imgKey: img, subKey: sub };
        }
    } catch (e) {}
    return { imgKey: '', subKey: '' };
}
async function encWbi(params) {
    var keys = await getWbiKeys();
    var orig = keys.imgKey + keys.subKey;
    if (!orig) return params;
    var mixinKey = _getMixinKey(orig);
    var p = {};
    for (var k in params) if (Object.prototype.hasOwnProperty.call(params, k)) p[k] = params[k];
    p.wts = Math.round(Date.now() / 1000);
    var sortedKeys = Object.keys(p).sort();
    var query = '';
    for (var i = 0; i < sortedKeys.length; i++) {
        var kk = sortedKeys[i];
        var vv = String(p[kk]).replace(/[!'()*]/g, '');
        query += (i ? '&' : '') + encodeURIComponent(kk) + '=' + encodeURIComponent(vv);
    }
    p.w_rid = md5(query + mixinKey);
    return p;
}

/* ==================== 常量 ==================== */

var COMMON_FILTERS = [
    {
        key: 'order', name: '排序',
        value: [
            { n: '综合', v: '' }, { n: '最多点击', v: 'click' }, { n: '最新发布', v: 'pubdate' },
            { n: '最多弹幕', v: 'dm' }, { n: '最多收藏', v: 'stow' }
        ]
    },
    {
        key: 'duration', name: '时长',
        value: [
            { n: '全部', v: '' }, { n: '60分钟以下', v: '1' }, { n: '60分钟以上', v: '2' }
        ]
    },
    {
        key: 'tids', name: '分区',
        value: [
            { n: '全部', v: '' }, { n: '动画', v: '1' }, { n: '番剧', v: '13' },
            { n: '国创', v: '167' }, { n: '音乐', v: '3' }, { n: '舞蹈', v: '129' },
            { n: '游戏', v: '4' }, { n: '知识', v: '36' }, { n: '科技', v: '188' },
            { n: '运动', v: '234' }, { n: '汽车', v: '223' }, { n: '生活', v: '160' },
            { n: '美食', v: '211' }, { n: '动物', v: '217' }, { n: '鬼畜', v: '119' },
            { n: '时尚', v: '155' }, { n: '资讯', v: '202' }, { n: '娱乐', v: '5' },
            { n: '影视', v: '181' }, { n: '纪录片', v: '177' }, { n: '电影', v: '23' },
            { n: '电视剧', v: '11' }, { n: '综艺', v: '182' }
        ]
    }
];

/* ==================== 配置 ==================== */

var MINE_TID = '__mine__';
var HISTORY_TID = '__mine_history__';
var FAV_TID = '__mine_fav__';
var CATEGORY_ACTION_ID = 'bili_category_config';
var CATEGORY_VISIBLE_ACTION_ID = 'bili_category_visible';
var STYLE_ACTION_ID = 'bili_list_style';
var RECOMMEND_ACTION_ID = 'bili_show_recommend';
var CFG_KEY = 'bili_wv_cfg_v4';
var _cfgMem = null;

var DEFAULT_CATEGORIES = [
    { type_id: 'hot',       type_name: '热门',   keyword: '热门',   style: 2, tids: '' },
    { type_id: 't_anime',   type_name: '动画',   keyword: '动画',   style: 2, tids: '1' },
    { type_id: 't_bangumi', type_name: '番剧',   keyword: '番剧',   style: 2, tids: '13' },
    { type_id: 't_guochuang',type_name:'国创',   keyword: '国创',   style: 2, tids: '167' },
    { type_id: 't_music',   type_name: '音乐',   keyword: '音乐',   style: 2, tids: '3' },
    { type_id: 't_dance',   type_name: '舞蹈',   keyword: '舞蹈',   style: 2, tids: '129' },
    { type_id: 't_game',    type_name: '游戏',   keyword: '游戏',   style: 2, tids: '4' },
    { type_id: 't_knowledge',type_name:'知识',   keyword: '知识',   style: 2, tids: '36' },
    { type_id: 't_tech',    type_name: '科技',   keyword: '科技',   style: 2, tids: '188' },
    { type_id: 't_sports',  type_name: '运动',   keyword: '运动',   style: 2, tids: '234' },
    { type_id: 't_auto',    type_name: '汽车',   keyword: '汽车',   style: 2, tids: '223' },
    { type_id: 't_life',    type_name: '生活',   keyword: '生活',   style: 2, tids: '160' },
    { type_id: 't_food',    type_name: '美食',   keyword: '美食',   style: 2, tids: '211' },
    { type_id: 't_animal',  type_name: '动物',   keyword: '动物',   style: 2, tids: '217' },
    { type_id: 't_kichiku', type_name: '鬼畜',   keyword: '鬼畜',   style: 2, tids: '119' },
    { type_id: 't_fashion', type_name: '时尚',   keyword: '时尚',   style: 2, tids: '155' },
    { type_id: 't_info',    type_name: '资讯',   keyword: '资讯',   style: 2, tids: '202' },
    { type_id: 't_ent',     type_name: '娱乐',   keyword: '娱乐',   style: 2, tids: '5' },
    { type_id: 't_film',    type_name: '影视',   keyword: '影视',   style: 2, tids: '181' },
    { type_id: 't_doc',     type_name: '纪录片', keyword: '纪录片', style: 2, tids: '177' },
    { type_id: 't_movie',   type_name: '电影',   keyword: '电影',   style: 2, tids: '23' },
    { type_id: 't_tv',      type_name: '电视剧', keyword: '电视剧', style: 2, tids: '11' },
    { type_id: 't_variety', type_name: '综艺',   keyword: '综艺',   style: 2, tids: '182' },
    { type_id: 'k_shadiao', type_name: '沙雕动画', keyword: '沙雕动画', style: 2, tids: '' },
    { type_id: 'k_document',type_name: '纪实',   keyword: '纪实',   style: 2, tids: '' },
    { type_id: 'k_live',    type_name: '演唱会', keyword: '演唱会', style: 2, tids: '' },
    { type_id: 'k_popsong', type_name: '流行音乐', keyword: '流行音乐', style: 2, tids: '' },
    { type_id: 'k_foodie',  type_name: '美食探店', keyword: '美食探店', style: 2, tids: '' },
    { type_id: 'k_recipe',  type_name: '食谱',   keyword: '食谱',   style: 2, tids: '' },
    { type_id: 'k_talk',    type_name: '说案',   keyword: '说案',   style: 2, tids: '' },
    { type_id: 'k_kids',    type_name: '儿童',   keyword: '儿童',   style: 2, tids: '' },
    { type_id: 'k_animals', type_name: '动物世界', keyword: '动物世界', style: 2, tids: '' },
    { type_id: 'k_comedy',  type_name: '相声小品', keyword: '相声小品', style: 2, tids: '' },
    { type_id: 'k_opera',   type_name: '戏曲',   keyword: '戏曲',   style: 2, tids: '' },
    { type_id: 'k_speech',  type_name: '演讲',   keyword: '演讲',   style: 2, tids: '' },
    { type_id: 'k_beauty',  type_name: '小姐姐', keyword: '小姐姐', style: 2, tids: '' },
    { type_id: 'k_survive', type_name: '荒野求生', keyword: '荒野求生', style: 2, tids: '' },
    { type_id: 'k_fitness', type_name: '健身',   keyword: '健身',   style: 2, tids: '' },
    { type_id: 'k_dance',   type_name: '舞蹈',   keyword: '舞蹈',   style: 2, tids: '' },
    { type_id: 'k_song',    type_name: '歌曲',   keyword: '歌曲',   style: 2, tids: '' },
    { type_id: 'k_mv',      type_name: 'MV',     keyword: 'MV',     style: 2, tids: '' },
    { type_id: 'k_4k',      type_name: '4K',     keyword: '4K',     style: 2, tids: '' },
    { type_id: 'k_noise',   type_name: '白噪音', keyword: '白噪音', style: 2, tids: '' },
    { type_id: 'k_exam',    type_name: '考公考证', keyword: '考公考证', style: 2, tids: '' },
    { type_id: 'k_ps',      type_name: '平面设计', keyword: '平面设计', style: 2, tids: '' },
    { type_id: 'k_win',     type_name: 'Windows', keyword: 'Windows', style: 2, tids: '' }
];

var LINE_OPTIONS = [
    { key: 'main',   name: '正片',     enabled: true },
    { key: 'upmore', name: 'UP主更多', enabled: true },
    { key: 'related',name: '相关推荐', enabled: true },
    { key: 'region', name: '同分区',   enabled: true },
    { key: 'search', name: '搜索相关', enabled: true }
];

var STYLE_OPTIONS = [
    { key: 'normal', name: '双列', style: { type: 'rect', ratio: 0.75 } },
    { key: 'wide', name: '大图', style: { type: 'rect', ratio: 1.78 } },
    { key: 'list', name: '列表', style: { type: 'list' } }
];

function cfgRead() {
    if (_cfgMem) return _cfgMem;
    var raw = '';
    try { raw = host.cache.get(CFG_KEY, ''); } catch (e) {}
    try {
        var data = JSON.parse(raw || 'null');
        if (data && typeof data === 'object') { _cfgMem = data; return data; }
    } catch (e2) {}
    _cfgMem = {};
    return _cfgMem;
}
function cfgWrite(data) {
    _cfgMem = data || {};
    try { host.cache.set(CFG_KEY, JSON.stringify(_cfgMem)); } catch (e) {}
}
function normalizeCategories(value) {
    var items = [];
    if (Array.isArray(value)) {
        for (var i = 0; i < value.length; i++) {
            var item = value[i];
            if (!item || typeof item !== 'object') continue;
            var name = safeText(item.name || item.type_name);
            var keyword = safeText(item.keyword || item.type_id || name);
            var style = Number(item.style);
            if (style !== 1 && style !== 2 && style !== 3) style = 0;
            var tids = safeText(item.tids || '');
            if (name && keyword && name !== '我的' && keyword !== MINE_TID) items.push({
                type_id: safeText(item.type_id || ('custom:' + encodeURIComponent(keyword))),
                type_name: name, keyword: keyword, style: style, tids: tids
            });
        }
    }
    return items;
}
function configuredCategories() {
    var cfg = cfgRead();
    var custom = normalizeCategories(cfg.categories);
    return custom.length ? custom : DEFAULT_CATEGORIES.slice();
}
function visibleCategories() {
    var categories = configuredCategories();
    var visible = cfgRead().visible;
    if (!Array.isArray(visible)) return categories;
    var result = categories.filter(function (item) { return visible.indexOf(item.type_id) >= 0; });
    return result.length ? result : categories;
}
function categoryConfigText() {
    return configuredCategories().map(function (item) {
        return item.type_name + '=' + item.keyword
            + (item.tids ? '@' + item.tids : '')
            + (item.style ? ',' + item.style : '');
    }).join(';');
}
function parseCategoryConfig(text) {
    var raw = String(text == null ? '' : text).replace(/\r/g, '\n').trim();
    if (!raw) return [];
    if (raw.charAt(0) === '[') {
        try { return normalizeCategories(JSON.parse(raw)); } catch (e) {}
    }
    var result = [];
    var matcher = /([^,;\n=]+)=([^,;\n@]+?)(?:@([^,;\n]*?))?(?:,(1|2|3))?(?=,|;|\n|$)/g;
    var match;
    while ((match = matcher.exec(raw)) !== null) {
        var name = safeText(match[1]);
        var keyword = safeText(match[2]);
        var tids = safeText(match[3] || '');
        var style = Number(match[4] || 0);
        if (!name || !keyword || name === '我的' || keyword === MINE_TID) continue;
        result.push({
            type_id: 'custom:' + encodeURIComponent(keyword),
            type_name: name, keyword: keyword, style: style, tids: tids
        });
    }
    return result;
}
function getListStyle() {
    var cfg = cfgRead();
    for (var i = 0; i < STYLE_OPTIONS.length; i++) {
        if (STYLE_OPTIONS[i].key === cfg.listStyle) return STYLE_OPTIONS[i].style;
    }
    return STYLE_OPTIONS[0].style;
}
function getCategoryStyle(categoryId) {
    var categories = configuredCategories();
    for (var i = 0; i < categories.length; i++) {
        if (categories[i].type_id !== categoryId) continue;
        var specified = Number(categories[i].style);
        if (specified === 1) return STYLE_OPTIONS[0].style;
        if (specified === 2) return STYLE_OPTIONS[1].style;
        if (specified === 3) return STYLE_OPTIONS[2].style;
        break;
    }
    return getListStyle();
}
function applyCategoryStyle(list, categoryId) {
    var style = getCategoryStyle(categoryId);
    for (var i = 0; i < list.length; i++) list[i].style = style;
    return list;
}

function getEnabledLines() {
    var cfg = cfgRead();
    var userLines = cfg.lines;
    if (!Array.isArray(userLines)) {
        return LINE_OPTIONS.filter(function (l) { return l.enabled; }).map(function (l) { return l.key; });
    }
    return userLines;
}
function isLineEnabled(key) {
    return getEnabledLines().indexOf(key) >= 0;
}
function currentLinesText() {
    var enabled = getEnabledLines();
    var names = [];
    for (var i = 0; i < LINE_OPTIONS.length; i++) {
        if (enabled.indexOf(LINE_OPTIONS[i].key) >= 0) names.push(LINE_OPTIONS[i].name);
    }
    return names.join('、') || '无';
}

function folderItem(id, name, remark) {
    return { vod_id: id, vod_name: name, vod_tag: 'folder', vod_pic: '', vod_remarks: remark || '', style: { type: 'list' } };
}
function actionItem(config, remark) {
    return { vod_id: JSON.stringify(config), vod_name: config.title || config.actionId, vod_tag: 'action', vod_remarks: remark || '', style: { type: 'list' } };
}
function isBiliLoggedIn() {
    try {
        var cookie = String(host.cookies.get('https://www.bilibili.com/') || '');
        return /(?:^|;)\s*(?:SESSDATA|bili_jct|DedeUserID)=/i.test(cookie);
    } catch (e) { return false; }
}
function currentVisibleCategoryText() {
    return visibleCategories().map(function (item) { return item.type_name; }).join('、') || '无';
}
function currentStyleText() {
    var cfg = cfgRead();
    for (var i = 0; i < STYLE_OPTIONS.length; i++) {
        if (STYLE_OPTIONS[i].key === cfg.listStyle) return STYLE_OPTIONS[i].name;
    }
    return STYLE_OPTIONS[0].name;
}

function mineMenu() {
    var loginUrl = 'https://passport.bilibili.com/login';
    var loggedIn = isBiliLoggedIn();
    var cfg = cfgRead();
    var categories = configuredCategories();
    var visible = Array.isArray(cfg.visible) ? visibleCategories().map(function (item) { return item.type_id; }) : null;
    var enabledLines = getEnabledLines();
    return [
        actionItem({ actionId: 'bili_login', type: 'webview', title: '账号登录', url: loginUrl, height: -180, textZoom: 90 }, loggedIn ? '当前已登录' : '当前未登录'),
        folderItem(HISTORY_TID, '历史记录', '查看所有历史记录'),
        folderItem(FAV_TID, '我的收藏', '查看我的收藏夹'),
        actionItem({ actionId: CATEGORY_ACTION_ID, type: 'input', id: 'categories', title: '分类设置',
            tip: '格式：名称=关键词[@分区ID],style；例：动画=动画@1,2',
            value: categoryConfigText(),
            msg: '当前分类：' + categories.map(function (item) { return item.type_name; }).join('、')
                + '；style: 1双列 2大图 3列表' },
            '当前分类：' + categories.map(function (item) { return item.type_name; }).join('、')),
        actionItem({ actionId: CATEGORY_VISIBLE_ACTION_ID, type: 'select', title: '显示分类',
            msg: '激活表示显示，取消激活表示隐藏；“我的”始终显示',
            option: categories.map(function (item) {
                var selected = !Array.isArray(visible) || visible.indexOf(item.type_id) >= 0;
                return { name: item.type_name, action: item.type_id, selected: selected };
            }) }, '当前显示：' + currentVisibleCategoryText()),
        actionItem({ actionId: STYLE_ACTION_ID, type: 'menu', title: '列表样式',
            option: STYLE_OPTIONS.map(function (item) { return { name: item.name, action: item.key }; }),
            selectedIndex: Math.max(0, STYLE_OPTIONS.findIndex(function (item) { return item.key === cfg.listStyle; })) }, '当前样式：' + currentStyleText()),
        actionItem({ actionId: 'bili_lines_config', type: 'select', title: '播放线路',
            msg: '勾选详情页要显示的线路，取消勾选隐藏',
            option: LINE_OPTIONS.map(function (item) {
                var selected = enabledLines.indexOf(item.key) >= 0;
                return { name: item.name, action: item.key, selected: selected };
            }) }, '当前线路：' + currentLinesText()),
        actionItem({ actionId: RECOMMEND_ACTION_ID, type: 'menu', title: '显示推荐',
            option: [{ name: '开', action: 'on' }, { name: '关', action: 'off' }],
            selectedIndex: cfg.showRecommend === false ? 1 : 0 },
            cfg.showRecommend === false ? '关' : '开')
    ];
}

async function action(actionStr) {
    var data = {};
    try { data = JSON.parse(actionStr || '{}'); } catch (e) { data = {}; }
    var actionId = data.action || '';
    var value = data.value && typeof data.value === 'object' ? data.value : {};
    var cfg = cfgRead();

    if (actionId === CATEGORY_ACTION_ID) {
        var cats = parseCategoryConfig(value.categories || '');
        if (!cats.length) return '分类设置未保存：至少需要一个分类';
        cfg.categories = cats;
        cfgWrite(cfg);
        return '分类设置已保存，刷新首页生效';
    }
    if (actionId === CATEGORY_VISIBLE_ACTION_ID) {
        var selected = safeText(value.select || '').split(',').filter(function (item) { return item; });
        var allowed = configuredCategories().map(function (item) { return item.type_id; });
        selected = selected.filter(function (item) { return allowed.indexOf(item) >= 0; });
        if (!selected.length) return '至少显示一个分类，设置未保存';
        cfg.visible = selected;
        cfgWrite(cfg);
        return '显示分类已保存，刷新首页生效';
    }
    if (actionId === STYLE_ACTION_ID) {
        var style = safeText(value.menu || value.style || 'normal');
        cfg.listStyle = STYLE_OPTIONS.some(function (item) { return item.key === style; }) ? style : 'normal';
        cfgWrite(cfg);
        return '列表样式已保存，刷新分类页面生效';
    }
    if (actionId === 'bili_lines_config') {
        var lineSel = safeText(value.select || '').split(',').filter(function (item) { return item; });
        var allowedLines = LINE_OPTIONS.map(function (item) { return item.key; });
        lineSel = lineSel.filter(function (item) { return allowedLines.indexOf(item) >= 0; });
        if (!lineSel.length) return '至少保留一个线路，设置未保存';
        if (lineSel.indexOf('main') < 0) lineSel.unshift('main');
        cfg.lines = lineSel;
        cfgWrite(cfg);
        return '播放线路已保存，刷新详情页生效';
    }
    if (actionId === RECOMMEND_ACTION_ID) {
        cfg.showRecommend = safeText(value.menu || '') !== 'off';
        cfgWrite(cfg);
        return '显示推荐已保存，刷新详情页面生效';
    }
    return '';
}

var routes = {
    homeContent: function () { return false; },
    homeVideoContent: function () { return false; },
    categoryContent: function () { return false; },
    detailContent: function () { return false; },
    recommendContent: function () { return false; },
    searchContent: function () { return false; },
    playerContent: function () { return false; }
};

/* ==================== API ==================== */
function biliHeaders() {
    return {
        'User-Agent': DESKTOP_UA,
        'Referer': 'https://www.bilibili.com/',
        'Origin': 'https://www.bilibili.com',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
    };
}
async function biliGet(url) {
    var res = await fetch(url, { headers: biliHeaders() });
    if (!res.ok) throw new Error('bili HTTP ' + res.status);
    return res.json();
}
function fmtDuration(seconds) {
    var s = Math.max(0, Math.floor(Number(seconds) || 0));
    if (!s) return '';
    var h = Math.floor(s / 3600);
    var m = Math.floor((s % 3600) / 60);
    var sec = s % 60;
    if (h > 0) return h + ':' + ('0' + m).slice(-2) + ':' + ('0' + sec).slice(-2);
    return m + ':' + ('0' + sec).slice(-2);
}
function picFix(url) {
    var u = safeText(url);
    if (!u) return '';
    if (u.charAt(0) === '/') u = 'https:' + u;
    if (u.indexOf('//') === 0) u = 'https:' + u;
    return u;
}
function mapBiliVideo(item) {
    if (!item) return null;
    var bvid = safeText(item.bvid);
    var aid = item.aid || item.id || 0;
    if (!bvid && !aid) return null;
    var title = safeText(item.title || item.name);
    if (!title) return null;
    var pic = picFix(item.pic || item.cover || item.first_frame);
    var dur = item.duration || item.length || 0;
    var remark = fmtDuration(dur);
    var playCount = item.play || (item.stat && item.stat.view) || 0;
    if (playCount) {
        var w = playCount >= 10000 ? Math.round(playCount / 10000) + '万' : playCount;
        remark = remark ? (remark + ' · ' + w + '播放') : (w + '播放');
    }
    return {
        vod_id: packPlayId({ type: 'video', bvid: bvid, aid: aid }),
        vod_name: title.replace(/<[^>]+>/g, ''),
        vod_pic: pic,
        vod_remarks: remark,
        style: getListStyle()
    };
}

/* ---------- 搜索（四路兜底） ---------- */
async function searchApiWbi(keyword, page, ext) {
    ext = ext || {};
    var params = {
        search_type: 'video',
        keyword: keyword,
        page: page || 1,
        page_size: 30
    };
    if (ext.order) params.order = ext.order;
    if (ext.duration) params.duration = ext.duration;
    if (ext.tids) params.tids = ext.tids;
    var signed = await encWbi(params);
    var qs = '';
    for (var k in signed) if (Object.prototype.hasOwnProperty.call(signed, k)) {
        qs += (qs ? '&' : '') + encodeURIComponent(k) + '=' + encodeURIComponent(signed[k]);
    }
    var url = 'https://api.bilibili.com/x/web-interface/wbi/search/type?' + qs;
    var data = await biliGet(url);
    if (!data || data.code !== 0) return await searchApiLegacy(keyword, page, ext);
    var result = (data.data && data.data.result) || [];
    var list = [];
    for (var i = 0; i < result.length; i++) {
        var item = result[i];
        if (item.type && item.type !== 'video') continue;
        var mapped = mapBiliVideo(item);
        if (mapped) list.push(mapped);
    }
    return { list: list, numPages: (data.data && data.data.numPages) || 0 };
}
async function searchApiLegacy(keyword, page, ext) {
    ext = ext || {};
    var qs = 'search_type=video&keyword=' + encodeURIComponent(keyword)
        + '&page=' + (page || 1) + '&page_size=30';
    if (ext.order) qs += '&order=' + encodeURIComponent(ext.order);
    if (ext.duration) qs += '&duration=' + encodeURIComponent(ext.duration);
    if (ext.tids) qs += '&tids=' + encodeURIComponent(ext.tids);
    var url = 'https://api.bilibili.com/x/web-interface/search/type?' + qs;
    try {
        var data = await biliGet(url);
        if (!data || data.code !== 0) return { list: [], numPages: 0 };
        var result = (data.data && data.data.result) || [];
        var list = [];
        for (var i = 0; i < result.length; i++) {
            var item = result[i];
            if (item.type && item.type !== 'video') continue;
            var mapped = mapBiliVideo(item);
            if (mapped) list.push(mapped);
        }
        return { list: list, numPages: (data.data && data.data.numPages) || 0 };
    } catch (e) { return { list: [], numPages: 0 }; }
}
async function searchApiRecommend(keyword, page) {
    var list = [];
    var seen = {};
    var tasks = [];
    var startPage = Math.max(1, (page - 1) * 3 + 1);
    for (var i = 0; i < 6; i++) tasks.push(recommendApi(startPage + i, 30));
    var results = await Promise.all(tasks);
    var kw = String(keyword || '').toLowerCase().replace(/\s+/g, '');
    for (var r = 0; r < results.length; r++) {
        var items = results[r] || [];
        for (var j = 0; j < items.length; j++) {
            var item = items[j];
            var title = String(item.vod_name || '').toLowerCase().replace(/\s+/g, '');
            if (kw && title.indexOf(kw) < 0) continue;
            if (seen[item.vod_id]) continue;
            seen[item.vod_id] = true;
            list.push(item);
        }
    }
    return { list: list, numPages: 0 };
}
async function searchApiWebDom(keyword, page) {
    try {
        var url = 'https://search.bilibili.com/video?keyword=' + encodeURIComponent(keyword) + '&page=' + (page || 1);
        var res = await fetch(url, { headers: biliHeaders() });
        var doc = res && res.doc;
        if (!doc && res && res.text) {
            var html = await res.text();
            doc = new DOMParser().parseFromString(html || '', 'text/html');
        }
        return { list: domVideoList(doc), numPages: 0 };
    } catch (e) { return { list: [], numPages: 0 }; }
}
async function searchApi(keyword, page, ext) {
    try { var r1 = await searchApiWbi(keyword, page, ext); if (r1.list && r1.list.length) return r1; } catch (e1) {}
    try { var r2 = await searchApiLegacy(keyword, page, ext); if (r2.list && r2.list.length) return r2; } catch (e2) {}
    try { var r3 = await searchApiRecommend(keyword, page); if (r3.list && r3.list.length) return r3; } catch (e3) {}
    try { var r4 = await searchApiWebDom(keyword, page); if (r4.list && r4.list.length) return r4; } catch (e4) {}
    return { list: [], numPages: 0 };
}

/* ---------- 分区接口 ---------- */
async function regionApi(tids, page, ps) {
    if (!tids) return [];
    try {
        var url = 'https://api.bilibili.com/x/web-interface/dynamic/region'
            + '?rid=' + encodeURIComponent(tids)
            + '&pn=' + (page || 1)
            + '&ps=' + (ps || 30);
        var data = await biliGet(url);
        if (data && data.code === 0 && data.data && data.data.archives) {
            var arr = data.data.archives || [];
            var list = [];
            for (var i = 0; i < arr.length; i++) {
                var m = mapBiliVideo(arr[i]);
                if (m) list.push(m);
            }
            return list;
        }
    } catch (e) {}
    try {
        var url2 = 'https://api.bilibili.com/x/web-interface/ranking/v2?rid=' + encodeURIComponent(tids) + '&type=all';
        var data2 = await biliGet(url2);
        if (data2 && data2.code === 0 && data2.data && data2.data.list) {
            var arr2 = data2.data.list || [];
            var list2 = [];
            for (var j = 0; j < arr2.length; j++) {
                var m2 = mapBiliVideo(arr2[j]);
                if (m2) list2.push(m2);
            }
            return list2;
        }
    } catch (e2) {}
    return [];
}

/* ---------- 推荐流 ---------- */
async function recommendApi(page, ps) {
    var url = 'https://api.bilibili.com/x/web-interface/index/top/feed/rcmd'
        + '?y_num=1&fresh_type=3&feed_version=SEO_VIDEO'
        + '&fresh_idx_1h=' + page + '&fetch_row=1&fresh_idx=' + page
        + '&brush=' + page + '&homepage_ver=1&ps=' + (ps || 20);
    try {
        var data = await biliGet(url);
        if (!data || data.code !== 0) return [];
        var items = (data.data && data.data.item) || [];
        var list = [];
        for (var i = 0; i < items.length; i++) {
            var m = mapBiliVideo(items[i]);
            if (m) list.push(m);
        }
        return list;
    } catch (e) { return []; }
}

async function videoDetail(bvid, aid) {
    var url = bvid
        ? 'https://api.bilibili.com/x/web-interface/view?bvid=' + bvid
        : 'https://api.bilibili.com/x/web-interface/view?aid=' + aid;
    var data = await biliGet(url);
    if (!data || data.code !== 0) return null;
    return data.data;
}
async function relatedVideos(bvid, aid) {
    var url = bvid
        ? 'https://api.bilibili.com/x/web-interface/archive/related?bvid=' + bvid
        : 'https://api.bilibili.com/x/web-interface/archive/related?aid=' + aid;
    try {
        var data = await biliGet(url);
        if (!data || data.code !== 0) return [];
        var items = data.data || [];
        var list = [];
        for (var i = 0; i < items.length; i++) {
            var m = mapBiliVideo(items[i]);
            if (m) list.push(m);
        }
        return list;
    } catch (e) { return []; }
}

/* ★ 同UP主更多视频 */
async function upMoreVideos(mid, page, ps) {
    if (!mid) return [];
    try {
        var params = { mid: mid, ps: ps || 30, pn: page || 1 };
        var signed = await encWbi(params);
        var qs = '';
        for (var k in signed) if (Object.prototype.hasOwnProperty.call(signed, k)) {
            qs += (qs ? '&' : '') + encodeURIComponent(k) + '=' + encodeURIComponent(signed[k]);
        }
        var url = 'https://api.bilibili.com/x/space/wbi/arc/search?' + qs;
        var data = await biliGet(url);
        if (!data || data.code !== 0) return [];
        var vlist = (data.data && data.data.list && data.data.list.vlist) || [];
        var list = [];
        for (var i = 0; i < vlist.length; i++) {
            var v = vlist[i];
            var bvid = safeText(v.bvid);
            var aid = v.aid || 0;
            if (!bvid && !aid) continue;
            var title = safeText(v.title);
            if (!title) continue;
            var pic = picFix(v.pic);
            var remark = safeText(v.length);
            if (v.play) {
                var w = v.play >= 10000 ? Math.round(v.play / 10000) + '万' : v.play;
                remark = remark ? (remark + ' · ' + w + '播放') : (w + '播放');
            }
            list.push({
                vod_id: packPlayId({ type: 'video', bvid: bvid, aid: aid }),
                vod_name: title.replace(/<[^>]+>/g, ''),
                vod_pic: pic,
                vod_remarks: remark,
                style: getListStyle()
            });
        }
        return list;
    } catch (e) { return []; }
}

/* ★★★ 我的收藏：B站收藏夹 API ★★★ */
async function getUserMid() {
    try {
        var data = await biliGet('https://api.bilibili.com/x/space/myinfo');
        if (data && data.code === 0 && data.data && data.data.mid) {
            return String(data.data.mid);
        }
    } catch (e) {}
    return '';
}

async function fetchFavFolders() {
    var mid = await getUserMid();
    if (!mid) return [];
    try {
        var url = 'https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid=' + mid + '&jsonp=jsonp';
        var data = await biliGet(url);
        if (!data || data.code !== 0) return [];
        var arr = (data.data && data.data.list) || [];
        var list = [];
        for (var i = 0; i < arr.length; i++) {
            var f = arr[i];
            list.push({
                id: f.id,
                title: safeText(f.title) || ('收藏夹' + (i + 1)),
                media_count: f.media_count || 0
            });
        }
        return list;
    } catch (e) { return []; }
}

async function fetchFavResources(mediaId, page, ps) {
    try {
        var url = 'https://api.bilibili.com/x/v3/fav/resource/list'
            + '?media_id=' + mediaId
            + '&pn=' + (page || 1)
            + '&ps=' + (ps || 20)
            + '&platform=web&type=0';
        var data = await biliGet(url);
        if (!data || data.code !== 0) return { list: [], hasMore: false, total: 0 };
        var arr = (data.data && data.data.medias) || [];
        var hasMore = !!(data.data && data.data.has_more);
        var total = (data.data && data.data.info && data.data.info.media_count) || 0;
        var list = [];
        for (var i = 0; i < arr.length; i++) {
            var v = arr[i];
            var bvid = safeText(v.bvid);
            var aid = v.id || 0;
            if (!bvid && !aid) continue;
            var title = safeText(v.title);
            if (!title) continue;
            var pic = picFix(v.cover);
            var remark = fmtDuration(v.duration);
            var playCount = v.cnt_info && v.cnt_info.play || 0;
            if (playCount) {
                var w = playCount >= 10000 ? Math.round(playCount / 10000) + '万' : playCount;
                remark = remark ? (remark + ' · ' + w + '播放') : (w + '播放');
            }
            list.push({
                vod_id: packPlayId({ type: 'video', bvid: bvid, aid: aid }),
                vod_name: title.replace(/<[^>]+>/g, ''),
                vod_pic: pic,
                vod_remarks: remark,
                style: getListStyle()
            });
        }
        return { list: list, hasMore: hasMore, total: total };
    } catch (e) { return { list: [], hasMore: false, total: 0 }; }
}

/* ★★★ 历史记录：B站历史 API ★★★ */
async function fetchHistory(page, ps) {
    try {
        // 先看最大页数
        var cursor = '';
        if (page > 1) {
            // 从缓存拿每页游标
            var cacheKey = 'bili_hist_cursor_' + (page - 1);
            cursor = safeText(host.cache.get(cacheKey, ''));
        }
        var url = 'https://api.bilibili.com/x/web-interface/history/cursor'
            + '?ps=' + (ps || 30)
            + (cursor ? ('&max=' + cursor) : '');
        var data = await biliGet(url);
        if (!data || data.code !== 0) return { list: [], hasMore: false };
        var d = data.data || {};
        var arr = d.list || [];
        var list = [];
        for (var i = 0; i < arr.length; i++) {
            var h = arr[i];
            var bvid = safeText(h.history && h.history.bvid);
            var aid = h.history && h.history.oid || 0;
            if (!bvid && !aid) continue;
            var title = safeText(h.title);
            if (!title) continue;
            var pic = picFix(h.cover);
            var dur = h.duration || 0;
            var progress = h.progress || 0;
            var remark = '';
            if (progress > 0 && dur > 0) {
                remark = fmtDuration(progress) + ' / ' + fmtDuration(dur);
            } else if (dur > 0) {
                remark = fmtDuration(dur);
            }
            list.push({
                vod_id: packPlayId({ type: 'video', bvid: bvid, aid: aid }),
                vod_name: title.replace(/<[^>]+>/g, ''),
                vod_pic: pic,
                vod_remarks: remark,
                style: getListStyle()
            });
        }
        // 记录下一页游标
        var nextCursor = '';
        try {
            nextCursor = String(d.cursor && d.cursor.max || '');
            if (nextCursor) {
                host.cache.set('bili_hist_cursor_' + page, nextCursor);
            }
        } catch (e) {}
        return { list: list, hasMore: !!nextCursor };
    } catch (e) { return { list: [], hasMore: false }; }
}

/* ---------- DOM 解析（备用） ---------- */
function domVideoList(doc) {
    var list = [];
    var seen = {};
    if (!doc || !doc.querySelectorAll) return list;
    var links = doc.querySelectorAll('a[href*="/video/"]');
    for (var i = 0; i < links.length; i++) {
        var link = links[i];
        var href = String(link.getAttribute('href') || link.href || '');
        var bvid = extractBvid(href);
        var aid = extractAid(href);
        if (!bvid && !aid) continue;
        var key = bvid || ('av' + aid);
        if (seen[key]) continue;
        var title = safeText(link.getAttribute('title') || link.getAttribute('aria-label') || link.textContent);
        var image = link.querySelector ? link.querySelector('img') : null;
        var pic = image ? String(image.getAttribute('src') || image.src || '') : '';
        if (!title) title = 'B站视频 ' + key;
        seen[key] = true;
        list.push({
            vod_id: packPlayId({ type: 'video', bvid: bvid, aid: aid }),
            vod_name: title, vod_pic: picFix(pic), vod_remarks: '',
            style: { type: 'list' }
        });
    }
    return list;
}

/* ==================== WebView 大方法 ==================== */

async function homeContent(filter) {
    var classList = [{ type_id: MINE_TID, type_name: '我的' }].concat(visibleCategories());
    var filters = {};
    for (var i = 1; i < classList.length; i++) filters[classList[i].type_id] = COMMON_FILTERS;
    filters[MINE_TID] = [];
    return { class: classList, filters: filters };
}

async function homeVideoContent() {
    if (cfgRead().showRecommend === false) return { list: [] };
    try {
        var list = await recommendApi(1, 20);
        return { list: list };
    } catch (e) { return { list: [] }; }
}

function CATEGORY_INFO(id) {
    var categories = configuredCategories();
    for (var i = 0; i < categories.length; i++) {
        if (categories[i].type_id === id) return categories[i];
    }
    if (String(id).indexOf('custom:') === 0) {
        try { return { keyword: decodeURIComponent(String(id).split(':')[1]), tids: '' }; } catch (e) {}
    }
    return { keyword: id || '热门', tids: '' };
}

async function categoryContent(tid, pg, filter, extend) {
    var routeId = normalizeCrTid(tid);
    var page = parseInt(pg) || 1;
    var ext = extend || {};
    var result = { page: page, pagecount: page, limit: 0, total: 0, list: [] };

    /* 我的 */
    if (routeId === MINE_TID) {
        return { page: 1, pagecount: 1, limit: 0, total: 0, style: { type: 'list' }, list: mineMenu() };
    }

    /* ★ 历史记录：API */
    if (routeId === HISTORY_TID) {
        var hres = await fetchHistory(page, 30);
        result.list = applyCategoryStyle(hres.list, routeId);
        result.page = page;
        result.pagecount = hres.hasMore ? (page + 1) : page;
        result.limit = result.total = result.list.length;
        result.style = getListStyle();
        return result;
    }

    /* ★ 我的收藏：先展示收藏夹列表 */
    if (routeId === FAV_TID) {
        var folders = await fetchFavFolders();
        if (!folders.length) {
            result.list = [
                folderItem(FAV_TID, '未登录或没有收藏夹，请先登录', '')
            ];
            result.limit = result.total = result.list.length;
            return result;
        }
        var list = [];
        for (var fi = 0; fi < folders.length; fi++) {
            var f = folders[fi];
            list.push({
                vod_id: 'favcat:' + f.id,
                vod_name: f.title,
                vod_tag: 'folder',
                vod_pic: '',
                vod_remarks: f.media_count + ' 个视频',
                style: { type: 'list' }
            });
        }
        result.list = list;
        result.limit = result.total = result.list.length;
        return result;
    }

    /* ★ 收藏夹内容 */
    if (routeId.indexOf('favcat:') === 0) {
        var mediaId = routeId.slice(7);
        var fres = await fetchFavResources(mediaId, page, 20);
        result.list = applyCategoryStyle(fres.list, routeId);
        result.page = page;
        result.pagecount = fres.hasMore ? (page + 1) : page;
        result.limit = result.total = result.list.length;
        result.style = getListStyle();
        return result;
    }

    /* 常规分类 */
    try {
        var info = CATEGORY_INFO(routeId);
        var keyword = info.keyword || '热门';
        var tids = ext.tids || info.tids || '';
        var list2 = [];
        if (tids) {
            var regionList = await regionApi(tids, page, 30);
            if (regionList && regionList.length) list2 = regionList;
        }
        if (!list2.length) {
            var searchExt = { order: ext.order, duration: ext.duration, tids: tids };
            var sr = await searchApi(keyword, page, searchExt);
            list2 = sr.list || [];
            if (sr.numPages && page < sr.numPages) result.pagecount = page + 1;
        }
        if (!list2.length) list2 = await recommendApi(page, 30);
        result.list = applyCategoryStyle(list2, routeId);
        if (page >= result.pagecount && list2.length) result.pagecount = page + 1;
        result.style = getListStyle();
        result.limit = result.total = result.list.length;
    } catch (e) {
        try {
            var recList2 = await recommendApi(page, 30);
            result.list = applyCategoryStyle(recList2, routeId);
            result.limit = result.total = result.list.length;
        } catch (e2) {
            result.list = [];
            result.limit = result.total = 0;
        }
    }
    return result;
}

/* ==================== 详情：多线路 ==================== */
async function detailContent(ids) {
    var rawId = firstId(ids);
    var playData = unpackPlayId(rawId);
    var bvid = String(playData.bvid || '') || extractBvid(playData.url || rawId);
    var aid = String(playData.aid || '') || extractAid(playData.url || rawId);
    if (!bvid && !aid) return { list: [] };

    var info = await videoDetail(bvid, aid);
    if (!info) return { list: [] };
    bvid = info.bvid || bvid;
    aid = info.aid || aid;

    var out = {
        vod_id: packPlayId({ type: 'video', bvid: bvid, aid: aid }),
        vod_name: safeText(info.title) || 'B站视频',
        vod_pic: picFix(info.pic),
        vod_year: info.pubdate ? String(new Date(info.pubdate * 1000).getFullYear()) : '',
        vod_remarks: '', vod_content: safeText(info.desc), vod_actor: '',
        vod_play_from: '', vod_play_url: ''
    };
    var owner = info.owner || {};
    if (owner.name) out.vod_actor = owner.mid ? richLink(owner.name, 'channel:' + owner.mid) : safeText(owner.name);
    var stat = info.stat || {};
    var parts = [];
    if (stat.view) parts.push(stat.view >= 10000 ? Math.round(stat.view / 10000) + '万播放' : stat.view + '播放');
    if (stat.danmaku) parts.push(stat.danmaku + '弹幕');
    if (stat.like) parts.push(stat.like + '点赞');
    out.vod_remarks = parts.join(' · ');

    var pages = info.pages || [];
    var mainParts = [];
    if (pages.length > 1) {
        for (var i = 0; i < pages.length; i++) {
            var p = pages[i];
            mainParts.push({
                name: cleanPlayName('P' + p.page + ' ' + p.part, '第' + (i + 1) + '集'),
                id: packPlayId({ type: 'video', bvid: bvid, aid: aid, cid: p.cid, p: p.page })
            });
        }
    } else if (pages.length === 1) {
        mainParts.push({
            name: cleanPlayName(info.title, '正片'),
            id: packPlayId({ type: 'video', bvid: bvid, aid: aid, cid: pages[0].cid, p: 1 })
        });
    } else {
        mainParts.push({
            name: cleanPlayName(info.title, '正片'),
            id: packPlayId({ type: 'video', bvid: bvid, aid: aid, cid: info.cid })
        });
    }

    var lineNames = [];
    var lineUrls = [];

    if (isLineEnabled('main')) {
        lineNames.push('正片');
        lineUrls.push(buildPlayUrl(mainParts));
    }

    if (isLineEnabled('upmore') && owner.mid) {
        try {
            var upList = await upMoreVideos(owner.mid, 1, 50);
            if (upList.length) {
                var upParts = [];
                for (var ui = 0; ui < upList.length; ui++) {
                    upParts.push({
                        name: cleanPlayName(upList[ui].vod_name, '第' + (ui + 1) + '集'),
                        id: upList[ui].vod_id
                    });
                }
                lineNames.push('UP主更多(' + safeText(owner.name) + ')');
                lineUrls.push(buildPlayUrl(upParts));
            }
        } catch (eUp) {}
    }

    if (isLineEnabled('related')) {
        try {
            var relList = await relatedVideos(bvid, aid);
            relList = relList.filter(function (item) {
                var d = unpackPlayId(item.vod_id);
                return d.bvid !== bvid && String(d.aid) !== String(aid);
            });
            if (relList.length) {
                var relParts = [];
                for (var ri = 0; ri < relList.length; ri++) {
                    relParts.push({
                        name: cleanPlayName(relList[ri].vod_name, '第' + (ri + 1) + '集'),
                        id: relList[ri].vod_id
                    });
                }
                lineNames.push('相关推荐');
                lineUrls.push(buildPlayUrl(relParts));
            }
        } catch (eRel) {}
    }

    if (isLineEnabled('region') && info.tid) {
        try {
            var regionList = await regionApi(String(info.tid), 1, 40);
            if (regionList.length) {
                var regParts = [];
                for (var gi = 0; gi < regionList.length; gi++) {
                    regParts.push({
                        name: cleanPlayName(regionList[gi].vod_name, '第' + (gi + 1) + '集'),
                        id: regionList[gi].vod_id
                    });
                }
                lineNames.push('同分区(' + safeText(info.tname || '') + ')');
                lineUrls.push(buildPlayUrl(regParts));
            }
        } catch (eReg) {}
    }

    if (isLineEnabled('search')) {
        try {
            var kwTitle = safeText(info.title).replace(/[【】\[\]（）()《》""''!！?？,，.。:：;；\-_|/\\]/g, ' ').trim();
            var kw = kwTitle.split(/\s+/)[0] || kwTitle.slice(0, 12);
            if (kw) {
                var sr = await searchApi(kw, 1, {});
                if (sr.list && sr.list.length) {
                    var srParts = [];
                    for (var si = 0; si < sr.list.length; si++) {
                        var sv = sr.list[si];
                        var d = unpackPlayId(sv.vod_id);
                        if (d.bvid === bvid) continue;
                        srParts.push({
                            name: cleanPlayName(sv.vod_name, '第' + (si + 1) + '集'),
                            id: sv.vod_id
                        });
                    }
                    if (srParts.length) {
                        lineNames.push('搜索相关');
                        lineUrls.push(buildPlayUrl(srParts));
                    }
                }
            }
        } catch (eSearch) {}
    }

    if (!lineNames.length) {
        lineNames.push('正片');
        lineUrls.push(buildPlayUrl(mainParts));
    }

    out.vod_play_from = lineNames.join('$$$');
    out.vod_play_url = lineUrls.join('$$$');
    return { list: [out] };
}

function buildPlayUrl(parts) {
    var arr = [];
    for (var i = 0; i < parts.length; i++) {
        var n = String(parts[i].name || '').replace(/[$#]/g, ' ');
        arr.push(n + '$' + parts[i].id);
    }
    return arr.join('#');
}

async function recommendContent(ids, pg) {
    if (cfgRead().showRecommend === false) return { list: [] };
    var currentId = firstId(ids);
    var page = Math.max(1, parseInt(pg, 10) || 1);
    var data = unpackPlayId(currentId);
    var bvid = data.bvid || extractBvid(data.url || currentId);
    var aid = data.aid || extractAid(data.url || currentId);
    if (!bvid && !aid) return { list: [] };
    try {
        var list = await relatedVideos(bvid, aid);
        list = list.filter(function (item) {
            var d = unpackPlayId(item.vod_id);
            return d.bvid !== bvid && String(d.aid) !== String(aid);
        });
        var result = { list: list };
        if (page === 1 && list.length > 0) { result.page = page; result.pagecount = page + 1; }
        return result;
    } catch (e) { return { list: [] }; }
}

async function searchContent(key, quick, pg) {
    var page = parseInt(pg) || 1;
    var keyword = safeText(key || '');
    var result = { page: page, pagecount: page, limit: 0, total: 0, list: [] };
    if (!keyword) return result;
    try {
        var info = await searchApi(keyword, page, {});
        result.list = info.list || [];
        if (info.numPages && page < info.numPages) result.pagecount = page + 1;
        result.limit = result.total = result.list.length;
    } catch (e) {
        result.list = []; result.limit = result.total = 0;
    }
    return result;
}

/* ==================== 播放 ==================== */
async function playerContent(flag, id, vipFlags) {
    var raw = firstId(id);
    var data = unpackPlayId(raw);
    var bvid = data.bvid || extractBvid(data.url || raw);
    var aid = data.aid || extractAid(data.url || raw);
    if (!bvid && !aid) return {};

    var qs = [];
    if (bvid) qs.push('bvid=' + bvid); else qs.push('aid=' + aid);
    if (data.cid) qs.push('cid=' + data.cid);
    if (data.p) qs.push('p=' + data.p);
    qs.push('autoplay=1'); qs.push('danmaku=0'); qs.push('high_quality=1'); qs.push('as_wide=1');
    var url = wvPlayerUrl + '?' + qs.join('&');

    return {
        type: 'wvplayer',
        url: url,
        headers: {
            'User-Agent': DESKTOP_UA, 'Referer': 'https://www.bilibili.com/',
            'Origin': 'https://www.bilibili.com', 'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Sec-Fetch-Dest': 'iframe', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'same-origin'
        },
        playerSelector: 'body',
        selectors: ['#bilibili-player video', '.bpx-player-video-wrap video', 'video'],
        click: "(function(){var n=0;var t=setInterval(function(){"
            + "var v=document.querySelector('#bilibili-player video')||document.querySelector('.bpx-player-video-wrap video')||document.querySelector('video');"
            + "if(v&&v.videoWidth>0&&v.readyState>=2&&!v.paused){clearInterval(t);return;}"
            + "var b=document.querySelector('.bpx-player-ctrl-play,.bilibili-player-video-btn-start,.bpx-player-primary-area .bpx-player-ctrl-btn');"
            + "if(b)b.click();"
            + "if(v&&v.paused)v.play();"
            + "if(++n>=12)clearInterval(t);},1500);})();",
        script: "(function(){"
            + "var css='body,html{overflow:hidden!important;background:#000!important;margin:0!important;padding:0!important}"
            + ".bpx-player-top-wrap,.bilibili-player-video-top,.bpx-player-top-mask{display:none!important}"
            + ".bpx-player-dm-wrap,.bilibili-player-video-danmaku,.bpx-player-row-dm-wrap,.bpx-player-dm-switch{display:none!important}"
            + ".bpx-player-logo,.bilibili-player-logo,.bpx-player-ctrl-logo{display:none!important}"
            + ".bpx-player-ending-wrap,.bpx-player-elec-wrap,.bpx-player-recommend-wrap,.bilibili-player-video-btn-setting-right,.bpx-player-recommend{display:none!important}"
            + ".bpx-player-ctrl-btn.bpx-player-ctrl-like,.bpx-player-ctrl-btn.bpx-player-ctrl-coin,.bpx-player-ctrl-btn.bpx-player-ctrl-fav,.bpx-player-ctrl-btn.bpx-player-ctrl-share{display:none!important}"
            + ".bpx-player-ctrl-volume,.bilibili-player-video-btn-volume{display:none!important}"
            + ".bpx-player-ctrl-btn.bpx-player-ctrl-quality,.bpx-player-ctrl-btn.bpx-player-ctrl-playbackrate,.bpx-player-ctrl-btn.bpx-player-ctrl-subtitle,.bpx-player-ctrl-btn.bpx-player-ctrl-full{display:none!important}"
            + ".bpx-player-dm-input-wrap,.bpx-player-dm-input{display:none!important}"
            + ".bpx-player-toast-wrap,.bpx-player-tooltip{display:none!important}"
            + ".bpx-player-ctrl-setting{transform:translateY(36px)!important;z-index:2147483647!important}"
            + ".bilibili-player-video-btn-setting{transform:translateY(36px)!important;z-index:2147483647!important}';"
            + "var old=document.getElementById('ys-bili-wv-style');"
            + "if(old)old.remove();"
            + "var st=document.createElement('style');st.id='ys-bili-wv-style';st.textContent=css;"
            + "(document.head||document.documentElement).appendChild(st);"
            + "function hideExtraControls(){"
            + "var fixed=['.bpx-player-top-wrap','.bilibili-player-video-top','.bpx-player-top-mask','.bpx-player-dm-wrap','.bilibili-player-video-danmaku','.bpx-player-row-dm-wrap','.bpx-player-dm-switch','.bpx-player-logo','.bilibili-player-logo','.bpx-player-ctrl-logo','.bpx-player-ending-wrap','.bpx-player-elec-wrap','.bpx-player-recommend-wrap','.bpx-player-recommend','.bpx-player-ctrl-volume','.bilibili-player-video-btn-volume','.bpx-player-dm-input-wrap','.bpx-player-dm-input','.bpx-player-toast-wrap','.bpx-player-tooltip'];"
            + "for(var i=0;i<fixed.length;i++){var xs=document.querySelectorAll(fixed[i]);for(var j=0;j<xs.length;j++)xs[j].style.setProperty('display','none','important');}"
            + "var bs=document.querySelectorAll('button,[role=\"button\"],.bpx-player-ctrl-btn');"
            + "for(var k=0;k<bs.length;k++){var b=bs[k];var label=((b.getAttribute('aria-label')||'')+' '+(b.getAttribute('title')||'')+' '+(b.textContent||'')).replace(/\\s+/g,' ').trim();"
            + "if(label.length<=32&&/(点赞|收藏|投币|分享|画质|倍速|字幕|全屏|音量|静音|取消静音|弹幕)/.test(label)&&!/(设置|setting)/i.test(label)){b.style.setProperty('display','none','important');}}"
            + "}"
            + "hideExtraControls();"
            + "window.__ysHideBiliExtraControls=hideExtraControls;"
            + "})();"
            + "(function(){var n=0;var t=setInterval(function(){"
            + "if(window.__ysHideBiliExtraControls)window.__ysHideBiliExtraControls();"
            + "var xs=document.querySelectorAll('.bpx-player-top-wrap,.bpx-player-dm-wrap,.bpx-player-logo,.bpx-player-recommend-wrap,.bpx-player-ctrl-volume,.bpx-player-ctrl-btn');for(var xi=0;xi<xs.length;xi++){var el=xs[xi];var lab=((el.getAttribute('aria-label')||'')+' '+(el.getAttribute('title')||'')+' '+(el.textContent||'')).replace(/\\s+/g,' ').trim();if(lab.length<=32&&/(点赞|收藏|投币|分享|画质|倍速|字幕|全屏|音量|静音|取消静音|弹幕)/.test(lab)&&!/(设置|setting)/i.test(lab))el.style.setProperty('display','none','important');}"
            + "var v=document.querySelector('#bilibili-player video')||document.querySelector('.bpx-player-video-wrap video')||document.querySelector('video');"
            + "if(v&&v.muted){v.muted=false;if(v.volume===0)v.volume=1;}"
            + "var muteBtn=document.querySelector('.bpx-player-ctrl-volume,.bilibili-player-video-btn-volume,[aria-label=\"静音\"]');"
            + "if(muteBtn&&v&&v.muted)muteBtn.click();"
            + "if(v&&v.videoWidth>0&&v.readyState>=2&&v.paused){v.play();}"
            + "if(v&&!v.paused&&!v.muted){clearInterval(t);return;}"
            + "if(++n>=30)clearInterval(t);},1000);})();",
        timeout: 60
    };
}