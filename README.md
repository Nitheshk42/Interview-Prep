# StudySager

React + FastAPI rebuild of StudySage (the Streamlit app in the sibling `studysage-rag` folder).
This is a separate project on purpose — the Streamlit app stays untouched as a working
reference/fallback while this version is built out section by section.

## Status

Built and verified so far: signup/login (JWT), resume upload + onboarding, Chat Assistant
(RAG over your resume). Everything else (Hybrid Chat, EXP Level Answers, JD Answers, General
JD Answers, Resume Tailor, Visual RAG Learning) is stubbed in the sidebar as "coming soon" and
will be ported over next, one section at a time.

## Running locally

**Backend** (FastAPI):
```
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GROQ_API_KEY, HF_API_TOKEN, JWT_SECRET, etc.
uvicorn app.main:app --reload --port 8000
```

**Frontend** (React + Vite):
```
cd frontend
npm install
cp .env.example .env   # VITE_API_URL should point at the backend above
npm run dev
```

Then open http://localhost:5173.

## Structure

- `backend/app/routers/` — HTTP endpoints (auth, onboarding, chat)
- `backend/app/services/` — the actual RAG pipeline (document loading, embeddings, vector
  store, LLM provider switching) — ported directly from `studysage-rag/src/`
- `frontend/src/pages/` — one file per screen (auth, onboarding, chat)
- `frontend/src/sections.js` — shared registry of app sections, mirrors
  `studysage-rag/src/sections.py`
