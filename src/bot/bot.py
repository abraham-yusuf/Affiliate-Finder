"""
Telegram Bot for Affiliate Finder
"""
import asyncio
import logging
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)

from src.config import get_config
from src.db import database as db
from src.platforms import PlatformFactory, format_search_results, format_product_for_display
from src.bot.rate_limiter import check_rate_limit, check_access, get_rate_limiter, get_access_control

config = get_config()

# Conversation states
SEARCH_QUERY, SEARCH_PLATFORM, SEARCH_MAX_PRICE, SEARCH_MIN_COMMISSION = range(4)
ALERT_PRODUCT_ID, ALERT_TARGET_PRICE = range(4, 6)
SETTINGS_MENU, SETTINGS_VALUE = range(6, 8)

# User data keys
USER_DATA_SEARCH = "search_data"
USER_DATA_ALERT = "alert_data"

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in config.telegram.admin_ids


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Main menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("🔍 Cari Produk", callback_data="search")],
        [InlineKeyboardButton("🔔 Alert Harga", callback_data="alerts"),
         InlineKeyboardButton("📊 Riwayat Cari", callback_data="history")],
        [InlineKeyboardButton("⚙️ Pengaturan", callback_data="settings"),
         InlineKeyboardButton("📈 Statistik", callback_data="stats")],
        [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_platform_keyboard() -> InlineKeyboardMarkup:
    """Platform selection keyboard"""
    platforms = PlatformFactory.get_available_platforms()
    keyboard = []

    if "shopee" in platforms:
        keyboard.append([InlineKeyboardButton("🛍️ Shopee", callback_data="platform_shopee")])
    if "tiktok" in platforms:
        keyboard.append([InlineKeyboardButton("🎵 TikTok Shop", callback_data="platform_tiktok")])
    if len(platforms) > 1:
        keyboard.append([InlineKeyboardButton("🔍 Semua Platform", callback_data="platform_both")])

    keyboard.append([InlineKeyboardButton("« Kembali", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)


def get_price_keyboard() -> InlineKeyboardMarkup:
    """Price filter keyboard"""
    keyboard = [
        [InlineKeyboardButton("💰 ≤ 50.000", callback_data="max_price_50000"),
         InlineKeyboardButton("💰 ≤ 100.000", callback_data="max_price_100000")],
        [InlineKeyboardButton("💰 ≤ 500.000", callback_data="max_price_500000"),
         InlineKeyboardButton("💰 ≤ 1.000.000", callback_data="max_price_1000000")],
        [InlineKeyboardButton("💰 Custom...", callback_data="max_price_custom"),
         InlineKeyboardButton("⏭️ Lewati", callback_data="skip_price")],
        [InlineKeyboardButton("« Kembali", callback_data="search")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_commission_keyboard() -> InlineKeyboardMarkup:
    """Commission filter keyboard"""
    keyboard = [
        [InlineKeyboardButton("💵 ≥ 1%", callback_data="min_comm_1"),
         InlineKeyboardButton("💵 ≥ 3%", callback_data="min_comm_3")],
        [InlineKeyboardButton("💵 ≥ 5%", callback_data="min_comm_5"),
         InlineKeyboardButton("💵 ≥ 10%", callback_data="min_comm_10")],
        [InlineKeyboardButton("💵 Custom...", callback_data="min_comm_custom"),
         InlineKeyboardButton("⏭️ Lewati", callback_data="skip_commission")],
        [InlineKeyboardButton("« Kembali", callback_data="search")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_results_keyboard(platform: str, product_index: int, product_id: str) -> InlineKeyboardMarkup:
    """Keyboard for product results"""
    keyboard = [
        [InlineKeyboardButton("🔗 Dapatkan Link Afiliasi", callback_data=f"affiliate_{product_id}")],
        [InlineKeyboardButton("🔔 Buat Alert Harga", callback_data=f"alert_{product_id}"),
         InlineKeyboardButton("📊 Detail Produk", callback_data=f"detail_{product_id}")],
        [InlineKeyboardButton("🔍 Cari Lagi", callback_data="search"),
         InlineKeyboardButton("« Menu Utama", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_alert_keyboard(alert_id: int) -> InlineKeyboardMarkup:
    """Keyboard for alert management"""
    keyboard = [
        [InlineKeyboardButton("🗑️ Hapus Alert", callback_data=f"delete_alert_{alert_id}")],
        [InlineKeyboardButton("« Kembali", callback_data="alerts")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Settings keyboard"""
    keyboard = [
        [InlineKeyboardButton("🔢 Max Hasil", callback_data="set_max_results"),
         InlineKeyboardButton("💵 Min Komisi", callback_data="set_min_commission")],
        [InlineKeyboardButton("🌐 Platform Default", callback_data="set_platforms"),
         InlineKeyboardButton("🔔 Alert Harga", callback_data="set_price_alert")],
        [InlineKeyboardButton("🌐 Bahasa", callback_data="set_language"),
         InlineKeyboardButton("« Kembali", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


# ===================== COMMAND HANDLERS =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    user = update.effective_user
    db.get_or_create_user(
        user.id,
        username=user.username,
        first_name=user.first_name,
        is_admin=await is_admin(user.id)
    )

    welcome_text = (
        f"👋 Selamat datang, {user.first_name}!\n\n"
        f"🤖 <b>Affiliate Finder Bot</b>\n\n"
        f"Bot ini membantu Anda mencari produk dengan komisi afiliasi di:\n"
        f"🛍️ Shopee Affiliate\n"
        f"🎵 TikTok Shop Affiliate\n\n"
        f"Fitur utama:\n"
        f"🔍 Cari produk dengan filter harga & komisi\n"
        f"🔗 Generate link afiliasi otomatis\n"
        f"🔔 Alert harga turun (price drop alert)\n"
        f"📊 Riwayat pencarian & statistik\n\n"
        f"Gunakan menu di bawah untuk memulai:"
    )

    if update.message:
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())
    elif update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    help_text = (
        "📖 <b>Bantuan Affiliate Finder Bot</b>\n\n"
        "<b>Perintah Utama:</b>\n"
        "/start - Mulai bot & tampilkan menu\n"
        "/search - Cari produk langsung\n"
        "/alerts - Kelola alert harga\n"
        "/history - Riwayat pencarian\n"
        "/settings - Pengaturan bot\n"
        "/stats - Statistik penggunaan\n\n"
        "<b>Cara Pakai:</b>\n"
        "1. Tekan <b>🔍 Cari Produk</b>\n"
        "2. Pilih platform (Shopee/TikTok/Semua)\n"
        "3. Ketik kata kunci produk\n"
        "4. Filter harga maksimal (opsional)\n"
        "5. Filter komisi minimal (opsional)\n"
        "6. Lihat hasil & generate link afiliasi\n\n"
        "<b>Alert Harga:</b>\n"
        "• Set target harga untuk produk\n"
        "• Bot akan notif kalau harga turun\n"
        "• Kelola di menu 🔔 Alert Harga\n\n"
        "<b>Link Afiliasi:</b>\n"
        "• Otomatis generate link tracking\n"
        "• Copy & share ke media sosial\n\n"
        "Butuh bantuan? Hubungi admin."
    )

    if update.message:
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())
    elif update.callback_query:
        await update.callback_query.edit_message_text(help_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())


# ===================== SEARCH FLOW =====================

async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start search flow"""
    query = update.callback_query
    await query.answer()

    platforms = PlatformFactory.get_available_platforms()
    if not platforms:
        await query.edit_message_text(
            "⚠️ Belum ada platform yang dikonfigurasi. Hubungi admin.",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "🔍 <b>Cari Produk</b>\n\nPilih platform:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_platform_keyboard()
    )
    return SEARCH_PLATFORM


async def search_platform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle platform selection"""
    query = update.callback_query
    await query.answer()

    platform = query.data.replace("platform_", "")
    context.user_data[USER_DATA_SEARCH] = {"platform": platform}

    await query.edit_message_text(
        f"🔍 <b>Cari Produk di {platform.capitalize()}</b>\n\n"
        f"Ketik kata kunci produk yang dicari:\n"
        f"Contoh: <i>gula gmp 1kg</i>, <i>minyak goreng 1lt</i>, <i>sabun mandi</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Kembali", callback_data="search")]])
    )
    return SEARCH_QUERY


async def search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle search query input"""
    query_text = update.message.text.strip()
    context.user_data[USER_DATA_SEARCH]["query"] = query_text

    await update.message.reply_text(
        f"🔍 Mencari: <b>{query_text}</b>\n\n"
        f"Pilih filter harga maksimal (opsional):",
        parse_mode=ParseMode.HTML,
        reply_markup=get_price_keyboard()
    )
    return SEARCH_MAX_PRICE


async def search_max_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle max price filter"""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "skip_price":
        context.user_data[USER_DATA_SEARCH]["max_price"] = None
    elif data == "max_price_custom":
        await query.edit_message_text(
            "💰 Masukkan harga maksimal (dalam Rupiah):\nContoh: 50000",
            parse_mode=ParseMode.HTML
        )
        return SEARCH_MAX_PRICE
    else:
        price_map = {
            "max_price_50000": 50000,
            "max_price_100000": 100000,
            "max_price_500000": 500000,
            "max_price_1000000": 1000000,
        }
        context.user_data[USER_DATA_SEARCH]["max_price"] = price_map.get(data)

    await query.edit_message_text(
        "💵 Pilih komisi minimal (opsional):",
        parse_mode=ParseMode.HTML,
        reply_markup=get_commission_keyboard()
    )
    return SEARCH_MIN_COMMISSION


async def search_min_commission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle min commission filter"""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "skip_commission":
        context.user_data[USER_DATA_SEARCH]["min_commission"] = None
    elif data == "min_comm_custom":
        await query.edit_message_text(
            "💵 Masukkan komisi minimal (persen):\nContoh: 3",
            parse_mode=ParseMode.HTML
        )
        return SEARCH_MIN_COMMISSION
    else:
        comm_map = {
            "min_comm_1": 1.0,
            "min_comm_3": 3.0,
            "min_comm_5": 5.0,
            "min_comm_10": 10.0,
        }
        context.user_data[USER_DATA_SEARCH]["min_commission"] = comm_map.get(data)

    # Execute search
    search_data = context.user_data[USER_DATA_SEARCH]
    await query.edit_message_text("🔍 Mencari produk...")

    try:
        platform = search_data["platform"]
        keyword = search_data["query"]
        max_price = search_data.get("max_price")
        min_commission = search_data.get("min_commission")

        if platform == "both":
            results = PlatformFactory.search_all(
                keyword,
                max_price=max_price,
                min_commission=min_commission
            )
        else:
            results = {platform: PlatformFactory.search_all(keyword, max_price=max_price, min_commission=min_commission).get(platform, [])}

        # Log search
        total_results = sum(len(r) for r in results.values())
        db.log_search(
            update.effective_user.id,
            search_data["query"],
            platform,
            total_results,
            max_price,
            min_commission
        )

        # Format results
        response_parts = []
        for plat, products in results.items():
            if products:
                response_parts.append(format_search_results(products, plat))
            else:
                platform_name = "Shopee" if plat == "shopee" else "TikTok Shop"
                response_parts.append(f"😔 Tidak ditemukan produk di {platform_name}.")

        response_text = "\n\n".join(response_parts)

        # Add keyboard for first product if any
        first_product = None
        first_platform = None
        for plat, products in results.items():
            if products:
                first_product = products[0]
                first_platform = plat
                break

        reply_markup = None
        if first_product:
            reply_markup = get_results_keyboard(first_platform, 0, first_product["item_id"])

        await query.edit_message_text(
            response_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Search error: {e}")
        await query.edit_message_text(
            f"❌ Error saat mencari: {str(e)}",
            reply_markup=get_main_keyboard()
        )

    return ConversationHandler.END


# ===================== ALERT FLOW =====================

async def alerts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show alerts menu"""
    query = update.callback_query
    await query.answer()

    user_alerts = db.get_user_alerts(query.from_user.id)

    if not user_alerts:
        await query.edit_message_text(
            "🔔 <b>Alert Harga</b>\n\nBelum ada alert yang dibuat.\n\n"
            "Cari produk dulu, lalu tekan 🔔 Buat Alert Harga pada hasil pencarian.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Menu Utama", callback_data="main_menu")]])
        )
        return

    text = "🔔 <b>Alert Harga Anda</b>\n\n"
    keyboard = []

    for alert in user_alerts[:10]:
        status = "🟢 Aktif" if alert["is_active"] else "🔴 Triggered"
        platform_emoji = "🛍️" if alert["platform"] == "shopee" else "🎵"
        text += (
            f"{platform_emoji} <b>{alert['product_name'][:40]}</b>\n"
            f"   Target: Rp{alert['target_price']:,.0f} | "
            f"Sekarang: Rp{alert['current_price']:,.0f if alert['current_price'] else 'N/A'}\n"
            f"   {status}\n\n"
        )
        keyboard.append([
            InlineKeyboardButton(f"{'🗑️' if alert['is_active'] else '🔄'} {alert['product_name'][:20]}",
                                 callback_data=f"alert_detail_{alert['id']}")
        ])

    keyboard.append([InlineKeyboardButton("« Menu Utama", callback_data="main_menu")])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def alert_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show alert detail"""
    query = update.callback_query
    await query.answer()

    alert_id = int(query.data.replace("alert_detail_", ""))
    # Get alert details (would need to add get_alert_by_id to db)
    # For now, just show basic info
    await query.edit_message_text(
        f"🔔 Detail Alert ID: {alert_id}\n\nFitur detail akan segera hadir.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Kembali", callback_data="alerts")]])
    )


async def create_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create price alert for a product"""
    query = update.callback_query
    await query.answer()

    product_id = query.data.replace("alert_", "")
    context.user_data[USER_DATA_ALERT] = {"product_id": product_id}

    # Would need to get product details from cache or API
    await query.edit_message_text(
        f"🔔 <b>Buat Alert Harga</b>\n\n"
        f"Produk: (detail produk)\n\n"
        f"Masukkan target harga (Rupiah):\nContoh: 15000",
        parse_mode=ParseMode.HTML
    )
    return ALERT_TARGET_PRICE


async def alert_target_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle target price input"""
    try:
        target_price = float(update.message.text.replace(".", "").replace(",", ""))
        alert_data = context.user_data[USER_DATA_ALERT]
        product_id = alert_data["product_id"]

        # Would need to get product details from cache
        # For now, create alert with minimal info
        alert_id = db.create_price_alert(
            user_id=update.effective_user.id,
            product_id=product_id,
            platform="shopee",  # Would need to determine from product
            product_name="Produk",
            product_url="",
            target_price=target_price
        )

        await update.message.reply_text(
            f"✅ Alert berhasil dibuat!\n\n"
            f"Target harga: Rp{target_price:,.0f}\n"
            f"Kami akan notifikasi Anda jika harga turun ke target ini.",
            reply_markup=get_main_keyboard()
        )
    except ValueError:
        await update.message.reply_text("❌ Format harga tidak valid. Masukkan angka saja (contoh: 15000)")

    return ConversationHandler.END


# ===================== HISTORY =====================

async def history_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show search history"""
    query = update.callback_query
    await query.answer()

    history = db.get_search_history(query.from_user.id, 10)

    if not history:
        await query.edit_message_text(
            "📊 <b>Riwayat Pencarian</b>\n\nBelum ada riwayat pencarian.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Menu Utama", callback_data="main_menu")]])
        )
        return

    text = "📊 <b>Riwayat Pencarian Terbaru</b>\n\n"
    for i, h in enumerate(history, 1):
        platform_emoji = "🛍️" if h["platform"] == "shopee" else "🎵" if h["platform"] == "tiktok" else "🔍"
        text += (
            f"{i}. {platform_emoji} <b>{h['query']}</b>\n"
            f"   Platform: {h['platform']} | Hasil: {h['results_count']}\n"
            f"   Waktu: {h['created_at']}\n\n"
        )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Menu Utama", callback_data="main_menu")]])
    )


# ===================== SETTINGS =====================

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show settings menu"""
    query = update.callback_query
    await query.answer()

    user_settings = db.get_user_settings(query.from_user.id)

    text = (
        "⚙️ <b>Pengaturan</b>\n\n"
        f"🔢 Max hasil per cari: <b>{user_settings.get('max_results', 10)}</b>\n"
        f"💵 Min komisi: <b>{user_settings.get('min_commission_rate', 1.0)}%</b>\n"
        f"🌐 Platform default: <b>{user_settings.get('preferred_platforms', 'shopee,tiktok')}</b>\n"
        f"🔔 Alert harga: <b>{'Aktif' if user_settings.get('price_alert_enabled') else 'Nonaktif'}</b>\n"
        f"🌐 Bahasa: <b>{user_settings.get('language', 'id')}</b>"
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_settings_keyboard()
    )


async def settings_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle settings value input"""
    query = update.callback_query
    await query.answer()

    key = query.data.replace("set_", "")
    context.user_data["settings_key"] = key

    prompts = {
        "max_results": "Masukkan jumlah maksimal hasil per pencarian (1-50):",
        "min_commission": "Masukkan komisi minimal (persen, contoh: 3):",
        "platforms": "Pilih platform default (pisah dengan koma): shopee,tiktok",
        "price_alert": "Aktifkan alert harga? (1=ya, 0=tidak)",
        "language": "Kode bahasa (id/en):"
    }

    await query.edit_message_text(
        prompts.get(key, "Masukkan nilai baru:"),
        parse_mode=ParseMode.HTML
    )
    return SETTINGS_VALUE


async def settings_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save settings value"""
    key = context.user_data.get("settings_key")
    value = update.message.text.strip()

    try:
        if key == "max_results":
            value = int(value)
            if not 1 <= value <= 50:
                raise ValueError("Harus 1-50")
        elif key == "min_commission":
            value = float(value)
        elif key == "price_alert":
            value = "1" if value in ["1", "ya", "yes", "true"] else "0"
        elif key == "language":
            if value not in ["id", "en"]:
                raise ValueError("Bahasa harus 'id' atau 'en'")

        db.update_user_settings(update.effective_user.id, **{key: value})

        await update.message.reply_text(
            f"✅ Pengaturan <b>{key}</b> diubah ke <b>{value}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_keyboard()
        )
    except ValueError as e:
        await update.message.reply_text(f"❌ Nilai tidak valid: {e}")

    return ConversationHandler.END


# ===================== STATS =====================

async def stats_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot stats"""
    query = update.callback_query
    await query.answer()

    user_stats = db.get_user_settings(query.from_user.id)  # placeholder
    stats = db.get_stats()

    text = (
        "📈 <b>Statistik Bot</b>\n\n"
        f"📅 Hari ini:\n"
        f"   🔍 Pencarian: {stats.get('total_searches', 0)}\n"
        f"   👥 Pengguna: {stats.get('total_users', 0)}\n"
        f"   🔔 Alert dibuat: {stats.get('total_alerts_created', 0)}\n"
        f"   🔔 Alert trigger: {stats.get('total_alerts_triggered', 0)}\n"
        f"   🔗 Link afiliasi: {stats.get('total_affiliate_links', 0)}\n"
        f"   🛍️ Cari Shopee: {stats.get('shopee_searches', 0)}\n"
        f"   🎵 Cari TikTok: {stats.get('tiktok_searches', 0)}\n"
        f"   ❌ Error: {stats.get('errors', 0)}"
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Menu Utama", callback_data="main_menu")]])
    )


# ===================== AFFILIATE LINK =====================

async def generate_affiliate_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate affiliate link for a product"""
    query = update.callback_query
    await query.answer()

    # Parse callback data: affiliate_<product_id>
    product_id = query.data.replace("affiliate_", "")

    # Would need to get product from cache
    await query.edit_message_text(
        "🔗 <b>Generate Link Afiliasi</b>\n\n"
        "Fitur generate link afiliasi akan segera hadir.\n"
        "Saat ini silakan copy link produk dan buat manual via dashboard afiliasi.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Kembali", callback_data="main_menu")]])
    )


# ===================== RATE LIMIT & ACCESS WRAPPERS =====================

async def require_access_and_rate_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check access and rate limit, send error message if denied"""
    # Check access
    allowed, msg = await check_access(update, config)
    if not allowed:
        if update.callback_query:
            await update.callback_query.answer(msg, show_alert=True)
        elif update.message:
            await update.message.reply_text(msg)
        return False

    # Check rate limit
    allowed, msg = await check_rate_limit(update, config)
    if not allowed:
        if update.callback_query:
            await update.callback_query.answer(msg, show_alert=True)
        elif update.message:
            await update.message.reply_text(msg)
        return False

    return True


async def protected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, handler):
    """Wrapper that checks access and rate limit before calling handler"""
    if not await require_access_and_rate_limit(update, context):
        return
    return await handler(update, context)


async def protected_message(update: Update, context: ContextTypes.DEFAULT_TYPE, handler):
    """Wrapper for message handlers with access/rate limit"""
    if not await require_access_and_rate_limit(update, context):
        return
    return await handler(update, context)


# ===================== CALLBACK ROUTER =====================

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route callback queries"""
    if not await require_access_and_rate_limit(update, context):
        return
    query = update.callback_query
    data = query.data

    # Main menu
    if data == "main_menu":
        await start(update, context)
    elif data == "help":
        await help_command(update, context)
    elif data == "search":
        return await search_start(update, context)
    elif data == "alerts":
        await alerts_menu(update, context)
    elif data == "history":
        await history_menu(update, context)
    elif data == "settings":
        await settings_menu(update, context)
    elif data == "stats":
        await stats_menu(update, context)
    elif data.startswith("platform_"):
        return await search_platform(update, context)
    elif data.startswith("max_price"):
        return await search_max_price(update, context)
    elif data.startswith("min_comm"):
        return await search_min_commission(update, context)
    elif data == "skip_price":
        return await search_max_price(update, context)
    elif data == "skip_commission":
        return await search_min_commission(update, context)
    elif data.startswith("set_"):
        return await settings_value(update, context)
    elif data.startswith("affiliate_"):
        await generate_affiliate_link(update, context)
    elif data.startswith("alert_"):
        return await create_alert(update, context)
    elif data.startswith("alert_detail_"):
        await alert_detail(update, context)
    elif data == "help":
        await help_command(update, context)
    elif data == "channels":
        await channels_menu(update, context)
    elif data == "channel_add":
        return await channel_add_start(update, context)
    elif data.startswith("ch:"):
        return await channel_detail(update, context)
    elif data.startswith("ch_toggle:"):
        await channel_toggle(update, context)
    elif data.startswith("ch_test:"):
        await channel_test(update, context)
    elif data.startswith("ch_del:"):
        await channel_delete(update, context)
    elif data.startswith("ch_stats:"):
        await channel_stats(update, context)
    elif data == "help":
        await help_command(update, context)
    else:
        await query.answer("Fitur belum tersedia", show_alert=True)


# ===================== CHANNEL MANAGEMENT =====================

async def channels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show channels menu"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    channels = db.list_channels(user_id)

    if not channels:
        text = (
            "📡 <b>Channel Management</b>\n\n"
            "Belum ada channel yang ditambahkan.\n\n"
            "Tambah channel untuk auto-post deal atau manual post."
        )
        keyboard = [
            [InlineKeyboardButton("➕ Tambah Channel", callback_data="channel_add")],
            [InlineKeyboardButton("« Menu Utama", callback_data="main_menu")]
        ]
    else:
        text = "📡 <b>Channel Management</b>\n\n"
        keyboard = []
        for ch in channels:
            status = "✅" if ch["enabled"] else "🚫"
            auto = "🤖" if ch["auto_post"] else ""
            platform_emoji = "📱" if ch["platform"] == "telegram" else "🌐"
            keyboard.append([
                InlineKeyboardButton(
                    f"{platform_emoji} {ch['title'] or ch['chat_id']} {status}{auto}",
                    callback_data=f"ch:{ch['id']}"
                )
            ])
        keyboard.append([
            InlineKeyboardButton("➕ Tambah Channel", callback_data="channel_add"),
            InlineKeyboardButton("« Menu Utama", callback_data="main_menu")
        ])

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def channel_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding a new channel"""
    query = update.callback_query
    await query.answer()

    context.user_data["channel_data"] = {"platform": "telegram"}
    await query.edit_message_text(
        "➕ <b>Tambah Channel</b>\n\n"
        "Masukkan <b>chat_id</b> channel/grup:\n"
        "• Format publik: <code>@username</code>\n"
        "• Format privat: <code>-1001234567890</code>\n\n"
        "Contoh: <code>@my_channel</code> atau <code>-1001234567890</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Kembali", callback_data="channels")]])
    )
    return "CHANNEL_CHAT_ID"


async def channel_add_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle chat_id input"""
    chat_id = update.message.text.strip()
    context.user_data["channel_data"]["chat_id"] = chat_id

    await update.message.reply_text(
        f"✅ Chat ID: <code>{chat_id}</code>\n\n"
        "Masukkan nama channel (ketik '-' untuk skip):",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Kembali", callback_data="channel_add")]])
    )
    return "CHANNEL_NAME"


async def channel_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle channel name input"""
    name = update.message.text.strip() if update.message else None
    if name and name != "-":
        context.user_data["channel_data"]["title"] = name
    else:
        context.user_data["channel_data"]["title"] = context.user_data["channel_data"]["chat_id"]

    chat_id = context.user_data["channel_data"]["chat_id"]

    await update.message.reply_text(
        f"✅ Channel: <b>{context.user_data['channel_data']['title']}</b>\n"
        f"Chat ID: <code>{chat_id}</code>\n\n"
        "Aktifkan auto-post?",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 Auto-post ON", callback_data="ch_autopost:1"),
             InlineKeyboardButton("📝 Manual only", callback_data="ch_autopost:0")],
            [InlineKeyboardButton("« Kembali", callback_data="channel_add")]
        ])
    )
    return "CHANNEL_OPTIONS"


async def channel_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle channel options (auto-post toggle + save)"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("ch_autopost:"):
        val = int(data.split(":", 1)[1])
        context.user_data["channel_data"]["auto_post"] = val
        await query.answer(f"Auto-post: {'ON' if val else 'OFF'}")

    elif data == "ch_save":
        cd = context.user_data.get("channel_data", {})
        cid = db.add_channel(
            user_id=query.from_user.id,
            chat_id=cd.get("chat_id"),
            platform=cd.get("platform", "telegram"),
            title=cd.get("title"),
            auto_post=cd.get("auto_post", 0),
        )
        await query.edit_message_text(
            f"✅ Channel <b>{cd.get('title', 'saved')}</b> disimpan!\n\n"
            f"ID: <code>{cid}</code>\n"
            f"Auto-post: {'ON' if cd.get('auto_post') else 'OFF'}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Kembali", callback_data="channels")]])
        )
        return ConversationHandler.END


async def channel_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show channel detail and actions"""
    query = update.callback_query
    await query.answer()

    channel_id = int(query.data.replace("ch:", ""))
    channel = db.get_channel(channel_id)

    if not channel:
        await query.edit_message_text(
            "❌ Channel tidak ditemukan",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Kembali", callback_data="channels")]])
        )
        return

    status = "✅ Aktif" if channel["enabled"] else "🚫 Nonaktif"
    auto = "🤖 Auto-post ON" if channel["auto_post"] else "📝 Manual only"
    platform_emoji = "📱" if channel["platform"] == "telegram" else "🌐"

    text = (
        f"{platform_emoji} <b>{channel['title'] or channel['chat_id']}</b>\n\n"
        f"Chat ID: <code>{channel['chat_id']}</code>\n"
        f"Platform: <b>{channel['platform']}</b>\n"
        f"Status: {status}\n"
        f"Auto-post: {auto}\n"
        f"Posts: <b>{channel['posts_count']}</b>"
    )

    keyboard = [
        [InlineKeyboardButton(
            f"{'🚫 Nonaktifkan' if channel['enabled'] else '✅ Aktifkan'}",
            callback_data=f"ch_toggle:{channel['id']}:enabled"
        ),
        InlineKeyboardButton(
            f"{'🤖 Matikan auto' if channel['auto_post'] else '🤖 Aktifkan auto'}",
            callback_data=f"ch_toggle:{channel['id']}:auto_post"
        )],
        [InlineKeyboardButton("🧪 Test Post", callback_data=f"ch_test:{channel['id']}")],
        [InlineKeyboardButton("🗑️ Hapus", callback_data=f"ch_del:{channel['id']}"),
         InlineKeyboardButton("« Kembali", callback_data="channels")]
    ]

    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def channel_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle enabled/auto_post"""
    query = update.callback_query
    await query.answer()
    _, cid_str, field = query.data.split(":", 2)
    channel_id = int(cid_str)

    new_val = db.toggle_channel(channel_id, field)
    await query.answer(f"{field}: {'ON' if new_val else 'OFF'}")
    await channel_detail(update, context)


async def channel_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send test message to channel"""
    query = update.callback_query
    await query.answer()

    channel_id = int(query.data.replace("ch_test:", ""))
    channel = db.get_channel(channel_id)

    if not channel:
        await query.edit_message_text("❌ Channel tidak ditemukan")
        return

    await query.edit_message_text("📤 Mengirim test message...")

    from src.publisher import publish_to_channel
    test_product = {
        "name": "🧪 Test Message dari Affiliate Finder",
        "price": 0,
        "commission_rate": 0,
        "platform": "telegram",
    }
    result = await publish_to_channel(
        channel["id"], test_product, "https://example.com",
        query.from_user.id, template="short",
        bot=context.bot
    )

    if result.get("ok"):
        await query.edit_message_text(
            f"✅ Test berhasil!\nMessage ID: <code>{result.get('message_id')}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Kembali", callback_data=f"ch:{channel_id}")]])
        )
    else:
        await query.edit_message_text(
            f"❌ Test gagal: {result.get('error')}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Kembali", callback_data=f"ch:{channel_id}")]])
        )


async def channel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete channel"""
    query = update.callback_query
    await query.answer()

    channel_id = int(query.data.replace("ch_del:", ""))
    if db.delete_channel(channel_id):
        await query.edit_message_text(
            "🗑️ Channel dihapus",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Kembali", callback_data="channels")]])
        )
    else:
        await query.edit_message_text(
            "❌ Gagal hapus",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Kembali", callback_data="channels")]])
        )


async def channel_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show channel stats"""
    query = update.callback_query
    await query.answer()

    channel_id = int(query.data.replace("ch_stats:", ""))
    stats = db.post_stats(query.from_user.id)
    channel = db.get_channel(channel_id)

    if not channel:
        await query.edit_message_text("❌ Channel tidak ditemukan")
        return

    text = (
        f"📊 <b>Stats Channel: {channel['title'] or channel['chat_id']}</b>\n\n"
        f"Total post: <b>{stats.get('total', 0)}</b>\n"
        f"✅ Terkirim: <b>{stats.get('sent', 0)}</b>\n"
        f"❌ Gagal: <b>{stats.get('failed', 0)}</b>\n"
        f"⏳ Pending: <b>{stats.get('pending', 0)}</b>"
    )

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Kembali", callback_data=f"ch:{channel_id}")]])
    )


# ===================== ERROR HANDLER =====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"Update {update} caused error: {context.error}")

    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Terjadi kesalahan. Silakan coba lagi atau hubungi admin.",
                reply_markup=get_main_keyboard()
            )
        except Exception:
            pass


# ===================== MAIN =====================

def create_application() -> Application:
    """Create and configure the bot application"""
    if not config.telegram.bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN not configured")

    application = Application.builder().token(config.telegram.bot_token).build()

    # Conversation handlers
    search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_start, pattern="^search$")],
        states={
            SEARCH_PLATFORM: [CallbackQueryHandler(search_platform, pattern="^platform_")],
            SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_query)],
            SEARCH_MAX_PRICE: [
                CallbackQueryHandler(search_max_price, pattern="^(max_price_|skip_price)"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_max_price)
            ],
            SEARCH_MIN_COMMISSION: [
                CallbackQueryHandler(search_min_commission, pattern="^(min_comm_|skip_commission)"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_min_commission)
            ],
        },
        fallbacks=[CallbackQueryHandler(start, pattern="^main_menu$")],
        per_message=False,
        per_chat=True,
    )

    alert_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_alert, pattern="^alert_")],
        states={
            ALERT_TARGET_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, alert_target_price)],
        },
        fallbacks=[CallbackQueryHandler(start, pattern="^main_menu$")],
        per_message=False,
        per_chat=True,
    )

    settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(settings_value, pattern="^set_")],
        states={
            SETTINGS_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, settings_save)],
        },
        fallbacks=[CallbackQueryHandler(start, pattern="^main_menu$")],
        per_message=False,
        per_chat=True,
    )

    channel_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(channel_add_start, pattern="^channel_add$"),
            CallbackQueryHandler(channel_add_name, pattern="^ch_platform:"),
            CallbackQueryHandler(channel_add_name, pattern="^ch_autopost:"),
            CallbackQueryHandler(channel_option, pattern="^ch_autopost:"),
            CallbackQueryHandler(channel_option, pattern="^ch_platform:"),
            CallbackQueryHandler(channel_option, pattern="^ch_save$"),
        ],
        states={
            "CHANNEL_CHAT_ID": [MessageHandler(filters.TEXT & ~filters.COMMAND, channel_add_chat_id)],
            "CHANNEL_NAME": [MessageHandler(filters.TEXT & ~filters.COMMAND, channel_add_name)],
            "CHANNEL_OPTIONS": [
                CallbackQueryHandler(channel_option, pattern="^ch_platform:"),
                CallbackQueryHandler(channel_option, pattern="^ch_autopost:"),
                CallbackQueryHandler(channel_option, pattern="^ch_save$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(start, pattern="^main_menu$")],
        per_message=False,
        per_chat=True,
    )

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(search_conv)
    application.add_handler(alert_conv)
    application.add_handler(settings_conv)
    application.add_handler(channel_conv)
    application.add_handler(CallbackQueryHandler(callback_router))
    application.add_error_handler(error_handler)

    return application


async def run_bot():
    """Run the bot"""
    application = create_application()

    # Initialize database
    db.init_db()

    # Start price alert scheduler in background
    from src.scheduler.price_alerts import start_price_alert_scheduler
    await start_price_alert_scheduler(bot=application.bot)

    logger.info("Starting Affiliate Finder Bot...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    logger.info("Bot started successfully!")

    # Keep running
    try:
        await asyncio.Event().wait()
    finally:
        from src.scheduler.price_alerts import stop_price_alert_scheduler
        await stop_price_alert_scheduler()
        await application.updater.stop_polling()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(run_bot())