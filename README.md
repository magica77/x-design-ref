# Design Refs — X inspiration library

A local, git-tracked catalog of design references collected from X (Twitter) posts, covering
**infographics, animated websites, product launch/intro videos and app intro/demo videos**, plus a static
browser (`index.html`). The gold-standard example is the
[Excalidraw CLI intro](https://x.com/excalidraw/status/2108249557519970369).

Open `index.html` directly (`file://` works because the catalog is embedded at build time).

```
design-refs/
├── index.html                 # generated navigator (don't edit; edit scripts/template.html)
├── preview.png                # headless render of index.html (also preview-dark.png, preview-detail.png)
├── data/
│   ├── refs.json              # THE catalog (source of truth)
│   ├── state.json             # last_run, per-run log, total_entries, newest_post_id
│   ├── candidates/            # one JSON per run (curated candidates fed to ingest.py)
│   └── raw/<date>/            # raw MCP responses kept for provenance (posts, replies)
├── shots/<post_id>.png        # screenshot of the post (official embed render)
├── thumbs/<post_id>.jpg       # card thumbnail: frame ~40% into the video, or the attached image
└── scripts/
    ├── queries.json           # the daily X searches + field lists
    ├── mcp_to_candidates.py   # raw MCP result files -> candidate stubs (filters >50K, dedupes)
    ├── ingest.py              # candidates -> refs.json (+ screenshots, thumbs, state, index.html)
    ├── screenshot.py          # embed -> iframe -> media-preview fallback chain
    ├── build_index.py         # refs.json + template.html -> index.html
    ├── template.html          # the UI (vanilla JS/CSS)
    └── preview.py             # renders preview*.png for visual QA
```

## Catalog entry (data/refs.json)

| field | meaning |
|---|---|
| `id`, `url` | X post id and link |
| `author.handle`, `author.name` | from the X user expansion |
| `created_at`, `collected_at` | post time / when we added it (UTC ISO) |
| `category` | exactly one of `Infographic`, `Animated Website`, `Product Intro`, `App Intro` |
| `tags` | the post's **real X hashtags**, lowercased |
| `derived_tags` | only when the post has no hashtags: 1-3 tags **we** chose (shown dashed in the UI) |
| `description` | 1-2 sentences: what it shows and why it's a good reference |
| `text` | full post text (note_tweet when long) |
| `metrics` | impressions, likes, reposts, replies, quotes, bookmarks (from X `public_metrics`), `metrics_updated_at` |
| `media_type`, `media` | `video` / `gif` / `image`; media URLs (preview, mp4 variant) |
| `replies_summary`, `notable_replies` | summary of top replies (and quote posts) + 2-3 short quotes with handles |
| `screenshot`, `screenshot_method`, `thumbnail` | `shots/<id>.png`, which method worked, `thumbs/<id>.jpg` |
| `gold_standard` | `true` only for the Excalidraw entry (pinned + gold ribbon in the UI) |

## Daily run (exact procedure)

X reads go through the MCP namespace `x` (not callable from a plain script), so the run is split:
**agent does the X calls → writes files → `ingest.py` does everything else.**
Budget: 30 calls/min, 1000/day. A normal daily run is about 8 searches + 1 reply search per new keeper + 1
`get_posts_by_ids` (optional), so typically 15-25 calls.

1. **Read state.** Get `last_run` from `data/state.json`. Set `SINCE = last_run - 1 day` (UTC, ISO-8601).
2. **Search.** For each entry in `scripts/queries.json → queries`, call
   `CallDynamicTool(namespace="x", toolName="search_posts_all", arguments={query, ...common_args, start_time: SINCE}, write_to_file=true)`.
   The queries are:
   - Infographic: `(from:VisualCap OR from:VoronoiApp OR from:OurWorldInData OR from:simongerman600 OR from:infobeautiful OR from:BrilliantMaps OR from:MaxCRoser OR from:StatistaCharts) has:images -is:retweet -is:reply`
   - Infographic: `(infographic OR dataviz OR "data visualization" OR #infographic OR #dataviz) has:media -is:retweet -is:reply lang:en`
   - Animated Website: `(from:awwwards OR from:framer OR from:webflow OR from:rive_app OR from:splinetool OR from:codrops OR from:greensock OR from:threejs OR from:jh3yy OR from:emilkowalski OR from:raunofreiberg OR from:rauchg OR from:mattgperry OR from:joshwcomeau) has:videos -is:retweet -is:reply`
   - Animated Website: `("scroll animation" OR webgl OR three.js OR awwwards OR gsap OR "landing page" OR #webdesign OR #motiondesign) has:videos -is:retweet -is:reply lang:en`
   - Product Intro: `(from:figma OR from:linear OR from:vercel OR from:raycastapp OR from:NotionHQ OR from:stripe OR from:github OR from:cursor_ai OR from:perplexity_ai OR from:OpenAI OR from:AnthropicAI OR from:tldraw OR from:supabase OR from:Replit OR from:excalidraw) has:videos -is:retweet -is:reply`
   - Product Intro: `(introducing OR "launch video" OR "today we're launching" OR "we just launched") has:videos -is:retweet -is:reply lang:en`
   - App Intro: `(from:warpdotdev OR from:zeddotdev OR from:obsdmd OR from:screenstudio OR from:CleanShotApp OR from:mymind OR from:CapacitiesHQ OR from:Superhuman OR from:browsercompany OR from:granola_ai OR from:shadcn OR from:Readwise) has:videos -is:retweet -is:reply`
   - App Intro: `("now available" OR "is here" OR "available today" OR "app demo" OR onboarding) (app OR CLI OR desktop OR iOS) has:videos -is:retweet -is:reply lang:en`

   Copy the result files into `data/raw/<YYYY-MM-DD>/`.
   (X search has **no** engagement operator: `min_faves` is silently dropped, so the threshold is applied locally.)
3. **Make stubs (threshold + dedupe):**
   ```bash
   cd /workspace/design-refs
   python3 scripts/mcp_to_candidates.py data/raw/$(date +%F)/*.txt -o data/candidates/$(date +%F).json
   ```
   This keeps only originals with **impression_count > 50,000**, drops ids already in `refs.json`, and de-dupes.
4. **Curate (agent).** For each stub, delete it if it isn't design-relevant (memes, politics, crypto shilling,
   events/merch with no design value). Then fill in `category`, `description` (1-2 sentences), and
   `derived_tags` (only if `hashtags` is empty). Fetch top replies with
   `search_posts_all(query="conversation_id:<ID> -from:<author>", sort_order="relevancy", max_results=15)`
   and write `replies_summary` (2-4 sentences) and 2-3 `notable_replies` `{handle, text}` quoted verbatim.
   Never invent metrics or replies. If none come back, say so in `replies_summary`.
5. **Ingest + rebuild:**
   ```bash
   python3 scripts/ingest.py data/candidates/$(date +%F).json   # dedupe, >50K check, shots, thumbs, state, index.html
   python3 scripts/preview.py                                   # optional visual QA -> preview*.png
   git add -A && git commit -m "daily: $(date +%F) +N refs"
   ```
   `ingest.py` skips ids already in the catalog and rejects stubs still marked `TODO`. It only screenshots new
   entries, appends to `refs.json`, writes `data/state.json` (`last_run`, run log), and rebuilds `index.html`.
   Flags: `--update-existing` (refresh metrics for known ids from a fresh `get_posts_by_ids`), `--no-shots`,
   `--dry-run`, `--min-impressions N`.

Other commands: `python3 scripts/build_index.py` (rebuild HTML only) and `python3 scripts/screenshot.py ID…`
(re-shoot specific posts).

## Screenshots

`screenshot.py` uses headless Chromium (Playwright; `pip install --break-system-packages playwright && python3 -m playwright install chromium`).
It never logs in and uses no credentials. The methods, in order:
1. **embed** (used for all 26 seed entries): a temp HTML page with the official
   `<blockquote class="twitter-tweet">` + `platform.twitter.com/widgets.js`. It waits for the iframe and images, then
   screenshots the iframe at 2x.
2. **iframe**: `https://platform.twitter.com/embed/Tweet.html?id=ID`.
3. **media**: downloads `preview_image_url`/`url` from the media expansion.

The embed shows video posts as a play-button poster, which is sometimes blank (Excalidraw's poster is pure white).
So the cards use `thumbs/<id>.jpg`, a real frame grabbed with ffmpeg ~40% into the public mp4 (or the attached image).
