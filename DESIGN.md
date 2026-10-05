# The Deal Desk: design rules

Every episode page follows these rules. The source of truth for values is `site/assets/style.css` (tokens at the top); if you change a value there, change it here too.

The idea in one line: **a financial publication's reading page, with one object from the deal world (the lucite tombstone) as its signature.** Everything else stays quiet.

## Type

| Role | Face | Why |
|---|---|---|
| Marco's lines, headings, figures in visuals | **Newsreader** (Production Type, self-hosted from Google Fonts), weights 400/500/600, optical sizes 6–72 | Designed for reading news on screen. Its optical sizes give headlines a sharper display cut and body text sturdier forms, the job Financier does for the FT. Its figures are tabular by default, so numbers line up. |
| Sofia's lines, interface, labels, tables, notes | **Public Sans** (USWDS, self-hosted from Google Fonts), weights 400/500/600 | A neutral grotesque descended from Libre Franklin, so it belongs to the Franklin Gothic family used for newspaper data and headlines. Unlike Libre Franklin, it has real tabular figures (`tabular-nums`), which tables and the player clock need. |

Marco speaks in the serif and Sofia in the sans, so readers can tell the two voices apart at a glance. Never add a third family, and never use a monospace face for labels.

**Type scale** (tokens `--fs-*`):

| Token | Size | Use |
|---|---|---|
| `--fs-3xl` | clamp(34px, 5.2vw, 56px), line-height 1.05 | Episode title (h1) only |
| `--fs-2xl` | 28px | Section headings (Quiz) |
| `--fs-xl` | 21px | Visual titles, quiz questions, term-sheet values |
| `--fs-l` | 19px, line-height 1.6 | Marco's transcript lines (serif) |
| (fixed) | 17px, line-height 1.6 | Sofia's transcript lines (sans; looks the same size as 19px Newsreader) |
| `--fs-m` | 16px | Interface body, hook (18–21px serif), verdicts |
| `--fs-s` | 14px | Labels, buttons, table body |
| `--fs-xs` | 13px | Notes, captions, sources, gutter timestamps. Never smaller. |

Rules:
- Sentence case everywhere. **No all-caps labels** and no letter-spaced eyebrows.
- Numbers in tables, bars, term sheets and the player use `font-variant-numeric: tabular-nums`.
- Line length: transcript max 46rem (about 70–75 characters); notes and footers max 70ch.
- Approximate figures carry a small "c." before the number, never "~" in body text (a "~" is acceptable inside dense table cells).

## Colour

Both themes are first-class. **Auto** follows the system setting; the Light/Dark switch in the masthead overrides it (stored in `localStorage` as `dd-theme`, applied before first paint).

| Token | Light | Dark | Use |
|---|---|---|---|
| `--ground` | `#F4F5F2` | `#11171A` | Page background (cool paper / slate; never cream) |
| `--panel` | `#FFFFFF` | `#172024` | Visual panels, quiz cards, player |
| `--panel-2` | `#ECEEEA` | `#1C262B` | Tombstone face, hover |
| `--rule` | `#D3D8D2` | `#2A363C` | Hairlines |
| `--rule-strong` | `#A9B1AC` | `#4A585E` | Table header rules, button outlines, axes |
| `--ink` | `#15191B` | `#ECE6DA` | Primary text |
| `--ink-2` | `#364146` | `#BCC3C4` | Body text in transcript and visuals |
| `--muted` | `#566267` | `#97A3A8` | Notes, timestamps, secondary labels |
| `--accent` | `#7A5410` | `#DDB872` | Brass for text: episode number, current speaker, figure references |
| `--brass` | `#B98935` | `#B98935` | Brass for marks: tombstone frame, bars, progress ticks, play button |
| `--teal` / `--rose` | `#1E9D91` / `#CA6353` | same | Chart: additions / subtractions (waterfall), normal-range band |
| `--good` / `--bad` | `#1D7353` / `#B23F2E` | `#6CC7A3` / `#EE8A7A` | Quiz feedback text and outlines, always with words |

Contrast (WCAG 2.1, checked against ground, panel, panel-2 and the current-line tint):
- Text tokens: all ≥ 4.5:1 in both themes. The lowest is `--good` and `--bad` on the light tint, at 4.8.
- Chart marks: ≥ 3:1 against the panel in both themes.
- Chart palette (brass, teal, rose): passes the dataviz validator in both modes for lightness band, chroma, colour-blind separation (ΔE 9.5 worst pair) and normal-vision separation.

Rules:
- Brass is the only accent. **No purple, no gradients, no glows, no drop shadows.** Depth comes from hairlines and the panel/ground step only. The one inset line allowed is the tombstone's inner frame.
- Colour never carries meaning alone. Quiz states say "Your answer" and "Correct answer"; the normal-range band has a key; waterfall steps carry signed values.
- Text never takes a series colour; the coloured mark sits beside text set in an ink token.

## Spacing and shape

- Spacing scale (`--sp-*`): 4, 8, 12, 16, 24, 32, 48, 72 px. Use only these.
- Side gutter: `clamp(16px, 4vw, 40px)`; content max width 1240px.
- **One radius, `--radius: 4px`**, everywhere: panels, cards, buttons, options, tombstones, the play button and the data end of chart bars. The only circle is the scrubber's thumb, because it's a handle.
- **One set of buttons:** `.btn` (primary, brass), `.btn.ghost` (secondary, outlined) and the `.small` size. Text actions inside content, such as "Hear Marco explain this", use `.link-btn`, which looks like a link. No other button styles.
- Every element with `hidden` stays hidden: a global `[hidden] { display: none !important }` stops component display rules from overriding it.
- Borders are 1px hairlines. **Never a coloured left border** on a card, quote or line. The current transcript line is marked by a tint plus an accent speaker name and timestamp.

## Layout

- **Desktop (> 960px):** the transcript on the left (max 46rem), and a sticky visuals panel on the right (340–430px) with Previous/Next. The player is fixed at the bottom, with brass ticks where visuals appear.
- **Tablet and phone (≤ 960px):**
  - The visuals panel sticks to the top at a fixed height of min(38vh, 330px) with internal scroll, so the transcript never jumps. It has a Hide button.
  - At ≤ 600px the player wraps to two rows and the transcript gutter (speaker, time) moves above the text.
- The page must work at 390px with no horizontal scroll. Only tables may scroll sideways, inside `.tbl-wrap`.

## Components

**Transcript line.**
- Gutter: speaker name (600) and start time (tabular).
- Text: Marco in Newsreader, Sofia in Public Sans.
- Click a line to jump there.
- A line where a visual appears ends with a plain "Fig. N" reference in accent text, like a footnote marker, not a badge.

**Quiz answers.** The line(s) where Marco reads the answers are blurred, with a "Reveal Marco's answers" button. When playback crosses the end of the "pause here" line, audio stops and a Continue box appears under it; Continue reveals the answers and resumes. Reaching the answers by playback, or pressing "Hear Marco's answers", also reveals them. The check runs on `timeupdate` so it works in background tabs and with the screen off. Tested by `pipeline/test_quiz_gate.py`.

**Visuals** (defined in `content/episode-NN.json`, anchored with `"at"`: a quote from the line where the visual appears):

| Type | Looks like | Use for |
|---|---|---|
| `tombstone` | Centred deal toy: brass frame with inner rule, italic kicker, serif name, short brass rule, details, date | Introducing a deal (cold open, deal of the day). The signature element: max two per episode. |
| `keynumbers` (2+ items) | A term sheet: label left, serif value right, hairline between rows | A deal's headline numbers. Never a grid of stat tiles. |
| `keynumbers` (1 item) | A pulled figure: large serif number beside its sentence-case caption, rule above | One number the listener must remember |
| `waterfall` | Columns with dashed connectors, brass totals, teal additions, rose subtractions, signed values on top | EV bridges, any build-up from one total to another |
| `bars` | Labelled horizontal bars, value at the right, optional dashed teal `band` with a key | Comparing 2–5 values (premiums, multiples) |
| `table` | Ruled table, tabular figures, optional highlighted row with a plain-text note ("median") | Comps, worked examples, before/after |
| `steps` | A funnel: grey bars narrowing to one brass bar, each with a bold label and one-line detail | A process that narrows to a result. Not numbered cards. |
| `formula` | The formula centred between two rules | One formula |
| `football` | Floating range bars and an offer-price line | Valuation summaries. If the episode has no real numbers, set `"illustrative": true` and put "(illustrative)" in the title. |
| `quizcall` | A sentence and a "Go to the quiz" button | The moment the quiz starts |

Only use figures that appear in the episode script; derived numbers (such as the waterfall's middle step) must be explained in the note.

**Quiz.**
- **Layout:** one question at a time, with "Question N of 5" beside the heading.
- **Options:** four full-width options in one column, top-aligned, each starting with a letter chip (A–D). They're shuffled on every page load, and the answer is stored by option id.
- **After answering:**
  - the right answer's letter chip is filled in `--good` and its text goes bold;
  - a wrong pick is outlined in `--bad`, with its chip filled and its text struck through;
  - the other options are dimmed with `--muted`, never opacity, so they still pass contrast.

  No feedback text ever goes inside an option.
- **Feedback** sits below the options in an `aria-live` region:
  - "Correct" or "Not quite" (the latter naming the right letter);
  - a one-or-two-sentence explanation;
  - "Hear Marco explain this", which jumps the audio to the transcript line in the question's `explain_at`.
- **End screen:**
  - "You scored X of 5";
  - each missed question with its answer, explanation and a "Hear Marco explain this" button;
  - "Retry the ones I missed" (or "Start again" if none were missed);
  - a link to the next episode (or the Season 1 page's next block if it isn't out yet).
- **Keyboard and screen readers:**
  - options are a `role="radiogroup"` of `role="radio"` buttons with a roving tab stop;
  - the arrow keys move focus without answering;
  - 1–4 or A–D answer;
  - Enter goes to the next question;
  - focus moves to "Next question" after answering, and to the score at the end.
- **Questions** must pass `pipeline/check_quiz.py`. The daily job runs it.
  - The wrong options are real mistakes, ideally Sofia's.
  - The right one is no longer or more specific than the others.
  - Its position varies across questions.
  - No "all/none of the above", no absolute wording in wrong options, and every question has an explanation and a valid `explain_at`.

**Player.**
- −15 / play / +15, the scrubber, the time and the speed, which cycles 0.75 → 1 → 1.25 → 1.5 → 2 and is remembered.
- The listening position is remembered per episode in `localStorage` (wrapped in try/catch). A `#t=SECONDS` link overrides it.
- **Keys:** Space plays and pauses; ← and → move 15 s. They're ignored while typing or inside the quiz, which has its own keys.
- **Chapter markers** on the scrubber, as 24×24 px buttons: cold open (or introduction), the concept (or the review), what they'll ask you, deal of the day, quiz. Click to jump.
  - The concept's start is anchored by `chapters.concept_at` in the content file; the rest come from the script's own signposts.
  - The same chapters are published as Podcasting 2.0 JSON (`site/chapters/`) and linked from the feed with `<podcast:chapters>`.
- **Visual ticks:** brass ticks mark where visuals appear.
- **Download:** a "Download MP3 (N MB)" link sits in the episode's facts line.
- **Errors:** if the audio fails to load, a message appears above the controls with a download link, and play is disabled.

**Every page.**
- **Head:**
  - a unique `<title>` ("Episode N: Title | The Deal Desk") and meta description (the hook);
  - a canonical URL;
  - Open Graph and Twitter tags with a 1200×630 share image (`site/share/`, drawn by `pipeline/make_share.py` in the cover's tombstone style: show name, episode number, title);
  - the favicons (`favicon.svg`, plus a 180 px `apple-touch-icon.png`);
  - preloads for the two main fonts.
- **Footer:**
  - About: one paragraph, including the AI-voiced disclosure;
  - Subscribe: the RSS feed now, and Spotify and Apple Podcasts automatically once `spotify_url` / `apple_url` are set in `podcast.json`;
  - the copyright line.
- `404.html`, `robots.txt` and `sitemap.xml` are built with the site.
- No layout shift: fixed sizes on the share and icon images, the SVG icon and the mobile visual panel; fonts self-hosted, preloaded, with `font-display: swap`. Lighthouse (mobile) on 5 Oct 2026, both home and an episode page: Performance 98, Accessibility 100, Best Practices 100, SEO 100, layout shift 0.

**Sources.** At the bottom of every episode: 3–5 plain links (13px, `--ink-2` link colour), read from `"sources"` in the content JSON. They're the primary sources for the deal figures; prefer the company announcement (RNS or press release) first.

**Season 1 page (home).**
- Shows "Season 1" with "X of 42 released", the Next episode block, then six weeks, each with a small "Week N" label above its serif title.
- Each row has the number, the title and, on the right, the duration (released) or the release date (upcoming).
- Released rows link to their episode page; upcoming rows are plain text in `--ink-2` and aren't clickable.
- Review episodes carry an italic "Review" in accent text after the title. That's text, not a badge.
- Titles and teasers come from `content/season-1.json`. Released episodes use the title from their script.

**Next episode block.**
- A `<details>` box with the episode number, its title and a one-line teaser. It sits on the home page and at the end of every episode page.
- Opening it shows the release time, 07:30 Europe/Rome on start date + N days, converted to the viewer's local time, with a live countdown (`assets/next.js`).
- At zero it says "Publishing now, refresh in a few minutes". More than three hours late, it says "Running late today".
- Without JavaScript it shows the date and Rome time as plain text.

## Security rules for the front end

- **No third-party requests.** Fonts are self-hosted in `site/assets/fonts/` (with their licences). There's no analytics, and no external scripts, styles or images. External links are plain `<a>` links only (sources).
- **Content-Security-Policy** on every page: `default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; media-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; object-src 'none'`.
  - No inline `<script>` code. The theme is applied before paint by the external `assets/theme-init.js`. The episode data lives in a `type="application/json"` block, which isn't executed.
  - No inline `style=""` attributes. Visuals write positions as `data-css` and `applyCss()` applies them through the CSSOM, which the policy allows.

## Motion

- No entrance animations, no bounces, no hover lifts.
- The only motion: the transcript follows the audio with a smooth scroll (instant when the system asks for reduced motion), and colour changes on hover.

## Words

- Buttons say what happens: "Reveal Marco's answers", "Continue", "Next question", "See your score", "Hear Marco explain this", "Retry the ones I missed", "Follow the audio", "Download MP3".
- Sentence case everywhere, including buttons and headings.
- Banned in the interface as in the scripts: unlock, dive in, elevate, seamless, empower, journey, game-changer, and friends. No emoji, no sparkle icons, no "→" on links.
- Always label the show as AI-voiced (the masthead and the footer).

## Checking a new episode

1. `python pipeline/build_site.py --serve`
2. `python pipeline/test_quiz_gate.py episode-NN` and `python pipeline/test_page_ui.py episode-NN`: all checks must pass.
3. `python pipeline/check_sync.py NN --browser`: line starts verified in the audio, visuals on their lines.
4. `python pipeline/check_quiz.py NN`: no flags.
5. `python pipeline/screenshots.py check --theme light` and `--theme dark`, then look at the desktop and 390px images for overlap, clipped labels and horizontal scroll.
