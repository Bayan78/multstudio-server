"""Assemble the final MP4 from a script — memory-safe, per-scene rendering.

Each scene is rendered to its own MP4 and immediately released from memory,
then all scenes are joined with ffmpeg's concat demuxer (stream copy, low RAM).
This keeps peak memory ~= one scene, so 2-3 minute videos don't blow up the
instance the way loading every clip at once would.

Per scene:
  1) TTS -> mp3 (length drives scene duration)
  2) background = Pexels clip (cover-cropped) OR generated gradient
  3) caption PNG (Pillow) overlaid
  4) audio = narration (+ silence tail)
  -> written to scene_NNN.mp4, then clips closed.
Finally: ffmpeg concat, optional background-music mix.
"""
import os, glob, tempfile, random, subprocess
import numpy as np
from PIL import Image as _PILImage
if not hasattr(_PILImage, "ANTIALIAS"):  # moviepy 1.0.3 <-> Pillow>=10 compat
    _PILImage.ANTIALIAS = _PILImage.LANCZOS
from moviepy.editor import (
    ImageClip, AudioFileClip, CompositeVideoClip, concatenate_audioclips,
)
from moviepy.audio.AudioClip import AudioArrayClip
import imageio_ffmpeg

import llm, tts, images, captions

RATIOS = {"916": (720, 1280), "11": (1080, 1080), "169": (1280, 720)}
MUSIC_DIR = os.path.join(os.path.dirname(__file__), "assets", "music")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FPS = 30
AUDIO_FPS = 44100


def _cover_arr(arr, w, h):
    return arr  # images are generated already at target w x h


def _visual(prompt, dur, w, h, idx=0, style="cartoon"):
    """AI image + gentle Ken Burns (alternating zoom in / out) for life."""
    arr = images.fetch(prompt, w, h, style)
    base = ImageClip(arr).set_duration(dur)
    z0, z1 = (1.0, 1.14) if idx % 2 == 0 else (1.14, 1.0)
    d = max(0.1, dur)
    base = base.resize(lambda t: z0 + (z1 - z0) * (t / d))
    return base.set_position(("center", "center")).set_duration(dur)


def _pad_audio(narr, min_dur=1.4, tail=0.35):
    target = max(min_dur, narr.duration + tail)
    if target <= narr.duration + 1e-3:
        return narr, narr.duration
    fps = int(narr.fps or AUDIO_FPS)
    nch = int(getattr(narr, "nchannels", 2) or 2)
    n = int((target - narr.duration) * fps)
    silence = AudioArrayClip(np.zeros((max(1, n), nch)), fps=fps)
    return concatenate_audioclips([narr, silence]), target


def _render_scene(sc, i, tmp, w, h, lang, female, rate_pct, subs, sub_pos,
                  sub_size, voice_id=None, karaoke=False, style="cartoon"):
    mp3 = os.path.join(tmp, f"v{i}.mp3")
    tts.synthesize(sc["text"], mp3, lang, female, rate_pct, voice_id)
    narr = AudioFileClip(mp3)
    audio, dur = _pad_audio(narr)
    prompt = sc.get("image_prompt") or sc.get("keyword") or sc.get("text") or "scene"
    base = _visual(prompt, dur, w, h, i, style)
    layers = [base]
    extra = []
    if subs and sc["text"]:
        if karaoke:
            words = sc["text"].split()
            n = max(1, len(words))
            step = dur / n
            for k in range(1, n + 1):
                img = captions.render_caption(sc["text"], w, h, sub_pos, sub_size,
                                              revealed=k)
                start = (k - 1) * step
                d = dur - start if k == n else step
                clip = (ImageClip(np.array(img)).set_start(start)
                        .set_duration(d).set_position((0, 0)))
                extra.append(clip)
        else:
            cap_img = captions.render_caption(sc["text"], w, h, sub_pos, sub_size)
            extra.append(ImageClip(np.array(cap_img)).set_duration(dur)
                         .set_position((0, 0)).crossfadein(0.25))
    scene = (CompositeVideoClip(layers + extra, size=(w, h))
             .set_duration(dur).set_audio(audio))
    out_i = os.path.join(tmp, f"scene_{i:03d}.mp4")
    scene.write_videofile(
        out_i, fps=FPS, codec="libx264", audio_codec="aac", audio_fps=AUDIO_FPS,
        threads=4, preset="veryfast", logger=None,
        temp_audiofile=os.path.join(tmp, f"a_{i}.m4a"),
    )
    for c in [scene, base, audio, narr] + extra:
        try: c.close()
        except Exception: pass
    return out_i


def _concat(files, out_path, tmp):
    listfile = os.path.join(tmp, "list.txt")
    with open(listfile, "w") as f:
        for p in files:
            f.write(f"file '{p}'\n")
    # fast path: stream copy (works because all scenes share codec params)
    r = subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0",
                        "-i", listfile, "-c", "copy", out_path],
                       capture_output=True)
    if r.returncode == 0 and os.path.exists(out_path):
        return out_path
    # robust fallback: re-encode the join (streaming, still low memory)
    subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", listfile,
                    "-c:v", "libx264", "-preset", "veryfast", "-r", str(FPS),
                    "-c:a", "aac", out_path], capture_output=True, check=True)
    return out_path


def _pick_music():
    files = glob.glob(os.path.join(MUSIC_DIR, "*.mp3")) + \
            glob.glob(os.path.join(MUSIC_DIR, "*.m4a"))
    return random.choice(files) if files else None


def _add_music(video_in, music, out_path):
    r = subprocess.run(
        [FFMPEG, "-y", "-i", video_in, "-stream_loop", "-1", "-i", music,
         "-filter_complex",
         "[1:a]volume=0.12[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
         "-shortest", out_path], capture_output=True)
    return r.returncode == 0 and os.path.exists(out_path)


def generate(job, topic, lang="ru", n_scenes=5, ratio="916",
             female=False, rate_pct=0, subs=True, sub_pos="bottom",
             sub_size="m", music=True, words_per_scene=14, scenes=None,
             voice_id=None, karaoke=False, style="cartoon",
             out_path=None, progress=lambda *_: None):
    w, h = RATIOS.get(ratio, RATIOS["916"])
    tmp = tempfile.mkdtemp(prefix="ms_")
    out_path = out_path or os.path.join(tmp, "multstudio.mp4")

    if scenes:  # user already reviewed/edited the story -> skip the LLM
        scenes = [{"text": (s.get("text") or "").strip(),
                   "image_prompt": (s.get("image_prompt") or s.get("text") or "scene").strip()}
                  for s in scenes if (s.get("text") or "").strip()]
    else:
        progress(4, "Пишу историю")
        scenes = llm.generate_script(topic, lang, n_scenes, words_per_scene)
    total = len(scenes)

    files = []
    for i, sc in enumerate(scenes):
        progress(6 + int(78 * i / total), f"Рисую сцену {i+1}/{total}")
        files.append(_render_scene(sc, i, tmp, w, h, lang, female, rate_pct,
                                   subs, sub_pos, sub_size, voice_id, karaoke, style))

    progress(86, "Склеиваю сцены")
    mpath = _pick_music() if music else None
    if mpath:
        joined = os.path.join(tmp, "joined.mp4")
        _concat(files, joined, tmp)
        progress(93, "Добавляю музыку")
        if not _add_music(joined, mpath, out_path):
            os.replace(joined, out_path)  # music failed -> keep video
    else:
        _concat(files, out_path, tmp)

    progress(100, "Готово")
    return out_path
