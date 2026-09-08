# Affiliate Finder Bot

Telegram bot untuk mencari produk dengan komisi afiliasi di **Shopee** dan **TikTok Shop**.

## Fitur

| Fitur | Deskripsi |
|-------|-----------|
| 🔍 **Multi-platform Search** | Cari produk di Shopee & TikTok Shop sekaligus |
| 💰 **Price & Commission Filter** | Filter harga maksimal & komisi minimal |
| 🔗 **Affiliate Link Generator** | Generate link tracking otomatis |
| 🔔 **Price Drop Alerts** | Notifikasi kalau harga turun ke target |
| 📊 **Search History** | Riwayat pencarian per user |
| ⚙️ **Customizable Settings** | Max results, min commission, platform default |
| 📈 **Statistics** | Statistik penggunaan bot |

## Arsitektur

```
affiliate-finder/
├── main.py                 # Entry point
├── requirements.txt        # Dependencies
├── config/
│   ├── .env.example        # Template konfigurasi
│   └── (auto-load .env)
├── src/
│   ├── config.py           # Config loader dengan dataclass
│   ├── db/
│   │   └── database.py     # SQLite operations (thread-safe)
│   ├── platforms/
│   │   ├── shopee.py       # Shopee Affiliate API client
│   │   ├── tiktok.py       # TikTok Shop Affiliate API client
│   │   └── __init__.py     # Factory & formatters
│   └── bot/
│       └── bot.py          # Telegram bot (ConversationHandler)
```

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Setup Configuration
```bash
cp config/.env.example config/.env
nano config/.env
```

Isi `.env` dengan credentials:
```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_ADMIN_IDS=123456789,987654321

# Shopee Affiliate (dari openplatform.shopee.com)
SHOPEE_APP_ID=123456
SHOPEE_SECRET_KEY=abcdef...
SHOPEE_ACCESS_TOKEN=...

# TikTok Shop Affiliate (dari affiliate.tiktokglobalshop.com)
TIKTOK_APP_KEY=abc123
TIKTOK_APP_SECRET=secret...
TIKTOK_ACCESS_TOKEN=...
```

### 3. Run Bot
```bash
python main.py
```

## Mendapatkan API Credentials

### Shopee Affiliate
1. Daftar di [Shopee Affiliate Open Platform](https://openplatform.shopee.com/)
2. Buat aplikasi → dapatkan `APP_ID` & `SECRET_KEY`
3. Generate `ACCESS_TOKEN` via OAuth

### TikTok Shop Affiliate
1. Daftar di [TikTok Shop Affiliate Center](https://affiliate.tiktokglobalshop.com/)
2. Buat aplikasi → dapatkan `APP_KEY` & `APP_SECRET`
3. Generate `ACCESS_TOKEN` via OAuth

## Penggunaan Bot

1. **Start** - `/start` untuk menu utama
2. **Cari Produk** - Pilih platform → ketik keyword → filter harga/komisi
3. **Generate Link** - Tekan tombol pada hasil pencarian
4. **Alert Harga** - Set target harga → dapat notif kalau turun
5. **Riwayat** - Lihat pencarian sebelumnya
6. **Settings** - Atur max results, min komisi, platform default

## Contoh Penggunaan

```
User: /start
Bot: Menu utama → 🔍 Cari Produk

User: Pilih "Shopee"
Bot: Ketik kata kunci...

User: "gula gmp 1kg"
Bot: Filter harga maksimal? → ≤ 15.000
Bot: Filter komisi minimal? → ≥ 3%

Bot: Menampilkan hasil:
1. 🛍️ Gula GMP 1kg Gunung Madu - Rp14.500 - Komisi 5.2%
2. 🛍️ Gula GMP Premium 1kg - Rp13.900 - Komisi 4.8%

User: Tekan "🔗 Dapatkan Link Afiliasi"
Bot: Link afiliasi generated: https://shopee.co.id/...?aff=...
```

## Database Schema

- `users` - User info & admin status
- `user_settings` - Per-user preferences
- `search_history` - Riwayat pencarian
- `price_alerts` - Alert harga turun
- `product_cache` - Cache produk (TTL 5 menit)
- `affiliate_links` - Link afiliasi yang di-generate
- `bot_stats` - Statistik harian

## Deployment

### Local
```bash
python main.py
```

### PM2 (Production)
```bash
pm2 start main.py --name affiliate-finder --interpreter python3
pm2 save && pm2 startup
```

### Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

```bash
docker build -t affiliate-finder .
docker run -d --env-file config/.env affiliate-finder
```

## Keamanan

- ✅ Admin-only access via `TELEGRAM_ADMIN_IDS`
- ✅ Credentials di `.env` (chmod 600)
- ✅ SQLite dengan WAL mode untuk concurrency
- ✅ Rate limiting & retry logic di API clients
- ✅ Input validation di semua handler

## Roadmap

- [ ] Tokopedia Affiliate support
- [ ] Web dashboard (FastAPI + Streamlit)
- [ ] Auto-post ke channel/grup
- [ ] Advanced analytics (ROI tracking)
- [ ] Multi-language support
- [ ] Affiliate link cloaking

## License

MIT License - Gunakan dengan risiko sendiri. Bukan financial advice.