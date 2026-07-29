# Reconciliation and Recovery Reference

Use this reference for incremental updates, count mismatches, hidden or mixed media, video recovery, reorganization, and final verification.

## Contents

1. Canonical identity and schema migration
2. Complete-post inventory pitfalls
3. Video discovery and download recovery
4. Publication-time organization
5. Verification commands and count contract
6. Failure-response matrix

## 1. Canonical identity and schema migration

Treat handles as mutable aliases. A profile can have old and current handles across manifests and URLs.

- Post key: numeric status ID, independent of handle.
- Photo keys: numeric media ID and normalized `pbs.twimg.com/media/<media-key>`.
- Video keys: numeric video media ID plus parent status ID, master URL, playlist basename, and local filename.

Normalize these photo forms to the same media key:

```text
https://pbs.twimg.com/media/<key>?format=jpg&name=orig
https://pbs.twimg.com/media/<key>.jpg?name=orig
```

Do not compare exact photo URLs: path extensions, `format=`, and size parameters can differ for the same asset.

Do not assume a downloaded video filename equals its numeric media ID. `yt-dlp` can name HLS output from the master-playlist basename. Preserve an explicit media-ID → master URL → playlist basename → local-path mapping.

Before incremental work:

1. Inspect all existing manifest keys and layouts.
2. Migrate camelCase, snake_case, and older layouts into one in-memory schema.
3. Index actual local files using manifests, media keys, playlist basenames, and validated file metadata.
4. Compare current remote IDs with canonical local IDs.
5. Preserve both sides when they disagree; do not interpret `null` or a failed query as an empty archive.
6. Replace authoritative manifests only when missing and unexpected sets are zero.

## 2. Complete-post inventory pitfalls

- X virtualizes media grids; the bottom visible DOM is not the accumulated result.
- Counting the final screen or profile photo/video label undercounts files.
- One stacked-media card can hide several additional files.
- One post can mix photos and videos, so grid link type is not post classification.
- A sensitive-content cover can make a valid post look empty until `Show`/`显示` is clicked.
- Reused tabs can restore a middle scroll position; reload and return to the top.
- Long-lived tabs can lose events or stall; use a fresh navigation when needed.
- Blank or throttled status pages are unknown results, not empty posts.
- A structured-metadata batch is authoritative only when every expected status has a complete successful response.

Validate any fallback metadata source against a known multi-item post. For batches, persist per-status responses, limit concurrency, and retry only failed IDs. Never combine a partial batch into final totals.

## 3. Video discovery and download recovery

### Network discovery

- A `blob:` video source means the browser player wrapped the underlying media; observe CDP network events.
- Watch `Network.requestWillBeSent` for `video.twimg.com` requests.
- Prefer master `.m3u8` URLs containing `variant_version=1`.
- A status can emit several masters or contain several videos. Match each master to the active tile/playback route and inventory media ID.
- Record child playlist candidates when useful for diagnosis.

### Download pattern

When `ffmpeg` is installed outside `PATH`, pass its directory explicitly:

```bash
yt-dlp \
  --ffmpeg-location /path/to/ffmpeg-dir \
  -a video_m3u8_urls.txt \
  --no-playlist \
  --format "bv+ba/b" \
  --merge-output-format mp4 \
  -P .staging/videos \
  -o '%(id)s.%(ext)s' \
  --write-info-json \
  --no-warnings
```

Operational cautions:

- Do not force `best[ext=mp4]/best` on generic master playlists; it can exclude the required video/audio pair.
- Some `yt-dlp` versions reject `--retries-sleep`; use only supported retry flags.
- List mode can behave poorly on network edge cases. Use per-URL loops and start/success/failure logs when reliability matters.
- If `ffmpeg` is unavailable or undiscoverable, expect unmerged tracks or lower-quality single-stream fallbacks.
- Keep tests separate from production files so they do not inflate counts.
- Treat `.staging/images/`, `.staging/videos/`, and their `.info.json` files as temporary. Move verified media into `media/`, transfer required facts into manifests/reports, then remove `.staging/`.
- Do not leave final `images/` or `videos/` directories unless the user explicitly requested a split archive.
- Some source videos are genuinely silent. Confirm through `.info.json`, `ffprobe`, or `ffmpeg -i` before retrying.
- Treat `.part`, `.ytdl`, `.f1234.mp4`, and `.faudio-*.mp4` as interrupted or unmerged artifacts until reconciled.

## 4. Publication-time organization

Use:

```text
<YYYYMMDD_HHMMSS>_<status-id>_<zero-padded-sequence>.<ext>
```

Sorting by download or modification time separates media recovered later from files downloaded earlier. Publication time keeps every post chronologically stable.

If metadata omits publication time, derive Unix milliseconds from the X Snowflake status ID:

```javascript
(BigInt(statusId) >> 22n) + 1288834974657n
```

Convert that UTC instant to the user's timezone and record the timezone. Preserve the source media-array order across both photos and videos.

Before moving:

1. Build the entire old-path → new-path mapping.
2. Reject missing sources, duplicate sources, and target collisions.
3. Record media ID, status ID, type, time, timezone, and sequence.
4. Move transactionally when practical and roll back prior moves on failure.
5. Verify all targets before removing `.staging/`.
6. Regenerate reports containing local paths; otherwise audio and organization reports become stale.
7. Remove `.staging/` and verify that `media/` is the only final directory unless the user requested otherwise.

## 5. Verification commands and count contract

Run checks equivalent to:

```bash
find downloads/<handle>/media -maxdepth 1 -type f | wc -l
find downloads/<handle>/media -maxdepth 1 -name '*.mp4' | wc -l
find downloads/<handle>/.staging/videos -maxdepth 1 -name '*.info.json' | wc -l
du -sh downloads/<handle> downloads/<handle>/media
file downloads/<handle>/media/*
```

Require:

- image files = unique photo media IDs
- MP4 files = unique video media IDs
- final media files = unique photo IDs + unique video IDs
- exactly one final path per post-media entry
- zero missing and zero unexpected canonical IDs
- one shared timestamp/status prefix and consecutive sequence numbers per post
- `.info.json` files = videos when requested for every video
- zero partial, split-stream, orphan-audio, or test files in final counts
- no `.staging/`, `images/`, or `videos/` directory remains in the default completed archive

For audio, inspect streams with `ffprobe` or `ffmpeg -i`. Report silent-source IDs separately.

## 6. Failure-response matrix

| Signal | Required response |
|---|---|
| Chrome automation unavailable | Repair the Chrome connection before inventing unrelated browser workflows. |
| Status download misses video | Switch to CDP master-playlist discovery. |
| Valid browser image URL fails in shell | Retry the same `curl -L`-style path with required network approval. |
| Media page still adds posts | Continue cumulative scrolling until bottom plus repeated stable passes. |
| Grid and post metadata disagree | Trust validated, deduplicated per-post media IDs. |
| Article shows no media | Check and expand sensitive-content controls first. |
| Repeated navigation returns blank | Use a fresh tab or validated structured metadata; do not record an empty post. |
| Metadata batch is incomplete | Preserve per-ID successes and retry failures; never finalize the partial set. |
| Existing manifests and files disagree | Preserve both, migrate schemas, build canonical indexes, and reconcile. |
| Timestamp is absent | Derive it from the numeric Snowflake ID in the user's timezone. |
| Run was interrupted | Reconcile and remove partial artifacts before rerunning final counts. |
| Keychain prompt appears | Stop cookie extraction and use CDP/public media routes. |
