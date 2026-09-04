# AI Sales Assistant Tanzania — Payment-ready v3

This version adds merchant accounts, product catalog, subscriptions, MalipoPay hosted checkout, signed MalipoPay webhooks, and AI access control.

## Plans
- Starter: TSh 35,000/month, 1,000 AI responses/messages counted by the app.
- Business: TSh 75,000/month, unlimited.

## MalipoPay
The backend uses MalipoPay hosted checkout (`POST /api/v1/payment/link`) with the `apiToken` header. The payment reference created by this app is stored in the database. MalipoPay calls `/webhook/malipopay` after payment events.

Required Render environment variables:
- `MALIPOPAY_API_TOKEN` — your MalipoPay API credential. Keep secret.
- `MALIPOPAY_WEBHOOK_SECRET` — the per-webhook signing secret from MalipoPay Settings > Webhooks. Keep secret.
- `MALIPO_BASE_URL=https://core-prod.malipopay.co.tz`
- `FRONTEND_URL=https://iddialy.github.io/ai-sales-assistant-v2/`
- `CORS_ORIGINS=https://iddialy.github.io`
- `JWT_SECRET` — long random secret.
- `GEMINI_API_KEY` and `GEMINI_MODEL`.
- `DATABASE_URL` for PostgreSQL in production.

## Webhook URL
After deployment, configure:
`https://YOUR-RENDER-SERVICE.onrender.com/webhook/malipopay`

The webhook verifies the `X-Malipopay-Signature` HMAC-SHA256 header over the raw request body before processing payment confirmation.

## Render
Build command:
`pip install -r requirements.txt`

Start command:
`uvicorn main:app --host 0.0.0.0 --port $PORT`
