import time
import random
import requests
from utils import (
    get_all_cookies,
    claim_rewards,
    get_task_list,
    extract_tasks_from_response,
    extract_user_info_from_cookies,
    claim_task_reward
)
from auto_read import ZaimanhuaReader

MAX_RETRIES = 3
COMMENT_TASK_ID = 14
COMMENT_SKIPPED = 'skipped'
CLIENT_ID = None

COMMENTS = [
    "(゜∀゜*)",
    "(⁠・⁠∀⁠・⁠)",
    "(⁠ ⁠╹⁠▽⁠╹⁠ ⁠)",
    "(´・ω・｀)",
    "₍˄·͈༝·͈˄*₎◞ ̑̑",
    "(・ω・)",
    "(*╹▽╹*)",
    "(¦3[▓▓]",
]


def mask_phone(phone):
    if phone is None:
        return None
    phone_str = str(phone)
    if phone_str.strip():
        return "***"
    return phone_str


def check_user_commented(token, comic_id, uid):
    import html as html_lib

    try:
        url = "https://v4api.zaimanhua.com/app/v1/comment/list"
        headers = {
            "Authorization": f"Bearer {token}",
        }
        params = {
            "type": 4,
            "objId": comic_id,
            "sort": 1,
            "page": 0,
            "size": 30,
            "channel": "android",
            "timestamp": str(int(time.time())),
            "uid": uid,
        }
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        result = resp.json()
        if result.get("errno") != 0:
            return False
        data = result.get("data", {})
        comment_list = data.get("commentList", {})
        comments = list(comment_list.values())
        print(f"  漫画ID {comic_id} 评论列表（{len(comments)} 条）:")
        for comment in comments:
            nickname = comment.get("nickname") or comment.get("author", {}).get("nickname") or "未知用户"
            content = html_lib.unescape(comment.get("content", "")).strip()
            print(f"    用户名: {nickname} | 评论内容: {content}")
        return any(comment.get("sender_uid") == uid for comment in comments)
    except Exception as e:
        print(f"  检查评论历史失败: {e}")
        return False


def get_user_recent_comments(token, uid, days=7, max_pages=5):
    import html as html_lib

    recent_contents = set()
    cutoff_ts = time.time() - (days * 86400)

    try:
        url = "https://account-api.zaimanhua.com/v1/other_center/comment_list"
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
        }

        for page in range(1, max_pages + 1):
            params = {
                "hisUid": uid,
                "page": page,
                "size": 10,
                "source": 4,       # 漫画评论
                "sortBy": 1,      # 按时间倒序
            }
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            result = resp.json()

            if result.get("errno") != 0:
                break

            data = result.get("data", {})
            comment_list = data.get("commentList", [])

            if not comment_list:
                break

            reached_old = False
            for item in comment_list:
                create_time = item.get("create_time", 0)
                # 兼容秒和毫秒时间戳
                if create_time > 10000000000:
                    create_time = create_time / 1000

                if create_time < cutoff_ts:
                    reached_old = True
                    break

                content = html_lib.unescape(item.get("content", "")).strip()
                if content:
                    recent_contents.add(content)
                    entity = item.get("entity", {})
                    comic_id = item.get("obj_id") or entity.get("id")
                    comic_title = html_lib.unescape(entity.get("name") or "未知标题")
                    comic_url = f"https://m.zaimanhua.com/pages/comic/detail?id={comic_id}"
                    print(f"  漫画ID: {comic_id} | 标题: {comic_title} | 评论内容: {content} | 链接: {comic_url}")

            if reached_old or len(comment_list) < 10:
                break

    except Exception as e:
        print(f"  [DEBUG] 获取往期评论异常: {e}")

    return recent_contents


def pick_unique_comment(recent_comments):
    available = [c for c in COMMENTS if c not in recent_comments]
    if available:
        return random.choice(available)
    # 全部用过后随机兜底
    return random.choice(COMMENTS)


def get_source_comic_ids(cookie_str):
    reader = ZaimanhuaReader(cookie_str)
    comics = reader.get_all_source_comics()
    comic_ids = []
    seen_ids = set()
    for comic in comics:
        comic_id = comic.get("comic_id") or comic.get("id")
        if comic_id and comic_id not in seen_ids:
            seen_ids.add(comic_id)
            comic_ids.append(str(comic_id))
    print(f"  从首页、排行榜、最近更新获取到 {len(comic_ids)} 本漫画")
    return comic_ids


def get_comment_comic_candidates(cookie_str, user_level, max_attempts=10):
    if user_level <= 3:
        print("  账号等级低于lv4，从首页、排行榜、最近更新获取漫画")
        try:
            comic_candidates = get_source_comic_ids(cookie_str)
        except Exception as e:
            print(f"  获取漫画失败: {e}")
            comic_candidates = []
        random.shuffle(comic_candidates)
        comic_candidates = comic_candidates[:max_attempts]
        if not comic_candidates:
            print("  获取漫画失败，改用随机漫画ID")
            comic_candidates = [
                str(random.randint(4, 89138))
                for _ in range(max_attempts)
            ]
    else:
        comic_candidates = [
            str(random.randint(4, 89138))
            for _ in range(max_attempts)
        ]
    return comic_candidates


def get_client_id():
    global CLIENT_ID
    if CLIENT_ID is None:
        try:
            resp = requests.get("https://v4api.zaimanhua.com/app/v1/config/common", timeout=10)
            CLIENT_ID = resp.json().get("data", {}).get("data", {}).get("clientId", "")
        except Exception:
            CLIENT_ID = ""
    return CLIENT_ID


def send_comment_api(token, comic_id, content, cookie_str=None):
    url = "https://v4api.zaimanhua.com/app/v1/comment/create"
    user_info = extract_user_info_from_cookies(cookie_str or "")
    client_id = str(user_info.get("uid") or get_client_id())
    params = {
        "platform": "android",
        "timestamp": str(int(time.time() * 1000)),
        "_v": "2.3.9",
        "_c": "101_01_01_000",
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "*/*",
        "Content-Type": "application/json; charset=utf-8",
        "Platform": "android",
        "X-Client-ID": client_id,
        "AppVersion": "2.3.9",
        "BuildNumber": "1502292",
    }
    data = {
        "obj_id": int(comic_id),
        "to_comment_id": 0,
        "type": 4,
        "content": content,
        "img": [],
    }
    try:
        resp = requests.post(url, headers=headers, params=params, json=data, timeout=20)
        result = resp.json()
        if result.get("errno") == 0:
            return True, result
        else:
            return False, result
    except Exception as e:
        return False, {"errmsg": str(e)}


def post_daily_comment(cookie_str, bind_phone=None):
    print("\n=== 每日评论任务 ===")

    user_info = extract_user_info_from_cookies(cookie_str)
    token = user_info.get('token')
    uid = user_info.get('uid')
    try:
        user_level = int(user_info.get('user_level') or 0)
    except (TypeError, ValueError):
        user_level = 0
    print(f"  用户等级: lv{user_level}")

    if token:
        print("检查当前任务状态...")
        task_result = get_task_list(token)
        if task_result and task_result.get('errno') == 0:
            tasks = extract_tasks_from_response(task_result)
            for task in tasks:
                task_id = task.get('id') or task.get('taskId')
                if task_id == COMMENT_TASK_ID:
                    if task.get('status') == 3:
                        print("  评论任务已完成，无需再次评论")
                        return True
                    break

    if bind_phone is not None:
        phone_bound = bind_phone and str(bind_phone) not in ['0', '', 'None', 'False']
        print(f"使用API登录返回的手机号: bind_phone={mask_phone(bind_phone)}")
    else:
        phone_bound = user_info.get('bind_phone')
        phone_bound = phone_bound and str(phone_bound) not in ['0', '', 'None', 'False']
        print(f"从Cookie中提取的手机号: bind_phone={mask_phone(user_info.get('bind_phone'))}")

    if not phone_bound:
        print(f"警告: 检测到当前账号未绑定手机号 (bind_phone={mask_phone(bind_phone or user_info.get('bind_phone'))})")
        print("注意: 未绑定手机号的账号无法完成评论任务。将跳过此任务。")
        return COMMENT_SKIPPED

    try:
        recent_comments = set()
        if uid:
            print("  查询往期评论记录...")
            recent_comments = get_user_recent_comments(token, uid, days=7)
            if recent_comments:
                print(f"  发现 {len(recent_comments)} 条近期已用评论，将避开")
            else:
                print(f"  无近期评论记录")

        max_comic_attempts = 10
        comic_candidates = get_comment_comic_candidates(
            cookie_str,
            user_level,
            max_comic_attempts,
        )

        for comic_attempt, comic_id in enumerate(comic_candidates, 1):
            print(f"随机选择漫画ID: {comic_id} (尝试 {comic_attempt}/{len(comic_candidates)})")
            print(f"  漫画详情页: https://m.zaimanhua.com/pages/comic/detail?id={comic_id}")

            if uid and check_user_commented(token, comic_id, uid):
                print(f"  该漫画已评论过，跳过...")
                continue

            comment_text = pick_unique_comment(recent_comments)
            print(f"发送评论: {comment_text}")

            success, result = send_comment_api(token, comic_id, comment_text, cookie_str)
            if success:
                print(f"  评论发送成功！")
                return True
            else:
                errmsg = result.get('errmsg', '未知错误')
                print(f"  评论发送失败: {errmsg}")
                continue

        print("多次随机漫画尝试后仍失败")
        return False

    except Exception as e:
        print(f"评论任务失败: {e}")
        return False


def check_comment_task_status(token):
    # 状态：1 未完成，2 可领取，3 已完成
    try:
        task_result = get_task_list(token)
        if task_result and task_result.get('errno') == 0:
            tasks = extract_tasks_from_response(task_result)
            for task in tasks:
                task_id = task.get('id') or task.get('taskId')
                task_name = task.get('title') or task.get('name') or task.get('taskName', '')
                is_comment_task = (task_id == COMMENT_TASK_ID or
                                 '评论' in str(task_name) or
                                 '一评' in str(task_name))
                if is_comment_task:
                    status = task.get('status', 0)
                    print(f"  评论任务状态: ID={task_id}, 名称={task_name}, status={status}")
                    return status, task_id
        return None, None
    except Exception as e:
        print(f"  检查任务状态异常: {e}")
        return None, None


def run_comment(cookie_str, bind_phone=None):
    try:
        comment_result = post_daily_comment(cookie_str, bind_phone=bind_phone)

        # 未绑定手机号时不计失败
        if comment_result == COMMENT_SKIPPED:
            return {
                'comment': None,
                'claim': False,
                'skipped': True,
            }

        claim_result = claim_rewards(cookie_str)

        user_info = extract_user_info_from_cookies(cookie_str)
        token = user_info.get('token') if isinstance(user_info, dict) else None

        if token and comment_result:
            print("\n=== 验证评论任务状态 ===")
            max_verify_retries = 3
            for verify_attempt in range(max_verify_retries):
                status, task_id = check_comment_task_status(token)

                if status == 3:
                    print(f"  [v] 评论任务已完成并领取 (status=3)")
                    break
                elif status == 2:
                    print(f"  [v] 评论任务已完成，尝试领取奖励...")
                    success, result = claim_task_reward(token, task_id)
                    if success:
                        print(f"  [OK] 奖励领取成功！")
                    break
                elif status == 1:
                    if verify_attempt < max_verify_retries - 1:
                        print(f"  [!] 评论任务未完成 (status=1)，可能评论未发送成功，准备重新评论...")
                        comment_result = post_daily_comment(cookie_str, bind_phone=bind_phone)
                        if comment_result:
                            print(f"  [v] 重新评论完成，等待服务器同步...")
                            time.sleep(5)
                        else:
                            print(f"  [x] 重新评论失败")
                            break
                    else:
                        print(f"  [x] 评论任务仍未完成，已达到最大重试次数")
                        comment_result = False
                else:
                    print(f"  [?] 无法获取评论任务状态，跳过验证")
                    break

        return {
            'comment': comment_result,
            'claim': claim_result
        }

    except Exception as e:
        print(f"任务执行出错: {e}")
        return {'comment': False, 'claim': False}


def main():
    cookies_list = get_all_cookies()

    if not cookies_list:
        print("Error: 未配置任何账号 Cookie")
        print("请设置 ZAIMANHUA_COOKIE 或 ZAIMANHUA_COOKIE_1 等环境变量")
        return False

    print(f"共发现 {len(cookies_list)} 个账号")

    all_success = True
    for index, (name, cookie_str) in enumerate(cookies_list):
        print(f"\n{'='*50}")
        print(f"正在执行评论任务: {name}")
        print('='*50)

        from auto_login import get_valid_cookie
        valid_cookie, is_auto_login = get_valid_cookie(cookie_str, name, account_index=index if index > 0 else None)

        if not valid_cookie:
            print(f"[ERROR] 无法获取有效Cookie")
            all_success = False
            continue

        if is_auto_login:
            print(f"  [v] 使用自动登录获取的新Cookie")
            cookie_str = valid_cookie
        else:
            print(f"  [v] 使用配置的Cookie")

        bind_phone = None
        user_info = extract_user_info_from_cookies(cookie_str)
        if isinstance(user_info, dict):
            bind_phone = user_info.get('bind_phone')
            if bind_phone:
                print(f"  [v] 获取到绑定手机号: {mask_phone(bind_phone)}")
            else:
                print(f"  [!] 未获取到绑定手机号")

        for attempt in range(1, MAX_RETRIES + 1):
            print(f"\n尝试第 {attempt}/{MAX_RETRIES} 次...")
            try:
                results = run_comment(cookie_str, bind_phone=bind_phone)

                if results.get('comment') is False:
                    if attempt < MAX_RETRIES:
                        print(f"评论失败，等待重试...")
                        time.sleep(10)
                        continue
                    else:
                        all_success = False
                break

            except Exception as e:
                print(f"第 {attempt} 次尝试出错: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(10)
                else:
                    all_success = False

    print(f"\n{'='*50}")
    if all_success:
        print("所有账号评论任务完成！")
    else:
        print("部分任务失败，请检查日志")

    return all_success


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
