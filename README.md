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

## Keep-alive workflow

`.github/workflows/keep_alive.yml` pings `https://webtel-lead-generator.streamlit.app` daily at 00:00 UTC. If your URL differs, edit it in that file. You can also run it manually from the **Actions** tab.

## Notes

- Results come from DuckDuckGo's public HTML page and the businesses' own websites; quality varies and DuckDuckGo may rate-limit heavy use — wait a minute and retry.
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
# in another terminal
cd frontend && python -m http.server 5500
```

Open http://localhost:5500. Under **Search → Backend server**, enter `http://localhost:8000`.

## Deploy the backend on Render (free)

1. Push this repo to GitHub.
2. On https://render.com choose **New → Blueprint** and select the repo. `render.yaml` sets everything up (root `backend`, Python 3.11, `uvicorn main:app`).
   Or choose **New → Web Service** with root directory `backend`, build command `pip install -r requirements.txt` and start command `uvicorn main:app --host 0.0.0.0 --port $PORT`.
3. Copy the URL, e.g. `https://lead-generator-api.onrender.com`.
4. Optional: set `ALLOWED_ORIGINS` to your frontend URL to lock down CORS.

Free Render services sleep after 15 minutes idle, so the first search can take about 50 seconds.

## Deploy the frontend

- **GitHub Pages:** go to repo **Settings → Pages**, choose to deploy from a branch, and pick branch `main` with folder `/ (root)`. Open `https://<user>.github.io/<repo>/frontend/`.
- **Vercel:** choose **Add New → Project**, import the repo and set the root directory to `frontend` (no build step).

Then set the backend URL in the app (**Search → Backend server**). You can also change `DEFAULT_API` in `frontend/index.html` so the URL is always pre-filled.

## Install on your phone

- **Android (Chrome):** menu ⋮ → **Add to Home screen / Install app**.
- **iPhone (Safari):** Share → **Add to Home Screen**.

Leads live only on that phone and browser. Export CSV regularly as a backup.
