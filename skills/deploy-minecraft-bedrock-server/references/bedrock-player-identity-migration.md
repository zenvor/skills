# Bedrock local-owner identity migration

> **Validation provenance:** The fresh-player symptom and successful restoration of one owner's inventory, XP, position and add-on progression were production-observed and player-confirmed. The hardened v3 tool was created afterward: its dry-run was real-offline-validated against the long-played world, while apply/refusal/privacy/atomicity behavior was synthetic/local-tested. v3 was not applied to the production server, and multi-player migration was not exercised.

## Status and risk

**Source:** Observed Bedrock compatibility behavior plus community LevelDB analysis. This is not an official Mojang migration API.

Official BDS documentation supports copying a Bedrock world but provides no command that maps the mobile/local owner record to an authenticated BDS player identity. A local owner is often stored under `~local_player`; BDS uses opaque `player_server_*` records plus `player_*` identity mappings. Copying the world can therefore preserve terrain while the owner joins as a fresh player.

Treat the procedure below as a community compatibility migration based on the Bedrock LevelDB record structure. It is version-sensitive and unsupported as a Mojang migration API. Never perform it silently, on a running database, or without rollback.

## Non-negotiable safeguards

**Source:** Operational safety requirements strengthened by real-offline and synthetic regression results.

- Keep the newest local export as the source of truth and immutable pristine backup.
- Work only on offline copies. Never open the active BDS `db/` with a third-party LevelDB library while BDS is running.
- Stop BDS before copying its identity-test database.
- Migrate one player at a time and require the user to be the only new joiner in the identity test.
- Derive opaque keys by comparing snapshots and authenticated logs; never derive them from a Gamertag or guess them.
- Copy raw NBT bytes. Do not parse and reserialize the player compound because add-on dynamic properties, unknown tags or custom item data may be lost or reordered.
- Require the fixed `~local_player` source, valid player NBT, a source SHA-256, explicit target key, explicit mapping keys, parsed `ServerId` equality, a tool-bound reviewed dry-run plan digest, an apply acknowledgment and post-write hash equality.
- Retain both original and working copies until in-game confirmation.

## Prepare three copies

**Source:** Community migration workflow and operational safety guidance. The source-of-truth separation was production-observed.

1. **Pristine source:** untouched newest mobile/local world.
2. **Working world:** fresh copy of the pristine source; this is the only copy the migration tool may modify.
3. **Identity snapshot:** disposable BDS test world after the target Xbox account joins once as a new player, spawns, exits, and BDS is gracefully stopped.

Do not use an older server test world as the working world when the user says the local export is newer.

## Collect the identity mapping

**Source:** The one-owner identity-capture approach was production-observed. The hardened private-output tooling and its refusal behavior were validated afterward offline and synthetically.

1. Deploy a disposable copy of the pristine world to BDS without changing the local owner record.
2. Ensure `online-mode=true` and allow only the target account to join during this capture.
3. Record the authenticated `Player connected` log containing Gamertag and XUID.
4. Let the target spawn once, then leave. Stop BDS gracefully.
5. Snapshot the stopped test world.
6. Copy `scripts/package.json`, `scripts/package-lock.json` and the required tools into an isolated unprivileged temporary directory containing no credentials. Run `npm ci --registry=https://registry.npmjs.org` there. The pinned native LevelDB dependency executes an install script; do not run it in a credential-rich or privileged environment.
7. Generate a redacted overview first. When full opaque keys are required, write them to a private file instead of the conversation log:

   ```bash
   node scripts/inspect-bedrock-players.mjs /path/to/pristine-world
   node scripts/inspect-bedrock-players.mjs /path/to/identity-snapshot \
     --include-identifiers --output /private/path/identity-records.json
   ```

8. Identify the source `~local_player` record and its SHA-256.
9. Identify the single newly introduced or changed `player_server_*` record and the `player_*` mapping records that refer to the target identity. Cross-check inventory/position characteristics and the test timing. If the comparison is ambiguous, stop and repeat a cleaner capture.

## Apply to a working copy

**Source:** v3 dry-run was real-offline-validated; v3 apply, atomic write, digest binding and refusal cases were synthetic/local-tested, not rerun against the production server.

Put the sensitive opaque keys and source hash in a private JSON file instead of command-line arguments, so they do not enter shell history or process listings. The tool rejects a group/world-readable file; set mode `0600` or stricter:

```json
{
  "targetKey": "player_server_EXPLICIT_KEY",
  "clientKeys": [
    "player_EXPLICIT_MAPPING_ONE",
    "player_EXPLICIT_MAPPING_TWO"
  ],
  "expectedSourceSha256": "EXPLICIT_SHA256"
}
```

This owner-only tool always reads `~local_player`; it rejects any identity spec that attempts to select another source key. The source must also parse as little-endian NBT with recognized player fields.

First run without `--apply`:

```bash
node scripts/migrate-bedrock-local-player.mjs \
  --working-world /path/to/working-world \
  --identity-world /path/to/identity-snapshot \
  --identity-spec /private/path/identity-spec.json \
  --output /private/path/dry-run-plan.json
```

The dry-run writes a new mode-0600 report, refuses to overwrite an existing file, and intentionally exits with status `3`. Review every path, key, byte count, mapping `ServerId`, identity fingerprint and hash in that private report. The v3 plan binds `toolSha256`, Node version, platform, CPU architecture and `package-lock.json` SHA-256, so changing the tool or locked runtime environment invalidates the digest. Save its `planDigest`. Then repeat with the same arguments, a different new private output path, the exact digest and both safety flags:

```bash
node scripts/migrate-bedrock-local-player.mjs \
  --working-world /path/to/working-world \
  --identity-world /path/to/identity-snapshot \
  --identity-spec /private/path/identity-spec.json \
  --output /private/path/apply-report.json \
  --apply-plan-sha256 DRY_RUN_PLAN_DIGEST \
  --acknowledge-community-migration \
  --apply
```

The tool must refuse an insecure identity-spec mode, a non-local source key, invalid player NBT, missing keys, an unexpected source hash, an existing destination/mapping key, identical database paths, mappings whose parsed `ServerId` differs from the selected target, missing or disagreeing identity fingerprints, a changed tool/runtime/plan digest, an existing report path, or an absent acknowledgment. Full paths, opaque player keys and unexpected argument values are not echoed by routine errors. It writes the target record and identity mappings in one synchronous LevelDB batch and verifies target/source raw-byte hashes afterward.

## Deploy and verify

**Source:** Deployment outcome and the affected owner's state were production-observed and player-confirmed. The exact v3 execution path itself was not used for that production migration.

1. Re-run the inspector on the working world. Confirm target/source byte count and SHA-256 match.
2. Package and test the archive structure locally.
3. Confirm zero players, stop BDS and move the current server world to a timestamped backup.
4. Deploy the working world and start BDS.
5. Require clean LevelDB open, correct world and expected Pack Stack.
6. Have the target account verify inventory/hotbar, armor, XP, position, ender chest, tutorial state, mod levels, dynamic properties and representative custom items.
7. Do not call the migration successful until the player confirms all state in game.

## Multiple players and failures

**Source:** Operational guidance. Additional-player migration and destructive-failure recovery were not exercised in this project.

- Existing remote players may already have usable server identity records in the exported world. Test them before migrating anything.
- If another player joins as fresh, repeat a separate one-player identity capture. Do not reuse the owner's opaque keys.
- If a player appears with empty data, ask them to leave immediately and avoid item/progression changes until diagnosis.
- On any mismatch or LevelDB error, stop, preserve logs and the failed working copy, and restore the timestamped server backup. Never “repair” by deleting `.ldb`, `MANIFEST`, `CURRENT` or `.log` files.
