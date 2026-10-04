#!/usr/bin/env python3
"""Build the static site in /site from rendered episodes.

    python pipeline/build_site.py            # build published episodes (published.json) + feed.xml
    python pipeline/build_site.py --drafts   # also build rendered but unpublished episodes (local preview)
    python pipeline/build_site.py --serve    # build, then preview at http://localhost:8000

Inputs per episode:
    audio/episode-NN.json     timestamps from render.py
    audio/episode-NN.mp3
    content/episode-NN.json   visuals and quiz (optional). Each visual has an "at"
                              field: a quote from the line where it should appear.
Output:
    site/episode-NN/index.html (data inlined, so it also works from file://)
    site/audio/episode-NN.mp3
    site/index.html
    site/feed.xml              podcast RSS (settings in podcast.json)
"""
import argparse, datetime, email.utils, glob, html, json, os, re, shutil, sys
from xml.sax.saxutils import escape as xml_escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
TEMPLATES = os.path.join(ROOT, "pipeline", "templates")
PUBLISHED = os.path.join(ROOT, "published.json")


class BuildError(Exception):
    pass


def load_json(path, default=None):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def fmt_dur(sec):
    return f"{int(sec // 60)} min"


def resolve(anchor, lines, what):
    hits = [l for l in lines if anchor.lower() in l["text"].lower()]
    if not hits:
        raise BuildError(f"{what}: no line contains {anchor!r}")
    if len(hits) > 1:
        print(f"  warning: {what}: {anchor!r} matches {len(hits)} lines, using the first", file=sys.stderr)
    return hits[0]["i"]


def build_episode(meta_path):
    meta = json.load(open(meta_path, encoding="utf-8"))
    ep_id = meta["id"]
    num = int(re.search(r"\d+", ep_id).group())
    content_path = os.path.join(ROOT, "content", ep_id + ".json")
    content = json.load(open(content_path, encoding="utf-8")) if os.path.exists(content_path) else {}

    visuals = []
    for v in content.get("visuals", []):
        v = dict(v)
        v["line"] = resolve(v.pop("at"), meta["lines"], f"{ep_id} visual {v.get('title')!r}")
        visuals.append(v)
    visuals.sort(key=lambda v: v["line"])
    quiz = content.get("quiz")
    if quiz:
        quiz = dict(quiz)
        if "answers_at" in quiz:
            quiz["answersLine"] = resolve(quiz.pop("answers_at"), meta["lines"], f"{ep_id} quiz answers")
        if "pause_at" in quiz:
            quiz["pauseLine"] = resolve(quiz.pop("pause_at"), meta["lines"], f"{ep_id} quiz pause")

    title = re.sub(r"^The Deal Desk, episode \d+:\s*", "", meta["title"] or "")
    data = {
        "id": ep_id, "number": num, "title": title, "hook": meta.get("hook"),
        "duration": meta["duration"], "audio": f"../audio/{meta['audio']}",
        "engine": meta["engine"], "lines": meta["lines"], "visuals": visuals, "quiz": quiz,
        "sources": content.get("sources", []),
    }

    os.makedirs(os.path.join(SITE, "audio"), exist_ok=True)
    src_mp3 = os.path.join(os.path.dirname(meta_path), meta["audio"])
    dst_mp3 = os.path.join(SITE, "audio", meta["audio"])
    # audio/*.mp3 isn't committed (site/audio is), so a fresh clone may only have the copy.
    if os.path.exists(src_mp3) and (not os.path.exists(dst_mp3) or os.path.getmtime(src_mp3) > os.path.getmtime(dst_mp3)):
        shutil.copy2(src_mp3, dst_mp3)
    if not os.path.exists(dst_mp3):
        raise BuildError(f"{ep_id}: no MP3 at {src_mp3}")

    tpl = open(os.path.join(TEMPLATES, "episode.html"), encoding="utf-8").read()
    page = (tpl.replace("{{TITLE}}", html.escape(title))
               .replace("{{NUMBER}}", str(num))
               .replace("{{HOOK}}", html.escape(meta.get("hook") or ""))
               .replace("{{DURATION}}", fmt_dur(meta["duration"]))
               .replace("{{VOICE_NOTE}}", "AI voices by Google Gemini" if meta["engine"] == "gemini"
                        else "AI voices by Kokoro")
               # "</" can't appear inside an inline script
               .replace("{{DATA}}", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")))
    out_dir = os.path.join(SITE, ep_id)
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8").write(page)
    print(f"  site/{ep_id}/index.html: {len(meta['lines'])} lines, {len(visuals)} visuals, "
          f"{len((quiz or {}).get('questions', []))} quiz questions")
    return {"id": ep_id, "number": num, "title": title, "hook": meta.get("hook"),
            "duration": fmt_dur(meta["duration"]), "seconds": meta["duration"], "audio": meta["audio"],
            "engine": meta["engine"], "sources": content.get("sources", []),
            "bytes": os.path.getsize(dst_mp3)}


def build_index(episodes):
    tpl = open(os.path.join(TEMPLATES, "index.html"), encoding="utf-8").read()
    items = "\n".join(
        f'      <li><a href="{e["id"]}/"><span class="ep-num">Episode {e["number"]}</span>'
        f'<span class="ep-title">{html.escape(e["title"])}</span>'
        f'<span class="ep-hook">{html.escape(e["hook"] or "")}</span>'
        f'<span class="ep-dur">{e["duration"]}</span></a></li>'
        for e in sorted(episodes, key=lambda e: -e["number"]))
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(tpl.replace("{{EPISODES}}", items))


def build_feed(episodes, published):
    """Podcast RSS 2.0 with the iTunes tags Spotify for Creators and Apple Podcasts read."""
    cfg = load_json(os.path.join(ROOT, "podcast.json"))
    base = cfg["base_url"].rstrip("/") + "/"
    x = lambda v: xml_escape(str(v or ""), {'"': "&quot;"})
    cats = "\n".join(
        f'    <itunes:category text="{x(c)}"><itunes:category text="{x(sub)}"/></itunes:category>'
        for c, sub in cfg["categories"])
    owner = ""
    if cfg.get("owner_email"):
        owner = (f"    <itunes:owner><itunes:name>{x(cfg['owner_name'])}</itunes:name>"
                 f"<itunes:email>{x(cfg['owner_email'])}</itunes:email></itunes:owner>\n")
    else:
        print("  warning: podcast.json has no owner_email; Spotify for Creators needs it to verify the feed",
              file=sys.stderr)
    items = []
    for e in sorted(episodes, key=lambda e: -e["number"]):
        page = f"{base}{e['id']}/"
        voices = "Google Gemini" if e["engine"] == "gemini" else "Kokoro"
        sources = "".join(f'<li><a href="{html.escape(s["url"])}">{html.escape(s["label"])}</a></li>'
                          for s in e["sources"])
        body = (f"<p>{html.escape(e['hook'] or '')}</p>"
                f'<p>Transcript, visuals and the interactive quiz: <a href="{page}">{page}</a></p>'
                f"<p>{html.escape(cfg['voice_note'])} Voices by {voices}.</p>"
                + (f"<p>Sources:</p><ul>{sources}</ul>" if sources else ""))
        plain = f"{e['hook'] or ''} Transcript, visuals and quiz: {page} {cfg['voice_note']}"
        pub = datetime.datetime.fromisoformat(published[e["id"]])
        items.append(f"""    <item>
      <title>{x(f"{e['number']}. {e['title']}")}</title>
      <description>{x(plain)}</description>
      <content:encoded><![CDATA[{body}]]></content:encoded>
      <link>{x(page)}</link>
      <guid isPermaLink="false">deal-desk-{x(e['id'])}</guid>
      <pubDate>{email.utils.format_datetime(pub)}</pubDate>
      <enclosure url="{x(base + 'audio/' + e['audio'])}" length="{e['bytes']}" type="audio/mpeg"/>
      <itunes:duration>{int(round(e['seconds']))}</itunes:duration>
      <itunes:episode>{e['number']}</itunes:episode>
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:explicit>false</itunes:explicit>
      <itunes:image href="{x(base + 'cover.jpg')}"/>
    </item>""")
    dates = [datetime.datetime.fromisoformat(published[e["id"]]) for e in episodes]
    last = f"    <lastBuildDate>{email.utils.format_datetime(max(dates))}</lastBuildDate>\n" if dates else ""
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{x(cfg['title'])}</title>
    <link>{x(base)}</link>
    <atom:link href="{x(base + 'feed.xml')}" rel="self" type="application/rss+xml"/>
    <language>{x(cfg['language'])}</language>
    <description>{x(cfg['description'])}</description>
    <itunes:subtitle>{x(cfg['subtitle'])}</itunes:subtitle>
    <itunes:summary>{x(cfg['description'])}</itunes:summary>
    <itunes:author>{x(cfg['author'])}</itunes:author>
{owner}    <itunes:image href="{x(base + 'cover.jpg')}"/>
    <image><url>{x(base + 'cover.jpg')}</url><title>{x(cfg['title'])}</title><link>{x(base)}</link></image>
{cats}
    <itunes:explicit>{'true' if cfg['explicit'] else 'false'}</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    <copyright>{x(cfg['title'])}. {x(cfg['voice_note'])}</copyright>
{last}{chr(10).join(items)}
  </channel>
</rss>
"""
    open(os.path.join(SITE, "feed.xml"), "w", encoding="utf-8").write(feed)
    print(f"  site/feed.xml: {len(items)} episodes")


def build(drafts=False):
    published = load_json(PUBLISHED, {})
    metas = sorted(glob.glob(os.path.join(ROOT, "audio", "episode-*.json")))
    metas = [m for m in metas if drafts or os.path.basename(m)[:-5] in published]
    episodes = [build_episode(p) for p in metas]
    # Remove pages and audio of anything not built this time (e.g. a draft previewed earlier),
    # so an unpublished episode can never be committed and deployed by accident.
    keep = {e["id"] for e in episodes}
    for d in glob.glob(os.path.join(SITE, "episode-*")):
        if os.path.basename(d) not in keep:
            shutil.rmtree(d)
    for f in glob.glob(os.path.join(SITE, "audio", "episode-*.mp3")):
        if os.path.basename(f)[:-4] not in keep:
            os.remove(f)
    build_index(episodes)
    print(f"  site/index.html: {len(episodes)} episodes")
    build_feed([e for e in episodes if e["id"] in published], published)
    return episodes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--drafts", action="store_true", help="include rendered episodes not yet in published.json")
    args = ap.parse_args()
    try:
        build(args.drafts)
    except BuildError as e:
        sys.exit(f"build failed: {e}")
    if args.serve:
        serve()


def serve(port=8000):
    """Local preview server. Supports HTTP Range requests, which audio seeking needs
    (Python's built-in server doesn't, so the player would jump back to 0:00)."""
    import functools, http.server

    class RangeHandler(http.server.SimpleHTTPRequestHandler):
        def send_head(self):
            rng = self.headers.get("Range")
            path = self.translate_path(self.path)
            m = re.match(r"bytes=(\d*)-(\d*)$", rng or "")
            if not m or not os.path.isfile(path):
                return super().send_head()
            size = os.path.getsize(path)
            start = int(m.group(1)) if m.group(1) else max(0, size - int(m.group(2)))
            end = int(m.group(2)) if m.group(1) and m.group(2) else size - 1
            end = min(end, size - 1)
            if start > end:
                self.send_error(416); return None
            f = open(path, "rb"); f.seek(start)
            self.send_response(206)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            self._remaining = end - start + 1
            return f

        def copyfile(self, src, dst):
            n = getattr(self, "_remaining", None)
            if n is None:
                return super().copyfile(src, dst)
            while n > 0:
                chunk = src.read(min(64 * 1024, n))
                if not chunk:
                    break
                dst.write(chunk); n -= len(chunk)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("Accept-Ranges", "bytes")
            super().end_headers()

    handler = functools.partial(RangeHandler, directory=SITE)
    print(f"  preview at http://localhost:{port}  (Ctrl+C to stop)")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()


if __name__ == "__main__":
    main()
