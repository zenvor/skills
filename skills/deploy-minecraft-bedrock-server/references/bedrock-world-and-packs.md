# Bedrock world and add-on migration

> **Validation provenance:** Phone-world import, selection of the newest local export, add-on extraction/binding, manifest-version interpretation and affected-player gameplay confirmation were production-observed in this project. The binding checker was also real-offline-validated against the long-played world. Template and every archive variant were not all exercised.

## Official world-copy path

**Source:** Official Minecraft/Microsoft documentation; the world-copy approach was also production-observed.

Microsoft documents copying an existing Bedrock world folder into BDS `worlds/` and selecting it with `level-name`. Use this path first. A valid world root normally contains `db/`, `level.dat`, `level.dat_old` and `levelname.txt`.

Reference:

- <https://learn.microsoft.com/en-us/minecraft/creator/documents/bedrockserver/getting-started?view=minecraft-bedrock-stable>
- <https://learn.microsoft.com/en-us/minecraft/creator/documents/createaworldtemplate?view=minecraft-bedrock-stable>
- <https://learn.microsoft.com/en-us/minecraft/creator/documents/packagingaworldtemplate?view=minecraft-bedrock-stable>

## Establish the source of truth

**Source:** Production-observed project decision plus operational safety guidance.

1. Ask which export is newest and whether the test-server world must be discarded.
2. Record size, file count, `levelname.txt`, archive hash and modification time.
3. Preserve the original export untouched.
4. Create a pristine copy and a separate working copy. Perform all pack or identity changes on the working copy.
5. Reject archives with an extra wrapper directory until the actual world root is identified.

## Understand package types

**Source:** Official packaging conventions and archive inspection. The distinction between the distributor filename version and internal manifest version was production-observed.

- `.mcworld`: exported playable world; usually a ZIP-compatible archive.
- `.mcpack`: one behavior or resource pack.
- `.mcaddon`: container that may hold multiple packs or nested archives.
- `.mctemplate`: template for creating a new world; do not substitute it for a newer long-played world unless the user explicitly chooses the template.

Inspect archive contents and every `manifest.json`; do not trust the filename alone. The manifest header/module UUID and version are authoritative for pack binding. A marketplace or distributor filename such as `v1.2.0` may legitimately contain an internal manifest version such as `[1,0,19]`.

## Bind packs to the chosen world

**Source:** Production-observed binding workflow, real-offline validation and official manifest conventions. Script API compatibility still requires runtime confirmation.

1. Extract packages into staging, never directly over the only world copy.
2. Classify modules: behavior packs commonly contain `data` or `script`; resource packs contain `resources`.
3. Copy packs either into the world-local `behavior_packs/` and `resource_packs/` folders or into BDS shared folders. Prefer world-local placement for a pack required only by that world.
4. Maintain `world_behavior_packs.json` and `world_resource_packs.json` using each manifest header UUID and exact version array.
5. Preserve existing bindings and history unless intentionally replacing them.
6. Run `scripts/check-bedrock-pack-bindings.py WORLD_PATH` and resolve missing packs, duplicate bindings/UUIDs, UUID dependency mismatches, incompatible module types and version mismatches. Runtime module dependencies such as `@minecraft/server` remain warnings that require BDS-version validation.
7. Treat this as an offline manifest/binding check, not proof that every script API is runtime-compatible. Start a disposable BDS copy and confirm the expected Pack Stack before replacing the live world.

## Replace the active BDS world

**Source:** Production-observed at the workflow level plus operational rollback guidance; exact backup and ownership actions must be verified in each execution record.

1. Confirm zero online players.
2. Gracefully stop BDS and verify the service is inactive.
3. Move the active world to a timestamped backup. Do not delete it.
4. Move the verified working world into `worlds/<level-name>` and set ownership to the BDS service account.
5. Ensure `server.properties` `level-name` exactly matches the directory, including spaces and case.
6. Start BDS and inspect startup logs from this exact start.
7. Verify public UDP and perform an in-game check.

## Validate gameplay

**Source:** The affected owner's map, inventory, XP and add-on progression were player-confirmed. Other players, dimensions and every listed state require their own confirmation.

Check more than spawn appearance:

- Known builds and coordinates.
- Inventory, armor, levels, effects, ender chest and spawn point.
- Required behavior/resource pack UI and representative custom items.
- Mod-specific attributes, tutorial/progression flags and dynamic properties.
- Multiple dimensions and chunks near important bases.

Keep the pristine local export and pre-replacement server backup until all owners confirm success.
