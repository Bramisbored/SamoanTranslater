"""Translation, Samoan text-to-speech and Samoan speech recognition.

Models load lazily on first use (or at startup with PRELOAD_MODELS=1) and are
kept in memory. Set FAKE_MODELS=1 to run the server without downloading
anything (returns placeholder text and a beep) — handy for testing the app.
"""

from __future__ import annotations

import io
import os
import logging
import subprocess
import threading
import time
import wave

import numpy as np

TTS_MODEL_ID = os.getenv("TTS_MODEL_ID", "facebook/mms-tts-smo")
ASR_MODEL_ID = os.getenv("ASR_MODEL_ID", "facebook/mms-1b-all")
ASR_LANG = os.getenv("ASR_LANG", "smo")
NLLB_MODEL_ID = os.getenv("NLLB_MODEL_ID", "facebook/nllb-200-distilled-600M")
TRANSLATOR = os.getenv("TRANSLATOR", "auto")  # auto (Google, then NLLB), google, nllb
FAKE = os.getenv("FAKE_MODELS") == "1"
ASR_RATE = 16_000
NLLB_CODES = {"en": "eng_Latn", "sm": "smo_Latn"}
GOOGLE_COOLDOWN = 15 * 60  # after Google blocks us, skip it for this many seconds

log = logging.getLogger(__name__)
_lock = threading.Lock()
_tts = None  # (tokenizer, model)
_asr = None  # (processor, model)
_nllb = None  # (tokenizer, model)
_google_blocked_until = 0.0
last_translator = None  # "google" or "nllb", whichever answered last


# ---------------------------------------------------------------- translation

def translate(text: str, source: str, target: str) -> str:
    """Translate with Google Translate, falling back to Meta's NLLB on this Mac.

    Google's free endpoint (via deep-translator) sometimes blocks an address with
    its "unusual traffic" page; NLLB runs locally and can't be blocked.
    Language codes: "en" English, "sm" Samoan.
    """
    global _google_blocked_until, last_translator
    if FAKE:
        return f"[{source}->{target}] {text}"

    if TRANSLATOR != "nllb" and (TRANSLATOR == "google" or time.time() >= _google_blocked_until):
        try:
            from deep_translator import GoogleTranslator

            result = GoogleTranslator(source=source, target=target).translate(text) or ""
            last_translator = "google"
            return result
        except Exception as e:
            if TRANSLATOR == "google":
                raise
            log.warning("Google Translate failed (%s: %s); using NLLB for %d min",
                        type(e).__name__, e, GOOGLE_COOLDOWN // 60)
            _google_blocked_until = time.time() + GOOGLE_COOLDOWN

    result = _translate_nllb(text, source, target)
    last_translator = "nllb"
    return result


def _load_nllb():
    global _nllb
    with _lock:
        if _nllb is None:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            _nllb = (
                AutoTokenizer.from_pretrained(NLLB_MODEL_ID),
                AutoModelForSeq2SeqLM.from_pretrained(NLLB_MODEL_ID).eval(),
            )
    return _nllb


def _translate_nllb(text: str, source: str, target: str) -> str:
    import torch

    tokenizer, model = _load_nllb()
    tokenizer.src_lang = NLLB_CODES[source]
    inputs = tokenizer(text, return_tensors="pt")
    with torch.no_grad():
        ids = model.generate(
            **inputs,
            forced_bos_token_id=tokenizer.convert_tokens_to_ids(NLLB_CODES[target]),
            max_new_tokens=256,
        )
    return tokenizer.batch_decode(ids, skip_special_tokens=True)[0].strip()


# ---------------------------------------------------------------- text-to-speech

def _load_tts():
    global _tts
    with _lock:
        if _tts is None:
            from transformers import AutoTokenizer, VitsModel

            _tts = (
                AutoTokenizer.from_pretrained(TTS_MODEL_ID),
                VitsModel.from_pretrained(TTS_MODEL_ID).eval(),
            )
    return _tts


def speak_samoan(text: str) -> bytes:
    """Return WAV bytes of `text` spoken in Samoan."""
    if FAKE:
        rate = 16_000
        t = np.linspace(0, 0.4, int(rate * 0.4), endpoint=False)
        return _to_wav(0.3 * np.sin(2 * np.pi * 440 * t), rate)

    import torch

    tokenizer, model = _load_tts()
    inputs = tokenizer(text, return_tensors="pt")
    with torch.no_grad():
        audio = model(**inputs).waveform[0].cpu().numpy()
    return _to_wav(audio, model.config.sampling_rate)


def _to_wav(audio: np.ndarray, rate: int) -> bytes:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


# ---------------------------------------------------------------- speech recognition

def _load_asr():
    global _asr
    with _lock:
        if _asr is None:
            from transformers import AutoProcessor, Wav2Vec2ForCTC

            processor = AutoProcessor.from_pretrained(ASR_MODEL_ID)
            model = Wav2Vec2ForCTC.from_pretrained(ASR_MODEL_ID).eval()
            processor.tokenizer.set_target_lang(ASR_LANG)
            model.load_adapter(ASR_LANG)
            _asr = (processor, model)
    return _asr


def decode_audio(data: bytes) -> np.ndarray:
    """Decode any audio format (webm/ogg/mp4/wav) to 16 kHz mono float32 via ffmpeg."""
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0",
         "-ac", "1", "-ar", str(ASR_RATE), "-f", "f32le", "pipe:1"],
        input=data, capture_output=True, timeout=60,
    )
    if proc.returncode != 0:
        raise ValueError("Couldn't read the recording: " + proc.stderr.decode(errors="ignore")[:200])
    return np.frombuffer(proc.stdout, dtype=np.float32)


def transcribe_samoan(audio: np.ndarray) -> str:
    """Turn 16 kHz mono Samoan speech into Samoan text."""
    if FAKE:
        return f"talofa lava ({len(audio) / ASR_RATE:.1f}s of audio)"

    import torch

    processor, model = _load_asr()
    inputs = processor(audio, sampling_rate=ASR_RATE, return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits
    ids = torch.argmax(logits, dim=-1)[0]
    return processor.decode(ids).strip()


def preload():
    if not FAKE:
        _load_tts()
        _load_asr()
        if TRANSLATOR == "nllb":  # in auto mode NLLB loads only if Google fails
            _load_nllb()


def status() -> dict:
    return {
        "fake_models": FAKE,
        "tts_loaded": _tts is not None,
        "asr_loaded": _asr is not None,
        "nllb_loaded": _nllb is not None,
        "tts_model": TTS_MODEL_ID,
        "asr_model": f"{ASR_MODEL_ID} ({ASR_LANG})",
        "translator": TRANSLATOR,
        "last_translator": last_translator,
        "google_blocked": time.time() < _google_blocked_until,
    }
