"""
通知模块 - Telegram 通知
"""

import os
from loguru import logger
from curl_cffi import requests


class NotificationManager:
    """Telegram 通知管理器"""

    def __init__(self):
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    def send_all(self, title: str, message: str):
        """发送通知"""
        self.send_telegram(title, message)

    def send_telegram(self, title: str, message: str):
        """发送 Telegram 通知"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            logger.info("未配置 TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID，跳过 Telegram 通知")
            return False

        try:
            telegram_url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            text = f"🤖 {title}\n\n{message}"
            response = requests.post(
                telegram_url,
                json={
                    "chat_id": self.telegram_chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
            response.raise_for_status()
            logger.success("Telegram 推送成功")
            return True
        except Exception as e:
            logger.error(f"Telegram 推送失败: {str(e)}")
            return False
