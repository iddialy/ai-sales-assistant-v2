# AI Sales Assistant Tanzania v5

Version hii inarekebisha mambo matatu ya msingi:

1. **Login/Signup persistence** — production inapaswa kutumia PostgreSQL kupitia `DATABASE_URL`, si SQLite ya local filesystem.
2. **Payment phone form** — website ina form ya namba ya mobile money badala ya browser `prompt()`.
3. **MalipoPay v2 direct collection** — server inatuma collection request kwa `/api/v2/payment/collection`. MNO hugunduliwa kutoka namba ya simu; PIN haikusanywi na website.

## Environment variables za Render

Weka hizi kwenye Render:

- `DATABASE_URL` = connection string ya PostgreSQL ya Render
- `JWT_SECRET` = secret ndefu ya kipekee
- `GEMINI_API_KEY` = Gemini API key
- `GEMINI_MODEL` = mfano `gemini-1.5-flash`
- `CORS_ORIGINS` = `https://iddialy.github.io`
- `MALIPO_BASE_URL` = `https://core-prod.malipopay.co.tz`
- `MALIPOPAY_API_TOKEN` = **Secret/API key ya MalipoPay kutoka Settings → API Keys** (`mp_sk_prod_...`), si webhook signing secret
- `MALIPOPAY_WEBHOOK_SECRET` = **View Signing Secret** ya webhook uliyounda
- `WEBHOOK_SECRET` = optional, kwa endpoint ya `/webhook/message`

MalipoPay docs zinasema API key inawekwa kwenye header `apiToken`, na collection ya v2 hutumia `service: mobile` + `account` ya simu. MNO hugunduliwa kutoka namba. Webhook signature ni HMAC-SHA256 ya raw body na signing secret ya webhook.

## Render

Backend start command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Baada ya PostgreSQL kuunganishwa, app itatengeneza tables zenyewe wakati wa startup.

## Muhimu kuhusu MalipoPay sandbox

Akaunti ambayo haija-approve go-live huwa na restriction ya **Test Recipients**. Namba unayotaka ku-charge inapaswa kuwa imeongezwa kwenye MalipoPay Settings → Test Recipients kabla ya test collection.
