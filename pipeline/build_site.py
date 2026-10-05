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


SEASON_FILE = os.path.join(ROOT, "content", "season-1.json")
# Same policy as in templates/episode.html: only this site's own files, no inline code.
CSP_META = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; script-src 'self'; "
            "style-src 'self'; font-src 'self'; img-src 'self'; media-src 'self'; connect-src 'self'; "
            "base-uri 'none'; form-action 'none'; object-src 'none'\">\n"
            "<meta name=\"referrer\" content=\"strict-origin-when-cross-origin\">")


class BuildError(Exception):
    pass


def release_date(season, n):
    """Episode N of the season is released on start + N days (2026-09-22 + N)."""
    return datetime.date.fromisoformat(season["start"]) + datetime.timedelta(days=n)


def long_date(d):
    return f"{d.day} {d:%B %Y}"


def next_block(season, published, prefix):
    """The "Next episode" box. Without JavaScript it shows the date as plain text;
    assets/next.js turns it into a countdown in the viewer's local time."""
    done = {int(k.split("-")[1]) for k in published}
    upcoming = [e for e in season["episodes"] if e["number"] > max(done, default=0)]
    if not upcoming:
        return ('<section class="wrap next" aria-labelledby="next-h"><h2 id="next-h">Next episode</h2>'
                '<p class="next-done">Season 1 is complete.</p></section>')
    e = upcoming[0]
    d = release_date(season, e["number"])
    t = season["release_time"]
    return f"""<section class="wrap next" aria-labelledby="next-h">
  <h2 id="next-h">Next episode</h2>
  <details class="next-ep" data-date="{d.isoformat()}" data-time="{t}" data-tz="{season['timezone']}">
    <summary>
      <span class="next-num">Episode {e['number']}</span>
      <span class="next-title">{html.escape(e['title'])}</span>
      <span class="next-teaser">{html.escape(e['teaser'])}</span>
    </summary>
    <div class="next-body">
      <p class="next-when">Releases on {long_date(d)} at {t}, Rome time.</p>
      <p class="next-count" aria-live="polite" hidden></p>
    </div>
  </details>
</section>"""


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


def find_chapters(n, lines, content):
    """Chapter starts: cold open, the concept (anchored in the content file), what they'll
    ask you, deal of the day, quiz. Returns [(line index, title)], in order."""
    def first(pred, after=0):
        return next((l["i"] for l in lines[after:] if pred(l["text"].lower())), None)
    review = n % 7 == 0
    out = [(0, "Introduction" if review else "Cold open")]
    at = (content.get("chapters") or {}).get("concept_at")
    concept = resolve(at, lines, f"episode {n} chapter") if at else None
    if concept:
        out.append((concept, "The review" if review else "The concept"))
    ask = first(lambda t: "what they'll ask you" in t, concept or 0)
    if ask:
        out.append((ask, "What they'll ask you"))
    deal = first(lambda t: "deal of the day" in t, ask or concept or 0)
    if deal:
        out.append((deal, "Deal of the day"))
    quiz = first(lambda t: re.search(r"\bquiz\b", t) is not None, deal or 0)
    if quiz:
        out.append((quiz, "Quiz"))
    starts = [i for i, _ in out]
    if starts != sorted(set(starts)):
        raise BuildError(f"episode {n}: chapters out of order: {out}")
    return out


def page_url(cfg, path=""):
    return cfg["base_url"].rstrip("/") + "/" + path


def footer(prefix, cfg):
    """About, subscribe links (Spotify and Apple appear once their URLs are in podcast.json), copyright."""
    subs = [f'<a href="{prefix}feed.xml">RSS feed</a>']
    for key, label in (("spotify_url", "Spotify"), ("apple_url", "Apple Podcasts")):
        if cfg.get(key):
            subs.append(f'<a href="{html.escape(cfg[key])}" rel="noopener">{label}</a>')
    return f"""<footer class="wrap foot">
  <div class="foot-grid">
    <section aria-labelledby="about-h">
      <h2 id="about-h">About</h2>
      <p>The Deal Desk teaches one corporate finance concept a day through a real deal, for students preparing for investment banking interviews. It is AI-voiced: Marco and Sofia are fictional characters with AI-generated voices, and the scripts are written with AI and checked against public sources. Nothing here is investment advice.</p>
    </section>
    <section aria-labelledby="subscribe-h">
      <h2 id="subscribe-h">Subscribe</h2>
      <ul class="subscribe">{"".join(f"<li>{s}</li>" for s in subs)}</ul>
    </section>
  </div>
  <p class="copyright">© {datetime.date.today().year} The Deal Desk</p>
</footer>"""


def head_meta(cfg, title, description, path, image, prefix):
    """Canonical URL, Open Graph and Twitter tags, favicons, font preloads."""
    url = page_url(cfg, path)
    img = page_url(cfg, image)
    e = html.escape
    return f"""<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="The Deal Desk">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{img}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{e(title)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(description)}">
<meta name="twitter:image" content="{img}">
<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{prefix}apple-touch-icon.png">
<link rel="preload" href="{prefix}assets/fonts/Newsreader-normal-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{prefix}assets/fonts/PublicSans-normal-latin.woff2" as="font" type="font/woff2" crossorigin>"""


def build_episode(meta_path, published, season, nxt):
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
        qs = []
        for q in quiz.get("questions", []):
            q = dict(q)
            if q.get("explain_at"):
                q["explainLine"] = resolve(q.pop("explain_at"), meta["lines"], f"{ep_id} {q.get('id')} explain_at")
            qs.append(q)
        quiz["questions"] = qs

    title = re.sub(r"^The Deal Desk, episode \d+:\s*", "", meta["title"] or "")
    cfg = load_json(os.path.join(ROOT, "podcast.json"))
    chapters = [{"line": i, "title": t, "start": 0.0 if k == 0 else meta["lines"][i]["start"]}
                for k, (i, t) in enumerate(find_chapters(num, meta["lines"], content))]
    os.makedirs(os.path.join(SITE, "chapters"), exist_ok=True)
    json.dump({"version": "1.2.0", "title": title,
               "chapters": [{"startTime": round(c["start"], 1), "title": c["title"]} for c in chapters]},
              open(os.path.join(SITE, "chapters", ep_id + ".json"), "w", encoding="utf-8"), indent=1)
    nid = f"episode-{num + 1:02d}"
    plan = {e["number"]: e for e in season["episodes"]}
    if nid in published:
        next_link = {"url": f"../{nid}/", "label": f"Next episode: {plan.get(num + 1, {}).get('title', '')}"}
    else:
        next_link = {"url": "../#next", "label": "See when the next episode is out"}
    import make_share
    make_share.episode_image(num, title, os.path.join(SITE, "share", ep_id + ".png"))
    data = {
        "id": ep_id, "number": num, "title": title, "hook": meta.get("hook"),
        "duration": meta["duration"], "audio": f"../audio/{meta['audio']}",
        "engine": meta["engine"], "lines": meta["lines"], "visuals": visuals, "quiz": quiz,
        "sources": content.get("sources", []), "chapters": chapters, "next": next_link,
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
               .replace("{{RELEASED}}", "First released " + long_date(
                   datetime.datetime.fromisoformat(published[ep_id]).date()) if ep_id in published else "Draft, not released")
               .replace("{{NEXT}}", nxt)
               .replace("{{CSP}}", CSP_META)
               .replace("{{HEAD_META}}", head_meta(cfg, f"Episode {num}: {title} | The Deal Desk",
                                                   meta.get("hook") or "", f"{ep_id}/", f"share/{ep_id}.png", "../"))
               .replace("{{FOOTER}}", footer("../", cfg))
               .replace("{{MP3}}", f"../audio/{meta['audio']}")
               .replace("{{MP3_MB}}", f"{os.path.getsize(dst_mp3) / 1e6:.0f}")
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


def build_index(episodes, published, season, nxt):
    """The Season 1 page: all 42 episodes in six weeks; released ones link to their page."""
    built = {e["number"]: e for e in episodes}
    plan = {e["number"]: e for e in season["episodes"]}
    weeks = []
    for w in season["weeks"]:
        rows = []
        for n in w["episodes"]:
            p, b = plan[n], built.get(n)
            kind = '<span class="ep-kind">Review</span>' if p["review"] else ""
            if b and b["id"] in published:
                rows.append(f'      <li class="ep"><a href="{b["id"]}/"><span class="ep-num">{n}</span>'
                            f'<span class="ep-title">{html.escape(b["title"])}{kind}</span>'
                            f'<span class="ep-meta">{b["duration"]}</span></a></li>')
            else:
                d = release_date(season, n)
                rows.append(f'      <li class="ep upcoming"><span class="ep-num">{n}</span>'
                            f'<span class="ep-title">{html.escape(p["title"])}{kind}</span>'
                            f'<span class="ep-meta"><time datetime="{d.isoformat()}">{d.day} {d:%b}</time></span></li>')
        weeks.append("\n".join([
            f'  <section class="week" aria-labelledby="week-{w["week"]}">',
            f'    <h3 id="week-{w["week"]}"><span class="week-n">Week {w["week"]}</span> {html.escape(w["title"])}</h3>',
            '    <ol class="episodes">', *rows, "    </ol>", "  </section>"]))
    released = sum(1 for e in episodes if e["id"] in published)
    tpl = open(os.path.join(TEMPLATES, "index.html"), encoding="utf-8").read()
    cfg = load_json(os.path.join(ROOT, "podcast.json"))
    import make_share
    make_share.home_image(os.path.join(SITE, "share", "home.png"))
    page = (tpl.replace("{{CSP}}", CSP_META).replace("{{NEXT}}", nxt)
               .replace("{{HEAD_META}}", head_meta(cfg, "The Deal Desk, Season 1", cfg["subtitle"], "", "share/home.png", ""))
               .replace("{{FOOTER}}", footer("", cfg))
               .replace("{{WEEKS}}", "\n".join(weeks)).replace("{{RELEASED_COUNT}}", str(released)))
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(page)
    nf = open(os.path.join(TEMPLATES, "404.html"), encoding="utf-8").read()
    base_path = "/" + cfg["base_url"].split("//", 1)[1].split("/", 1)[1] if cfg["base_url"].count("/") > 3 else "/"
    open(os.path.join(SITE, "404.html"), "w", encoding="utf-8").write(
        nf.replace("{{CSP}}", CSP_META).replace("{{BASE}}", base_path).replace("{{FOOTER}}", footer(base_path, cfg)))


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
      <itunes:author>{x(cfg['author'])}</itunes:author>
      <itunes:duration>{int(round(e['seconds']))}</itunes:duration>
      <itunes:season>1</itunes:season>
      <itunes:episode>{e['number']}</itunes:episode>
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:explicit>false</itunes:explicit>
      <itunes:image href="{x(base + 'cover.jpg')}"/>
      <podcast:chapters url="{x(base + 'chapters/' + e['id'] + '.json')}" type="application/json+chapters"/>
    </item>""")
    dates = [datetime.datetime.fromisoformat(published[e["id"]]) for e in episodes]
    last = f"    <lastBuildDate>{email.utils.format_datetime(max(dates))}</lastBuildDate>\n" if dates else ""
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:podcast="https://podcastindex.org/namespace/1.0">
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
    <itunes:type>serial</itunes:type>
    <copyright>{x(cfg['title'])}. {x(cfg['voice_note'])}</copyright>
{last}{chr(10).join(items)}
  </channel>
</rss>
"""
    open(os.path.join(SITE, "feed.xml"), "w", encoding="utf-8").write(feed)
    print(f"  site/feed.xml: {len(items)} episodes")


def build(drafts=False):
    published = load_json(PUBLISHED, {})
    season = load_json(SEASON_FILE)
    metas = sorted(glob.glob(os.path.join(ROOT, "audio", "episode-*.json")))
    metas = [m for m in metas if drafts or os.path.basename(m)[:-5] in published]
    nxt_episode = next_block(season, published, "../")
    episodes = [build_episode(p, published, season, nxt_episode) for p in metas]
    # Remove pages and audio of anything not built this time (e.g. a draft previewed earlier),
    # so an unpublished episode can never be committed and deployed by accident.
    keep = {e["id"] for e in episodes}
    for d in glob.glob(os.path.join(SITE, "episode-*")):
        if os.path.basename(d) not in keep:
            shutil.rmtree(d)
    for f in (glob.glob(os.path.join(SITE, "chapters", "episode-*.json")) +
              glob.glob(os.path.join(SITE, "share", "episode-*.png"))):
        if os.path.splitext(os.path.basename(f))[0] not in keep:
            os.remove(f)
    for f in glob.glob(os.path.join(SITE, "audio", "episode-*.mp3")):
        if os.path.basename(f)[:-4] not in keep:
            os.remove(f)
    build_index(episodes, published, season, next_block(season, published, ""))
    print(f"  site/index.html: Season 1, {len(episodes)} episodes built")
    build_feed([e for e in episodes if e["id"] in published], published)
    cfg = load_json(os.path.join(ROOT, "podcast.json"))
    urls = [page_url(cfg)] + [page_url(cfg, e["id"] + "/") for e in episodes if e["id"] in published]
    sitemap = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
               "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">",
               *[f"  <url><loc>{u}</loc></url>" for u in urls], "</urlset>"]
    open(os.path.join(SITE, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(sitemap) + "\n")
    open(os.path.join(SITE, "robots.txt"), "w", encoding="utf-8").write(
        "User-agent: *\nAllow: /\nSitemap: " + page_url(cfg, "sitemap.xml") + "\n")
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
