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
