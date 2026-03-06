import os
import random
import time
import functools
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger
from DrissionPage import ChromiumOptions, Chromium
from tabulate import tabulate
from curl_cffi import requests
from bs4 import BeautifulSoup
from notify import NotificationManager

ACCOUNT_SEPARATOR = "#"
MAX_WORKERS = 2


def retry_decorator(retries=3, min_delay=5, max_delay=10):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == retries - 1:  # 最后一次尝试
                        logger.error(f"函数 {func.__name__} 最终执行失败: {str(e)}")
                    logger.warning(
                        f"函数 {func.__name__} 第 {attempt + 1}/{retries} 次尝试失败: {str(e)}"
                    )
                    if attempt < retries - 1:
                        sleep_s = random.uniform(min_delay, max_delay)
                        logger.info(
                            f"将在 {sleep_s:.2f}s 后重试 ({min_delay}-{max_delay}s 随机延迟)"
                        )
                        time.sleep(sleep_s)
            return None

        return wrapper

    return decorator


os.environ.pop("DISPLAY", None)
os.environ.pop("DYLD_LIBRARY_PATH", None)

BROWSE_ENABLED = os.environ.get("BROWSE_ENABLED", "true").strip().lower() not in [
    "false",
    "0",
    "off",
]

HOME_URL = "https://linux.do/"
LOGIN_URL = "https://linux.do/login"
SESSION_URL = "https://linux.do/session"
CSRF_URL = "https://linux.do/session/csrf"


def parse_accounts():
    """
    解析环境变量，构建账号列表。支持 # 分隔多账号。
    按索引对齐：每个账号可同时拥有 Cookie 和账号密码，Cookie 优先，失败回退账号密码。
    示例：
      LINUXDO_COOKIES=cookie1##cookie3       （第2个为空，表示该账号无Cookie）
      LINUXDO_USERNAME=user1#user2#user3
      LINUXDO_PASSWORD=pass1#pass2#pass3
    """
    cookies_raw = os.environ.get("LINUXDO_COOKIES", "").strip()
    usernames_raw = os.environ.get("LINUXDO_USERNAME", "") or os.environ.get("USERNAME", "") or ""
    passwords_raw = os.environ.get("LINUXDO_PASSWORD", "") or os.environ.get("PASSWORD", "") or ""

    cookies_list = [c.strip() for c in cookies_raw.split(ACCOUNT_SEPARATOR)] if cookies_raw else []
    usernames_list = [u.strip() for u in usernames_raw.split(ACCOUNT_SEPARATOR)] if usernames_raw else []
    passwords_list = [p.strip() for p in passwords_raw.split(ACCOUNT_SEPARATOR)] if passwords_raw else []

    max_len = max(len(cookies_list), len(usernames_list), len(passwords_list))
    if not max_len:
        return []

    accounts = []
    for i in range(max_len):
        cookie = cookies_list[i] if i < len(cookies_list) else ""
        username = usernames_list[i] if i < len(usernames_list) else ""
        password = passwords_list[i] if i < len(passwords_list) else ""

        if not cookie and not (username and password):
            logger.warning(f"账号 {i + 1} 既无 Cookie 也无有效的账号密码，跳过")
            continue

        accounts.append({
            "cookies": cookie or None,
            "username": username or None,
            "password": password or None,
        })

    return accounts


class LinuxDoBrowser:
    def __init__(self, username=None, password=None, cookies=None) -> None:
        self.username = username
        self.password = password
        self.cookies = cookies
        self.account_label = username or "Cookie用户"

        from sys import platform

        if platform == "linux" or platform == "linux2":
            platformIdentifier = "X11; Linux x86_64"
        elif platform == "darwin":
            platformIdentifier = "Macintosh; Intel Mac OS X 10_15_7"
        elif platform == "win32":
            platformIdentifier = "Windows NT 10.0; Win64; x64"
        else:
            platformIdentifier = "X11; Linux x86_64"

        co = (
            ChromiumOptions()
            .headless(True)
            .incognito(True)
            .set_argument("--no-sandbox")
        )
        co.set_user_agent(
            f"Mozilla/5.0 ({platformIdentifier}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        self.browser = Chromium(co)
        self.page = self.browser.new_tab()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )
        # 初始化通知管理器
        self.notifier = NotificationManager()

    @staticmethod
    def parse_cookie_string(cookie_str: str) -> list[dict]:
        """
        解析浏览器复制的 Cookie 字符串格式: "name1=value1; name2=value2"
        返回 DrissionPage 所需的 cookie 列表格式。
        """
        cookies = []
        for part in cookie_str.strip().split(";"):
            part = part.strip()
            if "=" in part:
                name, _, value = part.partition("=")
                cookies.append(
                    {
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": ".linux.do",
                        "path": "/",
                    }
                )
        return cookies

    def login_with_cookies(self, cookie_str: str) -> bool:
        """使用手动设置的 Cookie 直接登录，跳过账号密码流程"""
        logger.info(f"[{self.account_label}] 检测到手动 Cookie，尝试 Cookie 登录...")
        dp_cookies = self.parse_cookie_string(cookie_str)
        if not dp_cookies:
            logger.error(f"[{self.account_label}] Cookie 解析失败或为空，无法使用 Cookie 登录")
            return False

        logger.info(f"[{self.account_label}] 成功解析 {len(dp_cookies)} 个 Cookie 条目")

        # 同步到 requests.Session，以便后续 API 请求（如 print_connect_info）使用
        for ck in dp_cookies:
            self.session.cookies.set(ck["name"], ck["value"], domain="linux.do")

        # 同步到 DrissionPage
        self.page.set.cookies(dp_cookies)
        logger.info(f"[{self.account_label}] Cookie 设置完成，导航至 linux.do...")
        self.page.get(HOME_URL)
        time.sleep(5)

        # 验证登录状态
        try:
            user_ele = self.page.ele("@id=current-user")
        except Exception as e:
            logger.warning(f"[{self.account_label}] Cookie 登录验证异常: {str(e)}")
            return True
        if not user_ele:
            if "avatar" in self.page.html:
                logger.info(f"[{self.account_label}] Cookie 登录验证成功 (通过 avatar)")
                return True
            logger.error(f"[{self.account_label}] Cookie 登录验证失败 (未找到 current-user)，Cookie 可能已过期")
            return False
        else:
            logger.info(f"[{self.account_label}] Cookie 登录验证成功")
            return True

    def login(self):
        logger.info(f"[{self.account_label}] 开始账号密码登录")
        # Step 1: Get CSRF Token
        logger.info(f"[{self.account_label}] 获取 CSRF token...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": LOGIN_URL,
        }
        resp_csrf = self.session.get(CSRF_URL, headers=headers, impersonate="firefox135")
        if resp_csrf.status_code != 200:
            logger.error(f"[{self.account_label}] 获取 CSRF token 失败: {resp_csrf.status_code}")
            return False
        csrf_data = resp_csrf.json()
        csrf_token = csrf_data.get("csrf")
        logger.info(f"[{self.account_label}] CSRF Token obtained: {csrf_token[:10]}...")

        # Step 2: Login
        logger.info(f"[{self.account_label}] 正在登录...")
        headers.update(
            {
                "X-CSRF-Token": csrf_token,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": "https://linux.do",
            }
        )

        data = {
            "login": self.username,
            "password": self.password,
            "second_factor_method": "1",
            "timezone": "Asia/Shanghai",
        }

        try:
            resp_login = self.session.post(
                SESSION_URL, data=data, impersonate="chrome136", headers=headers
            )

            if resp_login.status_code == 200:
                response_json = resp_login.json()
                if response_json.get("error"):
                    logger.error(f"[{self.account_label}] 登录失败: {response_json.get('error')}")
                    return False
                logger.info(f"[{self.account_label}] 登录成功!")
            else:
                logger.error(f"[{self.account_label}] 登录失败，状态码: {resp_login.status_code}")
                logger.error(resp_login.text)
                return False
        except Exception as e:
            logger.error(f"[{self.account_label}] 登录请求异常: {e}")
            return False

        # Step 3: Pass cookies to DrissionPage
        logger.info(f"[{self.account_label}] 同步 Cookie 到 DrissionPage...")

        cookies_dict = self.session.cookies.get_dict()

        dp_cookies = []
        for name, value in cookies_dict.items():
            dp_cookies.append(
                {
                    "name": name,
                    "value": value,
                    "domain": ".linux.do",
                    "path": "/",
                }
            )

        self.page.set.cookies(dp_cookies)

        logger.info(f"[{self.account_label}] Cookie 设置完成，导航至 linux.do...")
        self.page.get(HOME_URL)

        time.sleep(5)
        try:
            user_ele = self.page.ele("@id=current-user")
        except Exception as e:
            logger.warning(f"[{self.account_label}] 登录验证失败: {str(e)}")
            return True
        if not user_ele:
            # Fallback check for avatar
            if "avatar" in self.page.html:
                logger.info(f"[{self.account_label}] 登录验证成功 (通过 avatar)")
                return True
            logger.error(f"[{self.account_label}] 登录验证失败 (未找到 current-user)")
            return False
        else:
            logger.info(f"[{self.account_label}] 登录验证成功")
            return True

    def click_topic(self):
        topic_list = self.page.ele("@id=list-area").eles(".:title")
        if not topic_list:
            logger.error(f"[{self.account_label}] 未找到主题帖")
            return False
        logger.info(f"[{self.account_label}] 发现 {len(topic_list)} 个主题帖，随机选择1个")
        for topic in random.sample(topic_list, 1):
            self.click_one_topic(topic.attr("href"))
        return True

    @retry_decorator()
    def click_one_topic(self, topic_url):
        new_page = self.browser.new_tab()
        try:
            new_page.get(topic_url)
            if random.random() < 0.3:  # 0.3 * 30 = 9
                self.click_like(new_page)
            self.browse_post(new_page)
        finally:
            try:
                new_page.close()
            except Exception:
                pass

    def browse_post(self, page):
        prev_url = None
        # 开始自动滚动，最多滚动20次
        for _ in range(20):
            # 随机滚动一段距离
            scroll_distance = random.randint(550, 650)  # 随机滚动 550-650 像素
            logger.info(f"[{self.account_label}] 向下滚动 {scroll_distance} 像素...")
            page.run_js(f"window.scrollBy(0, {scroll_distance})")
            logger.info(f"[{self.account_label}] 已加载页面: {page.url}")

            if random.random() < 0.03:  # 33 * 4 = 132
                logger.success(f"[{self.account_label}] 随机退出浏览")
                break

            # 检查是否到达页面底部
            at_bottom = page.run_js(
                "window.scrollY + window.innerHeight >= document.body.scrollHeight"
            )
            current_url = page.url
            if current_url != prev_url:
                prev_url = current_url
            elif at_bottom and prev_url == current_url:
                logger.success(f"[{self.account_label}] 已到达页面底部，退出浏览")
                break

            # 动态随机等待
            wait_time = random.uniform(2, 4)  # 随机等待 2-4 秒
            logger.info(f"[{self.account_label}] 等待 {wait_time:.2f} 秒...")
            time.sleep(wait_time)

    def run(self):
        logger.info(f"========== 开始执行账号: {self.account_label} ==========")
        try:
            # 优先使用手动 Cookie 登录，没有再使用账号密码
            if self.cookies:
                login_res = self.login_with_cookies(self.cookies)
                if not login_res and self.username and self.password:
                    logger.warning(f"[{self.account_label}] Cookie 登录失败，尝试账号密码登录...")
                    login_res = self.login()
            elif self.username and self.password:
                login_res = self.login()
            else:
                logger.error(f"[{self.account_label}] 无可用的登录凭据")
                return False

            if not login_res:  # 登录
                logger.warning(f"[{self.account_label}] 登录验证失败")
                return False

            if BROWSE_ENABLED:
                click_topic_res = self.click_topic()  # 点击主题
                if not click_topic_res:
                    logger.error(f"[{self.account_label}] 点击主题失败，程序终止")
                    return False
                logger.info(f"[{self.account_label}] 完成浏览任务")
            connect_info = self.get_connect_info()  # 获取连接信息
            self.send_notifications(BROWSE_ENABLED, connect_info)  # 发送通知
            logger.info(f"========== 账号 {self.account_label} 执行完毕 ==========")
            return True
        finally:
            try:
                self.page.close()
            except Exception:
                pass
            try:
                self.browser.quit()
            except Exception:
                pass

    def click_like(self, page):
        try:
            # 专门查找未点赞的按钮
            like_button = page.ele(".discourse-reactions-reaction-button")
            if like_button:
                logger.info(f"[{self.account_label}] 找到未点赞的帖子，准备点赞")
                like_button.click()
                logger.info(f"[{self.account_label}] 点赞成功")
                time.sleep(random.uniform(1, 2))
            else:
                logger.info(f"[{self.account_label}] 帖子可能已经点过赞了")
        except Exception as e:
            logger.error(f"[{self.account_label}] 点赞失败: {str(e)}")

    def get_connect_info(self):
        """使用浏览器获取 connect.linux.do 等级信息（JS 渲染页面）"""
        logger.info(f"[{self.account_label}] 获取连接信息")
        connect_page = None
        try:
            connect_page = self.browser.new_tab()
            connect_page.get("https://connect.linux.do/")
            time.sleep(5)

            info = []

            # 解析标题和状态（如 "信任级别 3 的要求" / "已达到"）
            try:
                title_ele = connect_page.ele(".card-title")
                badge_ele = connect_page.ele(".badge")
                if title_ele and badge_ele:
                    self.trust_level_title = title_ele.text.strip()
                    self.trust_level_status = badge_ele.text.strip()
                    logger.info(f"[{self.account_label}] {self.trust_level_title}: {self.trust_level_status}")
            except Exception:
                self.trust_level_title = ""
                self.trust_level_status = ""

            # 活跃程度：.tl3-ring 内含 .tl3-ring-current / .tl3-ring-target / .tl3-ring-label
            for ring in connect_page.eles(".tl3-ring"):
                try:
                    label = ring.ele(".tl3-ring-label").text.strip()
                    current = ring.ele(".tl3-ring-current").text.strip()
                    target = ring.ele(".tl3-ring-target").text.replace("/", "").strip()
                    info.append([label, current, target])
                except Exception:
                    pass

            # 互动参与：.tl3-bar-item 内含 .tl3-bar-label / .tl3-bar-nums
            for bar in connect_page.eles(".tl3-bar-item"):
                try:
                    label = bar.ele(".tl3-bar-label").text.strip()
                    nums = bar.ele(".tl3-bar-nums").text.strip()
                    parts = nums.split("/")
                    if len(parts) == 2:
                        info.append([label, parts[0].strip(), parts[1].strip()])
                except Exception:
                    pass

            # 合规记录：.tl3-quota-card 内含 .tl3-quota-label / .tl3-quota-nums
            for quota in connect_page.eles(".tl3-quota-card"):
                try:
                    label = quota.ele(".tl3-quota-label").text.strip()
                    nums = quota.ele(".tl3-quota-nums").text.strip()
                    parts = nums.split("/")
                    if len(parts) == 2:
                        info.append([label, parts[0].strip(), parts[1].strip()])
                except Exception:
                    pass

            logger.info(f"[{self.account_label}] --------------Connect Info-----------------")
            if info:
                logger.info("\n" + tabulate(info, headers=["项目", "当前", "要求"], tablefmt="pretty"))
            else:
                logger.warning(f"[{self.account_label}] 未获取到等级信息（新号可能为空）")
            return info
        except Exception as e:
            logger.error(f"[{self.account_label}] 获取连接信息失败: {str(e)}")
            return []
        finally:
            try:
                if connect_page:
                    connect_page.close()
            except Exception:
                pass

    def send_notifications(self, browse_enabled, connect_info):
        """发送签到通知，包含等级信息"""
        status_msg = f"✅每日登录成功: {self.account_label}"
        if browse_enabled:
            status_msg += " + 浏览任务完成"

        if hasattr(self, "trust_level_title") and self.trust_level_title:
            status_msg += f"\n\n📋 <b>{self.trust_level_title}</b>: {self.trust_level_status}"

        if connect_info:
            status_msg += "\n\n📊 <b>等级信息</b>\n"
            for project, current, requirement in connect_info:
                status_msg += f"  {project}: {current} / {requirement}\n"
        else:
            status_msg += "\n\n📊 未获取到信息或等级未到2级以上"

        # 使用通知管理器发送所有通知
        self.notifier.send_all("LINUX DO", status_msg)


def run_account(account, index, total):
    """运行单个账号的签到任务"""
    label = account["username"] or f"Cookie账号{index}"
    logger.info(f"[{label}] 开始执行 ({index}/{total})")
    try:
        browser = LinuxDoBrowser(
            username=account["username"],
            password=account["password"],
            cookies=account["cookies"],
        )
        return browser.run()
    except Exception as e:
        logger.error(f"[{label}] 执行异常: {str(e)}")
        return False


if __name__ == "__main__":
    accounts = parse_accounts()
    if not accounts:
        print("未检测到任何账号配置。")
        print("请设置 LINUXDO_COOKIES（Cookie 登录，多账号用 # 分隔），")
        print("或同时设置 LINUXDO_USERNAME 和 LINUXDO_PASSWORD（账号密码登录，多账号用 # 分隔）")
        exit(1)

    logger.info(f"共检测到 {len(accounts)} 个账号，最大并发数: {MAX_WORKERS}")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(run_account, account, i + 1, len(accounts)): i
            for i, account in enumerate(accounts)
        }
        results = {}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                logger.error(f"账号 {idx + 1} 执行异常: {str(e)}")
                results[idx] = False

    # 汇总结果
    success = sum(1 for v in results.values() if v)
    fail = len(results) - success
    logger.info(f"========== 全部执行完毕: 成功 {success}, 失败 {fail} ==========")
