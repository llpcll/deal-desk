"""Forced alignment: where does each script line start inside a rendered chunk?

One TTS request now covers many lines, so line timings come from the audio itself:
faster-whisper (small.en, CPU, free and local) transcribes the chunk with word
timestamps, the transcript is matched against the script's words, and each line
starts at its first matched word. Numbers are spelled out in the scripts but Whisper
often writes digits, so matching leans on the ordinary words; a line with no match
is placed between its neighbours by character count. If too little of the chunk
matches, the whole chunk falls back to splitting by character count.

    starts, info = align(audio_24k, [(speaker, text), ...])
"""
import difflib, re

import numpy as np

SR = 24000
MODEL_NAME = "small.en"
MIN_COVERAGE = 0.6        # share of the script's ordinary words found in the transcript
_model = None


def _load():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
    return _model


def norm_words(text):
    """Lower-case word tokens; hyphenated letter groups (E-V, D-C-F) are joined."""
    text = re.sub(r"\b((?:[A-Za-z]-)+[A-Za-z])\b", lambda m: m.group(1).replace("-", ""), text)
    return [w for w in re.split(r"[^a-z0-9']+", text.lower().replace("-", " ")) if w]


def spell_numbers(text):
    """Whisper writes "8.6", "250", "66%", "2025"; the scripts spell them out as said."""
    from num2words import num2words

    def say(m):
        tok, pct = m.group(1).replace(",", ""), m.group(2)
        try:
            if re.fullmatch(r"(19|20)\d\d", tok) and not pct:
                words = num2words(int(tok), to="year")
            elif "." in tok:
                whole, frac = tok.split(".", 1)
                words = num2words(int(whole or 0)) + " point " + " ".join(num2words(int(d)) for d in frac)
            else:
                words = num2words(int(tok))
        except (ValueError, OverflowError):
            return m.group(0)
        return " " + words + (" percent" if pct else "") + " "
    return re.sub(r"(\d[\d,]*(?:\.\d+)?)\s*(%)?", say, text)


def transcribe(audio, sr=SR):
    """[(word, start_s, end_s)] for a mono float32 chunk."""
    n16 = int(len(audio) * 16000 / sr)
    a16 = np.interp(np.linspace(0, len(audio) - 1, n16), np.arange(len(audio)), audio).astype(np.float32)
    segments, _ = _load().transcribe(a16, language="en", word_timestamps=True, beam_size=5,
                                     vad_filter=False, condition_on_previous_text=True)
    out = []
    for seg in segments:
        for w in seg.words or []:
            for tok in norm_words(spell_numbers(w.word)):
                out.append((tok, w.start, w.end))
    return out


def speech_onsets(audio, min_pause=0.1):
    """Times (s) where speech resumes after at least min_pause of silence."""
    hop = int(0.01 * SR)
    n = len(audio) // hop
    rms = np.sqrt((audio[:n * hop].reshape(n, hop) ** 2).mean(axis=1)) + 1e-9
    db = 20 * np.log10(rms)
    silent = db < max(np.percentile(db, 75) - 30, -60)
    onsets, run = [], 0
    for i, quiet in enumerate(silent):
        if quiet:
            run += 1
        else:
            if run >= min_pause / 0.01:
                onsets.append(i * 0.01)
            run = 0
    return np.array(onsets)


def snap_to_onsets(audio, starts, window=0.8, min_pause=0.1):
    """Move each estimate to the nearest point where speech resumes after a pause:
    a new line almost always begins right after a short silence."""
    hop = int(0.01 * SR)
    n = len(audio) // hop
    rms = np.sqrt((audio[:n * hop].reshape(n, hop) ** 2).mean(axis=1)) + 1e-9
    db = 20 * np.log10(rms)
    silent = db < max(np.percentile(db, 75) - 30, -60)
    onsets, run = [], 0
    for i, s in enumerate(silent):
        if s:
            run += 1
        else:
            if run >= min_pause / 0.01:
                onsets.append(i * 0.01)
            run = 0
    onsets = np.array(onsets)
    if not len(onsets):
        return starts
    out = []
    for t in starts:
        # Whisper's word times can run a little early or late, so search both ways.
        d = np.abs(onsets - t)
        out.append(float(onsets[d.argmin()]) if d.min() <= window else t)
    return out


def proportional(lines, t0, t1):
    """Line starts by character count across [t0, t1]."""
    chars = np.array([max(len(t), 4) for _, t in lines], float)
    edges = t0 + np.concatenate([[0], np.cumsum(chars)]) / chars.sum() * (t1 - t0)
    return list(edges[:-1])


def align(audio, lines, speech_start=0.0, speech_end=None):
    """Return (line start times in seconds, info dict)."""
    speech_end = len(audio) / SR if speech_end is None else speech_end
    words = transcribe(audio)
    script, owner = [], []
    for i, (_, text) in enumerate(lines):
        for w in norm_words(text):
            script.append(w); owner.append(i)
    alpha = [i for i, w in enumerate(script) if not w.isdigit()]
    sm = difflib.SequenceMatcher(None, script, [w for w, _, _ in words], autojunk=False)
    match = {}
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            match[a + k] = b + k
    coverage = sum(1 for i in alpha if i in match) / max(1, len(alpha))
    info = {"coverage": round(coverage, 3), "transcribed_words": len(words), "script_words": len(script)}
    if coverage < MIN_COVERAGE or not words:
        info["method"] = "proportional"
        return proportional(lines, speech_start, speech_end), info

    # Each line: time of its first matched word, pulled back for any unmatched words before it.
    starts = [None] * len(lines)
    first_idx = {}
    for i, o in enumerate(owner):
        first_idx.setdefault(o, i)
    for li in range(len(lines)):
        idxs = [i for i in range(len(script)) if owner[i] == li]
        for n, i in enumerate(idxs[:8]):
            if i in match:
                t = words[match[i]][1] - n * 0.32     # ~0.32 s per spoken word
                starts[li] = max(speech_start, t)
                break
    # Fill gaps between known neighbours by character count, then force increasing order.
    known = [i for i, s in enumerate(starts) if s is not None]
    if not known:
        info["method"] = "proportional"
        return proportional(lines, speech_start, speech_end), info
    starts[0] = speech_start if starts[0] is None or starts[0] - speech_start < 0.8 else starts[0]
    anchors = [0] + [i for i in known if i > 0] + [len(lines)]
    times = [starts[0]] + [starts[i] for i in anchors[1:-1]] + [speech_end]
    for (a, ta), (b, tb) in zip(zip(anchors, times), list(zip(anchors, times))[1:]):
        if b - a > 1:
            fill = proportional(lines[a:b], ta, tb)
            for k in range(a + 1, b):
                starts[k] = fill[k - a]
    unmatched = [li for li in range(len(lines)) if li not in known and li > 0]
    starts = snap_to_onsets(audio, starts)
    # Short interjections ("Go on.", "Second?") are often missed by Whisper. Place an
    # unmatched line at the first speech onset after the previous line's last heard word.
    last_word_end = {}
    for i, o in enumerate(owner):
        if i in match:
            last_word_end[o] = words[match[i]][2]
    onsets = speech_onsets(audio)
    for li in unmatched:
        prev_end = last_word_end.get(li - 1)
        nxt = starts[li + 1] if li + 1 < len(starts) else speech_end
        if prev_end is None:
            continue
        after = onsets[(onsets > prev_end + 0.05) & (onsets < nxt - 0.15)]
        if len(after):
            starts[li] = float(after[0])
    for i in range(1, len(starts)):
        starts[i] = max(starts[i], starts[i - 1] + 0.2)
    info["method"] = "whisper"
    info["lines_matched"] = len(known)
    return starts, info
