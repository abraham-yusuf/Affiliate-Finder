"""
Price Alert Scheduler - Background job for checking price alerts
Uses APScheduler for async background tasks
"""
import asyncio
import logging
from typing import List, Optional
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.db import database as db
from src.platforms import PlatformFactory

logger = logging.getLogger(__name__)


class PriceAlertScheduler:
    """Background scheduler for checking price alerts"""

    def __init__(self, bot=None):
        self.scheduler = AsyncIOScheduler()
        self.bot = bot
        self._running = False

    async def start(self):
        """Start the scheduler"""
        if self._running:
            return

        # Add job to check price alerts every 5 minutes
        self.scheduler.add_job(
            self.check_price_alerts,
            trigger=IntervalTrigger(minutes=5),
            id="check_price_alerts",
            name="Check price alerts",
            replace_existing=True
        )

        # Add job to clean up old data daily at 3 AM
        self.scheduler.add_job(
            self.cleanup_old_data,
            trigger="cron",
            hour=3,
            minute=0,
            id="cleanup_old_data",
            name="Cleanup old data",
            replace_existing=True
        )

        self.scheduler.start()
        self._running = True
        logger.info("Price alert scheduler started")

    async def stop(self):
        """Stop the scheduler"""
        if self._running:
            self.scheduler.shutdown()
            self._running = False
            logger.info("Price alert scheduler stopped")

    async def check_price_alerts(self):
        """Check all active price alerts and trigger notifications"""
        logger.info("Checking price alerts...")

        try:
            alerts = db.get_all_active_alerts()
            logger.info(f"Found {len(alerts)} active alerts to check")

            for alert in alerts:
                try:
                    await self._check_single_alert(alert)
                except Exception as e:
                    logger.error(f"Error checking alert {alert['id']}: {e}")

        except Exception as e:
            logger.error(f"Error in check_price_alerts: {e}")

    async def _check_single_alert(self, alert: dict):
        """Check a single price alert"""
        alert_id = alert["id"]
        product_id = alert["product_id"]
        platform = alert["platform"]
        target_price = alert["target_price"]
        user_id = alert["user_id"]

        try:
            # Get current product price
            if platform == "shopee":
                client = PlatformFactory.get_shopee_client()
            elif platform == "tiktok":
                client = PlatformFactory.get_tiktok_client()
            else:
                logger.warning(f"Unknown platform: {platform}")
                return

            products = await client.get_product_detail([product_id])
            if not products:
                logger.warning(f"Product {product_id} not found on {platform}")
                return

            product = products[0]
            current_price = product.get("price", 0)

            # Update current price in DB
            db.update_alert_price(alert["id"], current_price)

            # Check if price dropped below target
            if current_price <= alert["target_price"]:
                # Trigger alert!
                await self._trigger_alert(alert, current_price)
            else:
                # Update current price only
                db.update_alert_price(alert["id"], current_price)

        except Exception as e:
            logger.error(f"Error checking alert {alert['id']}: {e}")

    async def _trigger_alert(self, alert: dict, current_price: float):
        """Trigger price alert notification"""
        alert_id = alert["id"]
        user_id = alert["user_id"]
        product_name = alert["product_name"]
        target_price = alert["target_price"]
        current_price = current_price
        affiliate_url = alert.get("affiliate_url")

        # Mark alert as triggered
        db.update_alert_price(alert["id"], current_price, triggered=True)

        # Send notification via Telegram bot
        if self.bot:
            try:
                from telegram import Bot
                from telegram.constants import ParseMode

                bot = Bot(token=alert.get("bot_token")) if alert.get("bot_token") else None
                if not bot:
                    # Try to get bot from context
                    from src.config import config
                    from telegram import Bot
                    bot = Bot(token=config.telegram.bot_token)

                message = (
                    f"🔔 <b>PRICE ALERT TRIGGERED!</b>\n\n"
                    f"📦 <b>{product_name}</b>\n"
                    f"🎯 Target: Rp{target_price:,.0f}\n"
                    f"💰 Current: Rp{current_price:,.0f}\n"
                    f"💰 Savings: Rp{target_price - current_price:,.0f}\n\n"
                    f"🔗 <a href='{affiliate_url}'>Beli Sekarang</a>"
                )

                # Send to user's private chat
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text=message,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=False
                    )
                    logger.info(f"Price alert notification sent to user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to send alert notification: {e}")
            except Exception as e:
                logger.error(f"Error triggering alert: {e}")

    async def cleanup_old_data(self):
        """Clean up old data"""
        logger.info("Running cleanup of old data...")
        try:
            results = db.cleanup_old_data(days=90)
            logger.info(f"Cleanup completed: {results}")
        except Exception as e:
            logger.error(f"Error in cleanup: {e}")


# Global scheduler instance
_scheduler: Optional["PriceAlertScheduler"] = None


async def get_scheduler(bot=None) -> "PriceAlertScheduler":
    """Get or create the global scheduler instance"""
    global _scheduler
    if _scheduler is None:
        _scheduler = PriceAlertScheduler(bot)
    return _scheduler


async def start_price_alert_scheduler(bot=None):
    """Start the price alert scheduler"""
    scheduler = await get_scheduler(bot)
    await scheduler.start()


async def stop_price_alert_scheduler():
    """Stop the price alert scheduler"""
    global _scheduler
    if _scheduler:
        await _scheduler.stop()
        _scheduler = None


_scheduler: Optional["PriceAlertScheduler"] = None