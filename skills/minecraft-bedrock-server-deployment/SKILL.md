---
name: minecraft-bedrock-server-deployment
description: Safely assess Linux VPS hosts, deploy and operate Minecraft Bedrock Dedicated Server (BDS), import existing Bedrock/mobile worlds and add-ons, preserve player data, configure allowlists/operators, and verify networking, backups, and rollback. Use when asked to inspect or purchase a Bedrock host, install BDS, migrate a long-played phone/Bedrock world, bind behavior/resource packs, diagnose missing inventory after BDS import, or perform the community LevelDB owner-identity migration.
license: MIT. See LICENSE.txt
---

# Minecraft Bedrock Server Deployment

## Interpret validation provenance

Treat the following labels as evidence boundaries, not quality rankings:

- **Production-observed:** performed against the concrete Tencent Cloud BDS deployment and confirmed from server behavior or by the affected player in game.
- **Real-offline-validated:** exercised against an offline copy of the long-played Bedrock world without changing the live server.
- **Synthetic/local-tested:** verified with generated fixtures, temporary databases, static checks, or localhost loopback tests; not a production-server claim.
- **Officially documented:** derived from current Minecraft/Microsoft documentation and must be rechecked at execution time.
- **Operational guidance:** conservative administration practice that was not necessarily exercised end to end in this deployment.
- **Not exercised here:** retained for the broader reusable skill, but not performed in this project.

Current evidence map:

| Area | Provenance |
| --- | --- |
| Tencent Cloud BDS deployment, phone-world import, world selection, add-on binding, allowlist handling and owner joining as a fresh player | Production-observed |
| Owner inventory, XP, position and add-on progression restored through the community LevelDB identity approach | Production-observed; player-confirmed |
| v3 migration tool against the long-played world | Real-offline-validated for dry-run; not applied to the production server with v3 |
| v3 atomic apply, digest refusal, privacy controls, repeat-apply refusal and raw-byte verification | Synthetic/local-tested |
| Pack-binding checker against the long-played world | Real-offline-validated |
| RakNet probe implementation | Synthetic/local-tested on localhost; production reachability must still be tested per server |
| Official world copy, `level-name`, BDS properties and supported management commands | Officially documented; selected parts were also production-observed |
| General VPS audit, sizing, hardening, upgrades, rollback and failure handling | Operational guidance unless a task reports concrete execution evidence |
| BDS upgrade rehearsal, IPv6 UDP validation and multi-player identity migration | Not exercised here |

Do not turn a stronger-looking label into a claim without new evidence. In particular, a clean synthetic test is not production validation, and an official procedure is not evidence that it was executed on a specific host.

## Work safely

1. Confirm that the target is Bedrock Edition/BDS. Do not use this skill for Java Edition deployment, and never imply that a Java Edition world can be copied directly into BDS.
2. Inspect before installing. Record OS, architecture, CPU, RAM, swap, disk, current services, listening ports, firewall/security-group state, public IP, latency, client versions, player count, world size, add-ons/mods, and backup requirements.
3. Preserve unrelated services. Do not stop proxies, overwrite firewall policy, expose management ports, install Docker, reboot, or replace a live world unless the user explicitly authorizes that action.
4. Treat the user's newest local world as the source of truth when they say so. Never merge an older test-server world back into it.
5. Back up before every stateful transition. Use timestamped, recoverable paths and verify the backup before changing the active world.
6. Separate inspection, plan, mutation, and verification. Pause before purchases, destructive replacement, downtime, EULA acceptance, or an unsupported data migration when authorization is not already explicit.
7. Fetch current server builds and version requirements from official Minecraft/Microsoft sources at execution time. Do not reuse versions or download URLs from examples.
8. Never expose private keys, tokens, XUIDs, public IPs, personal Gamertags, full process arguments, or player identifiers in reusable artifacts or logs beyond what the user needs. Keep forensic identity output in mode-0600 local files.

## Route the task

- Read [linux-host-and-network.md](references/linux-host-and-network.md) for VPS inspection, sizing, latency, ports, and coexistence with existing services. Run `scripts/audit-linux-minecraft-host.sh` for a read-only snapshot.
- Read [bedrock-edition.md](references/bedrock-edition.md) for BDS installation, systemd, configuration, allowlist/operator management, upgrades, and health checks. Use `scripts/probe-bedrock.py` for a RakNet UDP probe.
- Read [bedrock-world-and-packs.md](references/bedrock-world-and-packs.md) when importing a phone/BE world, `.mcworld`, `.mcaddon`, `.mcpack`, or `.mctemplate`, or when setting the default BDS world. Run `scripts/check-bedrock-pack-bindings.py` before deployment.
- Read [bedrock-player-identity-migration.md](references/bedrock-player-identity-migration.md) only when the imported owner joins BDS as a new player, loses inventory/tutorial/mod state, or explicitly requests identity migration. This is a community compatibility procedure, not an official Mojang migration command.
- After changing bundled tools, install dependencies with `npm ci` in an isolated copy of `scripts/` and run `scripts/tests/run-tests.sh`. The native LevelDB package executes an install script; keep that environment unprivileged and free of secrets.

## Use the staged workflow

### 1. Discover and report

Run read-only checks first. State assumptions and distinguish cloud security-group rules from the guest firewall. For a purchase decision, compare region latency for all players and sustained/peak bandwidth terms, not only CPU and RAM.

### 2. Plan and obtain gates

Name exact targets, downtime, ports, backup paths, rollback action, and expected client/server version. Ask before changing external security groups, accepting purchases, replacing a world, or performing LevelDB writes.

### 3. Deploy BDS

Use a dedicated unprivileged service account, a narrowly writable install directory, systemd supervision, graceful stop signals, and least-privilege filesystem protections. Keep server data separate from downloaded archives and temporary staging files.

### 4. Import data offline

Stop the target server gracefully before replacing or directly copying a world database. Validate archive layout, world name, pack manifests, JSON bindings, ownership, and available disk space. Stage the new world beside the active world; move the old world to a timestamped backup instead of deleting it.

### 5. Migrate identity only if needed

First test the official world-copy path. If the local owner becomes a fresh BDS player, collect a clean identity mapping from a disposable server copy, stop BDS, and work only on local/offline snapshots. Require the fixed `~local_player` owner source, explicit player-key selection, mapping-to-target `ServerId` equality, a tool-and-runtime-bound reviewed plan digest, raw-byte hashing, atomic batch writes, and an in-game confirmation. Never guess opaque player keys.

### 6. Verify before handoff

Verify the service, startup logs, correct world, pack stack, ports, public handshake, resources, disk, and errors. For migrated Bedrock players, require an in-game check of inventory, armor, XP, position, ender chest, tutorial state, achievements/mod progression, and representative custom items. Keep rollback artifacts until the user confirms success.

## Report provenance honestly

Label task results using both the procedure status below and, where relevant, the validation provenance above:

- **Official path:** documented server installation, world folder copy, `level-name`, pack binding, allowlist, or operator management.
- **Observed compatibility:** behavior verified on the concrete version but not guaranteed by official documentation.
- **Community migration:** direct LevelDB player-record work; backup-first, version-sensitive, and successful only after byte-level and in-game validation.

Do not claim success from a clean log alone. Player-data migration is complete only after the affected player confirms their data in game.
