"""
TikTok Shop Affiliate API Client
Documentation: https://partner.tiktokshop.com/documents (Affiliate API)
"""
import time
import json
import hmac
import hashlib
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import requests
from src.config import get_config

config = get_config()


@dataclass
class TikTokProduct:
    product_id: str
    name: str
    price: float
    original_price: float
    discount: float
    commission_rate: float
    image_url: str
    product_url: str
    shop_name: str
    rating: float
    sold: int
    category: str
    brand: str = ""


class TikTokShopAffiliateClient:
    """TikTok Shop Affiliate API Client"""

    def __init__(self):
        self.app_key = config.tiktok.app_key
        self.app_secret = config.tiktok.app_secret
        self.access_token = config.tiktok.access_token
        self.refresh_token = config.tiktok.refresh_token
        self.api_base = config.tiktok.api_base.rstrip("/")
        self.shop_cipher = config.tiktok.shop_cipher

        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "AffiliateFinderBot/1.0"
        })

    def _generate_sign(self, params: Dict, path: str) -> str:
        """Generate HMAC SHA256 signature for TikTok API"""
        sorted_params = sorted(params.items())
        param_string = "&".join([f"{k}={v}" for k, v in sorted_params])
        base_string = f"{path}?{param_string}"
        signature = hmac.new(
            self.app_secret.encode("utf-8"),
            base_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _get_auth_params(self) -> Dict:
        """Get common auth parameters"""
        return {
            "app_key": self.app_key,
            "timestamp": int(time.time()),
            "access_token": self.access_token,
        }

    def _request(self, method: str, path: str, params: Dict = None,
                 json_data: Dict = None, retry: int = 0) -> Dict:
        """Make API request with retry logic"""
        max_retries = config.network.max_retries
        timeout = config.network.request_timeout

        params = params or {}

        auth_params = self._get_auth_params()
        if params:
            auth_params.update(params)

        sign = self._generate_sign(auth_params, path)
        auth_params["sign"] = sign

        url = f"{self.api_base}{path}"

        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=auth_params, timeout=timeout)
            else:
                response = self.session.post(url, params=auth_params, json=json_data, timeout=timeout)

            if response.status_code == 429:
                if retry < max_retries:
                    wait_time = 2 ** retry
                    time.sleep(wait_time)
                    return self._request(method, path, params, json_data, retry + 1)
                raise Exception("Rate limit exceeded")

            response.raise_for_status()
            data = response.json()

            if data.get("code", 0) != 0:
                error_msg = data.get("message", "Unknown error")
                raise Exception(f"TikTok API Error [{data.get('code')}]: {error_msg}")

            return data.get("data", data)

        except requests.exceptions.RequestException as e:
            if retry < max_retries:
                time.sleep(2 ** retry)
                return self._request(method, path, params, json_data, retry + 1)
            raise Exception(f"Request failed: {str(e)}")

    def search_products(self, keyword: str, page: int = 1, page_size: int = 20,
                        min_price: float = None, max_price: float = None,
                        category_id: int = None, sort_by: str = "relevance",
                        filter_high_commission: bool = True) -> List[Dict]:
        """Search products via TikTok Shop Affiliate API"""
        path = "/affiliate/product/search"

        params = {
            "keyword": keyword,
            "page": page,
            "page_size": min(page_size, 50),
        }

        if min_price:
            params["min_price"] = int(min_price * 100)
        if max_price:
            params["max_price"] = int(max_price * 100)
        if category_id:
            params["category_id"] = category_id

        sort_map = {
            "relevance": "relevance",
            "sales": "sales",
            "price_asc": "price_asc",
            "price_desc": "price_desc",
            "commission_rate": "commission_rate_desc",
        }
        params["sort_by"] = sort_map.get(sort_by, "relevance")

        data = self._request("GET", path, params)

        if not data or "products" not in data:
            return []

        products = []
        for item in data.get("products", []):
            product = self._parse_product(item)
            if product:
                if filter_high_commission and product.commission_rate < 1.0:
                    continue
                products.append(product)

        return products

    def get_product_detail(self, product_ids: List[str]) -> List[Dict]:
        """Get detailed product info"""
        path = "/affiliate/product/detail"
        all_products = []

        for chunk in self._chunked(product_ids, 50):
            params = {"product_ids": chunk}
            data = self._request("GET", path, params)

            if data and "products" in data:
                for item in data["products"]:
                    product = self._parse_product(item)
                    if product:
                        all_products.append(product)

        return all_products

    def generate_affiliate_link(self, product_id: str, sub_id: str = "") -> str:
        """Generate affiliate link for a product"""
        path = "/affiliate/link/generate"

        params = {"product_id": product_id}
        if sub_id:
            params["sub_id"] = sub_id

        data = self._request("POST", path, json_data=params)

        if data and "promotion_url" in data:
            return data["promotion_url"]
        return ""

    def generate_affiliate_links_batch(self, product_ids: List[str], sub_id: str = "") -> Dict[str, str]:
        """Generate affiliate links for multiple products"""
        path = "/affiliate/link/batch_generate"
        results = {}

        for chunk in self._chunked(product_ids, 50):
            json_data = {"product_ids": chunk}
            if sub_id:
                json_data["sub_id"] = sub_id

            data = self._request("POST", path, json_data=json_data)

            if data and "links" in data:
                for item in data["links"]:
                    results[item["product_id"]] = item.get("promotion_url", "")

        return results

    def get_categories(self) -> List[Dict]:
        """Get product categories"""
        path = "/affiliate/category/list"
        data = self._request("GET", path)
        return data.get("categories", []) if data else []

    def get_commission_rates(self, category_ids: List[int] = None) -> List[Dict]:
        """Get commission rates by category"""
        path = "/affiliate/commission/rate"
        params = {}
        if category_ids:
            params["category_ids"] = category_ids
        data = self._request("GET", path, params)
        return data.get("rates", []) if data else []

    def get_shop_info(self, shop_ids: List[str]) -> List[Dict]:
        """Get shop information"""
        path = "/affiliate/shop/detail"
        all_shops = []

        for chunk in self._chunked(shop_ids, 50):
            params = {"shop_ids": chunk}
            data = self._request("GET", path, params)

            if data and "shops" in data:
                all_shops.extend(data["shops"])

        return all_shops

    def _parse_product(self, item: Dict) -> Optional[Dict]:
        """Parse TikTok product item to standard format"""
        try:
            price = item.get("price", 0) / 100
            original_price = item.get("original_price", 0) / 100
            discount = item.get("discount", 0)

            commission_rate = item.get("commission_rate", 0) / 100 if item.get("commission_rate") else 0

            product_url = item.get("product_url", "")
            if not product_url and "product_id" in item:
                product_url = f"https://www.tiktok.com/shop/product/{item['product_id']}"

            images = item.get("images", [])
            image_url = images[0] if images else item.get("cover_image", "")

            return {
                "platform": "tiktok",
                "item_id": str(item.get("product_id", "")),
                "name": item.get("title", ""),
                "price": price,
                "original_price": original_price,
                "discount": discount,
                "commission_rate": commission_rate,
                "image_url": image_url,
                "product_url": product_url,
                "shop_name": item.get("shop_name", ""),
                "shop_id": str(item.get("shop_id", "")),
                "rating": item.get("rating", 0),
                "sold": item.get("sales", 0),
                "category_id": item.get("category_id", 0),
                "category_name": item.get("category_name", ""),
                "brand": item.get("brand", ""),
                "stock": item.get("stock", 0),
                "is_official_shop": item.get("is_official_shop", False),
                "raw_data": item
            }
        except Exception as e:
            print(f"Error parsing TikTok product: {e}")
            return None

    def search(self, keyword: str, **kwargs) -> List[Dict]:
        """Alias for search_products"""
        return self.search_products(keyword, **kwargs)

    @staticmethod
    def _chunked(iterable, size):
        """Split iterable into chunks of size"""
        for i in range(0, len(iterable), size):
            yield iterable[i:i + size]


if __name__ == "__main__":
    client = TikTokShopAffiliateClient()
    if client.app_key and client.app_secret:
        results = client.search_products("gula gmp 1kg", page_size=5)
        for p in results:
            print(f"{p['name']} - Rp{p['price']:,.0f} - Commission: {p['commission_rate']}%")
    else:
        print("TikTok Shop credentials not configured")