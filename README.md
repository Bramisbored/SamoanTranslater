# Samoan Translater

Speak or type English → hear it in Samoan. Record someone speaking Samoan → read and hear it in English.

The Mac mini does the work (translation, Samoan voice, Samoan speech recognition). Your Android phone runs a
web app installed to the home screen, reaching the Mac through a Cloudflare Tunnel.

```
Phone (Chrome, installed app)
   │  HTTPS
Cloudflare (Access login) ── tunnel ──▶ Mac mini :8000  FastAPI server
                                          ├─ Google Translate      (en ⇄ sm)
                                          ├─ facebook/mms-tts-smo  (Samoan voice)
                                          └─ facebook/mms-1b-all   (Samoan speech → text)
```

## Folder

| Path | What it is |
|---|---|
| `server/app.py` | The API and web server |
| `server/models.py` | Translation, voice and speech recognition |
| `web/` | The phone app (one page + install files) |
| `scripts/setup_mac.sh` | Installs everything and runs the model check |
| `scripts/check_models.py` | Tests each step; saves `check_samoan.wav` |
| `scripts/run.sh` | Runs the server in the terminal |
| `scripts/setup_tunnel.sh` | Creates the Cloudflare Tunnel for your hostname |
| `scripts/install_services.sh` | Starts server + tunnel automatically on login |

## Steps on the Mac mini

You need Homebrew (https://brew.sh) and a domain on your Cloudflare account.

**1. Copy this folder to the Mac** (e.g. `~/SamoanTranslater`) and set up:

```bash
cd ~/SamoanTranslater
bash scripts/setup_mac.sh
```

This downloads ~4 GB of models the first time, then tests every step. Play `check_samoan.wav` to hear the voice.
If you have a real Samoan recording, test recognition on it too:
`.venv/bin/python scripts/check_models.py ~/Downloads/samoan-clip.m4a`

**2. Try it locally:**

```bash
bash scripts/run.sh
```

Open http://localhost:8000 in a browser on the Mac. (The microphone works on `localhost`; on other devices it needs
the HTTPS tunnel.)

**3. Create the tunnel** (in a second terminal, leave run.sh going):

```bash
bash scripts/setup_tunnel.sh samoan.yourdomain.com
cloudflared tunnel --config ~/.cloudflared/samoan.yml run samoan
```

Open `https://samoan.yourdomain.com` on your phone to check it works.

**4. Lock it down with Cloudflare Access** — otherwise anyone with the link can use your Mac mini.
In the Cloudflare dashboard → Zero Trust → Access → Applications → Add an application → Self-hosted:
- Application domain: `samoan.yourdomain.com`
- Policy: Allow, Include → Emails → your Gmail address
- Login method: One-time PIN (or Google)

**5. Start everything automatically:** stop the two terminals (Ctrl+C), then

```bash
bash scripts/install_services.sh
```

These run while you're logged in, so turn on automatic login for the Mac mini
(System Settings → Users & Groups) and stop it sleeping (System Settings → Energy → "Prevent automatic sleeping").
Logs are in `logs/`. Remove with `bash scripts/install_services.sh remove`.

**6. Install on your Android phone:** open `https://samoan.yourdomain.com` in Chrome, log in through Access,
then ⋮ menu → **Add to Home screen** / **Install app**. Allow the microphone the first time you record.

## Good to know

- **Accuracy:** Machine translation and recognition for Samoan are rough. Keep sentences short and clear, and
  have a Samoan speaker check anything important.
- **Speed:** After start-up, a short sentence takes about 1–3 s each way on an M1. Models take ~30 s to load after
  a restart.
- **Memory:** both models together use ~5–6 GB. Fine on 16 GB; tight on an 8 GB Mac mini.
- **Licences:** Meta's MMS models are CC-BY-NC 4.0 — personal / non-commercial use only. The translation uses
  Google Translate's free endpoint, which can rate-limit or change; swapping in another translator only means
  editing `translate()` in `server/models.py`.
- **Testing without models:** `FAKE_MODELS=1 bash scripts/run.sh` runs the app with placeholder results.
- **Settings** (environment variables): `PORT`, `PRELOAD_MODELS`, `TTS_MODEL_ID`, `ASR_MODEL_ID`, `ASR_LANG`.
