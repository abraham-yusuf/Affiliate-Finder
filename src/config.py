"""
Configuration loader for Affiliate Finder Bot
"""
import os
from dataclasses import dataclass, field
from typing import List, Optional
from dotenv import load_dotenv

# Load .env from config directory
config_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(config_dir)
env_path = os.path.join(config_dir, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    # Try project root
    load_dotenv(os.path.join(project_root, ".env"))


def _get(key: str, default: str = "") -> str:
    v = os.getenv(key)
    return v if v is not None and v.strip() != "" else default


def _i(key: str, default: int = 0) -> int:
    v = _get(key)
    try:
        return int(v) if v else default
    except ValueError:
        return default


def _f(key: str, default: float = 0.0) -> float:
    v = _get(key)
    try:
        return float(v) if v else default
    except ValueError:
        return default


def _list(key: str, default: List[str] = None) -> List[str]:
    v = _get(key)
    if not v:
        return default or []
    return [x.strip() for x in v.split(",") if x.strip()]


@dataclass
class TelegramConfig:
    bot_token: str = _get("TELEGRAM_BOT_TOKEN")
    admin_ids: List[int] = field(default_factory=lambda: [int(x) for x in _list("TELEGRAM_ADMIN_IDS") if x.isdigit()])


@dataclass
class DatabaseConfig:
    path: str = _get("DB_PATH", "affiliate_finder.db")


@dataclass
class ShopeeConfig:
    app_id: str = _get("SHOPEE_APP_ID")
    secret_key: str = _get("SHOPEE_SECRET_KEY")
    access_token: str = _get("SHOPEE_ACCESS_TOKEN")
    refresh_token: str = _get("SHOPEE_REFRESH_TOKEN")
    api_base: str = _get("SHOPEE_API_BASE", "https://openplatform.shopee.com")
    partner_id: str = _get("SHOPEE_PARTNER_ID")
    is_configured: bool = field(init=False)

    def __post_init__(self):
        self.is_configured = bool(self.app_id and self.secret_key and self.access_token)


@dataclass
class TikTokConfig:
    app_key: str = _get("TIKTOK_APP_KEY")
    app_secret: str = _get("TIKTOK_APP_SECRET")
    access_token: str = _get("TIKTOK_ACCESS_TOKEN")
    refresh_token: str = _get("TIKTOK_REFRESH_TOKEN")
    api_base: str = _get("TIKTOK_API_BASE", "https://open-api.tiktokglobalshop.com")
    shop_cipher: str = _get("TIKTOK_SHOP_CIPHER")
    is_configured: bool = field(init=False)

    def __post_init__(self):
        self.is_configured = bool(self.app_key and self.app_secret and self.access_token)


@dataclass
class NetworkConfig:
    http_proxy: str = _get("HTTP_PROXY")
    request_timeout: int = _i("REQUEST_TIMEOUT", 30)
    max_retries: int = _i("MAX_RETRIES", 3)
    rate_limit_per_minute: int = _i("RATE_LIMIT_PER_MINUTE", 60)


@dataclass
class BotSettings:
    default_max_results: int = _i("DEFAULT_MAX_RESULTS", 10)
    default_min_commission_rate: float = _f("DEFAULT_MIN_COMMISSION_RATE", 1.0)
    cache_ttl_seconds: int = _i("CACHE_TTL_SECONDS", 300)


@dataclass
class Config:
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    shopee: ShopeeConfig = field(default_factory=ShopeeConfig)
    tiktok: TikTokConfig = field(default_factory=TikTokConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    settings: BotSettings = field(default_factory=BotSettings)

    def validate(self) -> List[str]:
        """Return list of missing required configs"""
        errors = []
        if not self.telegram.bot_token:
            errors.append("TELEGRAM_BOT_TOKEN")
        if not self.telegram.admin_ids:
            errors.append("TELEGRAM_ADMIN_IDS (at least one)")
        if not self.shopee.is_configured and not self.tiktok.is_configured:
            errors.append("At least one platform (SHOPEE_* or TIKTOK_*) must be configured")
        return errors


# Global config instance
config = Config()


def get_config() -> Config:
    return config