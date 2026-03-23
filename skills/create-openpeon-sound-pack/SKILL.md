---
name: create-openpeon-sound-pack
description: Creates and publishes CESP v1.0 compatible sound packs for peon-ping. ALWAYS use this skill when the user wants to create a new voice pack, build a sound pack, package audio for peon-ping, submit to the OpenPeon registry, or mentions peon sound pack, CESP categories, openpeon.json, or peon registry PR — even if they only mention part of the process.
compatibility: Requires ffmpeg, python3, and gh (GitHub CLI) with authentication (run `gh auth login` first)
---

# Creating a peon-ping Sound Pack

Guide for creating and publishing CESP v1.0 compatible sound packs for peon-ping.

CESP defines a universal format for sound packs that respond to coding events in agentic IDEs. A single pack works across Claude Code, Cursor, Codex, and any tool that implements the specification. The spec covers three things: a set of event categories that IDEs emit, a manifest format (openpeon.json) that maps categories to audio files, and player behavior requirements for how sounds should be played. For the full specification (including JSON schema), see [references/cesp-v1.md](references/cesp-v1.md).

## Workflow

Progress:
- [ ] Step 1: Prepare audio files
- [ ] Step 2: Create directory structure
- [ ] Step 3: Pre-check audio quality
- [ ] Step 4: Map sounds to CESP categories
- [ ] Step 5: Normalize file names
- [ ] Step 6: Generate openpeon.json manifest
- [ ] Step 7: Create README, LICENSE, .gitignore
- [ ] Step 8: Push to GitHub with version tag
- [ ] Step 9: Submit registry PR

## Step 1: Prepare audio files

Copy source audio files to a `sounds/` directory. **Always copy files with their original names first**, then rename later. Changing names during copy makes it impossible to verify against source files.

Supported formats: `.wav`, `.mp3`, `.ogg`. Ideal clip duration: 1-5 seconds.

## Step 2: Create directory structure

```
my-pack/
  openpeon.json
  sounds/
    file1.wav
    file2.wav
  README.md
  LICENSE
  .gitignore
```

## Step 3: Pre-check audio quality

**This step is critical. The registry CI will reject your pack if quality checks fail.**

Use ffmpeg silencedetect to scan all files and flag any exceeding the thresholds below:

```bash
for f in sounds/*; do
  echo "=== $f ===";
  ffmpeg -i "$f" -af silencedetect=noise=-35dB:d=0.05 -f null - 2>&1 | grep -E "silence_(start|end|duration)";
done
```

### CI Quality Thresholds

| Check | Block (must fix) | Warn |
|---|---|---|
| Dead air at start | > 2000 ms | > 500 ms |
| Dead air at end | > 2000 ms | > 500 ms |
| Volume (true peak) | -- | >= -0.5 dBTP |
| Loudness (LUFS) | < -70.0 | < -35.0 or > -8.0 |
| Sample rate | < 8000 Hz | < 16000 Hz |
| Duration | > 20s or < 0.1s | > 5.0s |
| File size | -- | -- |
| Bitrate (lossy only) | -- | < 64 kbps |

**Size limits:** Max 1 MB per file, 50 MB total pack size.

### Trimming trailing silence

If any files exceed the block threshold (> 2000ms), trim trailing silence. Keep about 1900ms of silence as a safety margin -- close enough to sound natural but safely under the 2000ms block limit.

## Step 4: Map sounds to CESP categories

All 9 CESP event categories. The first 6 are **core** (required for coverage check):

| Category | Trigger | Min |
|---|---|---|
| `session.start` | Session opens | 1 |
| `task.acknowledge` | AI accepts task | 1 |
| `task.complete` | Task finished | 1 |
| `task.error` | Something failed | 1 |
| `input.required` | Waiting for input | 1 |
| `resource.limit` | Rate limit hit | 1 |
| `user.spam` | Too many messages | 0 |
| `task.progress` | Long task running | 0 |
| `session.end` | Session closes | 0 |

Aim for 2-3+ sounds per category for variety.

## Step 5: Normalize file names

File names must match `[a-zA-Z0-9._-]+` -- no spaces, no Unicode.

Recommended: English kebab-case (e.g., `welcome-to-kings-canyon.wav`).

**After renaming files, verify every `file` field in openpeon.json points to an existing file.** This is a common mistake -- updating the manifest without renaming actual files, or vice versa.

## Step 6: Generate openpeon.json manifest

**Required fields** (cesp_version, name, display_name, version, categories) + **recommended fields** (author, license, language, description):

Field constraints: `name` must be a-z0-9, hyphens, underscores only — no uppercase; `display_name` max 128 chars; `description` max 256 chars.

```json
{
  "cesp_version": "1.0",
  "name": "pack_name",
  "display_name": "Pack Display Name",
  "version": "1.0.0",
  "description": "Brief description",
  "author": { "name": "your_name", "github": "your_github" },
  "license": "MIT",
  "language": "en",
  "categories": {
    "session.start": {
      "sounds": [
        { "file": "sounds/file.wav", "label": "description", "sha256": "..." }
      ]
    }
  }
}
```

Generate SHA256 for each sound file:

```bash
shasum -a 256 sounds/*
```

Use a script to generate the full manifest to avoid JSON errors (trailing commas, etc). **Never manually edit large JSON arrays** -- use `python3 -c` or a script instead.

## Step 7: Create project files

- **README.md**: Pack description, install commands, sound map table, sources, license
- **LICENSE**: MIT or appropriate license
- **.gitignore**: `.DS_Store`, `*.tmp`

Install commands format:
```bash
peon packs install <pack_name>
peon packs use <pack_name>
```

## Step 8: Push to GitHub

Repo naming convention: `<username>/openpeon-<pack-name>` (e.g., `yourname/openpeon-my-pack`).

```bash
git init && git add -A
git commit -m "feat: <Pack Name> voice pack for peon-ping"
gh repo create openpeon-<pack-name> --public --description "<description>" --source . --push
git tag v1.0.0 && git push origin v1.0.0
```

## Step 9: Submit registry PR

1. Fork `PeonPing/registry` (if not already forked): `gh repo fork PeonPing/registry --clone`
2. If already forked and cloned, sync and pull latest:

```bash
gh repo sync <user>/registry --source PeonPing/registry
cd registry
git pull
```

3. Create a branch:

```bash
git checkout -b add-<pack-name>
```

4. Compute registry entry values (run from the **pack directory**, not the registry directory):

```bash
# manifest_sha256 — hash of openpeon.json
shasum -a 256 openpeon.json

# sound_count — number of audio files
ls sounds/ | wc -l

# total_size_bytes — total pack size in bytes (Linux)
du -sb . | cut -f1
# or on macOS:
find . -type f | xargs stat -f%z | awk '{s+=$1} END {print s}'
```

5. Add entry to `index.json` in alphabetical order by `name`. `preview_sounds` should list 2-3 representative filenames (just the filename, not the full path) that give a good sample of the pack's character.

Registry entry format:

```json
{
  "name": "pack_name",
  "display_name": "Display Name",
  "version": "1.0.0",
  "description": "...",
  "author": { "name": "...", "github": "..." },
  "trust_tier": "community",
  "categories": ["session.start", "task.acknowledge", "task.complete", "task.error", "input.required", "resource.limit"],
  "language": "en",
  "license": "MIT",
  "sound_count": 80,
  "total_size_bytes": 30000000,
  "source_repo": "user/repo-name",
  "source_ref": "v1.0.0",
  "source_path": ".",
  "manifest_sha256": "...",
  "tags": ["gaming", "..."],
  "preview_sounds": ["file1.wav", "file2.wav"],
  "added": "<YYYY-MM-DD>",
  "updated": "<YYYY-MM-DD>"
}
```

PR title convention: `Add <Pack Name> voice pack (<N> sounds)`

6. Push branch and open PR:

```bash
git add index.json
git commit -m "Add <Pack Name> voice pack"
git push origin add-<pack-name>
gh pr create --title "Add <Pack Name> voice pack (<N> sounds)" --body ""
```

7. Wait for CI to pass. If it fails, check the PR issue comments for details.

## Gotchas

- **Never force push a git tag.** GitHub caches `raw.githubusercontent.com` content (5 min to 24 hours). If you need to update files after tagging, create a new version (e.g., v1.0.1) instead.
- **SHA256 chain reaction.** Any audio file change requires updating: (1) the file's sha256 in openpeon.json, (2) openpeon.json's sha256 in registry index.json, and (3) total_size_bytes in registry index.json.
- **JSON editing by script only.** Hand-editing large JSON files leads to trailing commas and syntax errors. Use `python3 json.dump()` with `indent=2` and `ensure_ascii=False`.
- **File name and manifest must stay in sync.** When renaming files, update both the actual file AND the `file` field in openpeon.json. Verify after every rename.
- **Trailing silence is the #1 CI failure.** Always pre-check with ffmpeg before submitting. Block threshold is > 2000ms. Only trim what's necessary -- don't remove all silence.
- **Copy first, rename later.** Always copy source audio with original names, verify correctness, then batch rename to ASCII.
- **CI only checks blocking issues.** Warnings (e.g., dead air 500-2000ms, volume high) do not prevent the PR from passing. Only fix blocking issues to unblock CI.
- **Check CI failure details in PR issue comments.** Use `gh api repos/<owner>/<repo>/issues/<pr_number>/comments` to see detailed quality report. PR review comments (`pulls/.../comments`) may be empty.
- **Retrigger CI with a real file change.** Empty commits and `gh run rerun` may not work (no permission or workflow doesn't recognize them). Push a commit with actual file changes to reliably retrigger CI.
