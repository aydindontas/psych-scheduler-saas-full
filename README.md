# Psych Scheduler SaaS — Clean Deploy Pack

Hazır, hatasız ve Render/Railway uyumlu SaaS randevu planlayıcı:
- FastAPI backend
- Multi-tenant (tenant_key ile per-tenant WhatsApp webhook)
- WhatsApp Cloud API entegrasyonu için stub fonksiyon
- Zoom linki destekli onay + hatırlatma mesajları
- APScheduler ile 24s ve 1s önce hatırlatma
- Basit statik admin UI
- Python 3.11.9 (runtime.txt)

## Kurulum (lokal)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## Render (önerilen)
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Ortam değişkenleri: `.env.example` içindekileri Render Environment'a ekleyin.
- (Opsiyon) Postgres ekleyip `DATABASE_URL`'ü değiştirin (örn. `postgresql+psycopg://...`).

## WhatsApp Webhook
Panelde gözüken URL: `/whatsapp/webhook/<tenant_key>`
- Meta WhatsApp Cloud'da Webhook URL olarak girin.
- Verify Token: `WHATSAPP_VERIFY_TOKEN`

## Zoom
- `.env`'de `ZOOM_JOIN_URL` girin; onay ve hatırlatma mesajlarına eklenir.
- İleride tenant bazlı dinamik Zoom eklenebilir.
