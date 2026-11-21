# coding=utf-8
import os
import logging
import sys
import asyncio
import random
import aiohttp

BASE_URL = "http://api.hclyz.com:81/mf"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TARGET_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "lib"))
M3U_FILE = os.path.join(TARGET_DIR, "sbjh.m3u")

HEADERS = {
    # 完整浏览器级请求头，所有上游请求统一使用，降低被 WAF/限流拦截的概率
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": BASE_URL,
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

MAX_WORKERS = 4          # 并发上限，宁慢勿封
RETRY_STATUS = {412, 425, 429, 500, 502, 503, 504}   # 需要重试的状态码
PERMANENT_STATUS = {400, 401, 403, 404, 410}         # 重试也没用的状态码

def setup_logging():
    logger = logging.getLogger("ScraperLogger")
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    consoleHandler = logging.StreamHandler(sys.stdout)
    consoleHandler.setFormatter(formatter)
    logger.addHandler(consoleHandler)
    
    return logger

log = setup_logging()

async def safeGetJson(url, session, maxRetries=4, baseDelay=2.0):
    for attemptCount in range(1, maxRetries + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with session.get(url, headers=HEADERS, timeout=timeout) as responseObj:
                if responseObj.status == 200:
                    return await responseObj.json(content_type=None)

                if responseObj.status in PERMANENT_STATUS:
                    # 404/403 等永久错误，重试无意义，直接放弃
                    log.warning(f"HTTP {responseObj.status} (permanent) for {url}, giving up")
                    await responseObj.read()   # 读掉 body 以便复用连接
                    return None

                log.warning(f"HTTP {responseObj.status} for {url}. Attempt {attemptCount}/{maxRetries}")

                if attemptCount < maxRetries:
                    # 优先遵循服务端的 Retry-After
                    retryAfter = responseObj.headers.get("Retry-After")
                    if retryAfter and retryAfter.isdigit():
                        delay = min(float(retryAfter), 30)
                    else:
                        # 指数退避 + 随机抖动，避免固定节奏撞限流
                        delay = baseDelay * (2 ** (attemptCount - 1)) * (1 + random.random())
                    await asyncio.sleep(delay)
                else:
                    await responseObj.read()
        except Exception as e:
            log.error(f"Request Exception: {url} -> {e}. Attempt {attemptCount}/{maxRetries}")
            if attemptCount < maxRetries:
                await asyncio.sleep(baseDelay * (2 ** (attemptCount - 1)) * (1 + random.random()))

    return None

async def processPlatform(item, session, sem):
    async with sem:
        roomTitle = item.get("title", "").strip()
        number = item.get("Number", "")
        address = item.get("address", "")
        
        xinImg = item.get("xinimg", "")
        platformLogo = xinImg.replace("clun.top", "cdn.gcufbd.top")

        log.info(f"📺 Fetching Platform: {roomTitle} (Resource count: {number})")

        detail = await safeGetJson(f"{BASE_URL}/{address}", session)
        if not detail:
            return roomTitle, [], 1

        zhubo = detail.get("zhubo", [])
        if not zhubo:
            return roomTitle, [], 1

        groupName = f"{roomTitle}"
        results = []
        errors = 0

        for vod in zhubo:
            name = vod.get("title", "").strip()
            url = vod.get("address", "").strip()

            if not url:
                errors += 1
                continue

            anchorImg = (vod.get("img") or "").strip()
            logo = anchorImg or platformLogo

            results.append((groupName, name, url, logo))

        return roomTitle, results, errors

async def mainAsync():
    totalError = 0
    totalSuccess = 0

    log.info("🚀 Enhanced task initiated.")
    
    # 限流防护：连接池与信号量对齐，避免突发并发触发服务端限制
    connector = aiohttp.TCPConnector(limit=MAX_WORKERS, limit_per_host=MAX_WORKERS)
    async with aiohttp.ClientSession(connector=connector) as session:

        home = await safeGetJson(f"{BASE_URL}/json.txt", session)
        if not home:
            log.error("❌ Retrieval failed, collection terminated.")
            sys.exit(1)

        # Retrieve platform list and remove the first element
        data = home.get("pingtai", [])[1:]

        m3uLines = ["#EXTM3U x-tvg-url=\"\""]
        seenUrls = set()

        log.info(f"⚡ Found {len(data)} platforms in total.")

        sem = asyncio.Semaphore(MAX_WORKERS)

        tasks = [processPlatform(item, session, sem) for item in data]
        results = await asyncio.gather(*tasks)

        for roomTitle, res, errors in results:
            totalError += errors
            
            for groupName, name, url, logo in res:
                if url in seenUrls:
                    continue

                seenUrls.add(url)
                # Generate M3U tag with Logo
                m3uLines.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{groupName}",{name}')
                m3uLines.append(url)
                totalSuccess += 1

    try:
        os.makedirs(os.path.dirname(M3U_FILE), exist_ok=True)
        
        with open(M3U_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(m3uLines))
        log.info(f"📄 Generation successful. Total Streams: {totalSuccess}")
    except Exception as e:
        log.error(f"❌ Failed to write to file: {e}")
        sys.exit(1)

    summaryMsg = f"Collection completed, valid: {totalSuccess}, Abnormal: {totalError}"
    print(f"::notice title=📁 Save path: {M3U_FILE}::{summaryMsg}")

def main():
    asyncio.run(mainAsync())

if __name__ == "__main__":
    main()
