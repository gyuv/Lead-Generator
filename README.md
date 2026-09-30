# 📞 Webtel Sales Lead Generator & Telecalling Tracker

A 100% free Streamlit app that finds publicly listed businesses (name, phone, email, website, city) for any industry + city, and gives you a telecalling dashboard with click-to-call, WhatsApp chat links, status tracking, analytics and CSV/Excel export. No paid APIs.

## 1. Run locally

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501, enter an industry (e.g. `CA Firms`) and a city (e.g. `Chennai`), then click **🚀 Find Leads**.

## 2. Push to a public GitHub repository

```bash
git init
git add .
git commit -m "Initial commit: lead generator"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

## 3. Host free on Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **Create app** → **Deploy a public app from GitHub**.
3. Select your repository, branch `main`, and main file path `app.py`.
4. (Optional) Set the custom subdomain to `webtel-lead-generator`.
5. Click **Deploy**. Your app goes live at `https://<subdomain>.streamlit.app`.

## 24/7 hosting

Streamlit Community Cloud apps sleep after a period without visitors. For an always-on deployment, use the mobile PWA version on Render (below).

## Notes

- Results come from DuckDuckGo's public HTML page, falling back to Bing automatically when DuckDuckGo is blocked or runs out of results, plus the businesses' own websites. Quality varies; if both engines rate-limit you, wait a minute and retry.
- Leads live in the browser session only. Export to CSV/Excel before closing the tab.
- Respect DND/TRAI telemarketing rules and each site's terms when calling or messaging leads.

---

# 📱 Mobile PWA version (FastAPI + HTML5)

A phone-first app with a card list, one-tap Call and WhatsApp buttons, call status and notes saved on the phone (`localStorage`), analytics and CSV export. It can be installed to the home screen on Android and iOS.

```
backend/   FastAPI API  →  Render.com (free)
frontend/  PWA (HTML + Tailwind + Alpine.js)  →  GitHub Pages or Vercel (free)
```

## API

`GET /api/leads?industry=CA%20Firms&location=Chennai&limit=10`

```json
[{"id": "...", "name": "ABC & Co", "phone": "+91 98765 43210", "email": "a@abc.in",
  "website": "https://abc.in", "city": "Chennai",
  "tel_link": "tel:+919876543210", "wa_link": "https://wa.me/919876543210"}]
```

## Run locally

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open http://localhost:8000. The same server hosts the phone app and the API (`/api/leads`, health check `/healthz`).

## Deploy 24/7 on Render (free, no card)

1. On https://render.com sign in with GitHub and choose **New → Blueprint**.
2. Select this repo and branch. `render.yaml` creates one free web service named `lead-generator`. Click **Apply**.
3. After the build finishes, open `https://<your-service>.onrender.com`. That is your app.

### Keep it awake (important)

Free Render services sleep after 15 minutes without traffic. A free uptime monitor stops that:

1. Sign up at https://uptimerobot.com (or https://cron-job.org).
2. Add an **HTTP(s)** monitor for `https://<your-service>.onrender.com/healthz` with a **5-minute** interval.

Render's 750 free hours a month are shared by all free services in your account, which is enough for **one** service running 24/7. Don't run a second free service (for example the Streamlit app) on the same account, or the hours will run out before the month ends and both will be suspended.

### Optional: host the frontend separately

The Render service already serves the app. If you also want it on Vercel, Netlify or GitHub Pages, deploy the `frontend` folder and enter your Render URL in the app under **Search → Backend server**.

## Install on your phone

- **Android (Chrome):** open your Render URL, then menu ⋮ → **Add to Home screen / Install app**.
- **iPhone (Safari):** open your Render URL, then Share → **Add to Home Screen**.

Leads live only on that phone and browser. Export CSV regularly as a backup.
