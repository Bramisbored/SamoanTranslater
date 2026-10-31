"""Download the models and check every step works before you rely on the app.

Run from the project folder:  .venv/bin/python scripts/check_models.py

1. Translates an English sentence to Samoan (Google Translate).
2. Speaks the Samoan with Meta's MMS voice -> saves check_samoan.wav (listen to it!).
3. Feeds that audio to Meta's MMS speech recogniser in Samoan mode.
4. Translates what it heard back to English.

Step 3 on the voice's own audio is only a smoke test. Also try a real Samoan
recording:  .venv/bin/python scripts/check_models.py path/to/recording.m4a
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
import models  # noqa: E402


def step(name, fn):
    print(f"\n== {name}")
    t = time.time()
    try:
        out = fn()
    except Exception as e:
        print(f"   FAILED: {type(e).__name__}: {e}")
        sys.exit(1)
    print(f"   ok ({time.time() - t:.1f}s)")
    return out


english = "Thank you very much for the delicious food."
samoan = step("Translate English -> Samoan", lambda: models.translate(english, "en", "sm"))
print(f"   {english!r} -> {samoan!r}")

wav = step(f"Samoan voice ({models.TTS_MODEL_ID}) — first run downloads ~150 MB",
           lambda: models.speak_samoan(samoan))
out = ROOT / "check_samoan.wav"
out.write_bytes(wav)
print(f"   saved {out} — play it to hear the voice")

audio_path = Path(sys.argv[1]) if len(sys.argv) > 1 else out
audio = step(f"Decode {audio_path.name} with ffmpeg", lambda: models.decode_audio(audio_path.read_bytes()))
heard = step(f"Samoan speech recognition ({models.ASR_MODEL_ID}, {models.ASR_LANG}) — first run downloads ~4 GB",
             lambda: models.transcribe_samoan(audio))
print(f"   heard: {heard!r}")

back = step("Translate Samoan -> English", lambda: models.translate(heard, "sm", "en") if heard else "")
print(f"   {heard!r} -> {back!r}")

print("\nAll steps worked. Start the server with scripts/run.sh")
