#!/usr/bin/env python3
import re, sys, subprocess, tempfile, os
import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

script, out = sys.argv[1], sys.argv[2]
model_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.dirname(os.path.abspath(__file__))

VOICES = {"MARCO": ("bm_george", 1.0), "SOFIA": ("af_heart", 1.05)}
kokoro = Kokoro(os.path.join(model_dir, "kokoro-v1.0.onnx"), os.path.join(model_dir, "voices-v1.0.bin"))

def clean(t):
    t = re.sub(r"\bM\s*(?:&|-and-|and)\s*A\b", "mergers and acquisitions", t)
    t = re.sub(r"\*\*|__|\*|`|#", "", t)
    t = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", t)
    t = t.replace("—", ", ").replace("–", "-")
    t = re.sub(r"\((pause|beat|laughs?)\)", "...", t, flags=re.I)
    return t.strip()

turns, cur = [], None
for line in open(script, encoding="utf-8"):
    m = re.match(r"^\s*\**(MARCO|SOFIA)\**\s*:\s*\**\s*(.*)", line)
    if m:
        cur = [m.group(1), m.group(2)]
        turns.append(cur)
    elif cur and line.strip() and not line.lstrip().startswith("#"):
        cur[1] += " " + line.strip()
    elif not line.strip():
        cur = None

sr_out, chunks = 24000, []
for speaker, text in turns:
    text = clean(text)
    if not text:
        continue
    voice, speed = VOICES[speaker]
    parts = re.split(r"(?<=[.!?])\s+", text)
    buf = ""
    for p in parts + [None]:
        if p is not None and len(buf) + len(p) < 400:
            buf = (buf + " " + p).strip(); continue
        if buf:
            audio, sr = kokoro.create(buf, voice=voice, speed=speed, lang="en-us" if voice.startswith("a") else "en-gb")
            sr_out = sr
            chunks.append(audio); chunks.append(np.zeros(int(sr * 0.18), dtype=np.float32))
        buf = p or ""
    chunks.append(np.zeros(int(sr_out * 0.35), dtype=np.float32))

wav = np.concatenate(chunks)
with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
    sf.write(f.name, wav, sr_out)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f.name, "-af", "loudnorm", "-b:a", "96k", out], check=True)
print(f"{out}: {len(turns)} turns, {len(wav)/sr_out/60:.1f} min")
