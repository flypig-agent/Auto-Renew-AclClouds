#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import time
import requests
from datetime import datetime, timedelta, timezone

from seleniumbase import SB
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    WebDriverException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from zoneinfo import ZoneInfo


# ============================================================
# 配置
# ============================================================

EMAIL = os.getenv("EMAIL") or os.getenv("ACL_EMAIL") or ""
PASSWORD = os.getenv("PASSWORD") or os.getenv("ACL_PASSWORD") or ""

TG_CHAT_ID = os.getenv("TG_CHAT_ID") or ""
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN") or ""

LOGIN_PATH = "/auth/login"
BASE_URL = "https://dash.aclclouds.com"
PROJECTS_URL = f"{BASE_URL}/dashboard/projects"


# ============================================================
# 北京时间
# ============================================================

def beijing_time_str():
    try:
        return datetime.now(
            ZoneInfo("Asia/Shanghai")
        ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now(
            timezone(timedelta(hours=8))
        ).strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# Telegram
# ============================================================

def send_telegram(message):
    if TG_BOT_TOKEN and TG_CHAT_ID:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"

        data = {
            "chat_id": TG_CHAT_ID,
            "text": message,
        }

        try:
            response = requests.post(
                url,
                data=data,
                timeout=10,
            )

            if response.ok:
                print(f"Telegram sent: {message[:80]}...")
            else:
                print(
                    f"Telegram发送失败: "
                    f"HTTP {response.status_code} "
                    f"{response.text[:300]}"
                )

        except Exception as e:
            print(f"Failed to send Telegram: {e}")

    else:
        print(f"[Telegram disabled] {message}")


# ============================================================
# URL / 登录状态
# ============================================================

def wait_for_url_change(sb, original_url, timeout=30):
    start_time = time.time()

    while time.time() - start_time < timeout:
        current_url = sb.get_current_url()

        if current_url != original_url:
            return True

        sb.sleep(0.5)

    raise Exception(
        f"等待 URL 变化超时 ({timeout}秒)，"
        f"当前仍为: {original_url}"
    )


def is_login_page(sb):
    return LOGIN_PATH in sb.get_current_url()


def is_logged_in(sb):
    current_url = sb.get_current_url()

    return (
        BASE_URL in current_url
        and LOGIN_PATH not in current_url
    )


# ============================================================
# Selenium 基础操作
# ============================================================

def scroll_to_selector(sb, selector):
    try:
        sb.scroll_to(selector)
        sb.sleep(0.2)
    except Exception:
        pass


def safe_click_element(sb, element, label):
    try:
        sb.driver.execute_script(
            """
            arguments[0].scrollIntoView({
                block: "center",
                inline: "center"
            });
            """,
            element,
        )

        sb.sleep(0.5)

        try:
            element.click()
            return True

        except (
            ElementClickInterceptedException,
            WebDriverException,
            StaleElementReferenceException,
        ) as e:

            print(
                f"{label} 普通点击失败，"
                f"改用 JavaScript 点击: {e}"
            )

        sb.driver.execute_script(
            "arguments[0].click();",
            element,
        )

        sb.sleep(0.5)

        return True

    except StaleElementReferenceException:
        print(
            f"{label} 元素已失效，"
            f"点击前需要重新定位"
        )

        return False

    except Exception as e:
        print(f"{label} 点击失败: {e}")
        return False


def element_text(element):
    try:
        return element.text.strip()
    except Exception:
        return ""


def unique_elements(elements):
    unique = []
    seen = set()

    for element in elements:
        element_id = getattr(element, "id", None)

        if element_id and element_id in seen:
            continue

        if element_id:
            seen.add(element_id)

        unique.append(element)

    return unique


def element_contains(parent, child):
    if parent == child:
        return True

    try:
        children = parent.find_elements(
            By.XPATH,
            ".//*",
        )

        return any(
            getattr(item, "id", None)
            == getattr(child, "id", None)
            for item in children
        )

    except Exception:
        return False


# ============================================================
# DOM 查询
# ============================================================

def find_elements(root, selector):
    if selector.startswith(("/", ".//")):
        by = By.XPATH
    else:
        by = By.CSS_SELECTOR

    return root.find_elements(by, selector)


# ============================================================
# Renew 按钮
# ============================================================

def find_renew_buttons(root):

    selectors = [
        ".projects-renew-btn",

        (
            './/button[contains('
            'translate(normalize-space(.), '
            '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
            '"abcdefghijklmnopqrstuvwxyz"), '
            '"renew")]'
        ),

        (
            './/button[contains('
            'translate(normalize-space(.), '
            '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
            '"abcdefghijklmnopqrstuvwxyz"), '
            '"reactivate")]'
        ),

        (
            './/*[(@role="button" or self::a) and '
            'contains(translate(normalize-space(.), '
            '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
            '"abcdefghijklmnopqrstuvwxyz"), '
            '"renew")]'
        ),

        (
            './/*[(@role="button" or self::a) and '
            'contains(translate(normalize-space(.), '
            '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
            '"abcdefghijklmnopqrstuvwxyz"), '
            '"reactivate")]'
        ),
    ]

    buttons = []

    for selector in selectors:
        try:
            buttons.extend(
                find_elements(root, selector)
            )
        except Exception:
            continue

    result = []

    for button in unique_elements(buttons):
        try:
            if element_text(button) or button.is_displayed():
                result.append(button)
        except Exception:
            pass

    return unique_elements(result)


# ============================================================
# 查找项目卡片
# ============================================================

def find_card_container_from_child(sb, child):
    return sb.driver.execute_script(
        """
        const start = arguments[0];

        let node = start;

        for (
            let i = 0;
            node && i < 10;
            i += 1,
            node = node.parentElement
        ) {

            const text =
                (node.innerText || "").trim();

            const cls =
                (node.className || "")
                .toString()
                .toLowerCase();

            const looksLikeProject =
                /renew|reactivate|suspended|expiry|expire|expires|valid|续期|重新激活|恢复|暂停|过期|到期/i
                .test(text);

            const looksLikeCard =
                /card|project|service|server|item|row/
                .test(cls);

            if (
                node !== start &&
                text.length > 20 &&
                (looksLikeProject || looksLikeCard)
            ) {
                return node;
            }
        }

        return start.parentElement || start;
        """,
        child,
    )


def dedupe_project_cards(cards):
    cards = unique_elements(cards)

    if not cards:
        return []

    keep = []

    for card in cards:

        card_text = element_text(card)

        if len(card_text) < 3:
            continue

        duplicate = False

        for kept in list(keep):

            kept_text = element_text(kept)

            if element_contains(kept, card):
                duplicate = True
                break

            if element_contains(card, kept):

                if len(card_text) > len(kept_text):
                    keep.remove(kept)

                else:
                    duplicate = True

                break

        if not duplicate:
            keep.append(card)

    deduped = []

    seen_signatures = set()

    for card in keep:

        text = element_text(card)

        name = ""

        for line in text.splitlines():

            line = line.strip()

            if (
                line
                and not re.search(
                    r"expires|renewal|renew|reactivate|"
                    r"suspended|expiry|expire|valid|"
                    r"续期|重新激活|恢复|暂停|过期|到期",
                    line,
                    re.I,
                )
            ):
                name = line
                break

        signature = (
            name.lower(),
            get_project_expiry(card).lower(),
        )

        if signature in seen_signatures:
            continue

        seen_signatures.add(signature)
        deduped.append(card)

    return deduped


def find_project_cards(sb):

    candidate_selectors = [
        ".projects-card",
        '[class*="projects-card"]',
        '[class*="project"][class*="card"]',
        '[class*="Project"][class*="Card"]',
        '[class*="service"][class*="card"]',
        '[class*="server"][class*="card"]',
        "article",
    ]

    cards = []

    keywords = [
        "renew",
        "reactivate",
        "suspended",
        "expiry",
        "expire",
        "valid",
        "续期",
        "重新激活",
        "恢复",
        "暂停",
        "过期",
        "到期",
    ]

    for selector in candidate_selectors:

        try:

            elements = sb.driver.find_elements(
                By.CSS_SELECTOR,
                selector,
            )

            for card in elements:

                text = element_text(card).lower()

                if any(
                    keyword in text
                    for keyword in keywords
                ):
                    cards.append(card)

        except Exception:
            continue

    if cards:
        return dedupe_project_cards(cards)

    # --------------------------------------------------------
    # 根据 Renew 按钮反向寻找卡片
    # --------------------------------------------------------

    for button in find_renew_buttons(sb.driver):

        try:
            cards.append(
                find_card_container_from_child(
                    sb,
                    button,
                )
            )
        except Exception:
            continue

    if cards:
        return dedupe_project_cards(cards)

    # --------------------------------------------------------
    # 根据 expiry / expire / valid 查找
    # --------------------------------------------------------

    expiry_xpath = (
        '//*[contains('
        'translate(normalize-space(.), '
        '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
        '"abcdefghijklmnopqrstuvwxyz"), '
        '"expiry") '
        'or contains('
        'translate(normalize-space(.), '
        '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
        '"abcdefghijklmnopqrstuvwxyz"), '
        '"expire") '
        'or contains('
        'translate(normalize-space(.), '
        '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
        '"abcdefghijklmnopqrstuvwxyz"), '
        '"valid") '
        'or contains(normalize-space(.), "过期") '
        'or contains(normalize-space(.), "到期")]'
    )

    try:
        elements = sb.driver.find_elements(
            By.XPATH,
            expiry_xpath,
        )
    except Exception:
        elements = []

    for elem in elements:

        try:
            cards.append(
                find_card_container_from_child(
                    sb,
                    elem,
                )
            )
        except Exception:
            continue

    return dedupe_project_cards(cards)


# ============================================================
# 日期 / 剩余时间
# ============================================================

def extract_date_like(text):

    if not text:
        return ""

    patterns = [

        r"\d{4}[-/]\d{1,2}[-/]\d{1,2}"
        r"(?:\s+\d{1,2}:\d{2}"
        r"(?::\d{2})?)?",

        r"\d{1,2}[-/]\d{1,2}[-/]\d{4}"
        r"(?:\s+\d{1,2}:\d{2}"
        r"(?::\d{2})?)?",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
        )

        if match:
            return match.group(0)

    return ""


def extract_duration_like(text):

    if not text:
        return ""

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    for idx, line in enumerate(lines):

        if re.search(
            r"expires\s+in|剩余|还有",
            line,
            re.I,
        ):

            if idx + 1 < len(lines):
                return (
                    f"{line} "
                    f"{lines[idx + 1]}"
                )

    match = re.search(
        r"(?:expires\s+in\s*)?"
        r"\d+\s*"
        r"(?:d|day|days|j|天|日)"
        r"\s*\d*\s*"
        r"(?:h|hour|hours|小时)?",
        text,
        re.I,
    )

    if match:
        return match.group(0).strip()

    match = re.search(
        r"\d+\s*"
        r"(?:h|hour|hours|小时)",
        text,
        re.I,
    )

    if match:
        return match.group(0).strip()

    return ""


# ============================================================
# 项目名称 / 到期时间
# ============================================================

def get_project_name(card, idx):

    selectors = [
        ".projects-card-title",
        "h1",
        "h2",
        "h3",
        "h4",
        '[class*="title"]',
        '[class*="name"]',
    ]

    for selector in selectors:

        try:

            elements = card.find_elements(
                By.CSS_SELECTOR,
                selector,
            )

            for elem in elements:

                text = element_text(elem)

                if (
                    text
                    and len(text) <= 80
                    and "renew" not in text.lower()
                    and "expiry" not in text.lower()
                    and not extract_duration_like(text)
                ):
                    return text

        except Exception:
            continue

    for line in element_text(card).splitlines():

        line = line.strip()

        if (
            line
            and len(line) <= 80
            and not extract_duration_like(line)
            and not re.search(
                r"renew|reactivate|suspended|"
                r"expiry|expire|valid|"
                r"续期|重新激活|恢复|暂停|过期|到期",
                line,
                re.I,
            )
        ):
            return line

    return f"项目 #{idx}"


def get_project_expiry(card):

    selectors = [
        ".projects-expiry-value",
        '[class*="expiry"]',
        '[class*="expire"]',
        '[class*="Expires"]',

        (
            './/*[contains('
            'translate(normalize-space(.), '
            '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
            '"abcdefghijklmnopqrstuvwxyz"), '
            '"expiry")]'
        ),

        (
            './/*[contains('
            'translate(normalize-space(.), '
            '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
            '"abcdefghijklmnopqrstuvwxyz"), '
            '"expire")]'
        ),

        (
            './/*[contains('
            'translate(normalize-space(.), '
            '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
            '"abcdefghijklmnopqrstuvwxyz"), '
            '"valid")]'
        ),

        (
            './/*[contains(normalize-space(.), "过期") '
            'or contains(normalize-space(.), "到期")]'
        ),
    ]

    for selector in selectors:

        try:

            elements = find_elements(
                card,
                selector,
            )

            for elem in elements:

                text = element_text(elem)

                date_text = extract_date_like(text)

                if date_text:
                    return date_text

                duration_text = extract_duration_like(text)

                if duration_text:
                    return duration_text

                if text and len(text) <= 120:
                    return text

        except Exception:
            continue

    card_text = element_text(card)

    return (
        extract_date_like(card_text)
        or extract_duration_like(card_text)
        or "未知"
    )


# ============================================================
# 续期提示
# ============================================================

def get_renewal_available_note(card):

    if not card:
        return ""

    text = element_text(card)

    patterns = [
        r"Renewal\s+will\s+be\s+available[^\n]*",
        r"可续期[^\n]*",
        r"续期[^\n]*前[^\n]*",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.I,
        )

        if match:
            return match.group(0).strip()

    return ""


def get_renew_note(card):

    if not card:
        return "未到续期时间"

    selectors = [
        ".projects-renew-note",
        '[class*="renew-note"]',
        '[class*="note"]',
        '[class*="tip"]',
    ]

    for selector in selectors:

        try:

            elements = card.find_elements(
                By.CSS_SELECTOR,
                selector,
            )

            for elem in elements:

                text = element_text(elem)

                if text:
                    return text

        except Exception:
            continue

    return "未到续期时间"


def get_action_button_label(button):

    text = element_text(button)
    lowered = text.lower()

    if (
        "reactivate" in lowered
        or "重新激活" in text
        or "恢复" in text
    ):
        return "Reactivate"

    return "Renew"


# ============================================================
# 根据索引获取卡片
# ============================================================

def get_card_by_index(sb, idx):

    cards = find_project_cards(sb)

    if idx <= len(cards):
        return cards[idx - 1]

    return None


# ============================================================
# 等待续期结果
# ============================================================

def wait_for_renew_result(sb, idx, timeout=30):

    start_time = time.time()

    while time.time() - start_time < timeout:

        try:

            success_modals = sb.driver.find_elements(
                By.XPATH,
                '//div[contains(@class, "modal") and '
                'contains(translate(., '
                '"ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
                '"abcdefghijklmnopqrstuvwxyz"), '
                '"successfully")]',
            )

            if any(
                modal.is_displayed()
                for modal in success_modals
            ):

                card = get_card_by_index(
                    sb,
                    idx,
                )

                return (
                    True,
                    get_project_expiry(card)
                    if card
                    else "未知",
                    "success modal",
                )

            card = get_card_by_index(
                sb,
                idx,
            )

            if card:

                renewal_note = (
                    get_renewal_available_note(card)
                )

                renew_buttons = find_renew_buttons(
                    card
                )

                if renewal_note and not renew_buttons:

                    return (
                        True,
                        get_project_expiry(card),
                        renewal_note,
                    )

        except Exception as e:

            print(
                f"检查续期结果时暂时失败: {e}"
            )

        sb.sleep(1)

    card = get_card_by_index(
        sb,
        idx,
    )

    note = (
        get_renewal_available_note(card)
        if card
        else ""
    )

    expiry = (
        get_project_expiry(card)
        if card
        else "未知"
    )

    return (
        False,
        expiry,
        note,
    )


# ============================================================
# 验证码 / Anti-bot
# ============================================================

def has_renew_antibot_modal(sb):

    selectors = [
        '//div[contains(., "Anti-bot confirmation")]',
        '//div[contains(., "Confirm you are human")]',
        '//div[contains(., "I am not a robot")]',
    ]

    for selector in selectors:

        try:

            if any(
                elem.is_displayed()
                for elem in sb.driver.find_elements(
                    By.XPATH,
                    selector,
                )
            ):
                return True

        except Exception:
            continue

    return False


def handle_captcha_challenge(
    sb,
    label="验证码",
    timeout=20,
):
    """
    处理图形验证码挑战。
    """

    start_time = time.time()

    challenge = None

    challenge_selectors = [
        ".auth-captcha-challenge",
        ".auth-capcha-challenge",

        (
            '//*[contains(@class, "captcha") '
            'and contains(@class, "challenge")]'
        ),

        (
            '//*[contains(@aria-label, "Click on ") '
            'or contains(@aria-label, "Select ") '
            'or contains(@class, "challenge")]'
        ),
    ]

    def get_challenge():

        for selector in challenge_selectors:

            try:

                if selector.startswith("/"):

                    elems = sb.driver.find_elements(
                        By.XPATH,
                        selector,
                    )

                    for elem in elems:

                        if elem.is_displayed():
                            return elem

                else:

                    elem = sb.wait_for_element_visible(
                        selector,
                        timeout=1,
                    )

                    if elem and elem.is_displayed():
                        return elem

            except Exception:
                continue

        return None

    # --------------------------------------------------------
    # 等待验证码
    # --------------------------------------------------------

    while time.time() - start_time < timeout:

        challenge = get_challenge()

        if challenge:

            print(
                f"{label} 检测到图形验证码挑战"
            )

            break

        try:

            checkbox = sb.driver.find_element(
                By.CSS_SELECTOR,
                'div.auth-captcha-inner[role="checkbox"]',
            )

            if (
                checkbox.get_attribute(
                    "aria-checked"
                )
                == "true"
            ):

                print(
                    f"{label} 验证复选框已勾选，"
                    f"验证码流程已完成"
                )

                return True

        except Exception:
            pass

        sb.sleep(0.3)

    if not challenge:

        print(
            f"{label} 等待验证码挑战加载超时"
        )

        return False

    # --------------------------------------------------------
    # 获取目标
    # --------------------------------------------------------

    target = ""

    try:

        prompt = challenge.find_element(
            By.CSS_SELECTOR,
            ".auth-captcha-prompt strong",
        )

        target = prompt.text.strip()

    except Exception:
        pass

    if not target:

        try:

            prompt = challenge.find_element(
                By.CSS_SELECTOR,
                ".auth-capcha-prompt strong",
            )

            target = prompt.text.strip()

        except Exception:
            pass

    if not target:

        try:

            aria_label = (
                challenge.get_attribute(
                    "aria-label"
                )
                or ""
            )

            if "Click on " in aria_label:
                target = aria_label.split(
                    "Click on ",
                    1,
                )[-1].strip()

        except Exception:
            pass

    print(
        f"{label} 目标文本: "
        f"{target or '未识别'}"
    )

    # --------------------------------------------------------
    # 获取选项
    # --------------------------------------------------------

    option_selectors = [
        ".auth-captcha-option",
        ".auth-capcha-option",
        ".//button",
        ".//a",
        './/div[@role="button"]',
    ]

    def get_options(challenge_elem):

        for sel in option_selectors:

            try:

                if sel.startswith("."):

                    elems = challenge_elem.find_elements(
                        By.XPATH,
                        sel,
                    )

                else:

                    elems = challenge_elem.find_elements(
                        By.CSS_SELECTOR,
                        sel,
                    )

                if elems:

                    return [
                        elem
                        for elem in elems
                        if elem.is_displayed()
                        and elem.is_enabled()
                    ]

            except Exception:
                continue

        return []

    options = get_options(challenge)

    if not options:

        print(
            f"{label} 未找到可点击的选项"
        )

        return False

    # --------------------------------------------------------
    # 尝试找到匹配目标
    # --------------------------------------------------------

    attempts = 0
    max_attempts = 8

    while attempts < max_attempts:

        challenge = get_challenge()

        if not challenge:
            return False

        options = get_options(
            challenge
        )

        if not options:

            print(
                f"{label} 当前挑战没有可点击选项，"
                f"重试中..."
            )

            attempts += 1
            sb.sleep(0.8)
            continue

        current_target = ""

        try:

            prompt = challenge.find_element(
                By.CSS_SELECTOR,
                ".auth-captcha-prompt strong",
            )

            current_target = prompt.text.strip()

        except Exception:
            pass

        if not current_target:

            try:

                aria_label = (
                    challenge.get_attribute(
                        "aria-label"
                    )
                    or ""
                )

                if "Click on " in aria_label:

                    current_target = (
                        aria_label.split(
                            "Click on ",
                            1,
                        )[-1]
                        .strip()
                    )

            except Exception:
                pass

        candidate = None

        if target:

            for opt in options:

                opt_text = (
                    opt.text or ""
                ).strip()

                if not opt_text:

                    try:

                        img = opt.find_element(
                            By.TAG_NAME,
                            "img",
                        )

                        opt_text = (
                            img.get_attribute(
                                "alt"
                            )
                            or ""
                        ).strip()

                    except Exception:
                        pass

                if not opt_text:

                    try:

                        opt_text = (
                            opt.get_attribute(
                                "aria-label"
                            )
                            or ""
                        ).strip()

                    except Exception:
                        pass

                if (
                    target.lower()
                    in opt_text.lower()
                ):
                    candidate = opt
                    break

        # ----------------------------------------------------
        # 找不到精确目标时使用第一个选项
        # ----------------------------------------------------

        if candidate is None:
            candidate = options[0]

        print(
            f"{label} 点击候选选项 "
            f"#{attempts + 1} ..."
        )

        clicked = safe_click_element(
            sb,
            candidate,
            f"{label} 选项候选",
        )

        if not clicked:

            attempts += 1
            sb.sleep(0.8)
            continue

        sb.sleep(1.2)

        # ----------------------------------------------------
        # 检查是否完成
        # ----------------------------------------------------

        try:

            checkbox = sb.driver.find_element(
                By.CSS_SELECTOR,
                'div.auth-captcha-inner[role="checkbox"]',
            )

            if (
                checkbox.get_attribute(
                    "aria-checked"
                )
                == "true"
            ):

                print(
                    f"{label} 验证复选框已勾选，"
                    f"验证码流程已完成"
                )

                return True

        except Exception:
            pass

        if not get_challenge():

            print(
                f"{label} 挑战已消失，验证完成"
            )

            return True

        attempts += 1

    print(
        f"{label} 多次尝试后仍未完成验证码"
    )

    return False


def click_captcha_checkbox(
    sb,
    label="验证码",
    timeout=10,
):
    """
    点击 ACLClouds 页面上的人机验证复选框。
    """

    selectors = [
        'div.auth-captcha-inner[role="checkbox"]',

        (
            '//div[contains(., "Anti-bot confirmation")]'
            '//*[@role="checkbox"]'
        ),

        (
            '//div[contains(., "I am not a robot")]'
            '//*[@role="checkbox"]'
        ),

        (
            '//div[contains(@class, "modal") '
            'and contains(., "Secured by ACLClouds")]'
            '//*[@role="checkbox"]'
        ),
    ]

    last_error = None

    clicked = False
    selector = None

    for candidate in selectors:

        try:

            sb.wait_for_element_visible(
                candidate,
                timeout=timeout,
            )

            scroll_to_selector(
                sb,
                candidate,
            )

            sb.uc_click(candidate)

            sb.sleep(1)

            selector = candidate
            clicked = True

            break

        except Exception as e:

            last_error = e
            continue

    if not clicked:

        print(
            f"{label} 点击复选框失败: "
            f"{last_error}"
        )

        return False

    # 给验证码加载时间
    sb.sleep(5)

    captcha_ok = handle_captcha_challenge(
        sb,
        label,
        timeout=20,
    )

    if not captcha_ok:

        print(
            f"{label} 验证流程未完成，"
            f"等待状态仍未确认。"
        )

        return False

    try:

        checked = sb.get_attribute(
            selector,
            "aria-checked",
        )

        if checked == "true":

            print(
                f"{label} 验证通过"
            )

            return True

        print(
            f"{label} 验证未完成，"
            f"当前状态: {checked}"
        )

        return False

    except Exception:
        return False


# ============================================================
# 续期 Anti-bot
# ============================================================

def handle_renew_antibot(
    sb,
    project_name,
):
    """
    Renew 后如果弹出 Anti-bot confirmation，
    则点击确认。
    """

    modal_selectors = [
        '//div[contains(., "Anti-bot confirmation")]',
        '//div[contains(., "Confirm you are human")]',
        '//div[contains(., "I am not a robot")]',
    ]

    for selector in modal_selectors:

        try:

            sb.wait_for_element_visible(
                selector,
                timeout=5,
            )

            print(
                f"[{project_name}] "
                f"检测到续期人机验证窗口"
            )

            return click_captcha_checkbox(
                sb,
                "续期人机验证",
                timeout=5,
            )

        except Exception:
            continue

    print(
        f"[{project_name}] "
        f"未检测到续期人机验证窗口，"
        f"继续等待续期结果"
    )

    return False


# ============================================================
# 输入框
# ============================================================

def js_set_input_value(
    sb,
    selector,
    value,
):

    return sb.execute_script(
        """
        const el =
            document.querySelector(arguments[0]);

        if (!el) return false;

        el.focus();

        el.value = arguments[1];

        el.dispatchEvent(
            new Event("input", {
                bubbles: true
            })
        );

        el.dispatchEvent(
            new Event("change", {
                bubbles: true
            })
        );

        el.dispatchEvent(
            new Event("blur", {
                bubbles: true
            })
        );

        return true;
        """,
        selector,
        value,
    )


def fill_input(
    sb,
    selector,
    value,
    label,
    timeout=15,
):

    sb.wait_for_element_visible(
        selector,
        timeout=timeout,
    )

    scroll_to_selector(
        sb,
        selector,
    )

    sb.click(selector)

    sb.clear(selector)

    sb.type(
        selector,
        value,
    )

    entered_value = sb.get_value(
        selector
    )

    if label == "密码":

        print(
            f"{label}输入框当前值长度: "
            f"{len(entered_value)}"
        )

    else:

        print(
            f"{label}输入框当前值: "
            f"'{entered_value}'"
        )

    if entered_value != value:

        print(
            f"{label}输入未生效，"
            f"使用 JavaScript 强制赋值"
            f"并触发事件"
        )

        js_set_input_value(
            sb,
            selector,
            value,
        )

        entered_value = sb.get_value(
            selector
        )

        if label == "密码":

            print(
                f"JS 赋值后{label}长度: "
                f"{len(entered_value)}"
            )

        else:

            print(
                f"JS 赋值后{label}值: "
                f"'{entered_value}'"
            )

    return entered_value == value


# ============================================================
# 登录
# ============================================================

def login(sb, email, password):
    """
    执行登录，返回是否成功。

    注意：
    不再使用固定页面标题判断登录成功。

    ACLClouds 根据语言可能显示：

        Home | ACLClouds
        Accueil | ACLClouds

    因此只判断是否已经离开 /auth/login。
    """

    print("开始登录流程...")

    # --------------------------------------------------------
    # 填写邮箱
    # --------------------------------------------------------

    if not fill_input(
        sb,
        "#username",
        email,
        "邮箱",
    ):

        print(
            "⚠️ 邮箱仍未能正确填入，"
            "可能页面有动态行为。"
        )

    # --------------------------------------------------------
    # 填写密码
    # --------------------------------------------------------

    if not fill_input(
        sb,
        "#password",
        password,
        "密码",
    ):

        print(
            "⚠️ 密码仍未能正确填入。"
        )

    # --------------------------------------------------------
    # 验证码
    # --------------------------------------------------------

    captcha_ok = click_captcha_checkbox(
        sb,
        "登录验证码",
    )

    if not captcha_ok:

        print(
            "⚠️ 登录验证码未完成，"
            "暂不点击登录按钮，"
            "避免直接提交。"
        )

        return False

    sb.sleep(1)

    # --------------------------------------------------------
    # 点击登录按钮
    # --------------------------------------------------------

    login_page_url = sb.get_current_url()

    clicked = False

    login_selectors = [
        'button[type="submit"]',
        "div.auth-submit-btn",

        '//button[contains('
        'normalize-space(.), "Sign in")]',

        '//button[contains('
        'normalize-space(.), "Log in")]',

        '//div[contains('
        'normalize-space(.), "Sign in") ]',

        '//div[contains('
        'normalize-space(.), "Log in") ]',
    ]

    for selector in login_selectors:

        try:

            sb.wait_for_element_visible(
                selector,
                timeout=5,
            )

            scroll_to_selector(
                sb,
                selector,
            )

            try:

                sb.click(selector)

            except Exception as e:

                print(
                    f"普通点击失败，"
                    f"尝试 JS 点击: {e}"
                )

                elements = find_elements(
                    sb.driver,
                    selector,
                )

                if not elements:
                    raise Exception(
                        "没有找到登录按钮"
                    )

                sb.driver.execute_script(
                    "arguments[0].click();",
                    elements[0],
                )

            clicked = True

            print(
                f"点击登录按钮使用: "
                f"{selector}"
            )

            break

        except Exception as e:

            print(
                f"选择器 {selector} 失败: "
                f"{e}"
            )

    if not clicked:

        print(
            "❌ 所有登录按钮选择器均失败"
        )

        return False

    # --------------------------------------------------------
    # 等待登录结果
    # --------------------------------------------------------

    try:

        start_time = time.time()

        login_success = False

        while time.time() - start_time < 30:

            current_url = (
                sb.get_current_url()
            )

            # 最可靠的判断：
            # 已经离开登录页
            if "/auth/login" not in current_url:

                login_success = True
                break

            # ------------------------------------------------
            # 某些情况下 URL 可能不立即变化，
            # 再检查页面内容
            # ------------------------------------------------

            try:

                page_text = (
                    sb.driver
                    .find_element(
                        By.TAG_NAME,
                        "body",
                    )
                    .text
                    .lower()
                )

                logged_keywords = [
                    "dashboard",
                    "projects",
                    "project",
                    "logout",
                    "sign out",
                    "déconnexion",
                    "projets",
                ]

                if any(
                    keyword in page_text
                    for keyword in logged_keywords
                ):

                    login_success = True
                    break

            except Exception:
                pass

            sb.sleep(1)

        # ----------------------------------------------------
        # 登录成功
        # ----------------------------------------------------

        if login_success:

            current_url = (
                sb.get_current_url()
            )

            current_title = (
                sb.get_title()
            )

            print("✅ 登录成功！")
            print(
                f"当前 URL: {current_url}"
            )
            print(
                f"当前标题: {current_title}"
            )

            # 不再使用：
            #
            # sb.assert_title(
            #     "Home | ACLClouds"
            # )
            #
            # 因为法语页面可能返回：
            #
            # Accueil | ACLClouds

            return True

        # ----------------------------------------------------
        # 登录失败
        # ----------------------------------------------------

        error_msg = ""

        error_selectors = [
            ".auth-error-text",
            ".alert-danger",
            ".error-message",
            ".auth-error",
            '[class*="error"]',
        ]

        for selector in error_selectors:

            try:

                errors = sb.driver.find_elements(
                    By.CSS_SELECTOR,
                    selector,
                )

                for error in errors:

                    if error.is_displayed():

                        text = (
                            error.text.strip()
                        )

                        if text:

                            error_msg = text
                            break

                if error_msg:
                    break

            except Exception:
                continue

        print("❌ 登录失败")
        print(
            f"当前 URL: "
            f"{sb.get_current_url()}"
        )

        try:
            print(
                f"当前标题: "
                f"{sb.get_title()}"
            )
        except Exception:
            pass

        print(
            f"错误信息: "
            f"{error_msg or '未检测到明确错误信息'}"
        )

        return False

    except Exception as e:

        print(
            f"登录过程异常: {e}"
        )

        print(
            f"当前 URL: "
            f"{sb.get_current_url()}"
        )

        try:

            print(
                f"当前标题: "
                f"{sb.get_title()}"
            )

        except Exception:
            pass

        return False


# ============================================================
# 获取当前出口 IP
# ============================================================

def get_current_ip(
    proxy_server="",
):

    proxies = None

    if proxy_server:

        proxies = {
            "http": proxy_server,
            "https": proxy_server,
        }

    response = requests.get(
        "https://api.ip.sb/ip",
        proxies=proxies,
        timeout=15,
    )

    response.raise_for_status()

    return response.text.strip()


# ============================================================
# 邮箱脱敏
# ============================================================

def mask_email(email):

    if not email or "@" not in email:
        return email or ""

    local, domain = email.split(
        "@",
        1,
    )

    if len(local) <= 2:

        masked_local = (
            local[0] + "****"
            if local
            else "****"
        )

    elif len(local) <= 4:

        masked_local = (
            f"{local[0]}"
            f"****"
            f"{local[-1]}"
        )

    else:

        masked_local = (
            f"{local[:2]}"
            f"****"
            f"{local[-2:]}"
        )

    return (
        f"{masked_local}@{domain}"
    )


# ============================================================
# Telegram 消息
# ============================================================

def build_success_message(
    project_name,
    old_expiry,
    new_expiry,
):

    masked_email = mask_email(
        EMAIL
    )

    lines = [
        "🇫🇷 Aclclouds 续期通知",
        "",
        "✅ 续期成功",
        f"📦 项目: {project_name}",
        f"⏱️ 新过期时间: {new_expiry}",
        f"👤 登录账户: {masked_email}",
        f"⏱️ 运行时间: {beijing_time_str()}",
    ]

    return "\n".join(lines)


def build_not_yet_due_message(
    project_name,
    expiry,
):

    masked_email = mask_email(
        EMAIL
    )

    lines = [
        "🇫🇷 Aclclouds 续期通知",
        "",
        "⏳ 未到续期时间",
        f"📦 项目: {project_name}",
        f"⏱️ 当前过期时间: {expiry}",
        f"👤 登录账户: {masked_email}",
        f"⏱️ 运行时间: {beijing_time_str()}",
    ]

    return "\n".join(lines)


def build_unconfirmed_message(
    project_name,
    old_expiry,
    new_expiry,
    result_note,
):

    masked_email = mask_email(
        EMAIL
    )

    lines = [
        "🇫🇷 Aclclouds 续期通知",
        "",
        f"❌ 续期状态未确认: {project_name}",
        f"👤 登录账户: {masked_email}",
    ]

    if (
        old_expiry
        and old_expiry.lower()
        not in [
            "suspended",
            "paused",
            "暂停",
        ]
    ):

        lines.append(
            f"旧过期: {old_expiry}"
        )

    lines.extend(
        [
            f"当前过期: {new_expiry}",
            (
                "页面提示: "
                f"{result_note or '未发现成功提示'}"
            ),
        ]
    )

    return "\n".join(lines)


# ============================================================
# 页面诊断
# ============================================================

def log_projects_page_diagnostics(sb):

    current_url = (
        sb.get_current_url()
    )

    title = sb.get_title()

    body_text = ""

    try:

        body_text = (
            sb.driver
            .find_element(
                By.TAG_NAME,
                "body",
            )
            .text
            .strip()
        )

    except Exception:
        pass

    print(
        f"项目页诊断 URL: "
        f"{current_url}"
    )

    print(
        f"项目页诊断标题: "
        f"{title}"
    )

    print(
        "项目页可见文本摘要: "
        f"{body_text[:1200]}"
    )


# ============================================================
# 主程序
# ============================================================

def main():

    # --------------------------------------------------------
    # 代理配置
    # --------------------------------------------------------

    IS_PROXY = (
        os.environ
        .get(
            "IS_PROXY",
            "false",
        )
        .lower()
        == "true"
    )

    PROXY_SERVER = (
        os.getenv("S5_PROXY")
        or os.getenv("PROXY_SERVER")
        or "socks://127.0.0.1:1080"
    )

    # --------------------------------------------------------
    # SeleniumBase 配置
    # --------------------------------------------------------

    sb_options = {
        "uc": True,
        "headless": False,
    }

    if IS_PROXY:

        sb_options["proxy"] = (
            PROXY_SERVER
        )

        print(
            f"🔗 挂载代理: "
            f"{PROXY_SERVER}"
        )

    else:

        print(
            "🍭 未使用代理，直连访问"
        )

    # --------------------------------------------------------
    # 启动浏览器
    # --------------------------------------------------------

    with SB(**sb_options) as sb:

        try:

            # ------------------------------------------------
            # 获取出口 IP
            # ------------------------------------------------

            try:

                ip = get_current_ip(
                    PROXY_SERVER
                    if IS_PROXY
                    else ""
                )

                print(
                    f"📍 当前出口IP: {ip}"
                )

            except Exception as e:

                print(
                    f"获取出口IP失败: {e}"
                )

            # ------------------------------------------------
            # 浏览器窗口
            # ------------------------------------------------

            try:

                sb.set_window_size(
                    1366,
                    768,
                )

            except Exception:
                pass

            # ------------------------------------------------
            # 打开首页
            # ------------------------------------------------

            if not is_login_page(sb):

                sb.open(BASE_URL)

                sb.wait_for_ready_state_complete()

                time.sleep(2)

            # ------------------------------------------------
            # 登录
            # ------------------------------------------------

            if is_login_page(sb):

                if not EMAIL or not PASSWORD:

                    print(
                        "❌ 未配置 EMAIL/PASSWORD "
                        "或 ACL_EMAIL/ACL_PASSWORD，"
                        "无法执行账号密码登录。"
                    )

                    send_telegram(
                        "⚠️ 未配置 "
                        "EMAIL/PASSWORD "
                        "或 ACL_EMAIL/ACL_PASSWORD。"
                    )

                    return

                if not login(
                    sb,
                    EMAIL,
                    PASSWORD,
                ):

                    send_telegram(
                        "❌ Aclclouds 登录失败，"
                        "请检查账号、密码或验证码。"
                    )

                    return

            elif is_logged_in(sb):

                print(
                    f"✅ 当前已登录。"
                )

                print(
                    f"URL: "
                    f"{sb.get_current_url()}"
                )

                print(
                    f"标题: "
                    f"{sb.get_title()}"
                )

            else:

                print(
                    "❌ 未能确认登录状态。"
                )

                print(
                    f"URL: "
                    f"{sb.get_current_url()}"
                )

                print(
                    f"标题: "
                    f"{sb.get_title()}"
                )

                send_telegram(
                    "⚠️ 未能确认登录状态，"
                    "请检查账号密码配置。"
                )

                return

            # ------------------------------------------------
            # 进入项目页面
            # ------------------------------------------------

            print(
                "📂 正在进入项目页面..."
            )

            sb.open(PROJECTS_URL)

            sb.wait_for_ready_state_complete()

            time.sleep(3)

            print(
                f"项目页面 URL: "
                f"{sb.get_current_url()}"
            )

            # ------------------------------------------------
            # 查找项目卡片
            # ------------------------------------------------

            cards = find_project_cards(sb)

            if not cards:

                print(
                    "❌ 未找到项目卡片。"
                )

                log_projects_page_diagnostics(
                    sb
                )

                send_telegram(
                    "⚠️ 未找到项目卡片，"
                    "请检查页面结构。"
                )

                return

            print(
                f"找到 {len(cards)} 个项目卡片。"
            )

            # ------------------------------------------------
            # 处理每个项目
            # ------------------------------------------------

            for idx, card in enumerate(
                cards,
                1,
            ):

                try:

                    project_name = (
                        get_project_name(
                            card,
                            idx,
                        )
                    )

                    old_expiry = (
                        get_project_expiry(
                            card
                        )
                    )

                    print(
                        f"[{project_name}] "
                        f"当前过期: "
                        f"{old_expiry}"
                    )

                    # ------------------------------------------------
                    # 查找 Renew / Reactivate
                    # ------------------------------------------------

                    renew_btn = (
                        find_renew_buttons(
                            card
                        )
                    )

                    if renew_btn:

                        action_label = (
                            get_action_button_label(
                                renew_btn[0]
                            )
                        )

                        clicked = safe_click_element(
                            sb,
                            renew_btn[0],
                            (
                                f"[{project_name}] "
                                f"{action_label}按钮"
                            ),
                        )

                        if not clicked:

                            print(
                                f"[{project_name}] "
                                f"❌ {action_label} "
                                f"按钮点击失败"
                            )

                            send_telegram(
                                "🇫🇷 Aclclouds 续期通知\n\n"
                                f"❌ 项目: {project_name}\n"
                                f"❌ {action_label} "
                                f"按钮点击失败\n"
                                f"⏱️ 运行时间: "
                                f"{beijing_time_str()}"
                            )

                            continue

                        print(
                            f"[{project_name}] "
                            f"点击 {action_label}..."
                        )

                        # ------------------------------------------------
                        # 处理 Renew 后 Anti-bot
                        # ------------------------------------------------

                        handle_renew_antibot(
                            sb,
                            project_name,
                        )

                        # ------------------------------------------------
                        # 等待续期结果
                        # ------------------------------------------------

                        success, new_expiry, result_note = (
                            wait_for_renew_result(
                                sb,
                                idx,
                                timeout=30,
                            )
                        )

                        if success:

                            print(
                                f"[{project_name}] "
                                f"续期成功！"
                            )

                            print(
                                f"状态: "
                                f"{result_note}"
                            )

                            print(
                                f"新过期: "
                                f"{new_expiry}"
                            )

                            send_telegram(
                                build_success_message(
                                    project_name,
                                    old_expiry,
                                    new_expiry,
                                )
                            )

                        else:

                            print(
                                f"[{project_name}] "
                                f"续期状态未确认"
                            )

                            print(
                                f"当前过期: "
                                f"{new_expiry}"
                            )

                            print(
                                f"页面提示: "
                                f"{result_note}"
                            )

                            send_telegram(
                                build_unconfirmed_message(
                                    project_name,
                                    old_expiry,
                                    new_expiry,
                                    result_note,
                                )
                            )

                    else:

                        note = get_renew_note(
                            card
                        )

                        print(
                            f"[{project_name}] "
                            f"无 Renew 按钮，"
                            f"提示: {note}"
                        )

                        send_telegram(
                            build_not_yet_due_message(
                                project_name,
                                old_expiry,
                            )
                        )

                except Exception as e:

                    print(
                        f"处理卡片 {idx} 出错: "
                        f"{e}"
                    )

                    send_telegram(
                        "🇫🇷 Aclclouds 续期通知\n\n"
                        f"⚠️ 处理项目 #{idx} 出错:\n"
                        f"{str(e)}"
                    )

            print(
                "✅ 所有项目处理完成。"
            )

        except Exception as e:

            print(
                f"❌ 程序运行异常: {e}"
            )

            try:

                send_telegram(
                    "🇫🇷 Aclclouds 续期通知\n\n"
                    f"❌ 程序运行异常:\n{str(e)}\n"
                    f"⏱️ 时间: "
                    f"{beijing_time_str()}"
                )

            except Exception:
                pass

            raise


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":
    main()
