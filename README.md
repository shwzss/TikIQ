TikIQ - TikTok vidIQ (Python)
-----------------------------

1) Local dev:
   - create .env with TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET (optional)
   - pip install -r requirements.txt
   - uvicorn main:app --reload

2) Deploy to Render:
   - push to GitHub
   - create new Web Service from repo or use render.yaml
   - add env vars in Render dashboard

Notes:
 - Official TikTok API keys are required to retrieve live TikTok data.
 - If you don't have keys, endpoints will return messages explaining how to configure them.
