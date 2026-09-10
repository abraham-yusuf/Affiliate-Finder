"""
Dashboard FastAPI Backend
REST API for Affiliate Finder Dashboard
"""
from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import sqlite3
import threading
import os
import sys
import jwt
from passlib.context import CryptContext

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import get_config
from src.db import database as db
from src.platforms import PlatformFactory

config = get_config()

# Security
SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Thread-local DB connections
_thread_local = threading.local()

def get_db_conn():
    if not hasattr(_thread_local, "conn") or _thread_local.conn is None:
        _thread_local.conn = sqlite3.connect(config.database.path, check_same_thread=False)
        _thread_local.conn.row_factory = sqlite3.Row
        _thread_local.conn.execute("PRAGMA journal_mode=WAL")
    return _thread_local.conn


# ===================== PYDANTIC MODELS =====================

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None
    is_admin: bool = False


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    is_admin: bool
    created_at: int


class UserSettingsResponse(BaseModel):
    user_id: int
    max_results: int
    min_commission_rate: float
    preferred_platforms: str
    price_alert_enabled: int
    language: str


class UserSettingsUpdate(BaseModel):
    max_results: Optional[int] = Field(None, ge=1, le=50)
    min_commission_rate: Optional[float] = Field(None, ge=0)
    preferred_platforms: Optional[str] = None
    price_alert_enabled: Optional[int] = Field(None, ge=0, le=1)
    language: Optional[str] = None


class SearchHistoryItem(BaseModel):
    id: int
    user_id: int
    query: str
    platform: str
    results_count: int
    max_price: Optional[float]
    min_commission: Optional[float]
    created_at: int


class PriceAlertResponse(BaseModel):
    id: int
    user_id: int
    product_id: str
    platform: str
    product_name: str
    product_url: str
    target_price: float
    current_price: Optional[float]
    commission_rate: Optional[float]
    affiliate_url: Optional[str]
    is_active: int
    triggered_at: Optional[int]
    created_at: int
    updated_at: int


class PriceAlertCreate(BaseModel):
    product_id: str
    platform: str
    product_name: str
    product_url: str
    target_price: float
    current_price: Optional[float] = None
    commission_rate: Optional[float] = None
    affiliate_url: Optional[str] = None


class PriceAlertUpdate(BaseModel):
    target_price: Optional[float] = None
    is_active: Optional[int] = None


class ProductSearchRequest(BaseModel):
    keyword: str
    platform: str = "both"  # shopee, tiktok, both
    max_price: Optional[float] = None
    min_commission: Optional[float] = None
    page: int = 1
    page_size: int = 20


class ProductResponse(BaseModel):
    platform: str
    item_id: str
    name: str
    price: float
    original_price: Optional[float] = None
    discount: Optional[float] = None
    commission_rate: float
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    shop_name: Optional[str] = None
    shop_id: Optional[str] = None
    rating: Optional[float] = None
    sold: Optional[int] = None
    category_name: Optional[str] = None
    brand: Optional[str] = None


class SearchResponse(BaseModel):
    platform: str
    products: List[ProductResponse]
    total: int
    page: int
    page_size: int


class AffiliateLinkRequest(BaseModel):
    platform: str
    item_ids: List[str]
    sub_id: Optional[str] = None


class AffiliateLinkResponse(BaseModel):
    item_id: str
    affiliate_url: str


class StatsResponse(BaseModel):
    date: str
    total_searches: int
    total_users: int
    total_alerts_created: int
    total_alerts_triggered: int
    total_affiliate_links: int
    shopee_searches: int
    tiktok_searches: int
    errors: int


class DashboardStats(BaseModel):
    total_users: int
    total_searches_today: int
    total_alerts_active: int
    total_alerts_triggered_today: int
    total_affiliate_links_today: int
    searches_by_platform: Dict[str, int]
    top_searches: List[Dict[str, Any]]
    recent_alerts: List[Dict[str, Any]]


# ===================== AUTH =====================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        username: str = payload.get("sub")
        is_admin: bool = payload.get("is_admin", False)
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return TokenData(user_id=user_id, username=username, is_admin=is_admin)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_admin_user(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ===================== LIFESPAN =====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db.init_db()
    # Create admin user if not exists
    with get_db_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO users (user_id, username, first_name, is_admin, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
        """, (config.telegram.admin_ids[0] if config.telegram.admin_ids else 1, "admin", "Admin", int(datetime.now().timestamp()), int(datetime.now().timestamp())))
    yield
    # Shutdown
    if hasattr(_thread_local, "conn"):
        _thread_local.conn.close()


# ===================== FASTAPI APP =====================

app = FastAPI(
    title="Affiliate Finder Dashboard API",
    description="REST API for Affiliate Finder Dashboard",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security_scheme = HTTPBearer()


# ===================== AUTH ENDPOINTS =====================

@app.post("/auth/login", response_model=Token)
async def login(request: LoginRequest):
    """Login with username/password"""
    conn = get_db_conn()
    row = conn.execute(
        "SELECT user_id, username, password_hash, is_admin FROM users WHERE username = ?",
        (request.username,)
    ).fetchone()
    
    if not row or not verify_password(request.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(
        data={"sub": request.username, "user_id": row["user_id"], "is_admin": row["is_admin"]}
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/auth/register", response_model=UserResponse)
async def register(request: LoginRequest, current_user: TokenData = Depends(get_admin_user)):
    """Create new user (admin only)"""
    hashed = get_password_hash(request.password)
    conn = get_db_conn()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, first_name, is_admin, created_at, updated_at) VALUES (?, ?, ?, 0, ?, ?)",
            (request.username, hashed, request.username, int(datetime.now().timestamp()), int(datetime.now().timestamp()))
        )
        user_id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    return UserResponse(
        user_id=user_id,
        username=request.username,
        first_name=request.username,
        is_admin=False,
        created_at=int(datetime.now().timestamp())
    )


@app.get("/auth/me", response_model=UserResponse)
async def get_me(current_user: TokenData = Depends(get_current_user)):
    """Get current user info"""
    conn = get_db_conn()
    row = conn.execute(
        "SELECT user_id, username, first_name, is_admin, created_at FROM users WHERE user_id = ?",
        (current_user.user_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**dict(row))


# ===================== USER SETTINGS =====================

@app.get("/users/me/settings", response_model=UserSettingsResponse)
async def get_my_settings(current_user: TokenData = Depends(get_current_user)):
    """Get current user settings"""
    settings = db.get_user_settings(current_user.user_id)
    return UserSettingsResponse(**settings)


@app.put("/users/me/settings", response_model=UserSettingsResponse)
async def update_my_settings(update: UserSettingsUpdate, current_user: TokenData = Depends(get_current_user)):
    """Update current user settings"""
    db.update_user_settings(current_user.user_id, **update.model_dump(exclude_unset=True))
    settings = db.get_user_settings(current_user.user_id)
    return UserSettingsResponse(**settings)


# ===================== SEARCH HISTORY =====================

@app.get("/search/history", response_model=List[SearchHistoryItem])
async def get_search_history(
    limit: int = Query(50, ge=1, le=200),
    current_user: TokenData = Depends(get_current_user)
):
    """Get current user's search history"""
    history = db.get_search_history(current_user.user_id, limit)
    return [SearchHistoryItem(**h) for h in history]


@app.delete("/search/history")
async def clear_search_history(current_user: TokenData = Depends(get_current_user)):
    """Clear current user's search history"""
    conn = get_db_conn()
    conn.execute("DELETE FROM search_history WHERE user_id = ?", (current_user.user_id,))
    conn.commit()
    return {"message": "Search history cleared"}


# ===================== PRICE ALERTS =====================

@app.get("/alerts", response_model=List[PriceAlertResponse])
async def get_alerts(
    active_only: bool = Query(True),
    current_user: TokenData = Depends(get_current_user)
):
    """Get user's price alerts"""
    alerts = db.get_user_alerts(current_user.user_id, active_only)
    return [PriceAlertResponse(**a) for a in alerts]


@app.post("/alerts", response_model=PriceAlertResponse)
async def create_alert(alert: PriceAlertCreate, current_user: TokenData = Depends(get_current_user)):
    """Create a new price alert"""
    alert_id = db.create_price_alert(
        user_id=current_user.user_id,
        product_id=alert.product_id,
        platform=alert.platform,
        product_name=alert.product_name,
        product_url=alert.product_url,
        target_price=alert.target_price,
        current_price=alert.current_price,
        commission_rate=alert.commission_rate,
        affiliate_url=alert.affiliate_url
    )
    alert_data = db.get_alert_by_id(alert_id)
    return PriceAlertResponse(**alert_data)


@app.put("/alerts/{alert_id}", response_model=PriceAlertResponse)
async def update_alert(
    alert_id: int, 
    update: PriceAlertUpdate, 
    current_user: TokenData = Depends(get_current_user)
):
    """Update a price alert"""
    conn = get_db_conn()
    # Verify ownership
    row = conn.execute(
        "SELECT * FROM price_alerts WHERE id = ? AND user_id = ?",
        (alert_id, current_user.user_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    update_data = update.model_dump(exclude_unset=True)
    if update_data:
        set_clause = ", ".join(f"{k} = ?" for k in update_data)
        values = list(update_data.values()) + [int(datetime.now().timestamp()), alert_id]
        conn.execute(f"UPDATE price_alerts SET {set_clause}, updated_at = ? WHERE id = ?", values)
        conn.commit()
    
    alert_data = db.get_alert_by_id(alert_id)
    return PriceAlertResponse(**alert_data)


@app.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: int, current_user: TokenData = Depends(get_current_user)):
    """Delete/deactivate a price alert"""
    success = db.delete_alert(alert_id, current_user.user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert deleted"}


# ===================== PRODUCT SEARCH =====================

@app.post("/search", response_model=Dict[str, SearchResponse])
async def search_products(request: ProductSearchRequest, current_user: TokenData = Depends(get_current_user)):
    """Search products across platforms"""
    if request.platform == "both":
        results = PlatformFactory.search_all(
            request.keyword,
            max_price=request.max_price,
            min_commission=request.min_commission
        )
    else:
        results = {request.platform: PlatformFactory.search_all(
            request.keyword,
            max_price=request.max_price,
            min_commission=request.min_commission
        ).get(request.platform, [])}
    
    # Log search
    total_results = sum(len(r) for r in results.values())
    db.log_search(
        current_user.user_id,
        request.keyword,
        request.platform,
        total_results,
        request.max_price,
        request.min_commission
    )
    
    # Format response
    formatted = {}
    for platform, products in results.items():
        formatted[platform] = SearchResponse(
            platform=platform,
            products=[ProductResponse(**p) for p in products],
            total=len(products),
            page=1,
            page_size=len(products)
        )
    
    return formatted


@app.post("/search/affiliate-links", response_model=List[AffiliateLinkResponse])
async def generate_affiliate_links(request: AffiliateLinkRequest, current_user: TokenData = Depends(get_current_user)):
    """Generate affiliate links for products"""
    links = PlatformFactory.generate_affiliate_links(request.platform, request.item_ids, request.sub_id)
    
    # Log affiliate links
    for item_id, url in links.items():
        db.log_affiliate_link(current_user.user_id, request.platform, item_id, "", url)
    
    return [AffiliateLinkResponse(item_id=k, affiliate_url=v) for k, v in links.items()]


@app.get("/categories/{platform}", response_model=List[Dict])
async def get_categories(platform: str, current_user: TokenData = Depends(get_current_user)):
    """Get categories for a platform"""
    categories = PlatformFactory.get_categories(platform)
    return categories


# ===================== STATS & DASHBOARD =====================

@app.get("/stats/today", response_model=StatsResponse)
async def get_today_stats(current_user: TokenData = Depends(get_current_user)):
    """Get today's stats"""
    today = datetime.now().strftime("%Y-%m-%d")
    stats = db.get_stats(today)
    return StatsResponse(date=today, **stats)


@app.get("/stats/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(current_user: TokenData = Depends(get_admin_user)):
    """Get dashboard overview stats (admin only)"""
    conn = get_db_conn()
    
    # Total users
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    
    # Today's searches
    today = datetime.now().strftime("%Y-%m-%d")
    today_stats = db.get_stats(today)
    
    # Active alerts
    active_alerts = conn.execute("SELECT COUNT(*) FROM price_alerts WHERE is_active = 1").fetchone()[0]
    
    # Today's triggered alerts
    today_start = int(datetime.now().replace(hour=0, minute=0, second=0).timestamp())
    triggered_today = conn.execute(
        "SELECT COUNT(*) FROM price_alerts WHERE triggered_at >= ?", (today_start,)
    ).fetchone()[0]
    
    # Today's affiliate links
    affiliate_today = conn.execute(
        "SELECT COUNT(*) FROM affiliate_links WHERE created_at >= ?", (today_start,)
    ).fetchone()[0]
    
    # Searches by platform
    platform_searches = {
        "shopee": today_stats.get("shopee_searches", 0),
        "tiktok": today_stats.get("tiktok_searches", 0)
    }
    
    # Top searches today
    top_searches = conn.execute("""
        SELECT query, COUNT(*) as count FROM search_history 
        WHERE created_at >= ? GROUP BY query ORDER BY count DESC LIMIT 10
    """, (today_start,)).fetchall()
    
    # Recent alerts
    recent_alerts = conn.execute("""
        SELECT a.*, u.username FROM price_alerts a
        JOIN users u ON a.user_id = u.user_id
        WHERE a.created_at >= ?
        ORDER BY a.created_at DESC LIMIT 10
    """, (today_start,)).fetchall()
    
    return DashboardStats(
        total_users=total_users,
        total_searches_today=today_stats.get("total_searches", 0),
        total_alerts_active=active_alerts,
        total_alerts_triggered_today=triggered_today,
        total_affiliate_links_today=affiliate_today,
        searches_by_platform=platform_searches,
        top_searches=[dict(r) for r in top_searches],
        recent_alerts=[dict(r) for r in recent_alerts]
    )


@app.get("/stats/range")
async def get_stats_range(
    days: int = Query(7, ge=1, le=90),
    current_user: TokenData = Depends(get_admin_user)
):
    """Get stats for date range"""
    stats = db.get_recent_stats(days)
    return [StatsResponse(**s) for s in stats]


# ===================== USER MANAGEMENT (ADMIN) =====================

@app.get("/admin/users", response_model=List[UserResponse])
async def list_users(current_user: TokenData = Depends(get_admin_user)):
    """List all users (admin only)"""
    users = db.get_all_users()
    return [UserResponse(**u) for u in users]


@app.get("/admin/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, current_user: TokenData = Depends(get_admin_user)):
    """Get user by ID (admin only)"""
    conn = get_db_conn()
    row = conn.execute(
        "SELECT user_id, username, first_name, is_admin, created_at FROM users WHERE user_id = ?",
        (user_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**dict(row))


@app.put("/admin/users/{user_id}/admin")
async def toggle_admin(user_id: int, current_user: TokenData = Depends(get_admin_user)):
    """Toggle admin status (admin only)"""
    conn = get_db_conn()
    row = conn.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    new_status = 0 if row["is_admin"] else 1
    conn.execute("UPDATE users SET is_admin = ?, updated_at = ? WHERE user_id = ?",
                 (new_status, int(datetime.now().timestamp()), user_id))
    conn.commit()
    return {"user_id": user_id, "is_admin": bool(new_status)}


@app.delete("/admin/users/{user_id}")
async def delete_user(user_id: int, current_user: TokenData = Depends(get_admin_user)):
    """Delete user (admin only)"""
    if user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    conn = get_db_conn()
    conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    return {"message": "User deleted"}


# ===================== MAINTENANCE =====================

@app.post("/admin/cleanup")
async def cleanup_old_data(days: int = 90, current_user: TokenData = Depends(get_admin_user)):
    """Clean up old data (admin only)"""
    results = db.cleanup_old_data(days)
    return {"cleaned": results}


# ===================== HEALTH =====================

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# ===================== RUN =====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)