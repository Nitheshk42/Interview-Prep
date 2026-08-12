from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import CORS_ORIGINS
from app.routers import auth, onboarding, chat, hybrid_chat, level_chat, jd_chat, general_jd_chat, resume_tailor, chat_sessions, resume_sync

app = FastAPI(title="StudySager API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(chat.router)
app.include_router(hybrid_chat.router)
app.include_router(level_chat.router)
app.include_router(jd_chat.router)
app.include_router(general_jd_chat.router)
app.include_router(resume_tailor.router)
app.include_router(chat_sessions.router)
app.include_router(resume_sync.router)


@app.get("/health")
def health():
    return {"status": "ok"}
