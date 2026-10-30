import hashlib
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from auto_login import get_valid_cookie
from utils import get_all_cookies, extract_user_info_from_cookies

ACTIVITY_BASE = "https://activity.zaimanhua.com/dApi"
ACTIVITY_PAGE = "https://activity.zaimanhua.com/halloween-2026/"
READ_API_BASE = "https://v4api.zaimanhua.com/app/v1"
V4_API_BASE = "https://v4api.zaimanhua.com"
TOPIC_ID = 607
TOPIC_PAGE = f"https://zt.zaimanhua.com/details?id={TOPIC_ID}"
SIGN_KEY = "sKhGs_^0j6Mb^Lt!"
CHANNEL = "h5"
BEIJING_TZ = timezone(timedelta(hours=8))
ACTIVITY_END = datetime(2026, 11, 2, 0, 0, 0, tzinfo=BEIJING_TZ)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def is_activity_expired():
    now = datetime.now(BEIJING_TZ)
    if now >= ACTIVITY_END:
        print(f"[SKIP] 当前北京时间 {now:%Y-%m-%d %H:%M:%S} 已过活动结束时间 "
              f"2026-11-01 24:00，跳过")
        return True
    print(f"当前北京时间 {now:%Y-%m-%d %H:%M:%S}，活动进行中 "
          f"(截止 2026-11-01 24:00)")
    return False


def make_sign_params():
    timestamp = int(time.time() * 1000)
    raw = f"{CHANNEL}{timestamp}{SIGN_KEY}"
    return {
        "channel": CHANNEL,
        "timestamp": timestamp,
        "sign": hashlib.md5(raw.encode()).hexdigest(),
    }


def build_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
        "Referer": ACTIVITY_PAGE,
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
    }


def api_get(token, path, params=None):
    query = make_sign_params()
    if params:
        query.update(params)
    try:
        resp = requests.get(
            f"{ACTIVITY_BASE}{path}",
            headers=build_headers(token),
            params=query,
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        print(f"    [HTTP {resp.status_code}]")
    except Exception as e:
        print(f"    请求异常: {e}")
    return None


def api_post(token, path, data=None):
    query = make_sign_params()
    try:
        resp = requests.post(
            f"{ACTIVITY_BASE}{path}?{urlencode(query)}",
            headers=build_headers(token),
            json=data or {},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        print(f"    [HTTP {resp.status_code}]")
    except Exception as e:
        print(f"    请求异常: {e}")
    return None


def get_activity_status(token):
    result = api_get(token, "/draw/draw_load")
    if not result or result.get("errno") != 0:
        errmsg = result.get("errmsg", "未知错误") if result else "无法连接"
        print(f"  查询活动状态失败: {errmsg}")
        return None
    return result.get("data", {})


def get_topic_comics():
    try:
        resp = requests.get(
            f"{V4_API_BASE}/api/v1/zt/h5/detail",
            headers={
                "User-Agent": "okhttp/4.9.3",
                "Accept": "application/json, text/plain, */*",
            },
            params={"id": TOPIC_ID},
            timeout=15,
        )
        if resp.status_code == 200:
            result = resp.json()
            if result.get("errno") == 0:
                comics = []
                for item in result.get("data", {}).get("comicList", []) or []:
                    if not isinstance(item, dict):
                        continue
                    comic_id = item.get("comic_id") or item.get("id")
                    name = item.get("name") or item.get("title")
                    if comic_id and name:
                        comics.append({"id": comic_id, "name": name})
                return comics
    except Exception as e:
        print(f"  获取专题漫画异常: {e}")
    return []


def do_share_task(token):
    result = api_get(token, "/draw/share")
    if result and result.get("errno") == 0:
        print("  [v] 分享任务完成，抽奖次数 +1")
        return True
    errmsg = result.get("errmsg", "无响应") if result else "请求失败"
    print(f"  分享任务失败: {errmsg}")
    return False


def make_comment_content(comics):
    if comics:
        candidates = [comic for comic in comics if len(comic["name"]) <= 20]
        return random.choice(candidates or comics)["name"]
    return "万圣节快乐"


def do_comment_task(token, comics):
    content = make_comment_content(comics)
    print(f"  评论内容: {content}")
    result = api_post(token, "/draw/add_comment", {"con": content, "source": 2})
    if result and result.get("errno") == 0:
        print("  [v] 评论任务完成，抽奖次数 +1")
        return True
    errmsg = result.get("errmsg", "无响应") if result else "请求失败"
    print(f"  评论任务失败: {errmsg}")
    return False


class TopicReader:
    def __init__(self, token):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "okhttp/4.9.3",
            "Accept": "application/json, text/plain, */*",
        }

    def _get(self, path, params=None):
        try:
            resp = requests.get(
                f"{READ_API_BASE}{path}",
                headers=self.headers,
                params=params,
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"    请求异常: {e}")
        return None

    def view_topic(self):
        try:
            resp = requests.get(
                f"{V4_API_BASE}/api/v1/zt/h5/detail",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "User-Agent": USER_AGENT,
                    "Origin": "https://zt.zaimanhua.com",
                    "Referer": TOPIC_PAGE,
                    "Accept": "application/json, text/plain, */*",
                },
                params={"id": TOPIC_ID},
                timeout=15,
            )
            if resp.status_code == 200 and resp.json().get("errno") == 0:
                print(f"  [v] 已访问专题 {TOPIC_ID}")
                return True
        except Exception as e:
            print(f"  访问专题异常: {e}")
        return False

    def _get_chapters(self, comic_id):
        data = self._get(f"/comic/detail/{comic_id}", {"_v": "2.2.5"})
        if not data or data.get("errno") != 0:
            return []
        comic_info = data.get("data", {}).get("data", {})
        chapters = []
        for volume in comic_info.get("chapters") or []:
            if isinstance(volume, dict) and isinstance(volume.get("data"), list):
                for chapter in volume["data"]:
                    if chapter.get("canRead", True) and chapter.get("chapter_id"):
                        chapters.append(chapter)
        return chapters

    def _read_comic(self, comic):
        comic_id = comic["id"]
        comic_name = comic["name"]
        print(f"  随机选中漫画: {comic_name} (ID: {comic_id})")
        chapters = self._get_chapters(comic_id)
        if not chapters:
            print("    该漫画无可用章节")
            return False
        chapter = random.choice(chapters)
        chapter_id = chapter.get("chapter_id")
        chapter_title = (
            chapter.get("chapter_title")
            or chapter.get("title")
            or f"第{chapter_id}话"
        )
        print(f"    随机选中章节: {chapter_title} (ID: {chapter_id})")
        data = self._get(f"/comic/chapter/{comic_id}/{chapter_id}", {"_v": "2.2.5"})
        images = []
        if data and data.get("errno") == 0:
            inner = data.get("data", {}).get("data", {})
            images = (
                inner.get("page_url_hd")
                or inner.get("page_url")
                or inner.get("images")
                or []
            )
        if not images:
            print("    无法获取章节图片")
            return False
        pages_read = 0
        for image_url in images[:2]:
            try:
                resp = requests.get(image_url, headers=self.headers, timeout=15)
                if resp.status_code == 200:
                    pages_read += 1
            except Exception:
                pass
        print(f"    [v] 阅读完成，共读取 {pages_read} 页")
        return pages_read > 0

    def read(self, comics, max_attempts=8):
        self.view_topic()
        if not comics:
            print("  未获取到专题漫画")
            return False
        candidates = comics[:]
        random.shuffle(candidates)
        for comic in candidates[:max_attempts]:
            if self._read_comic(comic):
                return True
            print("    换一本重试...")
        return False


def do_read_task(cookie_str, comics):
    user_info = extract_user_info_from_cookies(cookie_str)
    token = user_info.get("token") if isinstance(user_info, dict) else None
    if not token:
        print("  无法获取 token")
        return False
    return TopicReader(token).read(comics)


def do_draw(token):
    result = api_get(token, "/draw/drawing")
    if not result:
        return False, None
    if result.get("errno") == 0:
        data = result.get("data", {})
        prize = data.get("prize", {}) if isinstance(data, dict) else {}
        return True, {
            "id": data.get("id"),
            "cate": prize.get("cate"),
            "name": prize.get("name"),
        }
    print(f"    抽奖失败: {result.get('errmsg', '')}")
    return False, None


def run_draw_lottery(token, draw_count):
    if draw_count <= 0:
        print("  当前没有可抽奖次数")
        return []
    print(f"\n=== 开始抽奖，共 {draw_count} 次 ===")
    results = []
    for index in range(1, draw_count + 1):
        print(f"\n--- 第 {index}/{draw_count} 次抽奖 ---")
        success, prize = do_draw(token)
        if not success or not prize:
            break
        results.append(prize)
        name = prize.get("name") or "未知奖品"
        cate = prize.get("cate")
        print(f"  [v] {name}")
        if cate and cate > 0:
            print(f"      奖品类别: {cate}, 记录 ID: {prize.get('id')}")
        time.sleep(1)
    return results


def print_draw_summary(results):
    print("\n" + "=" * 60)
    print("  抽奖结果汇总")
    print("=" * 60)
    if not results:
        print("  本轮没有获得奖品")
    else:
        print(f"  共抽奖 {len(results)} 次:")
        for index, prize in enumerate(results, 1):
            print(
                f"    {index}. {prize.get('name') or '未知奖品'} "
                f"(类别: {prize.get('cate', 0)}, ID: {prize.get('id')})"
            )
    print("=" * 60)


def run_account(index, name, cookie_str):
    print(f"\n{'=' * 60}")
    print(f"  账号: {name}")
    print(f"{'=' * 60}")
    valid_cookie, _ = get_valid_cookie(
        cookie_str,
        name,
        account_index=index if index > 0 else None,
    )
    if not valid_cookie:
        print("[ERROR] 无法获取有效 Cookie")
        return False
    cookie_str = valid_cookie
    user_info = extract_user_info_from_cookies(cookie_str)
    token = user_info.get("token") if isinstance(user_info, dict) else None
    if not token:
        print("[ERROR] 无法获取 token")
        return False

    comics = get_topic_comics()
    print(f"专题 {TOPIC_ID} 共 {len(comics)} 本漫画")

    print("\n=== 活动状态 ===")
    status = get_activity_status(token)
    if not status:
        return False
    draw_count = status.get("times", 0)
    share_done = status.get("shareTimes", 0) >= 1
    read_done = status.get("readTimes", 0) >= 1
    comment_done = status.get("addComTimes", 0) >= 1
    print(f"  抽奖次数: {draw_count}")
    print(f"  分享任务: {'已完成' if share_done else '未完成'}")
    print(f"  阅读任务: {'已完成' if read_done else '未完成'}")
    print(f"  评论任务: {'已完成' if comment_done else '未完成'}")

    if not share_done:
        print("\n--- 执行分享任务 ---")
        do_share_task(token)
        time.sleep(1)
    if not comment_done:
        print("\n--- 执行评论任务 ---")
        do_comment_task(token, comics)
        time.sleep(1)
    if not read_done:
        print("\n--- 执行阅读任务 ---")
        do_read_task(cookie_str, comics)
        time.sleep(1)

    print("\n--- 刷新活动状态 ---")
    time.sleep(5)
    latest_status = get_activity_status(token)
    if latest_status:
        status = latest_status
    draw_count = status.get("times", 0)
    print(f"  最终抽奖次数: {draw_count}")
    print(f"  分享任务: {'已完成' if status.get('shareTimes', 0) >= 1 else '未完成'}")
    print(f"  阅读任务: {'已完成' if status.get('readTimes', 0) >= 1 else '未完成'}")
    print(f"  评论任务: {'已完成' if status.get('addComTimes', 0) >= 1 else '未完成'}")

    results = run_draw_lottery(token, draw_count)
    print_draw_summary(results)
    return True


def main():
    if is_activity_expired():
        return True
    cookies_list = get_all_cookies()
    if not cookies_list:
        print("Error: 未配置任何账号 Cookie")
        print("请设置 ZAIMANHUA_COOKIE 或 ZAIMANHUA_USERNAME/ZAIMANHUA_PASSWORD 环境变量")
        return False
    print(f"共发现 {len(cookies_list)} 个账号")
    all_success = True
    for index, (name, cookie_str) in enumerate(cookies_list):
        if not run_account(index, name, cookie_str):
            all_success = False
        if index < len(cookies_list) - 1:
            print("\n等待 5 秒后切换下一个账号...")
            time.sleep(5)
    print("\n" + "=" * 60)
    if all_success:
        print("所有账号 Halloween 2026 活动执行完成！")
    else:
        print("部分账号活动执行失败，请检查日志")
    print("=" * 60)
    return all_success


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
