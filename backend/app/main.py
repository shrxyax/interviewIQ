from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.api.upload import router as upload_router
from app.api.chat import router as chat_router
from app.core.db import SessionLocal, init_db
from app.modules.aptitude.api import router as aptitude_router
from app.modules.aptitude.seed import seed_all as seed_aptitude
from app.modules.auth.api import router as auth_router
from app.modules.coding.api import router as coding_router
from app.modules.coding.seed import seed_all as seed_coding
from app.modules.content.api import router as content_router
from app.modules.content.seed import seed_all as seed_content
from app.modules.interview.api import router as interview_context_router
from app.modules.mkt.api import router as mkt_router
from app.modules.mkt.seed import seed_all as seed_mkt
from app.modules.whiteboard.api import router as whiteboard_router
from app.modules.whiteboard.seed import seed_all as seed_whiteboard
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    with SessionLocal() as db:
        seed_mkt(db)
        seed_whiteboard(db)
        seed_content(db)
        seed_coding(db)
        seed_aptitude(db)

    yield


app = FastAPI(
    title="InterviewIQ API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200", "http://127.0.0.1:4200",
        "http://localhost:2000", "http://127.0.0.1:2000",
        "http://localhost:5173", "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(chat_router)
app.include_router(interview_context_router)
app.include_router(auth_router)
app.include_router(mkt_router)
app.include_router(whiteboard_router)
app.include_router(content_router)
app.include_router(coding_router)
app.include_router(aptitude_router)

@app.get("/")
def root():
    return {
        "message": "InterviewIQ Backend Running "
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }
