"""
Shopee Affiliate API Client - Async Version
Documentation: https://openplatform.shopee.com/documents/v2/v2.affiliate.get_items
"""
import time
import hmac
import hashlib
import urllib.parse
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import httpx
from src.config import get_config

config = get_config()

logger = logging.getLogger(__name__)


@dataclass
class ShopeeProduct:
    item_id: str
    name: str
    price: float  # in IDR
    original_price: float
    discount: float
    commission_rate: float  # percentage
    image_url: str
    product_url: str
    shop_name: str
    rating: float
    sold: int
    category: str
    brand: str = ""

    @property
    def affiliate_url(self) -> str:
        return self.product_url  # Will be replaced with affiliate link


class ShopeeAffiliateClient:
    """Shopee Affiliate API Client - Async Version"""

    def __init__(self):
        self.app_id = config.shopee.app_id
        self.secret_key = config.shopee.secret_key
        self.access_token = config.shopee.access_token
        self.refresh_token = config.shopee.refresh_token
        self.api_base = config.shopee.api_base.rstrip("/")
        self.partner_id = config.shopee.partner_id

        self._client: Optional[httpx.AsyncClient] = None
        self._token_expires_at = 0

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(config.network.request_timeout),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "AffiliateFinderBot/1.0"
                }
            )
        return self._client

    async def close(self):
        """Close the HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def refresh_access_token(self) -> bool:
        """Refresh Shopee access token using refresh token"""
        if not self.refresh_token:
            logger.warning("No refresh token available for Shopee")
            return False

        try:
            path = "/api/v2/auth/access_token/get"
            params = {
                "partner_id": self.app_id,
                "refresh_token": self.refresh_token,
            }
            # Generate sign for token refresh
            sign = self._generate_sign(path, params)
            params["sign"] = sign

            client = await self._get_client()
            response = await client.post(
                f"{self.api_base}{path}",
                params=params,
                timeout=httpx.Timeout(config.network.request_timeout)
            )

            if response.status_code == 200:
                data = response.json()
                if "access_token" in data:
                    self.access_token = data["access_token"]
                    if "refresh_token" in data:
                        self.refresh_token = data["refresh_token"]
                    # Update config
                    config.shopee.access_token = self.access_token
                    config.shopee.refresh_token = self.refresh_token
                    logger.info("Shopee access token refreshed successfully")
                    return True

            logger.error(f"Failed to refresh Shopee token: {response.text}")
            return False

        except Exception as e:
            logger.error(f"Error refreshing Shopee token: {e}")
            return False

    def _generate_sign(self, path: str, params: Dict) -> str:
        """Generate HMAC SHA256 signature for Shopee API"""
        sorted_params = sorted(params.items())
        param_string = urllib.parse.urlencode(sorted_params)
        base_string = f"{path}?{param_string}"
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            base_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _get_auth_params(self, params: Dict = None) -> Dict:
        """Get common auth parameters with signature"""
        params = params or {}
        timestamp = int(time.time())

        auth_params = {
            "partner_id": self.app_id,
            "timestamp": timestamp,
            "access_token": self.access_token,
        }
        auth_params.update(params)

        sign = self._generate_sign("", auth_params)
        auth_params["sign"] = sign
        return auth_params

    async def _request(self, method: str, path: str, params: Dict = None,
                       json_data: Dict = None, retry: int = 0) -> Dict:
        """Make async API request with retry logic"""
        max_retries = config.network.max_retries
        timeout = config.network.request_timeout

        params = params or {}

        # Add auth params
        auth_params = {
            "partner_id": self.app_id,
            "timestamp": int(time.time()),
            "access_token": self.access_token,
        }
        if params:
            auth_params.update(params)

        # Generate signature
        sign = self._generate_sign(path, auth_params)
        auth_params["sign"] = sign

        url = f"{self.api_base}{path}"

        client = await self._get_client()

        try:
            if method.upper() == "GET":
                response = await client.get(url, params=auth_params, timeout=timeout)
            else:
                response = await client.post(url, params=auth_params, json=json_data, timeout=timeout)

            # Handle rate limiting
            if response.status_code == 429:
                if retry < 3:
                    wait_time = 2 ** retry
                    await asyncio.sleep(wait_time)
                    return await self._request(method, path, params, json_data, retry + 1)
                raise Exception("Rate limit exceeded")

            response.raise_for_status()
            data = response.json()

            # Check for API errors
            if "error" in data and data["error"]:
                raise Exception(f"Shopee API Error: {data.get('message', 'Unknown error')}")

            return data.get("response", data)

        except httpx.RequestError as e:
            if retry < 3:
                await asyncio.sleep(2 ** retry)
                return await self._request(method, path, params, json_data, retry + 1)
            raise Exception(f"Request failed: {str(e)}")

    async def search_products(self, keyword: str, page: int = 1, page_size: int = 20,
                              min_price: int = None, max_price: int = None,
                              category_id: int = None, sort_by: str = "relevance",
                              filter_high_commission: bool = True) -> List[Dict]:
        """
        Search products via Shopee Affiliate API

        Args:
            keyword: Search keyword
            page: Page number (1-based)
            page_size: Results per page (max 50)
            min_price: Minimum price in IDR
            max_price: Maximum price in IDR
            category_id: Category filter
            sort_by: relevance, sales, price_asc, price_desc, commission_rate
            filter_high_commission: Only show products with commission > 1%

        Returns:
            List of product dicts
        """
        path = "/api/v2/affiliate/get_items"

        params = {
            "keyword": keyword,
            "page": page,
            "page_size": min(page_size, 50),
            "sort_by": sort_by,
        }

        if min_price:
            params["min_price"] = min_price * 100000  # Shopee uses 1/100000 IDR
        if max_price:
            params["max_price"] = max_price * 100000
        if category_id:
            params["category_id"] = category_id

        data = await self._request("GET", path, params)

        if not data or "item_list" not in data:
            return []

        products = []
        for item in data.get("item_list", []):
            product = self._parse_product(item)
            if product:
                # Filter by commission rate
                if filter_high_commission and product.commission_rate < 1.0:
                    continue
                products.append(product)

        return products

    async def get_product_detail(self, item_ids: List[str]) -> List[Dict]:
        """Get detailed product info for multiple items"""
        all_products = []

        for chunk in chunked(item_ids, 50):
            params = {"item_ids": chunk}
            data = await self._request("GET", "/api/v2/affiliate/get_item_detail", params)

            if data and "item_list" in data:
                for item in data["item_list"]:
                    product = self._parse_product(item)
                    if product:
                        all_products.append(product)

        return all_products

    async def generate_affiliate_link(self, item_id: str, sub_id: str = "") -> str:
        """Generate affiliate link for a product"""
        path = "/api/v2/affiliate/generate_short_link"

        params = {
            "item_id": item_id,
        }
        if sub_id:
            params["sub_id"] = sub_id

        data = await self._request("GET", path, params)

        if data and "url" in data:
            return data["url"]
        return ""

    async def generate_affiliate_links_batch(self, item_ids: List[str], sub_id: str = "") -> Dict[str, str]:
        """Generate affiliate links for multiple products"""
        path = "/api/v2/affiliate/generate_short_link_batch"

        results = {}
        # Process in chunks of 50
        for chunk in chunked(item_ids, 50):
            params = {"item_ids": chunk}
            if sub_id:
                params["sub_id"] = sub_id

            data = await self._request("GET", path, params)

            if data and "url_list" in data:
                for item in data["url_list"]:
                    results[item["item_id"]] = item.get("short_link", "")

        return results

    def get_categories(self) -> List[Dict]:
        """Get product categories"""
        path = "/api/v2/affiliate/get_categories"
        # This is a synchronous call for simplicity, can be made async if needed
        import requests
        url = f"{self.api_base}{path}"
        auth_params = {
            "partner_id": self.app_id,
            "timestamp": int(time.time()),
            "access_token": self.access_token,
        }
        sign = self._generate_sign("/api/v2/affiliate/get_categories", {
            "partner_id": self.app_id,
            "timestamp": int(time.time()),
            "access_token": self.access_token,
        })
        auth_params["sign"] = sign

        response = requests.get(f"{self.api_base}{path}", params=auth_params, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("categories", []) if data else []

    def get_commission_rates(self, category_ids: List[int] = None) -> List[Dict]:
        """Get commission rates by category"""
        path = "/api/v2/affiliate/get_commission_rates"
        params = {}
        if category_ids:
            params["category_ids"] = category_ids
        # Using sync request for simplicity
        import requests
        auth_params = {
            "partner_id": self.app_id,
            "timestamp": int(time.time()),
            "access_token": self.access_token,
        }
        if category_ids:
            auth_params["category_ids"] = category_ids
        sign = self._generate_sign("/api/v2/affiliate/get_commission_rates", auth_params)
        auth_params["sign"] = sign

        response = requests.get(f"{self.api_base}{path}", params=auth_params, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("commission_rates", []) if data else []

    def _parse_product(self, item: Dict) -> Optional[Dict]:
        """Parse Shopee product item to standard format"""
        try:
            # Price is in 1/100000 IDR
            price = item.get("price", 0) / 100000
            original_price = item.get("price_before_discount", 0) / 100000
            discount = item.get("discount", 0)

            # Commission rate is in percentage
            commission_rate = item.get("commission_rate", 0) / 100

            # Product URL
            product_url = item.get("item_link", "")
            if not product_url and "item_id" in item:
                product_url = f"https://shopee.co.id/product/{item.get('shop_id')}/{item['item_id']}"

            return {
                "platform": "shopee",
                "item_id": str(item.get("item_id", "")),
                "name": item.get("item_name", ""),
                "price": price,
                "original_price": original_price,
                "discount": discount,
                "commission_rate": commission_rate,
                "image_url": item.get("image_url", ""),
                "product_url": product_url,
                "shop_name": item.get("shop_name", ""),
                "shop_id": str(item.get("shop_id", "")),
                "rating": item.get("rating_star", 0) / 10000,  # Shopee rating is x10000
                "sold": item.get("sold", 0),
                "category_id": item.get("cat_id", 0),
                "category_name": item.get("cat_name", ""),
                "brand": item.get("brand", ""),
                "stock": item.get("stock", 0),
                "is_official_shop": item.get("is_official_shop", False),
                "is_mall": item.get("is_mall", False),
                "raw_data": item  # Keep raw for debugging
            }
        except Exception as e:
            import logging
            logging.error(f"Error parsing Shopee product: {e}")
            return None

    async def search(self, keyword: str, **kwargs) -> List[Dict]:
        """Alias for search_products"""
        return await self.search_products(keyword, **kwargs)

    async def close(self):
        """Close the HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


def chunked(iterable, size):
    """Split iterable into chunks of size"""
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]


# For testing
if __name__ == "__main__":
    import asyncio

    async def test():
        client = ShopeeAffiliateClient()
        if client.app_id and client.secret_key:
            results = await client.search_products("gula gmp 1kg", page_size=5)
            for p in results:
                print(f"{p['name']} - Rp{p['price']:,.0f} - Commission: {p['commission_rate']}%")
        else:
            print("Shopee credentials not configured")

    asyncio.run(test())