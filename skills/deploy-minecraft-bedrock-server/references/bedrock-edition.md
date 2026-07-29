# Bedrock Dedicated Server workflow

> **Validation provenance:** The project production-observed BDS deployment, world selection, configuration, allowlist handling and player joins. This document also contains official and general hardening steps; do not infer that every numbered step or upgrade scenario was exercised on the live host.

## Authority

**Source:** Official Minecraft/Microsoft documentation, rechecked at execution time.

Fetch current requirements and builds at execution time:

- Official BDS download: <https://www.minecraft.net/en-us/download/server/bedrock>
- Microsoft getting started: <https://learn.microsoft.com/en-us/minecraft/creator/documents/bedrockserver/getting-started?view=minecraft-bedrock-stable>
- Server properties: <https://learn.microsoft.com/en-us/minecraft/creator/documents/bedrockserver/server-properties?view=minecraft-bedrock-stable>

Match the BDS protocol to every client. Mobile and Windows Bedrock clients use the same Bedrock server protocol, but preview/beta and mismatched patch versions may not interoperate.

## Install

**Source:** Mixed. Core BDS deployment and selected configuration were production-observed; least-privilege and staging details are also operational guidance.

1. Verify supported Ubuntu version, CPU architecture, libc/runtime requirements and available resources against the current official page.
2. Download the current Linux archive from the official page. Never synthesize a versioned URL without verifying it.
3. Create a `minecraft`-style service user with no interactive shell and a dedicated install directory.
4. Extract into a staging directory, inspect the archive layout, then install. Preserve user configuration on upgrades.
5. Configure at minimum server name, survival mode, difficulty, player limit, online mode, allowlist, ports, `level-name`, view distance, tick distance and default permission.
6. For a small 2–4 player server with 4 GiB RAM, begin conservatively around `view-distance=8` to `12` and `tick-distance=4`; measure before increasing. Use the user's preference when safe.
7. Run under systemd with `KillSignal=SIGINT` and enough stop timeout for LevelDB to close. Restrict writes to the BDS directory.
8. Permit UDP 19132/19133 only where required. Do not open TCP 19132 as a substitute.

## Private access and operators

**Source:** Official BDS behavior plus production-observed allowlist handling. Exact Gamertag/XUID resolution remains account- and version-specific.

- Keep `online-mode=true` for Xbox identity.
- Set `allow-list=true` and use exact runtime Gamertags. Xbox profile UI may display a suffix as `Name#1234` while Minecraft submits `Name1234`; prefer the name shown in the in-game friends list or BDS connection/rejection logs.
- Quote names containing spaces when using console commands.
- Prefer console `allowlist add`, `allowlist remove`, `allowlist reload`, `op` and `deop` when an interactive console is available.
- If editing `allowlist.json` or `permissions.json` externally, stop BDS or reload through the console. A running BDS can overwrite an externally edited file from its in-memory state.
- `permissions.json` entries use the authenticated XUID, for example `{"permission":"operator","xuid":"..."}`. Do not guess an XUID; obtain it from an authenticated connection log.

## Upgrade

**Source:** Operational guidance. A full BDS upgrade and rollback rehearsal was not exercised in this project.

1. Confirm all players are offline.
2. Gracefully stop BDS and verify it is inactive.
3. Back up world, properties, allowlist, permissions and packs.
4. Extract the new archive into staging; preserve or deliberately merge configuration rather than blindly overwriting it.
5. Start and inspect the exact new startup window for database, pack and protocol errors.
6. Retain the prior build and backup until representative gameplay succeeds.

## Verification

**Source:** Mixed. Startup/world/pack and player-state checks were production-observed; the bundled RakNet probe itself is synthetic/local-tested and still requires a public per-host run.

- Require `Server started`, the expected `Level Name`, `Opening level`, expected Pack Stack, and UDP port lines.
- Treat “content logging to console is disabled” as informational unless content debugging is needed.
- Run `scripts/probe-bedrock.py` from outside the VPS.
- Verify process RSS, available RAM, disk and recent journal errors after players join.
- A clean startup proves database readability, not player identity correctness; verify player state in game.
