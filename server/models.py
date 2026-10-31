"""Translation, Samoan text-to-speech and Samoan speech recognition.

Models load lazily on first use (or at startup with PRELOAD_MODELS=1) and are
kept in memory. Set FAKE_MODELS=1 to run the server without downloading
anything (returns placeholder text and a beep) — handy for testing the app.
"""

from __future__ import annotations

import io
import os
import subprocess
import threading
import wave

import numpy as np

TTS_MODEL_ID = os.getenv("TTS_MODEL_ID", "facebook/mms-tts-smo")
ASR_MODEL_ID = os.getenv("ASR_MODEL_ID", "facebook/mms-1b-all")
ASR_LANG = os.getenv("ASR_LANG", "smo")
FAKE = os.getenv("FAKE_MODELS") == "1"
ASR_RATE = 16_000

_lock = threading.Lock()
_tts = None  # (tokenizer, model)
_asr = None  # (processor, model)


# ---------------------------------------------------------------- translation

def translate(text: str, source: str, target: str) -> str:
    """Translate with Google Translate (free endpoint via deep-translator).

    Language codes: "en" English, "sm" Samoan.
    """
    if FAKE:
        return f"[{source}->{target}] {text}"
    from deep_translator import GoogleTranslator

    return GoogleTranslator(source=source, target=target).translate(text) or ""


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


def status() -> dict:
    return {
        "fake_models": FAKE,
        "tts_loaded": _tts is not None,
        "asr_loaded": _asr is not None,
        "tts_model": TTS_MODEL_ID,
        "asr_model": f"{ASR_MODEL_ID} ({ASR_LANG})",
    }
