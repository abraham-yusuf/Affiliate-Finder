"""
Rate Limiter for Telegram Bot
Simple in-memory rate limiter with per-user tracking
"""
import time
import logging
from typing import Dict, Optional, Tuple
from collections import defaultdict
from telegram import Update

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple rate limiter with sliding window"""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[int, list] = defaultdict(list)

    def is_allowed(self, user_id: int) -> tuple[bool, int]:
        """Check if user is allowed to make request. Returns (allowed, remaining)"""
        now = time.time()
        user_requests = self._requests[user_id]

        # Remove old requests outside the window
        cutoff = now - self.window_seconds
        while user_requests and user_requests[0] < cutoff:
            user_requests.pop(0)

        # Check if under limit
        if len(user_requests) < self.max_requests:
            user_requests.append(now)
            return True, self.max_requests - len(user_requests)

        return False, 0

    def get_remaining(self, user_id: int) -> int:
        """Get remaining requests for user"""
        now = time.time()
        user_requests = self._requests[user_id]
        cutoff = now - self.window_seconds
        while user_requests and user_requests[0] < cutoff:
            user_requests.pop(0)
        return max(0, self.max_requests - len(user_requests))

    def reset(self, user_id: int):
        """Reset rate limit for a user (admin only)"""
        if user_id in self._requests:
            del self._requests[user_id]


class AccessControl:
    """Access control with whitelist/blacklist support"""

    def __init__(self, config):
        self.config = config
        self.whitelist: set = set()
        self.blacklist: set = set()
        self.allow_all = getattr(config.telegram, 'allow_all_users', True)

    def is_allowed(self, user_id: int) -> bool:
        """Check if user is allowed to use the bot"""
        if user_id in self.blacklist:
            return False

        if user_id in self.whitelist:
            return True

        # If whitelist is configured and user not in it, deny
        if self.whitelist and not self.allow_all:
            return False

        return True

    def add_to_whitelist(self, user_id: int):
        self.whitelist.add(user_id)

    def remove_from_whitelist(self, user_id: int):
        self.whitelist.discard(user_id)

    def add_to_blacklist(self, user_id: int):
        self.blacklist.add(user_id)

    def remove_from_blacklist(self, user_id: int):
        self.blacklist.discard(user_id)


# Global instances
_rate_limiter: Optional[RateLimiter] = None
_access_control: Optional[AccessControl] = None


def get_rate_limiter(config) -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        max_req = getattr(config.telegram, 'rate_limit_per_minute', 30)
        _rate_limiter = RateLimiter(max_requests=max_req, window_seconds=60)
    return _rate_limiter


def get_access_control(config) -> AccessControl:
    global _access_control
    if _access_control is None:
        _access_control = AccessControl(config)
    return _access_control


async def check_rate_limit(update: Update, config) -> tuple[bool, str]:
    """Check rate limit for the current user"""
    user_id = update.effective_user.id
    limiter = get_rate_limiter(config)

    # Admins bypass rate limit
    if user_id in config.telegram.admin_ids:
        return True, ""

    allowed, remaining = limiter.is_allowed(user_id)
    if not allowed:
        return False, f"⚠️ Rate limit exceeded. Coba lagi dalam 1 menit.\nSisa request: {remaining}"
    return True, ""


async def check_access(update: Update, config) -> tuple[bool, str]:
    """Check if user has access to the bot"""
    user_id = update.effective_user.id
    access_control = get_access_control(config)

    if not access_control.is_allowed(user_id):
        return False, "❌ Akses ditolak. Hubungi admin untuk izin."
    return True, ""