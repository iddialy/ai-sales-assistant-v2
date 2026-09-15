# 24/7 Sales Assistant — ClickPesa Payment Build

This package adds a real ClickPesa Hosted Checkout button for the two subscription plans:

- TSh 2,000 — Daily
- TSh 50,000 — Monthly

## Render Environment Variables
Set these in Render → Environment Variables (never put secrets in GitHub):

- `CLICKPESA_API_TOKEN` — ClickPesa API access token. Because Checksum Security was enabled, regenerate the API token after changing checksum settings and use the new token.
- `CLICKPESA_CHECKSUM_KEY` — the checksum security key already created in ClickPesa.

The frontend button calls the backend. The secret token and checksum key are never exposed to the browser.

## ClickPesa webhook
The application webhook remains:
`POST /webhook/clickpesa/payment-received`

ClickPesa `PAYMENT RECEIVED` is validated using the checksum key. A successful TZS payment for exactly 2,000 or 50,000 activates the matching subscription.

## Important
The payment buttons are intentionally not enabled by a fake/static payment URL. If `CLICKPESA_API_TOKEN` is missing, the dashboard shows a clear configuration error instead of pretending that a payment was started.

Whitelisted IP is not hard-coded in this package because Render Free uses outbound IP ranges rather than a single stable dedicated IP.
