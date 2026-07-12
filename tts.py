"""Text-to-speech with a quality-first provider chain.

1) ElevenLabs  — natural, human voices (needs ELEVENLABS_API_KEY; free tier works).
2) edge-tts    — good neural voices, but Microsoft often blocks datacenter IPs (403).
3) gTTS        — last-resort robotic fallback so a job never fails outright.

Set ELEVENLABS_API_KEY to get human-sounding narration reliably on Railway.
"""
import os, asyncio
import httpx
import edge_tts

# ---- ElevenLabs config ----
ELEVEN_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVEN_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
# default voice ids (well-known public voices); override with env if you like
ELEVEN_MALE = os.getenv("ELEVENLABS_VOICE_MALE", "pNInz6obpgDQGcFmaJgB")   # Adam
ELEVEN_FEMALE = os.getenv("ELEVENLABS_VOICE_FEMALE", "21m00Tcm4TlvDq8ikWAM")  # Rachel

# ---- edge-tts voices ----
VOICES = {
    "ru": ["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"],
    "kk": ["kk-KZ-DauletNeural", "kk-KZ-AigulNeural"],
    "tr": ["tr-TR-AhmetNeural", "tr-TR-EmelNeural"],
    "en": ["en-US-GuyNeural", "en-US-JennyNeural"],
}
GTTS_LANG = {"ru": "ru", "kk": "ru", "tr": "tr", "en": "en"}


def voice_for(lang: str, female: bool = False) -> str:
    lst = VOICES.get(lang, VOICES["ru"])
    return lst[1] if (female and len(lst) > 1) else lst[0]


# ---------- 1) ElevenLabs ----------
def _try_eleven(text, out_path, female, voice_id=None):
    if not ELEVEN_KEY:
        return False
    vid = voice_id or (ELEVEN_FEMALE if female else ELEVEN_MALE)
    try:
        r = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"},
            json={
                "text": text or " ",
                "model_id": ELEVEN_MODEL,
                "voice_settings": {
                    "stability": 0.45, "similarity_boost": 0.8,
                    "style": 0.15, "use_speaker_boost": True,
                },
            },
            timeout=90,
        )
        if r.status_code == 200 and r.content:
            with open(out_path, "wb") as f:
                f.write(r.content)
            return True
        print("ElevenLabs error:", r.status_code, r.text[:200])
    except Exception as e:
        print("ElevenLabs failed:", e)
    return False


# ---------- 2) edge-tts ----------
async def _edge_save(text, voice, rate, out_path):
    await edge_tts.Communicate(text, voice, rate=rate).save(out_path)


def _try_edge(text, out_path, lang, female, rate_pct, attempts=2):
    voice = voice_for(lang, female)
    rate = f"{'+' if rate_pct >= 0 else ''}{int(rate_pct)}%"
    last = None
    for _ in range(attempts):
        try:
            asyncio.run(_edge_save(text or " ", voice, rate, out_path))
            return True
        except Exception as e:
            last = e
    print("edge-tts failed:", last)
    return False


# ---------- 3) gTTS ----------
def _try_gtts(text, out_path, lang):
    try:
        from gtts import gTTS
        gTTS(text=text or " ", lang=GTTS_LANG.get(lang, "ru")).save(out_path)
        return True
    except Exception as e:
        print("gTTS failed:", e)
        return False


def synthesize(text: str, out_path: str, lang: str = "ru",
               female: bool = False, rate_pct: int = 0, voice_id: str = None):
    """Write speech mp3. Tries ElevenLabs -> edge-tts -> gTTS. Returns out_path."""
    if _try_eleven(text, out_path, female, voice_id):
        return out_path
    if _try_edge(text, out_path, lang, female, rate_pct):
        return out_path
    if _try_gtts(text, out_path, lang):
        return out_path
    raise RuntimeError("Не удалось синтезировать озвучку ни одним движком.")


def list_voices():
    """Return [{id,name,female}] — from ElevenLabs if key set, else curated."""
    curated = [
        {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam — мужской", "female": False},
        {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni — мужской", "female": False},
        {"id": "VR6AewLTigWG4xSOukaG", "name": "Arnold — мужской", "female": False},
        {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel — женский", "female": True},
        {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella — женский", "female": True},
        {"id": "AZnzlk1XvdvUeBnXmlld", "name": "Domi — женский", "female": True},
    ]
    if not ELEVEN_KEY:
        return curated
    try:
        r = httpx.get("https://api.elevenlabs.io/v1/voices",
                      headers={"xi-api-key": ELEVEN_KEY}, timeout=20)
        if r.status_code == 200:
            out = []
            for v in r.json().get("voices", [])[:24]:
                g = (v.get("labels", {}) or {}).get("gender", "")
                out.append({"id": v["voice_id"], "name": v.get("name", "Voice"),
                            "female": g == "female"})
            return out or curated
    except Exception as e:
        print("list_voices failed:", e)
    return curated
