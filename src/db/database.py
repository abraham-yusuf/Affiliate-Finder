"""
Database layer for Affiliate Finder Bot
SQLite with thread-safe operations
"""
import sqlite3
import threading
import time
import json
from typing import Dict, List, Optional, Any
from contextlib import contextmanager
from src.config import get_config

config = get_config()

_lock = threading.Lock()
_thread_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Get thread-local database connection"""
    if not hasattr(_thread_local, "conn") or _thread_local.conn is None:
        _thread_local.conn = sqlite3.connect(config.database.path, check_same_thread=False)
        _thread_local.conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        _thread_local.conn.execute("PRAGMA journal_mode=WAL")
        _thread_local.conn.execute("PRAGMA busy_timeout=5000")
    return _thread_local.conn


@contextmanager
def get_db():
    """Context manager for database operations"""
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db():
    """Initialize database tables"""
    with _lock, get_db() as c:
        # Users table
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_admin INTEGER DEFAULT 0,
                created_at INTEGER DEFAULT (strftime('%s', 'now')),
                updated_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
        """)

        # User settings
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                max_results INTEGER DEFAULT 10,
                min_commission_rate REAL DEFAULT 1.0,
                preferred_platforms TEXT DEFAULT 'shopee,tiktok',  -- comma separated
                price_alert_enabled INTEGER DEFAULT 1,
                language TEXT DEFAULT 'id',
                updated_at INTEGER DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Search history
        c.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                platform TEXT NOT NULL,  -- 'shopee', 'tiktok', 'both'
                results_count INTEGER DEFAULT 0,
                max_price REAL,
                min_commission REAL,
                created_at INTEGER DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Price alerts
        c.execute("""
            CREATE TABLE IF NOT EXISTS price_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id TEXT NOT NULL,
                platform TEXT NOT NULL,  -- 'shopee', 'tiktok'
                product_name TEXT,
                product_url TEXT,
                target_price REAL NOT NULL,
                current_price REAL,
                commission_rate REAL,
                affiliate_url TEXT,
                is_active INTEGER DEFAULT 1,
                triggered_at INTEGER,
                created_at INTEGER DEFAULT (strftime('%s', 'now')),
                updated_at INTEGER DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Product cache
        c.execute("""
            CREATE TABLE IF NOT EXISTS product_cache (
                cache_key TEXT PRIMARY KEY,  -- platform:product_id
                platform TEXT NOT NULL,
                product_id TEXT NOT NULL,
                data TEXT NOT NULL,  -- JSON
                expires_at INTEGER NOT NULL,
                created_at INTEGER DEFAULT (strftime('%s', 'now'))
            )
        """)

        # Affiliate links generated
        c.execute("""
            CREATE TABLE IF NOT EXISTS affiliate_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                product_id TEXT NOT NULL,
                original_url TEXT NOT NULL,
                affiliate_url TEXT NOT NULL,
                commission_rate REAL,
                created_at INTEGER DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Bot stats
        c.execute("""
            CREATE TABLE IF NOT EXISTS bot_stats (
                date TEXT PRIMARY KEY,  -- YYYY-MM-DD
                total_searches INTEGER DEFAULT 0,
                total_users INTEGER DEFAULT 0,
                total_alerts_created INTEGER DEFAULT 0,
                total_alerts_triggered INTEGER DEFAULT 0,
                total_affiliate_links INTEGER DEFAULT 0,
                shopee_searches INTEGER DEFAULT 0,
                tiktok_searches INTEGER DEFAULT 0,
                errors INTEGER DEFAULT 0
            )
        """)

        # Create indexes
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_search_history_date ON search_history(created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_price_alerts_user ON price_alerts(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_price_alerts_active ON price_alerts(is_active)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_price_alerts_product ON price_alerts(product_id, platform)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_product_cache_expires ON product_cache(expires_at)")


# ===================== USER OPERATIONS =====================

def get_or_create_user(user_id: int, username: str = None, first_name: str = None, is_admin: bool = False) -> Dict:
    """Get or create user"""
    with get_db() as c:
        row = c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            # Update last seen
            c.execute("UPDATE users SET username = ?, first_name = ?, updated_at = ? WHERE user_id = ?",
                      (username, first_name, int(time.time()), user_id))
            return dict(row)
        
        c.execute("""
            INSERT INTO users (user_id, username, first_name, is_admin, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, first_name, 1 if is_admin else 0, int(time.time()), int(time.time())))
        
        # Create default settings
        c.execute("""
            INSERT INTO user_settings (user_id) VALUES (?)
        """, (user_id,))
        
        return {"user_id": user_id, "username": username, "first_name": first_name, "is_admin": is_admin}


def get_user_settings(user_id: int) -> Dict:
    """Get user settings"""
    with get_db() as c:
        row = c.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
        if row:
            return dict(row)
        # Return defaults
        return {
            "user_id": user_id,
            "max_results": config.settings.default_max_results,
            "min_commission_rate": config.settings.default_min_commission_rate,
            "preferred_platforms": "shopee,tiktok",
            "price_alert_enabled": 1,
            "language": "id"
        }


def update_user_settings(user_id: int, **kwargs) -> bool:
    """Update user settings"""
    allowed = {"max_results", "min_commission_rate", "preferred_platforms", "price_alert_enabled", "language"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    
    updates["updated_at"] = int(time.time())
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [user_id]
    
    with get_db() as c:
        c.execute(f"UPDATE user_settings SET {set_clause} WHERE user_id = ?", values)
    return True


# ===================== SEARCH HISTORY =====================

def log_search(user_id: int, query: str, platform: str, results_count: int = 0, 
               max_price: float = None, min_commission: float = None) -> int:
    """Log search query"""
    with get_db() as c:
        cur = c.execute("""
            INSERT INTO search_history (user_id, query, platform, results_count, max_price, min_commission, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, query, platform, results_count, max_price, min_commission, int(time.time())))
        return cur.lastrowid


def get_search_history(user_id: int, limit: int = 20) -> List[Dict]:
    """Get user's recent searches"""
    with get_db() as c:
        rows = c.execute("""
            SELECT * FROM search_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


# ===================== PRICE ALERTS =====================

def create_price_alert(user_id: int, product_id: str, platform: str, 
                       product_name: str, product_url: str, target_price: float,
                       current_price: float = None, commission_rate: float = None,
                       affiliate_url: str = None) -> int:
    """Create a price drop alert"""
    with get_db() as c:
        # Check if alert already exists
        existing = c.execute("""
            SELECT id FROM price_alerts 
            WHERE user_id = ? AND product_id = ? AND platform = ? AND is_active = 1
        """, (user_id, product_id, platform)).fetchone()
        
        if existing:
            # Update target price if lower
            if target_price < (existing_row := c.execute("SELECT target_price FROM price_alerts WHERE id = ?", (existing["id"],)).fetchone())["target_price"]:
                c.execute("UPDATE price_alerts SET target_price = ?, updated_at = ? WHERE id = ?",
                          (target_price, int(time.time()), existing["id"]))
            return existing["id"]
        
        cur = c.execute("""
            INSERT INTO price_alerts (user_id, product_id, platform, product_name, product_url,
                                      target_price, current_price, commission_rate, affiliate_url, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (user_id, product_id, platform, product_name, product_url,
              target_price, current_price, commission_rate, affiliate_url,
              int(time.time()), int(time.time())))
        return cur.lastrowid


def get_user_alerts(user_id: int, active_only: bool = True) -> List[Dict]:
    """Get user's price alerts"""
    with get_db() as c:
        query = "SELECT * FROM price_alerts WHERE user_id = ?"
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY created_at DESC"
        rows = c.execute(query, (user_id,)).fetchall()
        return [dict(r) for r in rows]


def get_all_active_alerts() -> List[Dict]:
    """Get all active alerts for monitoring"""
    with get_db() as c:
        rows = c.execute("""
            SELECT * FROM price_alerts WHERE is_active = 1
        """).fetchall()
        return [dict(r) for r in rows]


def update_alert_price(alert_id: int, current_price: float, triggered: bool = False) -> bool:
    """Update alert's current price and trigger status"""
    with get_db() as c:
        if triggered:
            c.execute("""
                UPDATE price_alerts 
                SET current_price = ?, is_active = 0, triggered_at = ?, updated_at = ?
                WHERE id = ?
            """, (current_price, int(time.time()), int(time.time()), alert_id))
        else:
            c.execute("""
                UPDATE price_alerts 
                SET current_price = ?, updated_at = ?
                WHERE id = ?
            """, (current_price, int(time.time()), alert_id))
        return True


def delete_alert(alert_id: int, user_id: int = None) -> bool:
    """Delete/deactivate price alert"""
    with get_db() as c:
        if user_id:
            c.execute("UPDATE price_alerts SET is_active = 0, updated_at = ? WHERE id = ? AND user_id = ?",
                      (int(time.time()), alert_id, user_id))
        else:
            c.execute("UPDATE price_alerts SET is_active = 0, updated_at = ? WHERE id = ?",
                      (int(time.time()), alert_id))
        return c.rowcount > 0


def get_alert_by_id(alert_id: int) -> Optional[Dict]:
    """Get alert by ID"""
    with get_db() as c:
        row = c.execute("SELECT * FROM price_alerts WHERE id = ?", (alert_id,)).fetchone()
        return dict(row) if row else None


# ===================== ADMIN / UTILS =====================

def get_cached_product(cache_key: str) -> Optional[Dict]:
    """Get cached product data"""
    with get_db() as c:
        row = c.execute("""
            SELECT data FROM product_cache 
            WHERE cache_key = ? AND expires_at > ?
        """, (cache_key, int(time.time()))).fetchone()
        if row:
            return json.loads(row["data"])
    return None


def set_cached_product(cache_key: str, platform: str, product_id: str, 
                       data: Dict, ttl: int = None) -> bool:
    """Cache product data"""
    ttl = ttl or config.settings.cache_ttl_seconds
    expires_at = int(time.time()) + ttl
    
    with get_db() as c:
        c.execute("""
            INSERT OR REPLACE INTO product_cache (cache_key, platform, product_id, data, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (cache_key, platform, product_id, json.dumps(data), expires_at, int(time.time())))
    return True


def clear_expired_cache() -> int:
    """Remove expired cache entries"""
    with get_db() as c:
        cur = c.execute("DELETE FROM product_cache WHERE expires_at <= ?", (int(time.time()),))
        return cur.rowcount


# ===================== AFFILIATE LINKS =====================

def log_affiliate_link(user_id: int, platform: str, product_id: str,
                       original_url: str, affiliate_url: str, 
                       commission_rate: float = None) -> int:
    """Log generated affiliate link"""
    with get_db() as c:
        cur = c.execute("""
            INSERT INTO affiliate_links (user_id, platform, product_id, original_url, affiliate_url, commission_rate, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, platform, product_id, original_url, affiliate_url, commission_rate, int(time.time())))
        return cur.lastrowid


def get_user_affiliate_links(user_id: int, limit: int = 50) -> List[Dict]:
    """Get user's generated affiliate links"""
    with get_db() as c:
        rows = c.execute("""
            SELECT * FROM affiliate_links WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
        """, (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


# ===================== STATS =====================

def increment_stat(date: str, field: str, value: int = 1) -> bool:
    """Increment daily stat counter"""
    allowed = {"total_searches", "total_users", "total_alerts_created", "total_alerts_triggered",
               "total_affiliate_links", "shopee_searches", "tiktok_searches", "errors"}
    if field not in allowed:
        return False
    
    with get_db() as c:
        c.execute(f"""
            INSERT INTO bot_stats (date, {field}) VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET {field} = {field} + excluded.{field}
        """, (date, value))
    return True


def get_stats(date: str = None) -> Dict:
    """Get bot stats"""
    if not date:
        date = time.strftime("%Y-%m-%d")
    
    with get_db() as c:
        row = c.execute("SELECT * FROM bot_stats WHERE date = ?", (date,)).fetchone()
        return dict(row) if row else {}


def get_recent_stats(days: int = 7) -> List[Dict]:
    """Get recent stats"""
    with get_db() as c:
        rows = c.execute("""
            SELECT * FROM bot_stats 
            WHERE date >= date('now', ?) 
            ORDER BY date DESC
        """, (f"-{days} days",)).fetchall()
        return [dict(r) for r in rows]


# ===================== ADMIN / UTILS =====================

def get_all_users() -> List[Dict]:
    """Get all users (admin)"""
    with get_db() as c:
        rows = c.execute("SELECT user_id, username, first_name, is_admin, created_at FROM users ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    with get_db() as c:
        row = c.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row and row["is_admin"])


def cleanup_old_data(days: int = 90) -> Dict[str, int]:
    """Clean up old data"""
    cutoff = int(time.time()) - (days * 86400)
    results = {}
    
    with get_db() as c:
        for table, date_col in [("search_history", "created_at"), 
                                 ("affiliate_links", "created_at")]:
            cur = c.execute(f"DELETE FROM {table} WHERE {date_col} < ?", (cutoff,))
            results[table] = cur.rowcount
    
    return results


# Initialize on import
init_db()