# МультСтудия — генератор мультфильмов / иллюстрированных историй

По архитектуре — как НейроКлип, но вместо стоковых клипов каждая сцена — это
**ИИ-картинка** с плавным движением камеры (Ken Burns), озвучкой и субтитрами.

## Конвейер
1. **История** — `llm.py`: ИИ пишет сюжет по сценам (реплика рассказчика + описание кадра).
2. **Картинки** — `images.py`: Pollinations.ai (бесплатно, без ключа); при сбое — градиент.
3. **Озвучка** — `tts.py`: ElevenLabs → edge-tts → gTTS.
4. **Субтитры** — `captions.py` (Pillow, без ImageMagick), есть караоке-режим.
5. **Сборка** — `pipeline.py`: посценовый рендер + склейка ffmpeg (память = 1 сцена).
6. **API + UI** — `main.py` (FastAPI), `static/index.html`.

## Локально
```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload   # http://localhost:8000
```

## Переменные окружения
| Переменная | Зачем | Без неё |
|---|---|---|
| `LLM_API_KEY` | сюжет через LLM | простой фолбэк |
| `ELEVENLABS_API_KEY` | живой голос | edge-tts / gTTS |
| `POLLINATIONS_TOKEN` | выше лимиты картинок | работает и без токена |

## Деплой на Railway
Залей папку в GitHub → New Project → Deploy from repo → добавь переменные →
Generate Domain. `nixpacks.toml` ставит ffmpeg и шрифты, старт из `Procfile`.

## Стили рисовки
cartoon (2D), pixar (3D), anime, watercolor, comic, realistic — выбираются в UI.

## Ограничения
Задания в памяти одного инстанса; для продакшена вынеси в очередь и храни файлы
на Volume/S3. Картинки Pollinations иногда генерятся медленно — длинные истории
собираются дольше.
