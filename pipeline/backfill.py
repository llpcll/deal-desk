#!/usr/bin/env python3
"""Season 1 backfill: render episodes from existing scripts and mark them published
with their original release dates. Gemini only (every Season 1 episode must sound the
same), so no Kokoro fallback: if the monthly cap would be passed, it stops.

    python pipeline/backfill.py --first         # episode 1 only, to check end to end
    python pipeline/backfill.py                 # the rest, in order; resumable
    python pipeline/backfill.py --episodes 12   # e.g. re-render episode 12 in the current voice

Holds the repo lock while running. Keeps --reserve requests of Gemini's daily limit
free for the 6:45 episode. If the daily limit is reached it stops (exit code 75);
running it again the next day carries on where it left off, since rendered chunks
are cached. It doesn't commit or push: the daily job publishes.
"""
import argparse, datetime, glob, json, os, subprocess, sys, zoneinfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import build_site, daily, repolock  # noqa: E402
from render import VOICE_VERSION  # noqa: E402

ROME = zoneinfo.ZoneInfo("Europe/Rome")


def original_release(n):
    season = build_site.load_json(build_site.SEASON_FILE)
    d = datetime.date.fromisoformat(season["start"]) + datetime.timedelta(days=n)
    return datetime.datetime(d.year, d.month, d.day, 7, 0, tzinfo=ROME).isoformat()


def up_to_date(ep_id):
    meta = build_site.load_json(os.path.join(ROOT, "audio", ep_id + ".json"))
    return bool(meta) and meta.get("engine") == "gemini" and meta.get("voice_version") == VOICE_VERSION


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", action="store_true", help="episode 1 only")
    ap.add_argument("--episodes", default="1-11", help="e.g. 1-11 or 12 or 1,3,5")
    ap.add_argument("--reserve", type=int, default=20, help="daily requests kept free for the 6:45 job")
    args = ap.parse_args()
    nums = [1] if args.first else sorted({n for part in args.episodes.split(",")
                                          for n in (range(int(part.split("-")[0]), int(part.split("-")[-1]) + 1))})
    with repolock.hold("backfill", wait_minutes=0):
        for n in nums:
            ep_id = f"episode-{n:02d}"
            if up_to_date(ep_id) and ep_id in build_site.load_json(build_site.PUBLISHED, {}):
                print(f"{ep_id}: already rendered in the current voice"); continue
            script, content = daily.episode_files(n)
            problems = daily.check_episode(script, content)
            if problems:
                print(f"{ep_id}: fails the checks, stopping:\n  " + "\n  ".join(problems)); return 1
            code = subprocess.run([sys.executable, os.path.join(ROOT, "pipeline", "render.py"), script,
                                   "--engine", "gemini", "--reserve", str(args.reserve)], cwd=ROOT).returncode
            if code:
                print(f"{ep_id}: render stopped (exit {code})" +
                      (", daily limit reached: run again after the reset (midnight Pacific, 09:00 in Rome)" if code == 75 else ""))
                return code
            published = build_site.load_json(build_site.PUBLISHED, {})
            published[ep_id] = original_release(n)
            json.dump(dict(sorted(published.items())), open(build_site.PUBLISHED, "w", encoding="utf-8"), indent=2)
            build_site.build()
            print(f"{ep_id}: rendered and marked released on {published[ep_id]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
