import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import leveldbPackage from "@8crafter/leveldb-zlib";
import nbt from "prismarine-nbt";

const { LevelDB } = leveldbPackage;
const sha256 = (value) => crypto.createHash("sha256").update(value).digest("hex");
const fingerprint = (value) => (value ? sha256(Buffer.from(value)).slice(0, 16) : null);

function usage(exitCode = 2) {
  console.error(`Usage: node inspect-bedrock-players.mjs <offline-world-copy> [options]

Options:
  --include-identifiers  Include full paths, LevelDB keys and identity fields; requires --output
  --output PATH          Write JSON to a new local mode-0600 file instead of stdout`);
  process.exit(exitCode);
}

function parseArgs(args) {
  let input;
  let output;
  let includeIdentifiers = false;
  for (let index = 0; index < args.length; index += 1) {
    const argument = args[index];
    if (argument === "--help") usage(0);
    else if (argument === "--include-identifiers") includeIdentifiers = true;
    else if (argument === "--output") {
      if (index + 1 >= args.length) usage();
      output = args[++index];
    } else if (!input) input = argument;
    else throw new Error("Unexpected extra argument");
  }
  if (!input) usage();
  if (includeIdentifiers && !output) {
    throw new Error("--include-identifiers requires --output to keep full identity data out of terminal logs");
  }
  return { input, output, includeIdentifiers };
}

function safeRealpath(input) {
  try {
    return fs.realpathSync(input);
  } catch {
    throw new Error("Offline world does not resolve to an existing path");
  }
}

async function main() {
  const { input, output, includeIdentifiers } = parseArgs(process.argv.slice(2));
  const worldPath = safeRealpath(input);
  const dbPath = path.join(worldPath, "db");
  try {
    if (!fs.statSync(dbPath).isDirectory()) throw new Error("not-directory");
  } catch {
    throw new Error("Offline world has no readable db directory");
  }

  const database = new LevelDB(dbPath, { bufferKeys: true, createIfMissing: false });
  try {
    await database.open();
  } catch {
    throw new Error("Cannot open the offline LevelDB copy");
  }

  try {
    const records = [];
    try {
      for await (const [rawKey, rawValue] of database) {
        const keyBuffer = Buffer.from(rawKey);
        const key = keyBuffer.toString("utf8");
        if (key !== "~local_player" && !key.startsWith("player_server_") && !key.startsWith("player_")) continue;

        const value = Buffer.from(rawValue);
        const keyType = key === "~local_player" ? "local" : key.startsWith("player_server_") ? "server" : "mapping";
        const record = {
          keyType,
          keyFingerprint: fingerprint(key),
          bytes: value.length,
          sha256: sha256(value),
        };
        if (includeIdentifiers) Object.assign(record, { key, keyHex: keyBuffer.toString("hex") });

        try {
          const parsed = await nbt.parse(value, "little");
          const simple = nbt.simplify(parsed.parsed);
          Object.assign(record, {
            inventorySlots: Array.isArray(simple.Inventory) ? simple.Inventory.length : null,
            armorSlots: Array.isArray(simple.Armor) ? simple.Armor.length : null,
            offhandSlots: Array.isArray(simple.Offhand) ? simple.Offhand.length : null,
            enderChestSlots: Array.isArray(simple.EnderChestInventory) ? simple.EnderChestInventory.length : null,
            level: simple.PlayerLevel ?? simple.XpLevel ?? null,
            position: simple.Pos ?? null,
            dimensionId: simple.DimensionId ?? simple.Dimension ?? null,
            gameMode: simple.PlayerGameMode ?? simple.GameMode ?? null,
            serverIdFingerprint: fingerprint(simple.ServerId),
            hasMicrosoftAccountId: Boolean(simple.MsaId ?? simple.MSAId ?? simple.MicrosoftAccountId),
            hasSelfSignedId: Boolean(simple.SelfSignedId),
            topLevelKeys: Object.keys(simple).sort(),
          });
          if (includeIdentifiers) {
            Object.assign(record, {
              microsoftAccountId: simple.MsaId ?? simple.MSAId ?? simple.MicrosoftAccountId ?? null,
              serverId: simple.ServerId ?? null,
              selfSignedId: simple.SelfSignedId ?? null,
            });
          }
        } catch {
          record.nbtParseError = "NBT parse failed";
        }
        records.push(record);
      }
    } catch {
      throw new Error("Failed while reading player records from the offline LevelDB copy");
    }

    records.sort((left, right) => left.keyFingerprint.localeCompare(right.keyFingerprint));
    const result = {
      worldPathFingerprint: fingerprint(worldPath),
      identifiersIncluded: includeIdentifiers,
      records,
    };
    if (includeIdentifiers) {
      Object.assign(result, { worldName: path.basename(worldPath), worldPath, dbPath });
    }

    const json = `${JSON.stringify(result, null, 2)}\n`;
    if (output) {
      const outputPath = path.resolve(output);
      try {
        fs.writeFileSync(outputPath, json, { encoding: "utf8", mode: 0o600, flag: "wx" });
        fs.chmodSync(outputPath, 0o600);
      } catch {
        throw new Error("Cannot create private inspection output; use a new path in a writable directory");
      }
      console.error(`Wrote ${records.length} records to a mode-0600 file`);
    } else {
      process.stdout.write(json);
    }
  } finally {
    await database.close().catch(() => {});
  }
}

main().catch((error) => {
  console.error(`Inspection refused: ${error?.message ?? "unknown error"}`);
  process.exitCode = 1;
});
