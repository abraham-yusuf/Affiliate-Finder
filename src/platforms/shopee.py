"""
Shopee Affiliate API Client
Documentation: https://openplatform.shopee.com/documents/v2/v2.affiliate.get_items
"""
import time
import hmac
import hashlib
import urllib.parse
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import requests
from src.config import get_config

config = get_config()


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
    """Shopee Affiliate API Client"""
    
    def __init__(self):
        self.app_id = config.shopee.app_id
        self.secret_key = config.shopee.secret_key
        self.access_token = config.shopee.access_token
        self.refresh_token = config.shopee.refresh_token
        self.api_base = config.shopee.api_base.rstrip("/")
        self.partner_id = config.shopee.partner_id
        
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "AffiliateFinderBot/1.0"
        })
        
        self._token_expires_at = 0
    
    def _generate_sign(self, path: str, params: Dict) -> str:
        """Generate HMAC SHA256 signature for Shopee API"""
        # Sort params by key
        sorted_params = sorted(params.items())
        param_string = urllib.parse.urlencode(sorted_params)
        base_string = f"{path}?{param_string}"
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            base_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _get_headers(self, path: str, params: Dict) -> Dict[str, str]:
        """Generate request headers with signature"""
        timestamp = int(time.time())
        params["timestamp"] = timestamp
        params["partner_id"] = self.app_id
        params["access_token"] = self.access_token
        params["sign"] = self._generate_sign(path, params)
        
        return {
            "Content-Type": "application/json"
        }
    
    def _request(self, method: str, path: str, params: Dict = None, 
                 json_data: Dict = None, retry: int = 0) -> Dict:
        """Make API request with retry logic"""
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
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=auth_params, timeout=timeout)
            else:
                response = self.session.post(url, params=auth_params, json=json_data, timeout=timeout)
            
            # Handle rate limiting
            if response.status_code == 429:
                if retry < max_retries:
                    wait_time = 2 ** retry
                    time.sleep(wait_time)
                    return self._request(method, path, params, json_data, retry + 1)
                raise Exception("Rate limit exceeded")
            
            response.raise_for_status()
            data = response.json()
            
            # Check for API errors
            if "error" in data and data["error"]:
                raise Exception(f"Shopee API Error: {data.get('message', 'Unknown error')}")
            
            return data.get("response", data)
            
        except requests.exceptions.RequestException as e:
            if retry < max_retries:
                time.sleep(2 ** retry)
                return self._request(method, path, params, json_data, retry + 1)
            raise Exception(f"Request failed: {str(e)}")
    
    def search_products(self, keyword: str, page: int = 1, page_size: int = 20,
                        min_price: int = None, max_price: int = None,
                        category_id: int = None, sort_by: str = "relevance",
                        filter_high_commission: bool = True) -> List[Dict]:
        """
        Search products via Shopee Affiliate API
        
        Args:
            keyword: Search keyword
            page: Page number (1-based)
            page_size: Results per page (max 50)
            min_price: Minimum price in IDR (x100000 for Shopee)
            max_price: Maximum price in IDR (x100000 for Shopee)
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
        
        data = self._request("GET", path, params)
        
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
    
    def get_product_detail(self, item_ids: List[str]) -> List[Dict]:
        """Get detailed product info for multiple items"""
        path = "/api/v2/affiliate/get_item_detail"
        
        # API accepts max 50 items per request
        chunks = [item_ids[i:i+50] for i in range(0, len(item_ids), 50)]
        all_products = []
        
        for chunk in chunked(item_ids, 50):
            params = {"item_ids": chunk}
            data = self._request("GET", "/api/v2/affiliate/get_item_detail", params)
            
            if data and "item_list" in data:
                for item in data["item_list"]:
                    product = self._parse_product(item)
                    if product:
                        all_products.append(product)
        
        return all_products
    
    def generate_affiliate_link(self, item_id: str, sub_id: str = "") -> str:
        """Generate affiliate link for a product"""
        path = "/api/v2/affiliate/generate_short_link"
        
        params = {
            "item_id": item_id,
        }
        if sub_id:
            params["sub_id"] = sub_id
        
        data = self._request("GET", path, params)
        
        if data and "url" in data:
            return data["url"]
        return ""
    
    def generate_affiliate_links_batch(self, item_ids: List[str], sub_id: str = "") -> Dict[str, str]:
        """Generate affiliate links for multiple products"""
        path = "/api/v2/affiliate/generate_short_link_batch"
        
        results = {}
        # Process in chunks of 50
        for chunk in chunked(item_ids, 50):
            params = {"item_ids": chunk}
            if sub_id:
                params["sub_id"] = sub_id
            
            data = self._request("GET", path, params)
            
            if data and "url_list" in data:
                for item in data["url_list"]:
                    results[item["item_id"]] = item.get("short_link", "")
        
        return results
    
    def get_categories(self) -> List[Dict]:
        """Get product categories"""
        path = "/api/v2/affiliate/get_categories"
        data = self._request("GET", path)
        return data.get("categories", []) if data else []
    
    def get_commission_rates(self, category_ids: List[int] = None) -> List[Dict]:
        """Get commission rates by category"""
        path = "/api/v2/affiliate/get_commission_rates"
        params = {}
        if category_ids:
            params["category_ids"] = category_ids
        data = self._request("GET", path, params)
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
            print(f"Error parsing Shopee product: {e}")
            return None
    
    def search(self, keyword: str, **kwargs) -> List[Dict]:
        """Alias for search_products"""
        return self.search_products(keyword, **kwargs)


def chunked(iterable, size):
    """Split iterable into chunks of size"""
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]


# For testing
if __name__ == "__main__":
    client = ShopeeAffiliateClient()
    if client.app_id and client.secret_key:
        results = client.search_products("gula gmp 1kg", page_size=5)
        for p in results:
            print(f"{p['name']} - Rp{p['price']:,.0f} - Commission: {p['commission_rate']}%")
    else:
        print("Shopee credentials not configured")