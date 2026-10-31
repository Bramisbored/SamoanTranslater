"""SamoanTranslater server.

    POST /api/speak   {"text": "..."}          English -> Samoan text + Samoan audio
    POST /api/say     {"text": "..."}          Samoan text -> Samoan audio (replay/edit)
    POST /api/listen  multipart file "audio"   Samoan speech -> Samoan text + English
                      (?translate=false: Samoan text only, the phone translates it)
    POST /api/translate {"text", "source", "target"}  translate on the Mac ("en" / "sm")
                      ("engine": "nllb" skips Google)
    GET  /api/health
    GET  /                                     the phone web app

Run:  uvicorn app:app --host 127.0.0.1 --port 8000   (from this folder)
"""

from __future__ import annotations

import base64
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import models

log = logging.getLogger("samoan")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MAX_TEXT = 500
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_SECONDS = 60


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("PRELOAD_MODELS") == "1":
        log.info("Loading models…")
        models.preload()
        log.info("Models loaded.")
    yield


app = FastAPI(title="SamoanTranslater", lifespan=lifespan)


class TextIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT)


class TranslateIn(TextIn):
    source: Literal["en", "sm"]
    target: Literal["en", "sm"]
    engine: Literal["auto", "nllb"] = "auto"  # "nllb": skip Google (the phone is already asking it)


def _b64_wav(wav: bytes) -> str:
    return "data:audio/wav;base64," + base64.b64encode(wav).decode()


@app.get("/api/health")
def health():
    return {"ok": True, **models.status()}


@app.post("/api/speak")
def speak(body: TextIn):
    english = body.text.strip()
    try:
        samoan = models.translate(english, "en", "sm")
    except Exception as e:
        log.exception("translate failed")
        raise HTTPException(502, f"Translation failed: {e}")
    if not samoan:
        raise HTTPException(502, "Translation came back empty.")
    wav = models.speak_samoan(samoan)
    return {"english": english, "samoan": samoan, "audio": _b64_wav(wav),
            "translator": models.last_translator}


@app.post("/api/say")
def say(body: TextIn):
    samoan = body.text.strip()
    return {"samoan": samoan, "audio": _b64_wav(models.speak_samoan(samoan))}


@app.post("/api/translate")
def translate(body: TranslateIn):
    try:
        text = models.translate(body.text.strip(), body.source, body.target, body.engine)
    except Exception as e:
        log.exception("translate failed")
        raise HTTPException(502, f"Translation failed: {e}")
    return {"text": text, "translator": models.last_translator}


@app.post("/api/listen")
def listen(audio: UploadFile = File(...), translate: bool = True):
    data = audio.file.read(MAX_AUDIO_BYTES + 1)
    if not data:
        raise HTTPException(400, "The recording was empty.")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Recording is too large.")
    try:
        samples = models.decode_audio(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    seconds = len(samples) / models.ASR_RATE
    if seconds < 0.3:
        raise HTTPException(400, "Recording was too short — hold the button while you speak.")
    if seconds > MAX_AUDIO_SECONDS:
        raise HTTPException(413, f"Keep recordings under {MAX_AUDIO_SECONDS} seconds.")

    samoan = models.transcribe_samoan(samples)
    if not samoan or not translate:
        return {"samoan": samoan, "english": "", "seconds": round(seconds, 1)}
    try:
        english = models.translate(samoan, "sm", "en")
    except Exception as e:
        log.exception("translate failed")
        raise HTTPException(502, f"Translation failed: {e}")
    return {"samoan": samoan, "english": english, "seconds": round(seconds, 1),
            "translator": models.last_translator}


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js")
def service_worker():
    return FileResponse(WEB_DIR / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
