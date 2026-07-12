import os, uuid, threading, traceback
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse

import pipeline
import llm
import tts

app = FastAPI(title="МультСтудия")
HERE = os.path.dirname(os.path.abspath(__file__))
JOBS: dict[str, dict] = {}


def _find_index() -> str | None:
    """Works whether index.html is in ./static/ or dropped in the project root."""
    for p in (os.path.join(HERE, "static", "index.html"),
              os.path.join(HERE, "index.html")):
        if os.path.exists(p):
            return p
    return None


INDEX = _find_index()


def _run(job_id: str, params: dict):
    job = JOBS[job_id]

    def prog(pct, msg):
        job["progress"], job["message"] = pct, msg

    try:
        out = pipeline.generate(job=job, progress=prog, **params)
        job["status"], job["file"], job["progress"] = "done", out, 100
        job["message"] = "Готово"
    except Exception as e:
        traceback.print_exc()
        job["status"], job["message"] = "error", f"{type(e).__name__}: {e}"


@app.get("/")
async def home():
    if INDEX:
        return FileResponse(INDEX, media_type="text/html")
    return HTMLResponse(
        "<h1>МультСтудия</h1><p>index.html не найден. Положи его в static/ "
        "или в корень проекта.</p>", status_code=200)


@app.get("/health")
async def health():
    return {"ok": True, "index": bool(INDEX)}


def _scene_budget(target: int):
    target = max(10, min(180, int(target)))
    n_scenes = max(3, min(48, round(target / 5.0)))
    words_per_scene = max(6, min(28, round(target * 2.3 / n_scenes)))
    return n_scenes, words_per_scene


@app.post("/api/ideas")
async def ideas(req: Request):
    body = await req.json()
    hint = (body.get("hint") or "").strip()
    lang = body.get("lang", "ru")
    return {"ideas": llm.generate_ideas(hint, lang, 6)}


@app.get("/api/voices")
async def voices():
    return {"voices": tts.list_voices()}


@app.post("/api/script")
async def script(req: Request):
    """Generate a script for preview/editing before rendering."""
    body = await req.json()
    topic = (body.get("topic") or "").strip()
    if not topic:
        return JSONResponse({"error": "Впиши тему ролика."}, status_code=400)
    lang = body.get("lang", "ru")
    n_scenes, wps = _scene_budget(body.get("target_seconds", 30))
    scenes = llm.generate_script(topic, lang, n_scenes, wps)
    return {"scenes": scenes}


@app.post("/api/generate")
async def generate(req: Request):
    body = await req.json()
    n_scenes, words_per_scene = _scene_budget(body.get("target_seconds", 30))
    scenes = body.get("scenes")  # pre-edited script (optional)
    params = {
        "topic": (body.get("topic") or "").strip(),
        "lang": body.get("lang", "ru"),
        "n_scenes": n_scenes,
        "words_per_scene": words_per_scene,
        "scenes": scenes if scenes else None,
        "ratio": body.get("ratio", "916"),
        "style": body.get("style", "cartoon"),
        "female": bool(body.get("female", False)),
        "voice_id": body.get("voice_id") or None,
        "karaoke": bool(body.get("karaoke", False)),
        "rate_pct": int(body.get("rate_pct", 0)),
        "subs": bool(body.get("subs", True)),
        "sub_pos": body.get("sub_pos", "bottom"),
        "sub_size": body.get("sub_size", "m"),
        "music": bool(body.get("music", True)),
    }
    if not params["topic"] and not scenes:
        return JSONResponse({"error": "Впиши тему ролика."}, status_code=400)
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": "running", "progress": 0, "message": "Старт", "file": None}
    threading.Thread(target=_run, args=(job_id, params), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/status/{job_id}")
async def status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"status": job["status"], "progress": job["progress"],
            "message": job["message"]}


@app.get("/api/video/{job_id}")
async def video(job_id: str):
    job = JOBS.get(job_id)
    if not job or job["status"] != "done" or not job["file"]:
        return JSONResponse({"error": "not ready"}, status_code=404)
    return FileResponse(job["file"], media_type="video/mp4", filename="multstudio.mp4")
