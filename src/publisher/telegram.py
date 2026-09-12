"""
Telegram Channel Publisher
Posts affiliate product deals to Telegram channels/groups.

Design: platform-agnostic interface (Publisher base) so Facebook / X / WhatsApp
publishers can be added later without touching the call sites.
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from src.config import get_config
from src.db import database as db

logger = logging.getLogger(__name__)
config = get_config()


# ===================== CAPTION TEMPLATES =====================

DEFAULT_TEMPLATE = """{emoji} <b>{name}</b>

💰 Harga: <b>Rp{price:,.0f}</b>{original_line}
💵 Komisi: {commission:.1f}%
⭐ {rating:.1f} · 📦 {sold:,} terjual

🔗 <a href="{affiliate_url}">Beli Sekarang</a>

#{platform} #deals #affiliate"""

SHORT_TEMPLATE = """{emoji} <b>{name}</b>
💰 Rp{price:,.0f} · 💵 {commission:.1f}%
🔗 <a href="{affiliate_url}">Beli</a>"""

DEAL_TEMPLATE = """🔥 <b>DEAL HARI INI</b> 🔥

{emoji} <b>{name}</b>
🏪 {shop}

💰 Harga: <s>Rp{original_price:,.0f}</s> → <b>Rp{price:,.0f}</b>
💵 Komisi affiliate: {commission:.1f}%

🔗 <a href="{affiliate_url}">Ambil Deal</a>

#deals #{platform} #promo"""

TEMPLATES = {
    "default": DEFAULT_TEMPLATE,
    "short": SHORT_TEMPLATE,
    "deal": DEAL_TEMPLATE,
}

PLATFORM_EMOJI = {"shopee": "🛍️", "tiktok": "🎵", "tokopedia": "🟢"}


def build_caption(product: Dict, affiliate_url: str, template: str = "default") -> str:
    """Render a product dict into an HTML caption safe for Telegram."""
    price = float(product.get("price") or 0)
    original = float(product.get("original_price") or 0)
    platform = product.get("platform", "shopee")

    original_line = ""
    if original > price > 0:
        disc = product.get("discount") or round((1 - price / original) * 100)
        original_line = f" <s>Rp{original:,.0f}</s> (-{disc}%)"

    ctx = {
        "emoji": PLATFORM_EMOJI.get(platform, "🛒"),
        "name": _esc(product.get("name", "Produk")),
        "price": price,
        "original_price": original or price,
        "original_line": original_line,
        "commission": float(product.get("commission_rate") or 0),
        "rating": float(product.get("rating") or 0),
        "sold": int(product.get("sold") or 0),
        "shop": _esc(product.get("shop_name") or "-"),
        "platform": platform,
        "affiliate_url": affiliate_url,
    }

    body = TEMPLATES.get(template, DEFAULT_TEMPLATE).format(**ctx)

    # optional per-channel custom template (plain-text, we HTML-escape it)
    override = ""
    return body


def _esc(s: str) -> str:
    """Escape for Telegram HTML parse mode."""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ===================== PUBLISHER INTERFACE =====================

class Publisher(ABC):
    """Base class for all posting destinations."""

    platform = "base"

    @abstractmethod
    async def publish(self, channel: Dict, product: Dict,
                      affiliate_url: str, template: str = "default") -> Dict:
        """Post product to channel. Returns {'ok': bool, 'message_id': int, 'error': str}."""
        raise NotImplementedError


class TelegramPublisher(Publisher):
    """Publishes to Telegram channels/groups via Bot API."""

    platform = "telegram"

    def __init__(self, bot: Optional[Bot] = None):
        self._bot = bot

    @property
    def bot(self) -> Bot:
        if self._bot is None:
            self._bot = Bot(token=config.telegram.bot_token)
        return self._bot

    async def publish(self, channel: Dict, product: Dict,
                      affiliate_url: str, template: str = "default") -> Dict:
        chat_id = channel["chat_id"]
        caption = build_caption(product, affiliate_url, template)
        image = product.get("image_url")

        # Per-channel custom template override (escaped, uses same placeholders)
        if channel.get("post_template"):
            caption = _render_custom(channel["post_template"], product, affiliate_url)

        try:
            if image:
                try:
                    msg = await self.bot.send_photo(
                        chat_id=chat_id, photo=image, caption=caption,
                        parse_mode=ParseMode.HTML
                    )
                except TelegramError:
                    # image URL rejected by Telegram → send text only
                    msg = await self.bot.send_message(
                        chat_id=chat_id, text=caption,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=False
                    )
            else:
                msg = await self.bot.send_message(
                    chat_id=chat_id, text=caption,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False
                )
            return {"ok": True, "message_id": msg.message_id, "error": None}
        except TelegramError as e:
            logger.error(f"Telegram publish to {chat_id} failed: {e}")
            return {"ok": False, "message_id": None, "error": str(e)}
        except Exception as e:
            logger.exception(f"Telegram publish unexpected error: {e}")
            return {"ok": False, "message_id": None, "error": str(e)}

    async def verify_channel(self, chat_id: str) -> Dict:
        """Check the bot can post to this channel. Returns {ok, title, username, error}."""
        try:
            chat = await self.bot.get_chat(chat_id)
            member = await self.bot.get_chat_member(chat_id, self.bot.id)
            can_post = getattr(member, "can_post_messages", None)
            # In channels only admins can post; in groups any member can
            if chat.type == "channel" and can_post is False:
                return {"ok": False, "title": chat.title, "username": chat.username,
                        "error": "Bot bukan admin / tidak punya izin post"}
            return {"ok": True, "title": chat.title, "username": chat.username, "error": None}
        except TelegramError as e:
            return {"ok": False, "title": None, "username": None, "error": str(e)}


def _render_custom(template: str, product: Dict, affiliate_url: str) -> str:
    """Render a per-channel custom template (plain text + basic placeholders)."""
    plat = product.get("platform", "shopee")
    ctx = {
        "emoji": PLATFORM_EMOJI.get(plat, "🛒"),
        "name": _esc(product.get("name", "Produk")),
        "price": f"{float(product.get('price') or 0):,.0f}",
        "original_price": f"{float(product.get('original_price') or 0):,.0f}",
        "commission": f"{float(product.get('commission_rate') or 0):.1f}",
        "rating": f"{float(product.get('rating') or 0):.1f}",
        "sold": f"{int(product.get('sold') or 0):,}",
        "shop": _esc(product.get("shop_name") or "-"),
        "platform": plat,
        "affiliate_url": affiliate_url,
    }
    try:
        return template.format(**ctx)
    except (KeyError, IndexError, ValueError):
        return build_caption(product, affiliate_url, "default")


# ===================== PUBLISH ORCHESTRATION =====================

_publishers: Dict[str, Publisher] = {}


def get_publisher(platform: str, bot: Optional[Bot] = None) -> Optional[Publisher]:
    """Get (cached) publisher for a platform."""
    if platform == "telegram":
        if "telegram" not in _publishers or bot is not None:
            _publishers["telegram"] = TelegramPublisher(bot)
        return _publishers["telegram"]
    # roadmap: facebook | x | whatsapp
    return None


async def publish_to_channel(channel_id: int, product: Dict,
                             affiliate_url: str, user_id: int,
                             template: str = "default",
                             bot: Optional[Bot] = None) -> Dict:
    """Post a product to one channel and record history."""
    channel = db.get_channel(channel_id)
    if not channel:
        return {"ok": False, "error": "Channel tidak ditemukan"}

    pub = get_publisher(channel["platform"], bot)
    if not pub:
        result = {"ok": False, "error": f"Platform '{channel['platform']}' belum didukung"}
    else:
        result = await pub.publish(channel, product, affiliate_url, template)

    post_id = db.log_post(
        user_id=user_id,
        channel_id=channel_id,
        platform=channel["platform"],
        product_id=product.get("item_id"),
        product_platform=product.get("platform"),
        product_name=product.get("name"),
        price=product.get("price"),
        affiliate_url=affiliate_url,
        message_id=result.get("message_id"),
        status="sent" if result.get("ok") else "failed",
        error=result.get("error"),
    )
    if result.get("ok"):
        db.bump_channel_post(channel_id)

    result["post_id"] = post_id
    result["channel_title"] = channel.get("title") or channel["chat_id"]
    return result


async def broadcast(product: Dict, affiliate_url: str, user_id: int,
                    channel_ids: Optional[List[int]] = None,
                    template: str = "default",
                    bot: Optional[Bot] = None) -> List[Dict]:
    """Post a product to multiple channels (or all of the user's enabled ones)."""
    if channel_ids is None:
        channel_ids = [c["id"] for c in db.list_channels(user_id, enabled_only=True)]

    results = []
    for cid in channel_ids:
        results.append(await publish_to_channel(cid, product, affiliate_url,
                                                user_id, template, bot))
    return results


async def auto_post_deal(product: Dict, affiliate_url: str, user_id: int,
                         bot: Optional[Bot] = None) -> List[Dict]:
    """Auto-post a new deal to every channel that has auto_post enabled."""
    channels = db.auto_post_channels()
    if not channels:
        return []
    results = []
    for ch in channels:
        results.append(await publish_to_channel(ch["id"], product, affiliate_url,
                                                user_id, "default", bot))
    return results