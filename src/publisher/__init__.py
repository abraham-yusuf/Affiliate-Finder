"""
Publisher package — auto-post affiliate deals to channels/groups.

Current: Telegram.
Roadmap: Facebook Page/Group, X (Twitter), WhatsApp Channel.
"""
from src.publisher.telegram import (
    Publisher,
    TelegramPublisher,
    build_caption,
    get_publisher,
    publish_to_channel,
    broadcast,
    auto_post_deal,
    DEFAULT_TEMPLATE,
    SHORT_TEMPLATE,
    DEAL_TEMPLATE,
    TEMPLATES,
)

__all__ = [
    "Publisher",
    "TelegramPublisher",
    "build_caption",
    "get_publisher",
    "publish_to_channel",
    "broadcast",
    "auto_post_deal",
    "DEFAULT_TEMPLATE",
    "SHORT_TEMPLATE",
    "DEAL_TEMPLATE",
    "TEMPLATES",
]