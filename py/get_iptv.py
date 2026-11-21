import re
import os
import json
import time
import unicodedata
import requests
import logging
import shutil
import threading
from collections import OrderedDict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from logging.handlers import RotatingFileHandler

# ============================================================================
# 路径解析(修复回归): C2 曾把所有路径锚定到脚本所在目录，但两种部署布局下
# 脚本位置不同，拼接结果不同:
#   布局A(本工作区): <根>/get_iptv.py          -> 配置/输出期望在 <根>/py/config 与 <根>/lib
#   布局B(tvbox CI): <根>/py/get_iptv.py       -> 期望仍在 <根>/py/config 与 <根>/lib
# C2 的 BASE_DIR=dirname(__file__) 在布局B下等于 <根>/py，再拼 "py/config"
# 产生 <根>/py/py/config(错误，即 CI 日志中的重复 py/py 段)。
# 修复: 自动探测候选目录，取第一个真实存在者；都不存在时回退布局A基准。
# ============================================================================
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _resolve_first_dir(candidates, fallback):
    """返回第一个真实存在的候选目录；都不存在时返回 fallback(便于日志定位)。"""
    for c in candidates:
        if os.path.isdir(c):
            return c
    return fallback

CONFIG_DIR = _resolve_first_dir(
    (
        os.path.join(_SCRIPT_DIR, "py", "config"),          # 布局A/B 共用
        os.path.join(_SCRIPT_DIR, "config"),                # 布局C: 配置与脚本同目录
    ),
    os.path.join(_SCRIPT_DIR, "py", "config"),
)

LIB_DIR = _resolve_first_dir(
    (
        os.path.join(_SCRIPT_DIR, "lib"),                   # 布局A: 输出在脚本根下
        os.path.join(os.path.dirname(_SCRIPT_DIR), "lib"),  # 布局B: 输出在仓库根下
    ),
    os.path.join(_SCRIPT_DIR, "lib"),
)

# === 配置日志 ===
def setup_logger():
    # 日志目录统一放 config 下，与源状态/报告同级，避免依赖"当前工作目录"
    log_dir = os.path.join(CONFIG_DIR, "logs")
    # 确保日志目录存在
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.handlers.clear() # 清除已有 handler 避免重复
    
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # 控制台输出
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件输出(轮转: 单文件 10MB, 保留 3 个备份, 防止长期运行无限膨胀)
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "iptv_update.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()

# 全局锁，用于文件写入
write_lock = threading.Lock()

def ensure_dir(file_path):
    """确保文件所在的目录存在"""
    dirname = os.path.dirname(file_path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)

_DASH_VARIANTS_RE = re.compile(r'[－—﹣–─]')
_MULTI_SPACE_RE = re.compile(r'\s+')

def normalize_channel_name(name):
    """
    频道名称归一化，用于匹配前的预处理（不用于最终显示名）：
    - 全角字符转半角（如 ＣＣＴＶ１ -> CCTV1）
    - 统一各类破折号/连字符为标准 "-"
    - 合并连续空白并去除首尾空格
    """
    if not name:
        return ""
    name = unicodedata.normalize('NFKC', name)
    name = _DASH_VARIANTS_RE.sub('-', name)
    name = _MULTI_SPACE_RE.sub(' ', name).strip()
    return name

# ============================================================================
# 与 normalize_channel_name 职责不同:
#   normalize_channel_name -> 供"匹配"用，尽量保留信息、只做等价归一
#   sanitize_channel_name  -> 供"显示 / tvg-id / Logo 文件名"用，做激进清洗
# 强化点(相对网页版): 前置 NFKC，使 ＣＣＴＶ１ 这类全角输入也能正确识别为 CCTV1。
# ============================================================================
# 强化(相对网页版 sanitizeName):
#  1) CCTV 与序号间容忍空白/连字符(CCTV-13 / CCTV 13 也能归一为 CCTV13)
#  2) 括号成对/孤立集合扩全(补齐 NFKC 后的半角 () {}，以及 CJK 角括号「」『』)
_CCTV_RE = re.compile(r'^CCTV[\s\-]*(\d+)\s*([+K]?)', re.IGNORECASE)
_HD_RE = re.compile(r'超清|超高清|极清|高清|标清|HD|SD', re.IGNORECASE)
_BRACKET_PAIR_RE = re.compile(r'[\[\(（【｛\{<＜「『].*?[\]\)）】｝\}>＞」』]')
_BRACKET_SOLO_RE = re.compile(r'[\[\]\(\)（）【】｛｝\{\}<>＜＞「」『』]')
_DASH_UNDERSCORE_RE = re.compile(r'[-_]')

def sanitize_channel_name(name):
    """频道名净化: CCTV 归一化 / 去清晰度后缀 / 去括号 / 去连字符下划线。"""
    if not name:
        return ""
    # 强化: 先做全角->半角等价折叠 + 破折号变体归一，
    # 兼容 ＣＣＴＶ１ / ＨＤ / CCTV－13 等写法
    name = unicodedata.normalize('NFKC', name)
    name = _DASH_VARIANTS_RE.sub('-', name)

    # CCTV 系列特殊处理
    m = _CCTV_RE.match(name)
    if m:
        num = m.group(1)
        suffix = (m.group(2) or '')
        if num == '5' and suffix == '+':
            return 'CCTV5+'
        if num in ('4', '8') and suffix.upper() == 'K':
            return 'CCTV' + num + 'K'
        return 'CCTV' + num

    clean = name
    # 强化(顺序修正): 先去掉成对括号及其内容，再剥离清晰度后缀。
    # 网页版先按 HD 截断再删括号，会把 "台名(HD)" 从括号中间截断而残留孤立 "("。
    clean = _BRACKET_PAIR_RE.sub('', clean)

    # 去掉"超清/超高清/极清/高清/标清/HD/SD"及其后所有内容
    hd = _HD_RE.search(clean)
    if hd:
        clean = clean[:hd.start()]

    # 再次清除残留的孤立括号符号(含半角 () {} 与角括号)
    clean = _BRACKET_SOLO_RE.sub('', clean)
    # 去掉短横线 / 下划线，并去除首尾空白
    clean = _DASH_UNDERSCORE_RE.sub('', clean).strip()
    return clean

def get_session():
    """创建一个带有重试机制的requests Session"""
    session = requests.Session()
    # 增强: 增加 total 上限，并对常见的服务端临时错误状态码也进行重试
    retry = Retry(
        total=3,
        connect=3,
        read=2,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    # 增强: 部分源站会拒绝无 User-Agent 的请求，补充常见浏览器 UA 提升成功率
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    })
    return session

def load_urls_from_file(file_path):
    """从文本文件加载URL列表"""
    urls = []
    if not os.path.exists(file_path):
        logger.warning(f"URL配置文件未找到: {file_path}")
        return urls

    try:
        # 使用 utf-8-sig 安全过滤由于记事本编辑可能产生的 \ufeff BOM 头
        with open(file_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
        logger.info(f"从 {file_path} 加载了 {len(urls)} 个源")
    except Exception as e:
        logger.error(f"读取URL文件失败: {e}")
    return urls

def parse_template(template_file):
    """解析模板文件"""
    template_channels = OrderedDict()
    current_category = None

    try:
        # 使用 utf-8-sig 避免首行解析出错
        with open(template_file, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if "#genre#" in line:
                    current_category = line.split(",")[0].strip()
                    # 修复: 若同一分类在模板中重复出现，不应清空之前已收集的频道
                    if current_category not in template_channels:
                        template_channels[current_category] = []
                elif current_category:
                    channel_name = line.split(",")[0].strip()
                    # 修复(崩溃预防): 跳过空白频道名，避免后续 match_channels 中
                    # variants 列表为空导致 IndexError
                    if channel_name:
                        template_channels[current_category].append(channel_name)
    except FileNotFoundError:
        logger.warning(f"模板文件未找到: {template_file}")
        return None 

    return template_channels

def fetch_channels(url):
    """从URL获取频道列表"""
    channels = OrderedDict()

    # 使用上下文管理器确保 socket 资源正确释放
    with get_session() as session:
        try:
            # 增强: 拆分连接/读取超时，连接更快失败，读取给足时间
            with session.get(url, timeout=(10, 30)) as response:
                response.raise_for_status()
                raw_bytes = response.content

        except Exception as e:
            logger.error(f"处理 {url} 时出错: {e}")
            return channels

    # 防护(伪源/空响应): 部分"直播源"实际只是占位文件(如 logo.png 返回空或极小内容)，
    # 内容量不足以承载任何频道。此类响应直接判定为无效源：
    # - 不计入成功数
    # - 不进入待匹配数据
    # 优化: 128B 仅作快速预筛(真正的判定在解析后按"频道数==0"进行)，
    # 避免把合法的小体积 txt 源(几个频道)误杀，也避免放行 1KB 的 HTML 错误页
    MIN_VALID_BODY_BYTES = 128
    if len(raw_bytes) < MIN_VALID_BODY_BYTES:
        logger.warning(f"源 {url} 响应内容过小({len(raw_bytes)}B < {MIN_VALID_BODY_BYTES}B)，"
                       f"判定为伪源/空源，忽略")
        return channels

    # 修复(编码): 国内 IPTV 源大量使用 GBK/GB2312 编码，直接强制 utf-8 会导致乱码。
    # 跳过缓慢的 chardet(apparent_encoding) 探测，改用 utf-8 优先、
    # gb18030 兜底(GBK/GB2312 完整超集，覆盖全部生僻字/扩展区，几乎不再误丢字)。
    try:
        text_content = raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        try:
            text_content = raw_bytes.decode('gb18030')
        except UnicodeDecodeError:
            text_content = raw_bytes.decode('utf-8', errors='ignore')

    lines = [line.strip() for line in text_content.splitlines() if line.strip()]
    if not lines:
        return channels

    # 修复(健壮性): 部分 M3U 源在 #EXTINF 之前有较多头部/注释行，仅扫描前10行可能误判为 txt 格式；
    # 优先判断标准 #EXTM3U 头，并放宽扫描窗口
    is_m3u = lines[0].strip().upper().startswith("#EXTM3U") or any(
        "#EXTINF" in line for line in lines[:30]
    )

    if is_m3u:
        DEFAULT_CATEGORY = "默认分类"
        DEFAULT_NAME = "未知频道"
        current_category = DEFAULT_CATEGORY
        current_name = DEFAULT_NAME

        re_group = re.compile(r'group-title="([^"]*)"')
        # 强化正则: 优先取最后一个带引号属性之后的逗号分隔内容，兼容频道名本身含逗号的情况；
        # 若没有任何带引号属性，则回退为 EXTINF: 后第一个逗号之后的内容
        re_name_after_quote = re.compile(r'"\s*,(.*)$')
        re_name_fallback = re.compile(r'#EXTINF:[^,]*,(.*)$')

        for line in lines:
            if line.startswith("#EXTINF"):
                # 修复(分类状态重置): 每条 EXTINF 若未显式声明 group-title，
                # 不应继续沿用上一条频道残留的分类，而应重置为默认分类
                group_match = re_group.search(line)
                current_category = group_match.group(1).strip() if group_match else DEFAULT_CATEGORY

                name_match = re_name_after_quote.search(line) or re_name_fallback.search(line)
                # 修复(状态重置): 未匹配到名称时重置为默认值，避免沿用上一条频道的名称
                current_name = name_match.group(1).strip() if name_match else DEFAULT_NAME
            elif not line.startswith("#") and "://" in line:
                if current_category not in channels:
                    channels[current_category] = []
                if current_name and current_name != DEFAULT_NAME:
                    channels[current_category].append((current_name, line))
                current_name = DEFAULT_NAME
    else:
        current_category = None
        for line in lines:
            if "#genre#" in line:
                current_category = line.split(",")[0].strip()
                if current_category not in channels:
                    channels[current_category] = []
            # 修复: 分类名为空字符串时属于合法但异常的边界情况，用 is not None 判断
            # 避免因空字符串的假值特性而错误丢弃整段内容
            elif current_category is not None and "," in line:
                parts = line.split(",", 1)
                if len(parts) == 2:
                    name, url_part = parts
                    if name.strip() and url_part.strip():
                        channels[current_category].append((name.strip(), url_part.strip()))

    # 真正的伪源判定(优化②): 解析完成后仍无任何频道 -> 该响应不承载有效数据
    # (如 1KB 的 HTML 错误页、只有头部注释的占位文件)，按无效源处理，
    # 不计入成功数
    if not channels:
        logger.warning(f"源 {url} 解析后频道数为 0，判定为伪源/空源，忽略")
        return OrderedDict()

    return channels

def fetch_all_channels(tv_urls, max_workers=5, overall_timeout=120):
    """
    增强(性能): 将并发抓取聚合逻辑抽出为独立函数。
    原先每个 process_iptv_task 都会各自抓取一遍相同的源，重复请求；
    抽出后可在主流程中"抓取一次、多任务复用"。
    返回聚合后的 all_channels (OrderedDict: 分类 -> [(name, url), ...])。

    增强(整体超时): 单源有 (10, 30) 超时，但 N 个源并发仍可能被最慢的源
    拖到 N*30s。增加 overall_timeout 整体上限(默认120s)，超时后直接跳过
    未完成任务的"结果处理"，保证主流程有确定的时长(适配 GitHub Actions 的
    timeout-minutes 限制)。

    注意: ThreadPoolExecutor 的 with 退出是 shutdown(wait=True)，会等待
    所有线程自然结束；已启动的线程无法被 cancel 中断。因此整体超时实际保证
    "主流程最多等待 overall_timeout 内的结果"，总执行时长上限约为
    overall_timeout + 单源读超时(30s) + 少量收尾。本脚本单源有 (10,30)
    硬超时，实际最坏总时长仍在 Actions 15 分钟限制内。
    """
    all_channels = OrderedDict()
    timeout_count = 0     # 整体超时被强制跳过
    success_count = 0     # 抓取且解析出频道 -> 真正成功
    invalid_count = 0     # 伪源/空源/异常(解析结果为空) -> 不计入成功

    # 修复(C3): 旧实现用 with ThreadPoolExecutor(...)，其 __exit__ 等价于
    # shutdown(wait=True)，整体超时后正在抓取的线程仍会被 join，主流程实际
    # 最长在 overall_timeout 之后再阻塞约 90s(3 次连接重试×10s + 2 次读重试×30s)。
    # 改为显式实例 + 超时分支 shutdown(wait=False, cancel_futures=True)，
    # 立即返回已抓结果；未完成线程失去引用后随进程退出终止，不泄漏资源。
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        future_to_url = {executor.submit(fetch_channels, url): url for url in tv_urls}
        deadline = time.monotonic() + overall_timeout
        try:
            for future in as_completed(future_to_url, timeout=overall_timeout):
                url = future_to_url[future]

                try:
                    # 剩余时间不足时抛 TimeoutError，由外层 as_completed 继续
                    data = future.result(timeout=max(0.0, deadline - time.monotonic()))
                except FuturesTimeoutError:
                    # 未在整体时限内完成: 跳过，不再等待
                    timeout_count += 1
                    logger.warning(f"源 {url} 超过整体时限({overall_timeout}s)，跳过")
                    continue
                except Exception as e:
                    data = None
                    logger.error(f"源 {url} 异常: {e}")

                if data:
                    success_count += 1
                    for cat, chans in data.items():
                        if cat not in all_channels:
                            all_channels[cat] = []
                        all_channels[cat].extend(chans)
                else:
                    # 修复(计数失真): 空数据=伪源(解析出0频道)或抓取/解析异常，
                    # 旧日志把它们全部记作"成功"，高可用性被虚报
                    invalid_count += 1

            # 正常完成: 等待所有已提交任务收尾(语义与原 with 版本一致)
            executor.shutdown(wait=True)
            return _finalize_fetch_log(
                all_channels, success_count, invalid_count, timeout_count, tv_urls)

        # 整体超时: as_completed 到点抛 TimeoutError；未完成任务全部计入超时。
        # cancel_futures 会清掉排队中未启动的任务；已在运行的线程无法被中断，
        # 但不再 join，主流程立即收尾，总时长上限回归 overall_timeout 本身。
        except FuturesTimeoutError:
            pending = [f for f in future_to_url if not f.done()]
            for f in pending:
                url = future_to_url[f]
                timeout_count += 1
                logger.warning(f"源 {url} 未在整体时限({overall_timeout}s)内完成，跳过")
            logger.warning(
                f"整体抓取超过时限 {overall_timeout}s，剩余 {len(pending)} 个源被跳过"
            )
            executor.shutdown(wait=False, cancel_futures=True)
        except BaseException:
            # 其余异常(如外部 KeyboardInterrupt)同样不再无限 join
            executor.shutdown(wait=False, cancel_futures=True)
            raise

    except BaseException:
        # submit 阶段异常兜底(如 tv_urls 非可迭代等)，同样不无限 join
        executor.shutdown(wait=False, cancel_futures=True)
        raise

    return _finalize_fetch_log(
        all_channels, success_count, invalid_count, timeout_count, tv_urls)

def _finalize_fetch_log(all_channels, success_count, invalid_count,
                        timeout_count, tv_urls):
    """汇总抓取结果日志(成功/伪源/超时分类)，返回聚合数据。"""
    total = len(tv_urls)
    logger.info(
        f"数据获取完毕: 成功 {success_count} 个(解析出频道)，"
        f"伪源/空源/异常 {invalid_count} 个，"
        f"整体超时跳过 {timeout_count} 个"
        f"(总计 {total}，核对: {success_count + invalid_count + timeout_count})"
    )
    return all_channels

def parse_template_variants(tmpl_name):
    """拆分模板行的变体列表(保护 re: 段: 行内 |re: 之后全部归正则变体)。"""
    if tmpl_name.lower().startswith("re:"):
        variants_raw = [tmpl_name.strip()]
    elif "|re:" in tmpl_name:
        re_idx = tmpl_name.index("|re:")
        variants_raw = [n.strip() for n in tmpl_name[:re_idx].split("|") if n.strip()]
        variants_raw.append(tmpl_name[re_idx + 1:].strip())  # 保留 "re:..."
    else:
        variants_raw = [n.strip() for n in tmpl_name.split("|") if n.strip()]
    return list(OrderedDict.fromkeys(variants_raw))


def literal_variant_patterns(variant):
    """
    返回字面变体对应的"匹配键"列表(0-2 个):
      [0] = 归一化名(norm)匹配键
      [1] = 净化名(san)匹配键(去连字符/HD 等, 与 norm 不同时才返回)
    与原实现的 pattern / pattern_san 两条搜索完全对应。
    """
    variant_lower = normalize_channel_name(variant).lower()
    if not variant_lower:
        return ()
    variant_san = normalize_channel_name(sanitize_channel_name(variant)).lower()
    if variant_san and variant_san != variant_lower:
        return (variant_lower, variant_san)
    return (variant_lower,)


def match_channels(template_channels, all_channels):
    matched = OrderedDict()
    unmatched_template = OrderedDict()

    # 1. 数据扁平化
    flattened_source_channels = []
    for cat, chans in all_channels.items():
        for name, url in chans:
            flattened_source_channels.append({
                # 增强(频道名归一化): 匹配前统一全角/半角、破折号变体、多余空白，
                # 提升如 ＣＣＴＶ１ / CCTV－1 / CCTV 1 等变体的识别率
                'norm_name': normalize_channel_name(name).lower(),
                # 增强(净化名兜底): sanitize 会把 CCTV-1 综合 -> CCTV1、去 HD 后缀等，
                # 供匹配时做第二遍兜底，解决"CCTV-1"式源名匹配不到模板"CCTV1"的缺口
                'san_name': normalize_channel_name(sanitize_channel_name(name)).lower(),
                'name': name,
                'url': url,
                'cat': cat,
                'key': f"{name}_{url}",
                # 优化①: 扁平化顺序号，用于索引候选合并后还原原扫描顺序
                'order': len(flattened_source_channels),
            })

    # 优化①: 字典树多模式匹配。
    # 将所有模板字面变体的匹配键(norm 键 + san 键)插入同一棵树，
    # 一次扫描所有源名(norm_name / san_name)，按原边界语义
    # (^|非字母数字 起、$|非字母数字非+ 止)判定命中；
    # 结果按 (源序号, 模板行序, 变体序, 键序) 存入 hits，
    # 随后按同序贪心消费 -> 与原实现"按扁平化顺序扫、命中即取"完全一致。
    trie = {}   # 字符 -> 子节点; 叶子带 {"variants": [(行序, 变体序, 键序)], "tail": bool}

    def _trie_insert(word, tag):
        node = trie
        for ch in word:
            node = node.setdefault(ch, {})
        node.setdefault("_v", []).append(tag)

    template_rows = []   # (分类, 模板行名, variants, re_specs)
    re_specs = []        # (行序, 变体序, pattern)  单独编译, 保持全表扫描
    for category, tmpl_names in template_channels.items():
        for tmpl_name in tmpl_names:
            row_idx = len(template_rows)
            variants = parse_template_variants(tmpl_name)
            if not variants:
                continue
            specs = []
            for v_idx, variant in enumerate(variants):
                if variant.lower().startswith("re:"):
                    regex_expr = variant[len("re:"):].strip()
                    if not regex_expr:
                        continue
                    try:
                        pat = re.compile(regex_expr, re.IGNORECASE)
                    except re.error as e:
                        logger.warning(f"模板正则变体无效, 已跳过: {variant} -> {e}")
                        continue
                    specs.append((v_idx, pat))
                    re_specs.append((row_idx, v_idx, pat))
                else:
                    for k_idx, word in enumerate(literal_variant_patterns(variant)):
                        _trie_insert(word, (row_idx, v_idx, k_idx))
            template_rows.append((category, tmpl_name, variants, specs))
        # end for tmpl_names
    # end for categories

    def _trie_scan(text):
        """扫描单个源名, 返回命中的 (行序, 变体序, 键序) 列表; 严格复刻原边界语义。
        注意: 沿途每个深度都要检查(短词是长词前缀时两者都可能命中)，
        不能在遇到首个 _v 时停止下降。"""
        if not text:
            return []
        out = []
        n = len(text)
        for start in range(n):
            # 开头边界: 字符串起始, 或前一字符非 [a-z0-9]
            # (源名已 lower: 用 isalnum+isascii 等价于 [a-z0-9]，CJK 等非 ascii 视为边界)
            if start > 0 and (text[start - 1].isalnum()
                              and text[start - 1].isascii()):
                continue
            node = trie.get(text[start])
            if node is None:
                continue
            end = start + 1   # node 覆盖 text[start:end]
            while True:
                if "_v" in node:
                    # 结尾边界: 字符串末尾, 或下一字符非 [a-z0-9+]
                    if end >= n:
                        out.extend(node["_v"])
                    else:
                        nx = text[end]
                        if not ((nx.isalnum() and nx.isascii()) or nx == '+'):
                            out.extend(node["_v"])
                if end >= n:
                    break
                nxt = node.get(text[end])
                if nxt is None:
                    break
                node = nxt
                end += 1
        return out

    # 字面命中 + re: 正则命中 统一收集为 (源序, 行序, 变体序, 键序)
    # 键序: 0=归一化名扫描, 1=净化名扫描(对应原 pattern 先、pattern_san 后)
    hits_set = set()
    for src in flattened_source_channels:
        so = src['order']
        for row_idx, v_idx, k_idx in _trie_scan(src['norm_name']):
            hits_set.add((so, row_idx, v_idx, k_idx))
        san = src['san_name']
        if san != src['norm_name']:
            for row_idx, v_idx, k_idx in _trie_scan(san):
                hits_set.add((so, row_idx, v_idx, k_idx))
        # re: 正则变体(全表扫描, 数量占比极低)
        for row_idx, v_idx, pat in re_specs:
            if pat.search(src['norm_name']):
                hits_set.add((so, row_idx, v_idx, 0))
            elif san != src['norm_name'] and pat.search(san):
                hits_set.add((so, row_idx, v_idx, 1))

    # 消费顺序 = 原实现顺序: 按 模板行 -> 变体 -> 源序 (键序仅用于去重,
    # 原实现对同一变体按源顺序消费, 键 norm/san 在同一 if 中取或)
    hits = sorted(hits_set, key=lambda h: (h[1], h[2], h[0], h[3]))

    used_channel_keys = set()

    # 初始化
    for cat in template_channels:
        matched[cat] = OrderedDict()
        unmatched_template[cat] = []

    # 2. 匹配消费(优化①): 按预排序 hits 贪心消费，语义与原"行->变体->源序"
    # 顺序扫描完全一致: 一行会消费其所有命中且未被更早行占用的源
    found_rows = set()
    for so, row_idx, _v_idx, _k_idx in hits:
        src = flattened_source_channels[so]
        if src['key'] in used_channel_keys:
            continue          # 源已被更早的行消费: 跳过
        category, tmpl_name, variants, _specs = template_rows[row_idx]
        primary_name = variants[0]
        if primary_name not in matched[category]:
            matched[category][primary_name] = []
        matched[category][primary_name].append((src['name'], src['url']))
        used_channel_keys.add(src['key'])
        found_rows.add(row_idx)

    # 未匹配: template_rows 中未被命中的行(与原 found_for_this_template 逻辑一致)
    for row_idx, (category, tmpl_name, _variants, _specs) in enumerate(template_rows):
        if row_idx not in found_rows:
            unmatched_template[category].append(tmpl_name)

    # 3. 找出源中未使用的频道
    unmatched_source = OrderedDict()
    for src in flattened_source_channels:
        if src['key'] not in used_channel_keys:
            if src['cat'] not in unmatched_source:
                unmatched_source[src['cat']] = []
            unmatched_source[src['cat']].append((src['name'], src['url']))

    return matched, unmatched_template, unmatched_source

def is_ipv6(url):
    return "://[" in url

# === 线路地址类型分类(生成配置时按 ipv4 -> 域名 -> ipv6 顺序排列) ===
_IPV4_HOST_RE = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}$')

def classify_url_type(url):
    """
    将线路地址分类为三组，返回排序用序号(小的在前)：
      0 = IPv4 直连   (host 为纯数字点分十进制，如 1.2.3.4:8080)
      1 = 域名        (host 含字母，如 example.com、xn--xx.net)
      2 = IPv6 直连   (host 为方括号形式，如 [2001:db8::1])
    仅按 "$" 分隔前的真实播放地址判断，忽略 $token 等附加参数与路径。
    """
    base = url.split("$", 1)[0].strip()
    m = re.match(r'^(?:[a-zA-Z][a-zA-Z0-9+.-]*://)?([^/?#]+)', base)
    if not m:
        return 1  # 解析不出 host 按域名组处理
    hostport = m.group(1)
    # 去掉 user:pass@ 前缀
    if '@' in hostport:
        hostport = hostport.rsplit('@', 1)[1]
    if hostport.startswith('['):          # [2001:db8::1]:port
        return 2
    host = hostport.split(':', 1)[0]      # 去端口
    if _IPV4_HOST_RE.match(host):         # 纯数字点分
        return 0
    return 1

def _build_extinf(display_name, category, clean_name=None):
    """
    - tvg-id / tvg-name 使用净化名，利于播放器识别同一频道
    - 可见名 display_name 保持模板/源提供的名称
    """
    if clean_name is None:
        clean_name = sanitize_channel_name(display_name) or display_name

    attrs = f'tvg-id="{clean_name}" tvg-name="{clean_name}"'
    attrs += f' group-title="{category}"'
    return f'#EXTINF:-1 {attrs},{display_name}'

def _m3u_header():
    return "#EXTM3U\n"

def generate_outputs(channels, template_channels, m3u_path, txt_path):
    """生成文件 - 路径参数化"""
    # 修复(跨频道去重): 去重维度按 (频道, base_url) 记，同一 base URL 出现在
    # 不同频道名下时不再互相吞线路。原逻辑把 written_urls 做成全局 base URL 集合，
    # 会导致"两个不同模板频道匹配到同一条流地址"时，后写的频道直接没有线路。
    written_line_keys = set()

    # 安全地确保输出目录存在
    ensure_dir(m3u_path)
    ensure_dir(txt_path)

    try:
        with write_lock:
            with open(m3u_path, "w", encoding="utf-8") as m3u, \
                 open(txt_path, "w", encoding="utf-8") as txt:

                m3u.write(_m3u_header())

                for category in template_channels:
                    if category not in channels or not channels[category]:
                        continue

                    txt.write(f"\n{category},#genre#\n")

                    for channel_key_name, channel_list in channels[category].items():

                        unique_urls = []
                        seen_base_urls = set()

                        for _, url in channel_list:
                            url = url.strip()
                            if not url:
                                continue
                            # 修复(URL去重): 去重应基于 "$" 分隔符前的真实播放地址，
                            # 而非原始字符串。不同源可能给同一条播放地址附加不同的
                            # 追踪后缀(如 $token=xxx)，原先按原始字符串去重会导致
                            # 同一条真实流地址被重复写入多次。
                            base_for_dedup = url.split("$")[0].strip()
                            if not base_for_dedup:
                                continue
                            if base_for_dedup not in seen_base_urls and \
                               (channel_key_name, base_for_dedup) not in written_line_keys:
                                unique_urls.append(url)
                                seen_base_urls.add(base_for_dedup)
                                written_line_keys.add((channel_key_name, base_for_dedup))

                        # 排序(生成格式): 按 ipv4 -> 域名 -> ipv6 顺序排列线路；
                        # 稳定排序保证同类型内保持源抓取时的原始顺序
                        unique_urls.sort(key=classify_url_type)

                        # 净化名供 tvg-id / tvg-name 使用；可见名保留模板名
                        clean_name = sanitize_channel_name(channel_key_name) or channel_key_name
                        display_name = channel_key_name

                        total_lines = len(unique_urls)
                        for idx, url in enumerate(unique_urls, 1):
                            # 修复(参数保留): 源 URL 中 "$" 后的段(如 $token=xxx / $sp=xxx)
                            # 是源站播放规则的一部分，不能丢弃。此处把这些原始参数段原样保留，
                            # 仅在此基础上追加 LR 元数据(供播放器解析线路)，避免线路因缺参数失效。
                            base_url, _, extra_param = url.partition("$")
                            base_url = base_url.strip()
                            suffix_name = "IPV6" if is_ipv6(url) else "IPV4"

                            # LR 元数据不带前导 $，由下方统一用 "$" 拼接，避免出现双 $ 分隔符
                            meta_suffix = f"LR•{suffix_name}"
                            if total_lines > 1:
                                meta_suffix += f"•{total_lines}『线路{idx}』"

                            parts = [base_url]
                            if extra_param:
                                parts.append(extra_param)
                            parts.append(meta_suffix)
                            final_url = "$".join(parts)

                            m3u.write(_build_extinf(display_name, category, clean_name) + "\n")
                            m3u.write(f"{final_url}\n")

                            txt.write(f"{display_name},{final_url}\n")

        logger.info(f"输出完成: {m3u_path}, {txt_path}")
    except Exception as e:
        logger.error(f"写入输出文件失败: {e}")

def generate_unmatched_report(unmatched_template, unmatched_source, report_file):
    """生成未匹配报告"""
    total_template_lost = sum(len(v) for v in unmatched_template.values())
    
    # 如果未指定报告文件路径，则仅计算丢失数量，不执行文件写入
    if not report_file:
        return total_template_lost

    ensure_dir(report_file)

    try:
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(f"# 未匹配报告 {datetime.now()}\n")
            f.write(f"# 模板未匹配数: {total_template_lost}\n\n")
            f.write("## 模板中有但源中无\n")
            for cat, names in unmatched_template.items():
                if names:
                    f.write(f"\n{cat},#genre#\n")
                    for name in list(OrderedDict.fromkeys(names)):
                        f.write(f"{name},\n")

            # 源中多余频道按其"源自带分类"归类展示
            f.write("\n\n## 源中有但模板无\n")
            for cat, chans in unmatched_source.items():
                unique_names = list(OrderedDict.fromkeys(name for name, _url in chans))
                if unique_names:
                    f.write(f"\n{cat},#genre#\n")
                    for name in unique_names:
                        f.write(f"{name},\n")
        logger.info(f"报告已生成: {report_file}")
        return total_template_lost
    except Exception as e:
        logger.error(f"生成报告失败: {e}")
        return 0

def remove_unmatched_from_template(template_file, unmatched_template):
    backup_file = template_file + ".backup"
    try:
        shutil.copy2(template_file, backup_file)
        with open(template_file, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()

        new_lines = []
        current_cat = None
        to_remove = {cat: set(names) for cat, names in unmatched_template.items()}

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue
            if "#genre#" in stripped:
                current_cat = stripped.split(",")[0].strip()
                new_lines.append(line)
                continue
            if current_cat:
                name = stripped.split(",")[0].strip()
                if current_cat in to_remove and name in to_remove[current_cat]:
                    continue
                new_lines.append(line)
            else:
                # 修复: 若不在任何 category 内的内容（如异常格式），不应被错误丢弃
                new_lines.append(line)

        with open(template_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        logger.info(f"已从模板 {template_file} 移除无效频道")
    except Exception as e:
        logger.error(f"更新模板失败: {e}")

def process_iptv_task(template_file, tv_urls, output_m3u, output_txt, report_file,
                      auto_clean=True, all_channels=None):
    """
    处理单个IPTV任务的封装函数
    增强: 新增 all_channels 参数支持"预抓取复用"，避免多任务重复请求同一批源；
          返回值 (matched, unmatched_tmpl, unmatched_src)，供调用方在任务间
          传递"未匹配"数据(例如把任务1的未匹配频道追加进任务2的模板)。
          解析失败(模板不存在)时返回 (None, None, None)，调用方需做空值判断。
    """
    logger.info(f"=== 开始处理任务: {template_file} ===")
    
    template = parse_template(template_file)
    if not template:
        return None, None, None

    # 增强: 若未传入预抓取数据，则自行抓取(保持向后兼容)
    if all_channels is None:
        logger.info(f"开始从 {len(tv_urls)} 个源获取数据...")
        all_channels = fetch_all_channels(tv_urls)

    logger.info("开始匹配频道...")
    matched, unmatched_tmpl, unmatched_src = match_channels(template, all_channels)

    generate_outputs(matched, template, output_m3u, output_txt)
    lost_count = generate_unmatched_report(unmatched_tmpl, unmatched_src, report_file)

    if auto_clean and lost_count > 0:
        logger.info(f"清理 {lost_count} 个无效频道...")
        remove_unmatched_from_template(template_file, unmatched_tmpl)
    
    logger.info(f"=== 任务完成: {template_file} ===\n")
    return matched, unmatched_tmpl, unmatched_src

# 频道未匹配轮数独立计数文件: 与模板文件同名替换扩展名，
# 例如 py/config/iptv_test.txt -> py/config/iptv_test_fc.json
# (_fail_counts.json 为早期后缀，读取时自动重命名迁移)
_FAIL_COUNTS_EXT = "_fc.json"
_LEGACY_FAIL_COUNTS_EXT = "_fail_counts.json"

def _fail_counts_path(target_template_file):
    """由目标模板路径推导独立计数文件路径。"""
    root, _ext = os.path.splitext(target_template_file)
    return root + _FAIL_COUNTS_EXT

def load_fail_counts(target_template_file):
    """读取目标模板对应独立计数文件中的"频道键 -> 累计未匹配轮数"。"""
    path = _fail_counts_path(target_template_file)
    # 旧后缀计数文件自动迁移为短名(仅在新文件不存在时执行一次)
    legacy_path = os.path.splitext(target_template_file)[0] + _LEGACY_FAIL_COUNTS_EXT
    if not os.path.exists(path) and os.path.exists(legacy_path):
        try:
            os.replace(legacy_path, path)
            logger.info(f"计数文件已迁移: {legacy_path} -> {path}")
        except Exception as e:
            logger.error(f"迁移计数文件失败(仍可读旧文件): {e}")
            path = legacy_path
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.error(f"读取 FAIL_COUNTS 计数文件失败，视为无历史计数: {e}")
        return {}

def save_fail_counts(target_template_file, fail_rounds):
    """原子写计数文件: 只保留非零计数，避免文件无限膨胀。"""
    path = _fail_counts_path(target_template_file)
    try:
        ensure_dir(path)
        active_counts = {k: v for k, v in fail_rounds.items() if v}
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(active_counts, f, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception as e:
        logger.error(f"写入 FAIL_COUNTS 计数文件失败: {e}")

def _strip_legacy_fail_counts_comment(target_template_file):
    """迁移历史遗留: 模板头残留 "# FAIL_COUNTS: {...}" 注释行时，
    读出计数并合并进独立计数文件，然后从模板头删除该注释行。"""
    path = _fail_counts_path(target_template_file)
    legacy_counts = None
    try:
        with open(target_template_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        for line in lines:
            m = re.match(r'#\s*FAIL_COUNTS:\s*(\{.*\})\s*$', line.strip())
            if m:
                try:
                    parsed = json.loads(m.group(1))
                except Exception:
                    parsed = None
                if isinstance(parsed, dict) and legacy_counts is None:
                    legacy_counts = parsed
                continue          # 该行不再写回
            new_lines.append(line)

        if not new_lines and not lines:
            return
        if legacy_counts is not None:
            merged = load_fail_counts(target_template_file)
            for key, val in legacy_counts.items():
                # 独立文件已有计数时取较大值，避免迁移覆盖更高轮数
                merged[key] = max(int(merged.get(key, 0)), int(val))
            save_fail_counts(target_template_file, merged)
            with open(target_template_file, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            logger.info(
                f"已将模板头 FAIL_COUNTS 注释行迁移至独立计数文件 {path}"
            )
    except Exception as e:
        logger.error(f"迁移模板头 FAIL_COUNTS 注释行失败(不影响运行): {e}")

def append_unmatched_to_template(unmatched_template, target_template_file,
                                 max_append_rounds=None):
    """
    把"任务1未匹配到的模板频道"合并进另一个模板文件(如 iptv_test.txt)，
    以便后续任务继续尝试匹配 / 持续观察这些频道后续是否恢复可用。

    治理(膨胀控制): 不再"追加一段分类块直接写文件末尾"，而是
    - 读取目标模板现有全部频道(parse_template 会把同一分类合并)
    - 与本次未匹配频道做归一去重合并
    - 用"分类,#genre#" 结构整体重写(不再产生碎片分类/注释块)

    治理(自动退役): 记录每个频道累计滞留轮数(脚本注释头 MATCH_FAIL_ROUNDS)，
    超过阈值轮仍未匹配的频道自动移出，防止只增不减。
    阈值优先级: 显式传参 max_append_rounds > 模板头 # MATCH_FAIL_ROUNDS: > 默认 8，
    最终生效值会回写模板头。
    各频道累计轮数持久化到独立计数文件 FAIL_COUNTS_FILE(跨轮读回累加)；若
    旧模板文件头仍残留历史 FAIL_COUNTS 注释行，会自动迁移到独立文件并从
    模板头清除。

    幂等: 已存在于目标模板对应分类下的频道不会被重复追加。
    返回本次实际追加的频道数量(0 表示无需追加)。
    """
    total_lost = sum(len(v) for v in (unmatched_template or {}).values())
    if total_lost == 0:
        logger.info(f"任务未匹配数为 0，无需追加到 {target_template_file}")
        return 0

    # 读取目标模板中已有的频道(parse_template 自动合并重复分类)
    existing = parse_template(target_template_file) or OrderedDict()

    # 记录每个频道的滞留轮数: 从独立计数文件读取(跨轮持久化)，
    # 若模板头残留历史 FAIL_COUNTS 注释行则迁移进独立文件并从模板头清除。
    fail_rounds = load_fail_counts(target_template_file)
    if os.path.exists(target_template_file):
        _strip_legacy_fail_counts_comment(target_template_file)

    # 读取模板头 MATCH_FAIL_ROUNDS 配置(允许沿用历史文件中的阈值)。
    # 修复(死代码): 旧逻辑阈值恒等于默认 8，模板头配置永远不生效；
    # 新语义: 显式传参 > 模板头配置 > 默认 8，最终生效值回写模板头保持一致。
    file_max = None
    if os.path.exists(target_template_file):
        try:
            with open(target_template_file, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    m = re.match(r'#\s*MATCH_FAIL_ROUNDS:\s*(\d+)', stripped)
                    if m:
                        file_max = int(m.group(1))
        except Exception:
            pass

    # 本次未匹配集合(用于退役判断: 未匹配=本轮仍在尝试)
    this_unmatched = {(cat, name) for cat, names in (unmatched_template or {}).items()
                      for name in names}

    new_template = OrderedDict()
    appended_count = 0

    # 1) 保留目标模板中已有的频道(分类合并)，累计轮数
    for cat, names in existing.items():
        if cat not in new_template:
            new_template[cat] = []
        for name in names:
            norm_key = f"{cat}\u0001{name}"
            if (cat, name) in this_unmatched:
                # 本轮仍未匹配: 轮数+1
                fail_rounds[norm_key] = fail_rounds.get(norm_key, 0) + 1
                new_template[cat].append(name)
            else:
                # 本轮匹配成功或从未尝试: 轮数重置
                fail_rounds[norm_key] = 0
                new_template[cat].append(name)

    # 2) 追加本次未匹配频道的"新增项"(不在目标模板中的)
    for cat, names in (unmatched_template or {}).items():
        if cat not in new_template:
            new_template[cat] = []
        existing_names = set(new_template[cat])
        for name in names:
            if name not in existing_names:
                new_template[cat].append(name)
                fail_rounds[f"{cat}\u0001{name}"] = 1
                appended_count += 1

    # 3) 自动退役: 阈值取值优先级 显式传参 > 模板头配置 > 默认 8
    retire_rounds = max_append_rounds
    if retire_rounds is None:
        retire_rounds = file_max
    if retire_rounds is None:
        retire_rounds = 8
    if retire_rounds and retire_rounds > 0:
        retired = 0
        for cat in list(new_template.keys()):
            kept = []
            for name in new_template[cat]:
                if fail_rounds.get(f"{cat}\u0001{name}", 0) > retire_rounds:
                    retired += 1
                    continue
                kept.append(name)
            if kept:
                new_template[cat] = kept
            else:
                new_template.pop(cat, None)
        if retired:
            logger.info(f"自动退役 {retired} 个长期无源频道(超过 {retire_rounds} 轮未匹配)")

    # 整体重写: 分类聚合、无碎片分类；FAIL_COUNTS 不再写回模板头，
    # 独立持久化到计数文件
    try:
        ensure_dir(target_template_file)
        with open(target_template_file, "w", encoding="utf-8") as f:
            f.write(f"# 测试模板(由 get_iptv.py 自动维护)\n")
            f.write(f"# MATCH_FAIL_ROUNDS: {retire_rounds}\n")
            for cat, names in new_template.items():
                uniq = list(OrderedDict.fromkeys(names))
                if not uniq:
                    continue
                f.write(f"\n{cat},#genre#\n")
                for name in uniq:
                    f.write(f"{name},\n")
        # 频道键 -> 累计轮数的持久化(退役依赖此值跨轮累计)
        save_fail_counts(target_template_file, fail_rounds)
        logger.info(f"已将 {appended_count} 个未匹配频道合并进 {target_template_file}"
                    f"(现有 {sum(len(v) for v in new_template.values())} 个频道)")
        return appended_count
    except Exception as e:
        logger.error(f"合并未匹配频道到 {target_template_file} 失败: {e}")
        return 0

if __name__ == "__main__":
    # === 配置区 ===
    # 修复(C2+回归): 路径不再依赖 CWD 也不依赖单脚本的 BASE_DIR 拼接，
    # 由 CONFIG_DIR / LIB_DIR 自动探测(见文件头部注释)，兼容:
    #   布局A: <根>/get_iptv.py + <根>/py/config + <根>/lib (本工作区)
    #   布局B: <根>/py/get_iptv.py + <根>/py/config + <根>/lib (tvbox CI)
    URLS_FILE = os.path.join(CONFIG_DIR, "urls.txt")

    # 1. 加载源
    TV_URLS = load_urls_from_file(URLS_FILE)
    if not TV_URLS:
        logger.warning("未从文件中加载到URL，使用空列表")
        TV_URLS = [] 

    # 增强(性能): 全部源只抓取一次，供后续所有任务复用
    logger.info(f"开始从 {len(TV_URLS)} 个源统一获取数据...")
    ALL_CHANNELS = fetch_all_channels(TV_URLS) if TV_URLS else OrderedDict()

    # === 任务1: 主列表 ===
    _matched1, unmatched_tmpl1, _unmatched_src1 = process_iptv_task(
        template_file=os.path.join(CONFIG_DIR, "iptv.txt"),
        tv_urls=TV_URLS,
        output_m3u=os.path.join(LIB_DIR, "iptv.m3u"),
        output_txt=os.path.join(LIB_DIR, "iptv.txt"),
        report_file=os.path.join(CONFIG_DIR, "iptv.log"),
        auto_clean=False,
        all_channels=ALL_CHANNELS,
    )

    # === 新增: 把任务1未匹配到的频道追加进测试列表模板，再执行任务2 ===
    TEST_TEMPLATE_FILE = os.path.join(CONFIG_DIR, "iptv_test.txt")
    if unmatched_tmpl1:
        append_unmatched_to_template(unmatched_tmpl1, TEST_TEMPLATE_FILE)

    # === 任务2: 测试列表 (追加后必然存在，除非任务1无未匹配且此前也无测试模板文件) ===
    if os.path.exists(TEST_TEMPLATE_FILE):
        process_iptv_task(
            template_file=TEST_TEMPLATE_FILE,
            tv_urls=TV_URLS,
            output_m3u="lib/iptv_test.m3u",
            output_txt="lib/iptv_test.txt",
            report_file=None,
            auto_clean=False,
            all_channels=ALL_CHANNELS,
        )
    else:
        logger.info(f"未检测到测试配置 {TEST_TEMPLATE_FILE}，跳过测试生成。")
