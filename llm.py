"""Story generation for МультСтудия. OpenAI-compatible endpoint (Groq default)."""
import os, json, re
import httpx

LANG_NAME = {"ru": "русском", "kk": "казахском", "tr": "турецком", "en": "английском"}
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
API_KEY = os.getenv("LLM_API_KEY", "")
MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")


def _fallback(topic, n):
    scenes = [{"text": f"{topic}.",
               "image_prompt": f"a scene about {topic}, main character introduced"}]
    for i in range(1, n - 1):
        scenes.append({"text": f"И вот что случилось дальше ({i}).",
                       "image_prompt": f"next moment of the story about {topic}, action"})
    scenes.append({"text": "Подпишись, чтобы увидеть продолжение!",
                   "image_prompt": "happy characters waving goodbye, subscribe scene"})
    return scenes[:n]


def generate_script(topic, lang="ru", n_scenes=6, words_per_scene=14):
    """Kept named generate_script for pipeline compatibility. Returns story scenes."""
    n_scenes = max(3, min(48, int(n_scenes)))
    words_per_scene = max(6, min(28, int(words_per_scene)))
    if not API_KEY:
        return _fallback(topic, n_scenes)
    lang_name = LANG_NAME.get(lang, "русском")
    prompt = (
        f'Ты сценарист коротких мультфильмов и иллюстрированных историй на тему: "{topic}".\n'
        f"Напиши цельную историю из {n_scenes} сцен на {lang_name} языке. "
        "У истории должны быть начало, развитие и концовка; последняя сцена — призыв подписаться. "
        f"Для каждой сцены дай: text — реплику рассказчика (~{words_per_scene} слов, для озвучки); "
        "image_prompt — подробное АНГЛИЙСКОЕ описание кадра (персонажи, их действия, эмоции, фон), "
        "БЕЗ упоминания стиля рисовки (стиль зададим отдельно). "
        "Держи персонажей и место действия консистентными между сценами. "
        'Ответь СТРОГО валидным JSON без markdown:\n'
        '{"title":"...","scenes":[{"text":"реплика","image_prompt":"english scene description"}]}'
    )
    try:
        r = httpx.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL, "temperature": 0.9,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        text = re.sub(r"```json|```", "", text).strip()
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            text = m.group(0)
        data = json.loads(text)
        scenes = [
            {"text": (s.get("text") or "").strip(),
             "image_prompt": (s.get("image_prompt") or s.get("text") or "scene").strip()}
            for s in data.get("scenes", []) if s.get("text")
        ]
        return scenes or _fallback(topic, n_scenes)
    except Exception as e:
        print("LLM error, using fallback:", e)
        return _fallback(topic, n_scenes)


def generate_ideas(hint="", lang="ru", n=6):
    n = max(3, min(10, int(n)))
    lang_name = LANG_NAME.get(lang, "русском")
    fallback = [
        "Как маленький дракон научился летать",
        "Приключения котёнка в большом городе",
        "Робот, который мечтал стать художником",
        "Тайна волшебного леса",
        "Космическое путешествие весёлого пингвина",
        "История о храбром мышонке",
    ]
    if not API_KEY:
        return fallback[:n]
    hint_part = f" по направлению: {hint}." if hint.strip() else "."
    prompt = (
        f"Предложи {n} идей для коротких мультфильмов / иллюстрированных историй "
        f"на {lang_name} языке{hint_part} Каждая — короткое цепляющее название (до 8 слов), "
        "разные сюжеты, без нумерации. "
        'Ответь СТРОГО валидным JSON без markdown: {"ideas":["...","..."]}'
    )
    try:
        r = httpx.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL, "temperature": 1.0,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=45,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        text = re.sub(r"```json|```", "", text).strip()
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            text = m.group(0)
        ideas = [str(x).strip() for x in json.loads(text).get("ideas", []) if str(x).strip()]
        return ideas[:n] or fallback[:n]
    except Exception as e:
        print("ideas error, using fallback:", e)
        return fallback[:n]
