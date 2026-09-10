"""
Streamlit Frontend for Affiliate Finder Dashboard
"""
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os
from typing import Optional, Dict, List

# Page config
st.set_page_config(
    page_title="Affiliate Finder Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Base URL
API_BASE = os.getenv("DASHBOARD_API_URL", "http://localhost:8000")

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: bold;
    }
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    .alert-card {
        border-left: 4px solid #ff4b4b;
        padding: 1rem;
        background: #fff5f5;
        border-radius: 5px;
        margin: 0.5rem 0;
    }
    .alert-card.active {
        border-left-color: #00d16a;
        background: #f0fff4;
    }
    .product-card {
        border: 1px solid #e1e4e8;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        background: white;
    }
    .sidebar-section {
        margin-bottom: 2rem;
    }
    .stButton > button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)


# ===================== SESSION STATE =====================

if "token" not in st.session_state:
    st.session_state.token = None
if "user" not in st.session_state:
    st.session_state.user = None
if "current_page" not in st.session_state:
    st.session_state.current_page = "dashboard"


# ===================== API HELPERS =====================

def api_request(method: str, endpoint: str, data: dict = None, params: dict = None) -> dict:
    """Make authenticated API request"""
    headers = {}
    if st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    
    url = f"{API_BASE}{endpoint}"
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=params, timeout=30)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=30)
        elif method == "PUT":
            response = requests.put(url, headers=headers, json=data, timeout=30)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        if response.status_code == 401:
            st.session_state.token = None
            st.session_state.user = None
            st.rerun()
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"API Error: {str(e)}")
        return {}


def login(username: str, password: str) -> bool:
    """Login and store token"""
    try:
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"username": username, "password": password},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            st.session_state.token = data["access_token"]
            # Get user info
            user_info = api_request("GET", "/auth/me")
            st.session_state.user = user_info
            return True
        else:
            st.error(f"Login failed: {response.json().get('detail', 'Invalid credentials')}")
            return False
    except Exception as e:
        st.error(f"Login error: {str(e)}")
        return False


def logout():
    st.session_state.token = None
    st.session_state.user = None
    st.session_state.current_page = "dashboard"
    st.rerun()


# ===================== UI COMPONENTS =====================

def render_login_page():
    """Render login page"""
    st.markdown('<h1 class="main-header">📊 Affiliate Finder Dashboard</h1>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("🔐 Login")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)
            
            if submitted:
                if login(username, password):
                    st.success("Login successful!")
                    st.rerun()
            
            st.info("Default admin: admin / admin (change after first login)")


def render_sidebar():
    """Render sidebar navigation"""
    with st.sidebar:
        st.markdown("### 📊 Affiliate Finder")
        if st.session_state.user:
            st.write(f"👤 {st.session_state.user.get('username', 'User')}")
            if st.session_state.user.get('is_admin'):
                st.success("👑 Admin")
        
        st.markdown("---")
        
        pages = {
            "📊 Dashboard": "dashboard",
            "🔍 Product Search": "search",
            "🔔 Price Alerts": "alerts",
            "📊 Search History": "history",
            "🔗 Affiliate Links": "affiliate_links",
            "⚙️ Settings": "settings",
        }
        
        if st.session_state.user and st.session_state.user.get('is_admin'):
            pages["👑 Admin Panel"] = "admin"
        
        for label, page in pages.items():
            if st.button(label, key=f"nav_{page}", use_container_width=True):
                st.session_state.current_page = page
                st.rerun()
        
        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            logout()


def render_metric_card(label: str, value: str, delta: str = None):
    """Render a metric card"""
    delta_html = f"<div style='font-size: 0.8rem; color: #00d16a;'>{delta}</div>" if delta else ""
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)


# ===================== PAGE RENDERERS =====================

def render_dashboard():
    """Render main dashboard"""
    st.markdown('<h1 class="main-header">📊 Dashboard Overview</h1>', unsafe_allow_html=True)
    
    if st.session_state.user and st.session_state.user.get('is_admin'):
        # Admin dashboard
        stats = api_request("GET", "/stats/dashboard")
        if stats:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                render_metric_card("Total Users", f"{stats.get('total_users', 0):,}")
            with col2:
                render_metric_card("Searches Today", f"{stats.get('total_searches_today', 0):,}")
            with col3:
                render_metric_card("Active Alerts", f"{stats.get('total_alerts_active', 0):,}")
            with col4:
                render_metric_card("Affiliate Links Today", f"{stats.get('total_affiliate_links_today', 0):,}")
            
            st.markdown("---")
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("🔍 Searches by Platform")
                platform_data = stats.get('searches_by_platform', {})
                if platform_data:
                    fig = px.pie(
                        values=list(platform_data.values()),
                        names=list(platform_data.keys()),
                        title="Searches by Platform"
                    )
                    st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("🏆 Top Searches Today")
                top_searches = stats.get('top_searches', [])
                if top_searches:
                    df = pd.DataFrame(top_searches)
                    fig = px.bar(df, x='query', y='count', title="Top Search Queries")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No searches today yet")
            
            st.markdown("---")
            st.subheader("🔔 Recent Alerts")
            recent_alerts = stats.get('recent_alerts', [])
            if recent_alerts:
                df = pd.DataFrame(recent_alerts)
                st.dataframe(df[['product_name', 'platform', 'target_price', 'current_price', 'is_active']], use_container_width=True)
            else:
                st.info("No recent alerts")
    else:
        # User dashboard
        st.info("👋 Welcome! Use the sidebar to search products, set alerts, and view history.")


def render_search_page():
    """Render product search page"""
    st.markdown('<h1 class="main-header">🔍 Product Search</h1>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        keyword = st.text_input("🔍 Search Keyword", placeholder="e.g., gula gmp 1kg, minyak goreng 1lt")
    
    with col2:
        platform = st.selectbox("Platform", ["both", "shopee", "tiktok"], format_func=lambda x: {"both": "🔍 Both", "shopee": "🛍️ Shopee", "tiktok": "🎵 TikTok Shop"}[x])
    
    col1, col2 = st.columns(2)
    with col1:
        max_price = st.number_input("Max Price (Rp)", min_value=0, value=0, step=1000, help="0 = no limit")
    with col2:
        min_commission = st.number_input("Min Commission (%)", min_value=0.0, value=0.0, step=0.5)
    
    if st.button("🔍 Search", type="primary", use_container_width=True):
        if keyword:
            with st.spinner("Searching..."):
                results = api_request("POST", "/search", {
                    "keyword": keyword,
                    "platform": platform,
                    "max_price": max_price if max_price > 0 else None,
                    "min_commission": min_commission if min_commission > 0 else None
                })
                
                if results:
                    st.session_state.search_results = results
                    st.session_state.search_keyword = keyword
                    st.success(f"Found products!")
                else:
                    st.error("Search failed")
        else:
            st.warning("Please enter a keyword")
    
    # Display results
    if "search_results" in st.session_state:
        results = st.session_state.search_results
        keyword = st.session_state.search_keyword
        
        st.markdown(f"### Results for: *{keyword}*")
        
        for plat, data in results.items():
            if data.get("products"):
                platform_name = "Shopee" if plat == "shopee" else "TikTok Shop"
                platform_emoji = "🛍️" if plat == "shopee" else "🎵"
                
                st.markdown(f"#### {platform_emoji} {platform_name} ({len(data['products'])} products)")
                
                for i, product in enumerate(data["products"][:10]):
                    with st.container():
                        col1, col2, col3 = st.columns([3, 2, 1])
                        with col1:
                            st.markdown(f"**{product['name'][:60]}**")
                            if product.get('shop_name'):
                                st.caption(f"🏪 {product['shop_name']}")
                        with col2:
                            st.metric("Price", f"Rp{product['price']:,.0f}")
                            st.caption(f"Commission: {product.get('commission_rate', 0):.1f}%")
                        with col3:
                            if st.button("🔗 Get Link", key=f"link_{plat}_{i}"):
                                links = api_request("POST", "/search/affiliate-links", {
                                    "platform": plat,
                                    "item_ids": [product['item_id']]
                                })
                                if links:
                                    st.success(f"Link: {links[0]['affiliate_url']}")
                                    st.code(links[0]['affiliate_url'])
                        
                        st.divider()


def render_alerts_page():
    """Render price alerts page"""
    st.markdown('<h1 class="main-header">🔔 Price Alerts</h1>', unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["🔔 My Alerts", "➕ Create Alert"])
    
    with tab1:
        alerts = api_request("GET", "/alerts", params={"active_only": True})
        if alerts:
            for alert in alerts:
                status = "🟢 Active" if alert['is_active'] else "🔴 Triggered"
                platform_emoji = "🛍️" if alert['platform'] == 'shopee' else "🎵"
                
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    with col1:
                        st.markdown(f"**{platform_emoji} {alert['product_name']}**")
                        st.caption(f"Platform: {alert['platform']} | {status}")
                    with col2:
                        st.metric("Target", f"Rp{alert['target_price']:,.0f}")
                        if alert['current_price']:
                            st.caption(f"Current: Rp{alert['current_price']:,.0f}")
                    with col3:
                        if st.button("🗑️ Delete", key=f"del_{alert['id']}"):
                            api_request("DELETE", f"/alerts/{alert['id']}")
                            st.rerun()
                st.divider()
        else:
            st.info("No active alerts. Create one in the 'Create Alert' tab.")
    
    with tab2:
        st.subheader("Create New Price Alert")
        with st.form("create_alert"):
            col1, col2 = st.columns(2)
            with col1:
                product_id = st.text_input("Product ID")
                platform = st.selectbox("Platform", ["shopee", "tiktok"])
                product_name = st.text_input("Product Name")
            with col2:
                product_url = st.text_input("Product URL")
                target_price = st.number_input("Target Price (Rp)", min_value=1, step=1000)
                current_price = st.number_input("Current Price (Rp)", min_value=0, step=1000)
                commission_rate = st.number_input("Commission Rate (%)", min_value=0.0, step=0.1)
                affiliate_url = st.text_input("Affiliate URL (optional)")
            
            if st.form_submit_button("Create Alert"):
                alert = api_request("POST", "/alerts", {
                    "product_id": product_id,
                    "platform": platform,
                    "product_name": product_name,
                    "product_url": product_url,
                    "target_price": target_price,
                    "current_price": current_price if current_price > 0 else None,
                    "commission_rate": commission_rate if commission_rate > 0 else None,
                    "affiliate_url": affiliate_url if affiliate_url else None
                })
                if alert:
                    st.success("Alert created!")
                    st.rerun()


def render_history_page():
    """Render search history page"""
    st.markdown('<h1 class="main-header">📊 Search History</h1>', unsafe_allow_html=True)
    
    history = api_request("GET", "/search/history", params={"limit": 50})
    if history:
        df = pd.DataFrame(history)
        df['created_at'] = pd.to_datetime(df['created_at'], unit='s')
        df['platform_emoji'] = df['platform'].map({'shopee': '🛍️', 'tiktok': '🎵', 'both': '🔍'})
        
        st.dataframe(
            df[['created_at', 'platform_emoji', 'query', 'platform', 'results_count', 'max_price', 'min_commission']],
            use_container_width=True,
            column_config={
                "created_at": "Time",
                "platform_emoji": "Platform",
                "query": "Keyword",
                "platform": "Platform",
                "results_count": "Results",
                "max_price": "Max Price",
                "min_commission": "Min Comm %"
            }
        )
    else:
        st.info("No search history yet")


def render_affiliate_links_page():
    """Render affiliate links page"""
    st.markdown('<h1 class="main-header">🔗 Affiliate Links</h1>', unsafe_allow_html=True)
    
    links = api_request("GET", "/users/me/affiliate_links", params={"limit": 50})
    if links:
        df = pd.DataFrame(links)
        df['created_at'] = pd.to_datetime(df['created_at'], unit='s')
        platform_emoji = df['platform'].map({'shopee': '🛍️', 'tiktok': '🎵'})
        
        st.dataframe(
            df[['created_at', 'platform', 'product_id', 'affiliate_url', 'commission_rate']],
            use_container_width=True,
            column_config={
                "created_at": "Created",
                "platform": "Platform",
                "product_id": "Product ID",
                "affiliate_url": st.column_config.LinkColumn("Affiliate Link"),
                "commission_rate": "Commission %"
            }
        )
        
        # Export button
        csv = df.to_csv(index=False)
        st.download_button("📥 Download CSV", csv, "affiliate_links.csv", "text/csv")
    else:
        st.info("No affiliate links generated yet. Search products and generate links!")


def render_settings_page():
    """Render settings page"""
    st.markdown('<h1 class="main-header">⚙️ Settings</h1>', unsafe_allow_html=True)
    
    settings = api_request("GET", "/users/me/settings")
    if not settings:
        st.error("Failed to load settings")
        return
    
    with st.form("settings_form"):
        col1, col2 = st.columns(2)
        with col1:
            max_results = st.number_input("Max Results per Search", 1, 50, settings.get('max_results', 10))
            min_commission = st.number_input("Min Commission Rate (%)", 0.0, 100.0, settings.get('min_commission_rate', 1.0), step=0.1)
        with col2:
            platforms = st.text_input("Preferred Platforms (comma-separated)", settings.get('preferred_platforms', 'shopee,tiktok'))
            price_alert = st.checkbox("Enable Price Alerts", value=bool(settings.get('price_alert_enabled', 1)))
            language = st.selectbox("Language", ["id", "en"], index=0 if settings.get('language', 'id') == 'id' else 1)
        
        if st.form_submit_button("Save Settings"):
            api_request("PUT", "/users/me/settings", {
                "max_results": max_results,
                "min_commission_rate": min_commission,
                "preferred_platforms": platforms,
                "price_alert_enabled": 1 if price_alert else 0,
                "language": language
            })
            st.success("Settings saved!")
            st.rerun()


def render_admin_page():
    """Render admin panel"""
    st.markdown('<h1 class="main-header">👑 Admin Panel</h1>', unsafe_allow_html=True)
    
    if not st.session_state.user.get('is_admin'):
        st.error("Admin access required")
        return
    
    tab1, tab2, tab3 = st.tabs(["👥 Users", "📈 Stats", "🧹 Maintenance"])
    
    with tab1:
        st.subheader("User Management")
        users = api_request("GET", "/admin/users")
        if users:
            df = pd.DataFrame(users)
            st.dataframe(df, use_container_width=True)
            
            st.markdown("---")
            st.subheader("Create New User")
            with st.form("create_user"):
                new_user = st.text_input("Username")
                new_pass = st.text_input("Password", type="password")
                is_admin = st.checkbox("Admin")
                if st.form_submit_button("Create"):
                    api_request("POST", "/auth/register", {"username": new_user, "password": new_pass})
                    st.success("User created!")
                    st.rerun()
    
    with tab2:
        st.subheader("System Statistics")
        stats = api_request("GET", "/stats/dashboard")
        if stats:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Users", stats.get('total_users', 0))
            with col2:
                st.metric("Searches Today", stats.get('total_searches_today', 0))
            with col3:
                st.metric("Active Alerts", stats.get('total_alerts_active', 0))
            with col4:
                st.metric("Affiliate Links Today", stats.get('total_affiliate_links_today', 0))
            
            # Weekly stats
            weekly = api_request("GET", "/stats/range", params={"days": 7})
            if weekly:
                df = pd.DataFrame(weekly)
                df['date'] = pd.to_datetime(df['date'])
                fig = px.line(df, x='date', y=['total_searches', 'total_affiliate_links'], title="Weekly Activity")
                st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        st.subheader("Database Maintenance")
        if st.button("🧹 Cleanup Old Data (90 days)"):
            result = api_request("POST", "/admin/cleanup", {"days": 90})
            st.success(f"Cleaned: {result}")


# ===================== MAIN =====================

def main():
    """Main app entry point"""
    render_sidebar()
    
    if not st.session_state.token:
        render_login_page()
        return
    
    # Route to current page
    page = st.session_state.current_page
    
    if page == "dashboard":
        render_dashboard()
    elif page == "search":
        render_search_page()
    elif page == "alerts":
        render_alerts_page()
    elif page == "history":
        render_history_page()
    elif page == "affiliate_links":
        render_affiliate_links_page()
    elif page == "settings":
        render_settings_page()
    elif page == "admin":
        render_admin_page()
    else:
        render_dashboard()


if __name__ == "__main__":
    main()