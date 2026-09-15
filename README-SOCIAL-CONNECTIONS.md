# Social Media Connections

Dashboard sasa ina sehemu ya kuunganisha akaunti za:
- WhatsApp Business (kupitia Meta)
- Facebook Page (kupitia Meta)
- Instagram Business (kupitia Meta)
- TikTok account (TikTok Login Kit)

## Render Environment Variables

Meta:
- `META_APP_ID`
- `META_APP_SECRET`
- `META_REDIRECT_URI=https://ai-sales-assistant-api-07y0.onrender.com/social/callback/meta`

TikTok:
- `TIKTOK_CLIENT_KEY`
- `TIKTOK_CLIENT_SECRET`
- `TIKTOK_REDIRECT_URI=https://ai-sales-assistant-api-07y0.onrender.com/social/callback/tiktok`

Optional encryption key:
- `SOCIAL_TOKEN_ENCRYPTION_KEY`

If the optional encryption key is omitted, the system derives an encryption key from `TOKEN_SECRET`.

## Important

The dashboard connection layer is now ready, including OAuth start/callback, encrypted token storage, connection status and disconnect support.

Meta accounts require the appropriate Meta business assets and approved permissions before real messaging can be used. TikTok account connection uses TikTok Login Kit; messaging capabilities require whatever TikTok products/scopes are available and approved for the app.
