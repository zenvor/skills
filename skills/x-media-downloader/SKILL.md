---
name: x-media-downloader
description: Reliably download and organize every image and video from an X/Twitter profile, including hidden media in multi-item posts. Use whenever the user asks to archive media from an X handle, profile, or `/media` page, especially when X uses lazy loading, stacked-media cards, sensitive-content covers, blob video playback, or when the archive must keep each post's photos and videos adjacent in chronological order.
license: MIT. See LICENSE.txt
---

# X Media Downloader

Archive an X/Twitter media tab into a reproducible local folder without exporting raw browser cookies.

## Requirements and use boundaries

- Require network access to X and its media hosts.
- Use a browser automation capability when authenticated, sensitive, virtualized, or hidden media must be inspected.
- Require `yt-dlp` for video downloads and `ffmpeg`/`ffprobe` for stream merging and audio verification.
- Archive only media the user is authorized to access and copy. Follow applicable law and service terms; do not bypass private-account restrictions, paywalls, or technical access controls.
- Treat the MIT license as applying to this Skill's files only, not to media downloaded from X.

## Required reading

Read [references/reconciliation-and-recovery.md](references/reconciliation-and-recovery.md) when any of these applies:

- updating or repairing an existing archive
- grid counts disagree with downloaded files or manifests
- a post contains stacked, mixed, sensitive, or multiple video media
- direct video discovery or download fails
- files must be renamed, moved, or reorganized

That reference contains canonical identity rules, known failure modes, recovery paths, timestamp derivation, and verification commands. Treat its safeguards as part of this workflow, not optional background.

## Core invariants

1. Separate discovery from download.
2. Use the media grid only to discover posts; never treat card count as file count.
3. Expand every discovered post and use its ordered, deduplicated media array as the inventory contract.
4. Identify posts and media canonically; handles and URL spellings are mutable aliases.
5. Reconcile manifests and actual files before incremental downloads or authoritative manifest replacement.
6. Verify every expected media ID maps to exactly one valid final file.
7. Name final files from post publication time and in-post order so one post's photos and videos remain adjacent.

## Inputs and identity

Accept a handle, profile URL, or `/media` URL and normalize it to:

```text
https://x.com/<handle>/media
```

Use numeric status IDs as stable post identity. Preserve old and current handle variants only for navigation and display. Use media IDs plus the canonical keys defined in the reference for file reconciliation.

## Output layout

Use the requested destination, or a clearly named workspace directory. By default, the completed archive must contain exactly one media directory, `media/`:

```text
downloads/<handle>/
  media_manifest.json
  post_media_manifest.json
  organization_manifest.json
  image_urls.txt
  video_urls.txt
  video_m3u8_manifest.json
  video_m3u8_urls.txt
  media/
```

During downloading, use `downloads/<handle>/.staging/images/` and `.staging/videos/` when separate work areas are needed. Treat `.staging/` as transient: remove it after successful organization and verification. Do not leave final `images/` or `videos/` directories. Create another persistent directory only when the user explicitly requests raw sidecar metadata or a split layout.

## Workflow

### 1. Discover every post cumulatively

- Prefer Chrome automation when a logged-in session is useful.
- Open a fresh `/media` tab when reused tabs are blank, paused, stale, or restored mid-page. Otherwise reload and explicitly return to the top.
- On every scroll pass, accumulate unique status links and `pbs.twimg.com/media/` URLs outside the currently visible DOM.
- Stop only at the bottom after 4–6 consecutive passes add nothing.
- Exclude avatars, banners, emoji SVGs, ads, recommendations, and `amplify_video_thumb` thumbnails.
- Save an initial discovery manifest containing the source page, handle, collection time, unique status URLs, and grid-visible photo/video/image observations.

X virtualizes the grid and unloads old nodes. A stacked-media card hides additional files, and a card labelled as photo or video may belong to a mixed-media post. Therefore accumulated grid totals are discovery diagnostics only.

### 2. Expand posts into the authoritative inventory

Resolve every discovered status ID to its complete ordered media array before downloading.

Use this order:

1. Read complete structured post metadata already exposed by the page or network layer.
2. Otherwise open the status page, select the exact target article, and enumerate all of its photos and videos.
3. Expand a sensitive-content `Show`/`显示` control and verify the media rendered before extraction.
4. If navigation becomes blank or throttled, use an allowed public structured metadata source and validate it against a known multi-item post.

For large metadata batches, use bounded parallelism, persist results per status ID, compare successful responses with expected posts, and retry only failures. Never merge a partial batch into the authoritative manifest.

Write `post_media_manifest.json` with one entry per post:

- numeric status ID and source URL
- publication time and sensitive-content state when available
- ordered media entries containing media ID, type, original URL, dimensions, and duration when available

Deduplicate by media ID, preserve source-array order, and calculate unique post, photo, video, total-media, and video-post counts from this manifest.

### 3. Reconcile incremental runs

Rebuild the current complete inventory first. Then compare it with both existing manifests and actual files; an earlier run may have downloaded files without updating metadata.

- Inspect and migrate old manifest schemas into one canonical in-memory schema.
- Normalize photo URLs and video mappings according to the reference.
- Compute missing and unexpected sets by canonical media identity, never by count differences or literal status URLs.
- Download only missing media IDs.
- Replace authoritative manifests only after missing and unexpected counts are both zero.

### 4. Download original images

Unless the user requested videos only:

- keep only `pbs.twimg.com/media/` assets from the authoritative inventory
- request original quality with `name=orig`
- preserve the declared image format as the extension when possible
- use deterministic names such as `.staging/images/001_<media-id>.jpg` while staging

If an allowed direct download fails because network access is sandboxed, request approval and rerun the same path rather than changing identity logic.

### 5. Discover every video source

Try direct `yt-dlp` on public status URLs when reliable. Otherwise use Chrome CDP network observation:

- process every video media ID, including multiple videos under one status
- open the exact status/media item and reload or start playback if necessary
- collect `video.twimg.com` network requests
- prefer matching master `.m3u8` URLs with `variant_version=1`
- when several masters appear, match the candidate to the current media item instead of taking the first
- treat a DOM `blob:` `currentSrc` as a signal to use the network layer, not as missing media

Save explicit media-ID → status → master URL → local-path mappings in `video_m3u8_manifest.json`, plus master URLs in `video_m3u8_urls.txt`.

### 6. Download and merge videos

Download discovered master playlists directly with `yt-dlp`. Explicitly provide `ffmpeg`'s directory when it is installed but absent from `PATH`, and prefer `--format "bv+ba/b"` plus `--merge-output-format mp4`.

- Do not force an MP4-only selector on generic Twitter master playlists.
- Log start/success/failure per URL so one failure does not hide batch progress.
- Download into `.staging/videos/` and keep test downloads outside the archive.
- Preserve `.info.json` temporarily when required for mapping and audio diagnosis; retain it after delivery only if the user requested raw sidecar metadata.
- Reconcile split streams and partial artifacts before final counts.

See the reference for the command pattern and version-specific pitfalls.

### 7. Organize all media by post

Unless the user requests another layout, put final photos and videos together in `media/`:

```text
<YYYYMMDD_HHMMSS>_<status-id>_<in-post-sequence>.<ext>
```

Rules:

- derive the timestamp from post publication time, never download or modification time
- use the user's timezone and record it in `organization_manifest.json`
- derive missing timestamps from the numeric X Snowflake status ID as documented in the reference
- preserve the post's media-array order and zero-pad sequence numbers
- give every item from the same post the same timestamp/status prefix
- preflight missing sources, duplicate sources, and target-name collisions
- move transactionally when practical and roll back completed moves if one rename fails
- verify new paths before removing staging directories
- regenerate every report or manifest containing local filenames after renaming
- remove `.staging/` after final-path verification; the default completed archive must not contain `images/` or `videos/`

Record old path, new path, status ID, media ID, type, publication time, and sequence in `organization_manifest.json`.

### 8. Verify by identity, count, and file integrity

Do not report success until all of these hold:

- image count equals unique photo media-ID count
- MP4 count equals unique video media-ID count
- total final files equal all unique media IDs
- every post-media entry maps to exactly one valid file
- canonical local IDs have zero missing and zero unexpected entries
- same-post files share one prefix and consecutive sequence numbers
- temporary `.info.json` count equals video count when requested for every video, before staging cleanup
- no `.part`, `.ytdl`, split-stream, orphan-audio, or test artifacts pollute final counts

Inspect file types and sizes, not filenames alone. Use the verification commands in the reference.

### 9. Verify audio when expected

Use `ffprobe` or `ffmpeg -i` to inspect audio streams. If metadata reports `acodec: none` or probing reports no audio, classify it as a silent source rather than a merge failure. Record silent-source IDs in `audio_check_report.txt` and avoid endless retries.

For mixed-media runs, report image URL/file counts, video/MP4 counts, and requested `.info.json` counts separately.

### 10. Deliver only after verification

- Move or copy only after all reconciliation checks pass.
- Ask for approval before writing outside the workspace or performing unrequested destructive cleanup.
- Recheck destination counts after moving.
- Remove the transient `.staging/` tree after successful final verification; this cleanup is part of the default workflow.
- Confirm that `media/` is the only directory in the completed account archive unless the user explicitly requested another persistent layout.

## Safety constraints

- Never print, copy, save, inspect, or export raw browser cookie values.
- Prefer CDP network observation and public media URLs over cookie extraction.
- Do not default to `yt-dlp --cookies-from-browser chrome`; it can trigger a macOS keychain prompt.
- Preserve conflicting manifests and files until canonical reconciliation determines the correct state.
- Do not classify blank/throttled pages as empty posts.

## Completion checklist

- cumulative top-to-bottom discovery stabilized
- every discovered post expanded into an ordered media inventory
- required discovery, post-media, image, video, and organization manifests exist for the paths used
- photo, video, and total counts reconcile by canonical ID
- every expected media entry maps to exactly one final file
- same-post photos and videos are adjacent under name sorting
- partial artifacts are absent and silent-source videos are documented
- `.staging/`, `images/`, and `videos/` are absent from the completed default archive
