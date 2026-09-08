"""
Platform factory and unified interface for affiliate APIs
"""
from typing import Dict, List, Optional, Any
from src.config import get_config
from src.platforms.shopee import ShopeeAffiliateClient
from src.platforms.tiktok import TikTokShopAffiliateClient

config = get_config()


class PlatformFactory:
    """Factory for creating platform clients"""

    _instances = {}

    @classmethod
    def get_shopee_client(cls) -> ShopeeAffiliateClient:
        if "shopee" not in cls._instances:
            cls._instances["shopee"] = ShopeeAffiliateClient()
        return cls._instances["shopee"]

    @classmethod
    def get_tiktok_client(cls) -> TikTokShopAffiliateClient:
        if "tiktok" not in cls._instances:
            cls._instances["tiktok"] = TikTokShopAffiliateClient()
        return cls._instances["tiktok"]

    @classmethod
    def get_available_platforms(cls) -> List[str]:
        """Return list of configured platforms"""
        platforms = []
        from src.config import config
        if config.shopee.is_configured:
            platforms.append("shopee")
        if config.tiktok.is_configured:
            platforms.append("tiktok")
        return platforms

    @classmethod
    def search_all(cls, keyword: str, **kwargs) -> Dict[str, List[Dict]]:
        """Search across all configured platforms"""
        results = {}

        if config.shopee.is_configured:
            try:
                client = cls.get_shopee_client()
                results["shopee"] = client.search_products(keyword, **kwargs)
            except Exception as e:
                print(f"Shopee search error: {e}")
                results["shopee"] = []

        if config.tiktok.is_configured:
            try:
                client = cls.get_tiktok_client()
                results["tiktok"] = client.search_products(keyword, **kwargs)
            except Exception as e:
                print(f"TikTok search error: {e}")
                results["tiktok"] = []

        return results

    @classmethod
    def generate_affiliate_links(cls, platform: str, item_ids: List[str], sub_id: str = "") -> Dict[str, str]:
        """Generate affiliate links for items"""
        if platform == "shopee" and config.shopee.is_configured:
            client = cls.get_shopee_client()
            return client.generate_affiliate_links_batch(item_ids, sub_id)
        elif platform == "tiktok" and config.tiktok.is_configured:
            client = cls.get_tiktok_client()
            return cls.get_tiktok_client().generate_affiliate_links_batch(platform, item_ids)
        return {}

    @classmethod
    def get_product_details(cls, platform: str, item_ids: List[str]) -> List[Dict]:
        """Get product details for multiple items"""
        if platform == "shopee" and config.shopee.is_configured:
            client = cls.get_shopee_client()
            return client.get_product_detail(item_ids)
        elif platform == "tiktok" and config.tiktok.is_configured:
            client = cls.get_tiktok_client()
            return client.get_product_detail(item_ids)
        return []

    @classmethod
    def get_categories(cls, platform: str) -> List[Dict]:
        """Get categories for a platform"""
        if platform == "shopee" and config.shopee.is_configured:
            client = cls.get_shopee_client()
            return client.get_categories()
        elif platform == "tiktok" and config.tiktok.is_configured:
            client = cls.get_tiktok_client()
            return client.get_categories()
        return []


def format_product_for_display(product: Dict, platform: str) -> str:
    """Format product for Telegram display"""
    lines = []

    # Platform emoji
    platform_emoji = "🛍️" if platform == "shopee" else "🎵"

    lines.append(f"{platform_emoji} <b>{product['name'][:80]}</b>")
    lines.append(f"💰 <b>Harga:</b> Rp{product['price']:,.0f}")

    if product.get("original_price", 0) > product.get("price", 0):
        lines.append(f"💸 <b>Harga asli:</b> Rp{product['original_price']:,.0f} (-{product.get('discount', 0)}%)")

    lines.append(f"💵 <b>Komisi:</b> {product.get('commission_rate', 0):.1f}%")
    lines.append(f"⭐ Rating: {product.get('rating', 0):.1f} | 📦 Terjual: {product.get('sold', 0):,}")

    if product.get("shop_name"):
        lines.append(f"🏪 Toko: {product['shop_name']}")

    if product.get("brand"):
        lines.append(f"🏷️ Brand: {product['brand']}")

    if product.get("category_name"):
        lines.append(f"📂 Kategori: {product['category_name']}")

    return "\n".join(lines)


def format_search_results(products: List[Dict], platform: str, max_results: int = 5) -> str:
    """Format search results for display"""
    if not products:
        return "😔 Tidak ditemukan produk yang cocok."

    platform_name = "Shopee" if platform == "shopee" else "TikTok Shop"
    header = f"🔍 <b>Hasil pencarian di {platform_name}</b> ({len(products)} produk)\n"

    results = [header]
    for i, product in enumerate(products[:5], 1):
        platform_emoji = "🛍️" if platform == "shopee" else "🎵"
        product_text = (
            f"\n{i}. {platform_emoji} <b>{product['name'][:60]}</b>\n"
            f"   💰 Rp{product['price']:,.0f} | 💵 Komisi: {product.get('commission_rate', 0):.1f}%\n"
            f"   ⭐ {product.get('rating', 0):.1f} | 📦 {product.get('sold', 0):,} terjual"
        )
        if product.get("shop_name"):
            product_text += f" | 🏪 {product['shop_name']}"
        results.append(product_text)

    if len(products) > 5:
        results.append(f"\n... dan {len(products) - 5} produk lainnya")

    return "\n".join(results)