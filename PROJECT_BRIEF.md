# The Deal Desk: project brief (handoff for the terminal session)

## What it is
A daily corporate-finance podcast for the show's owner, a first-year business student preparing for London investment banking spring week interviews (corporate finance / M&A). Each episode teaches one IB concept through a real deal, drills interview questions, covers a real deal from the last 7 days, and ends with a quiz. 12 episodes are done so far (scripts are in `/scripts`). **The next one is episode 13: intro to DCF and the time value of money.**

## Goal of this phase
1. **Natural voices, fully automated and cheap:** Gemini TTS (multi-speaker) through a pay-as-you-go API key.
2. **A visual episode page** that walks the listener through the audio: a transcript synced to the audio with the current line highlighted, visuals that appear at the right moment (EV bridge waterfall, comps table, football field, deal key-numbers card), and an interactive quiz at the end.
3. **Public release:** a website on GitHub Pages plus a podcast RSS feed (for Spotify / Apple Podcasts). Label the show as AI-voiced. The owner will later add a short weekly segment in their own voice.

## Characters (fixed roles, never swapped)
- **MARCO**, the expert: Italian, eight years in mergers and acquisitions at a London bank (a made-up career; never name a real bank as his employer). He does ALL the explaining. Calm, direct, dry wit.
- **SOFIA**, the student: first year at a Milan business school, applying for spring weeks. She only asks questions, makes wrong guesses and gets corrected. In every episode she voices 3–4 of the most common pitfalls or misunderstandings.

## Script rules
- Format: `# The Deal Desk, episode NN: <title>`, then a one-line hook, then `---`, then only `MARCO:` / `SOFIA:` lines.
- Structure: cold open with a real deal story → the concept with a worked example in round numbers → "What they'll ask you" (2–3 interview questions, where Sofia answers imperfectly and Marco gives the strong answer) → deal of the day (real, announced in the last 7 days, prefer Europe) → 5-question quiz with answers → teaser for the next episode. Sunday-style review episodes come every 7th episode.
- Tone: like an FT or Bloomberg podcast. Smart, conversational, never slangy.
- Banned words and phrases: delve, dive into, tapestry, landscape, realm, navigate, crucial, pivotal, vital, robust, seamless, holistic, unlock, unleash, empower, game-changer, elevate, embark, journey, intricate, nuanced, multifaceted, "it's important/worth noting", "let's break it down", "at the end of the day", "in a nutshell", "buckle up".
- Written for the ear: numbers spelled the way they're said; no symbols ($ € % & /) and no em dashes inside dialogue; always say "mergers and acquisitions", never "M&A".
- **Verify every number and date with web search. Never invent figures.**

## Syllabus (remaining)
13 Intro to DCF and time value of money · 14 REVIEW week 2 · 15 Unlevered FCF · 16 WACC, CAPM, beta (2022 rate shock) · 17 Terminal value · 18 DCF sensitivities and traps · 19 Levered vs unlevered FCF · 20 Valuing banks and insurers · 21 REVIEW · 22 Synergies (AB InBev–SABMiller) · 23 Deal process (Musk–Twitter) · 24 Accretion/dilution · 25 Purchase price allocation and goodwill (Kraft Heinz 2019) · 26 Hostile bids (Mittal–Arcelor) · 27 IPO process (Ferrari 2015 / Arm 2023) · 28 REVIEW · 29 What an LBO is (RJR Nabisco) · 30 IRR/MOIC · 31 Debt structure · 32 Paper LBO · 33 LBOs gone wrong (Toys R Us) · 34 Italian/European deal · 35 REVIEW · 36 Talking about a deal · 37 Markets pitch · 38 Restructuring · 39 Fit questions · 40 Mental maths · 41 SHL numerical tests · 42 REVIEW + mock superday. After 42, loop at an advanced level.

## Proposed architecture
- **Repo** (GitHub): `scripts/`, `audio/`, `site/`, `pipeline/`, `.env` (gitignored).
- **Script:** written daily by Claude (by the daily job via the Claude Code CLI; see Automation below) and committed to `scripts/`. A later option is to generate it in the pipeline via the API.
- **Voices:** Gemini TTS, multi-speaker (Marco = male voice, Sofia = female voice). **Check the current Gemini docs for the latest TTS model name and the multi-speaker config.** Render each line or chunk separately and record its duration, so we get timestamps to sync the transcript and visuals. Keep Kokoro (free, local) as the fallback.
- **Hard spending cap:** count the characters sent to the API each month; above the limit (~€8 worth), stop and fall back to Kokoro. A Google Cloud budget alert at €10 sits on top, but it only alerts and does not stop spending.
- **Visual page:** a static site, with one page per episode: audio player, timestamp-synced transcript, visuals triggered by timestamps (defined in a small JSON per episode), and the quiz.
- **Publishing:** GitHub Pages plus `feed.xml` (podcast RSS). A GitHub Actions daily cron renders the audio and deploys.
- **Secrets:** the Gemini key goes in `.env` locally and in GitHub Actions secrets. Never commit it.

## Status (updated 4 October 2026)

### Done
- **Voices approved:** Marco = Gemini voice `Sadaltager`, Sofia = `Autonoe` (sample C). Marco's style prompt was revised to be "measured, informative and authoritative, like an FT or Bloomberg presenter", with a slightly deeper register; the previous "dry wit" wording made him sound flippant. Samples are in `samples/`; the latest Marco test is `samples/sample_marco_informative.wav` (awaiting the owner's sign-off).
- **TTS model:** `gemini-3.8-flash-tts` through the `/v1beta/interactions` endpoint (the current API; `speech_config` is an array for a single speaker, and audio comes back as base64 WAV at 24 kHz in `steps[].content[].data`). Override with the `TTS_MODEL` env var.
- **`pipeline/render.py`:** script → `audio/episode-NN.mp3` + `audio/episode-NN.json` (start and end time of every line). Renders line by line (single-speaker requests, 4 in parallel), trims silence, levels to −16 LUFS, MP3 at 96 kbps. Rendered lines are cached in `pipeline/cache/` (keyed on text + voice + style + model), so re-runs only pay for changed lines. ffmpeg comes from the `imageio-ffmpeg` pip package if it isn't on PATH. `--dry-run` shows the cost estimate; `--engine kokoro` forces the fallback.
- **Spending cap:** `pipeline/usage.json` logs requests, characters, tokens, audio seconds and dollars per month, using the token counts the API returns. Before rendering, the episode's cost is estimated (2.5 output tokens per character, measured at 2.25); if this month's spend plus the estimate would pass $8 (`TTS_MONTHLY_CAP_USD`), the **whole episode** is rendered with Kokoro instead (engines are never mixed within an episode). Each request also re-checks the cap. `usage.json` must be committed so the count survives across GitHub Actions runs.
- **Kokoro fallback:** built into `render.py` (same voices as `kokoro_fallback_render.py`: `bm_george` / `af_heart`). Model files live in `pipeline/models/` (gitignored, ~340 MB; download from the kokoro-onnx `model-files-v1.0` release).
- **Episode 12** rendered with Gemini: 11.1 minutes, $0.20. Rendered **before** Marco's style change, so it needs a re-render (about $0.15) once the new tone is approved.
- **Website (`site/`):** built by `pipeline/build_site.py` from `audio/episode-NN.json` + `content/episode-NN.json`. One page per episode at `site/episode-NN/index.html` (data inlined), plus `site/index.html` listing episodes. Features: custom player (±15 s, speed, keyboard shortcuts, lock-screen controls, remembers position), transcript with speaker and timestamp per line that highlights the current line and follows the audio (click a line to jump there), timed visuals in a sticky side panel (a collapsible top panel on mobile) with brass ticks on the progress bar, `#t=SECONDS` deep links, the quiz as interactive cards, and a short Sources list. Preview with `python pipeline/build_site.py --serve` → http://localhost:8000.
- **Quiz answers held back:** Marco's answer line is blurred behind a "Reveal Marco's answers" button. When playback crosses the "pause here" line, the audio stops and a Continue box appears; Continue reveals the answers and resumes. Reaching the answers by playback, or pressing "Hear Marco's answers" on the quiz cards, also reveals them. Works in background tabs and with the phone screen off. `pipeline/test_quiz_gate.py` checks all of this in headless Chrome with a fake audio clock (7 checks, all passing).
- **Visuals JSON (`content/episode-NN.json`):** each visual has an `"at"` field that quotes text from the line where it should appear (more robust than timestamps, which change on every re-render). Types: `tombstone` (deal card), `keynumbers`, `waterfall` (EV bridge), `bars` (optional `band` for a normal range), `table` (optional `highlight` row), `steps`, `formula`, `football` (mark `illustrative` when no real numbers exist), `quizcall`. `steps` items are `{ label, detail }` and render as a narrowing funnel. The quiz is `{ "pause_at": "<quote>", "answers_at": "<quote>", "questions": [{ q, options, correct, explain }] }`. Sources are `"sources": [{ label, url }]` (3–5, primary sources first). Only use figures that are in the script.
- **Design: see `DESIGN.md`** (palette, type scale, spacing, component rules; every episode follows it). Summary: Newsreader (Marco, headings, figures) + Public Sans (Sofia, interface, data, real tabular figures); light and dark themes that follow the system setting, with an Auto/Light/Dark switch; brass is the only accent; no gradients, shadows, badges, all-caps labels or entrance animations; all text meets WCAG AA in both themes. The signature element is the lucite deal tombstone. The design was audited against common AI-design tells on 4 October 2026: before/after screenshots at 1440px and 390px are in `design/screenshots/` (`before-*`, `after-light-*`, `after-dark-*`), produced by `pipeline/screenshots.py`.

### Costs to plan for
- About $0.20 per 11-minute episode until 31 December 2026; Gemini TTS prices **double on 1 January 2027** (about $0.40 per episode, roughly $12/month for a daily show, which is over the $8 cap). Options: Gemini batch tier (half price, suits the nightly cron) or `gemini-3.8-flash-lite-tts` (a third cheaper on audio).

### Next
1. The owner approves Marco's new tone → re-render episode 12.
2. Episode 13 (intro to DCF and time value of money): script, then render, visuals JSON, build.
3. Check the FinanceFeeds source link in a browser (it returns 403 to scripts, probably bot protection).
4. `feed.xml` (podcast RSS, labelled AI-voiced), then GitHub repo + Pages + Actions daily cron (Gemini key in Actions secrets; commit `usage.json` after each run).
5. Decide on line-by-line vs short multi-line chunks if the line-by-line delivery sounds stiff.
6. Audio hosting: MP3s are ~7–8 MB each, so 40+ episodes in the repo is ~300 MB; consider GitHub Releases or a storage bucket later.
