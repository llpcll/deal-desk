#!/usr/bin/env python3
"""Render a ~30s Marco/Sofia sample with Gemini multi-speaker TTS for several voice pairs."""
import base64, json, os, sys, urllib.request, urllib.error, wave, io

HERE = os.path.dirname(os.path.abspath(__file__))
for line in open(os.path.join(HERE, "..", ".env"), encoding="utf-8"):
    k, _, v = line.strip().partition("=")
    if k: os.environ.setdefault(k, v.strip().strip('"'))
KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.environ.get("TTS_MODEL", "gemini-3.8-flash-tts")

STYLE = {
    "MARCO": "a man in his late thirties, a London mergers and acquisitions banker; slightly lower, deeper register than usual; calm, direct, dry wit, FT podcast host pace",
    "SOFIA": "a curious young university student; bright and engaged, conversational",
}
LINES = [
    ("MARCO", "This is The Deal Desk, episode twelve. Today, precedent transactions: what buyers have actually paid for the whole company."),
    ("SOFIA", "Which deal are we starting with?"),
    ("MARCO", "Spire Healthcare. On the fifth of September, a consortium agreed to buy it for two hundred and fifty pence a share."),
    ("SOFIA", "And the premium?"),
    ("MARCO", "Sixty-six percent above the unaffected price. Or about twenty-nine percent above the twelve-month average."),
    ("SOFIA", "Same offer, two completely different premiums. Which one's right?"),
    ("MARCO", "Both. They answer different questions. A target's board will quote the big number. A sceptical shareholder will quote the small one."),
]
PAIRS = {  # name: (Marco voice, Sofia voice)
    "C2_Sadaltager-Autonoe_deeper": ("Sadaltager", "Autonoe"),
}

def render(marco, sofia):
    body = {
        "model": MODEL,
        "input": [{"type": "user_input", "content": [
            {"type": "text", "text": t,
             "annotations": [{"type": "speech_metadata", "speaker": s, "style": STYLE[s]}]}
            for s, t in LINES]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": {"mode": "conversational", "speakers": [
            {"speaker": "MARCO", "voice": marco}, {"speaker": "SOFIA", "voice": sofia}]}},
    }
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        data=json.dumps(body).encode(), method="POST",
        headers={"x-goog-api-key": KEY, "Content-Type": "application/json"})
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=300))
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:2000]}")
    for step in resp.get("steps", []):
        for c in step.get("content", []) or []:
            if c.get("data"):
                return base64.b64decode(c["data"]), c.get("mime_type") or c.get("mimeType")
    sys.exit("No audio in response: " + json.dumps(resp)[:2000])

for name, (m, s) in PAIRS.items():
    if len(sys.argv) > 1 and name not in sys.argv[1:]: continue
    audio, mime = render(m, s)
    out = os.path.join(HERE, f"sample_{name}.wav")
    if audio[:4] == b"RIFF":
        open(out, "wb").write(audio)
    else:  # raw 16-bit PCM
        with wave.open(out, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(audio)
    with wave.open(out) as w:
        print(f"{out}  ({mime}, {w.getnframes()/w.getframerate():.1f}s)")
