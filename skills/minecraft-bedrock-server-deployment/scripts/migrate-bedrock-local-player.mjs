import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import leveldbPackage from "@8crafter/leveldb-zlib";
import nbt from "prismarine-nbt";

const { LevelDB } = leveldbPackage;
const PLAN_VERSION = "bedrock-local-player-migration-v3";
const LOCAL_OWNER_KEY = "~local_player";
const sha256 = (value) => crypto.createHash("sha256").update(value).digest("hex");
const fingerprint = (value) => sha256(Buffer.from(value)).slice(0, 16);

function usage(exitCode = 2) {
  console.error(`Usage:
  node migrate-bedrock-local-player.mjs --working-world PATH --identity-world PATH \
    --identity-spec PRIVATE_MODE_0600_JSON --output PRIVATE_REPORT_PATH

Dry-run first. To apply the exact reviewed plan, repeat all arguments and add:
  --apply-plan-sha256 DIGEST --acknowledge-community-migration --apply`);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const options = { apply: false, acknowledge: false };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    const value = () => {
      if (index + 1 >= argv.length) usage();
      index += 1;
      return argv[index];
    };
    if (argument === "--working-world") options.workingWorld = value();
    else if (argument === "--identity-world") options.identityWorld = value();
    else if (argument === "--identity-spec") options.identitySpec = value();
    else if (argument === "--output") options.output = value();
    else if (argument === "--apply-plan-sha256") options.applyPlanSha256 = value().toLowerCase();
    else if (argument === "--apply") options.apply = true;
    else if (argument === "--acknowledge-community-migration") options.acknowledge = true;
    else if (argument === "--help") usage(0);
    else throw new Error("Unknown or unexpected argument");
  }
  return options;
}

function safeRealpath(input, label) {
  try {
    return fs.realpathSync(input);
  } catch {
    throw new Error(`${label} does not resolve to an existing path`);
  }
}

function readIdentitySpec(input) {
  const specPath = safeRealpath(input, "Identity spec");
  let stat;
  let parsed;
  try {
    stat = fs.statSync(specPath);
    parsed = JSON.parse(fs.readFileSync(specPath, "utf8"));
  } catch {
    throw new Error("Identity spec must be a readable JSON file");
  }
  if (!stat.isFile() || (stat.mode & 0o077) !== 0) {
    throw new Error("Identity spec must be a regular file with mode 0600 or stricter");
  }
  if (parsed.sourceKey !== undefined && parsed.sourceKey !== LOCAL_OWNER_KEY) {
    throw new Error(`Identity spec sourceKey must be exactly ${LOCAL_OWNER_KEY}`);
  }
  return {
    sourceKey: LOCAL_OWNER_KEY,
    targetKey: parsed.targetKey,
    clientKeys: parsed.clientKeys,
    expectedSourceSha256:
      typeof parsed.expectedSourceSha256 === "string"
        ? parsed.expectedSourceSha256.toLowerCase()
        : parsed.expectedSourceSha256,
  };
}

async function maybeGet(database, key) {
  try {
    return await database.get(key);
  } catch (error) {
    if (error?.notFound || /not.?found/i.test(String(error?.message ?? error))) return undefined;
    throw new Error("LevelDB read failed");
  }
}

async function parseMapping(value, key) {
  const keyFingerprint = fingerprint(key);
  let simple;
  try {
    const parsed = await nbt.parse(Buffer.from(value), "little");
    simple = nbt.simplify(parsed.parsed);
  } catch {
    throw new Error(`Cannot parse client mapping NBT; key fingerprint: ${keyFingerprint}`);
  }
  if (typeof simple.ServerId !== "string" || !simple.ServerId.startsWith("player_server_")) {
    throw new Error(`Client mapping has no valid ServerId; key fingerprint: ${keyFingerprint}`);
  }
  const msaId = simple.MsaId ?? simple.MSAId ?? simple.MicrosoftAccountId;
  const selfSignedId = simple.SelfSignedId;
  if (typeof msaId !== "string" && typeof selfSignedId !== "string") {
    throw new Error(`Client mapping has no usable identity field; key fingerprint: ${keyFingerprint}`);
  }
  return {
    serverId: simple.ServerId,
    msaId: typeof msaId === "string" ? msaId : null,
    selfSignedId: typeof selfSignedId === "string" ? selfSignedId : null,
  };
}

async function validateLocalOwnerRecord(value) {
  let simple;
  try {
    const parsed = await nbt.parse(Buffer.from(value), "little");
    simple = nbt.simplify(parsed.parsed);
  } catch {
    throw new Error("Local owner source is not valid little-endian player NBT");
  }
  const playerMarkers = [
    "Inventory",
    "PlayerLevel",
    "XpLevel",
    "Pos",
    "DimensionId",
    "PlayerGameMode",
    "SpawnX",
  ];
  if (!simple || typeof simple !== "object" || !playerMarkers.some((field) => field in simple)) {
    throw new Error("Local owner source NBT has no recognized player fields");
  }
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]));
  }
  return value;
}

const planDigest = (plan) => sha256(Buffer.from(JSON.stringify(canonicalize(plan)), "utf8"));

function currentToolSha256() {
  try {
    return sha256(fs.readFileSync(fileURLToPath(import.meta.url)));
  } catch {
    throw new Error("Cannot hash the migration tool");
  }
}

function currentRuntimeBinding() {
  try {
    const toolDirectory = path.dirname(fileURLToPath(import.meta.url));
    return {
      nodeVersion: process.version,
      platform: process.platform,
      arch: process.arch,
      packageLockSha256: sha256(fs.readFileSync(path.join(toolDirectory, "package-lock.json"))),
    };
  } catch {
    throw new Error("Cannot bind the migration runtime and package lock");
  }
}

async function main() {
  const cli = parseArgs(process.argv.slice(2));
  for (const field of ["workingWorld", "identityWorld", "identitySpec", "output"]) {
    if (!cli[field]) throw new Error(`Missing required option: ${field}`);
  }
  if (cli.apply && !cli.acknowledge) {
    throw new Error("--apply requires --acknowledge-community-migration");
  }
  if (cli.apply && !/^[0-9a-f]{64}$/.test(cli.applyPlanSha256 ?? "")) {
    throw new Error("--apply requires a valid --apply-plan-sha256 from the reviewed dry-run");
  }
  if (!cli.apply && cli.applyPlanSha256) {
    throw new Error("--apply-plan-sha256 is only valid with --apply");
  }

  const identitySpec = readIdentitySpec(cli.identitySpec);
  const options = { ...cli, ...identitySpec };
  if (typeof options.targetKey !== "string" || !options.targetKey.startsWith("player_server_")) {
    throw new Error("Identity spec targetKey must start with player_server_");
  }
  if (!Array.isArray(options.clientKeys) || options.clientKeys.length === 0) {
    throw new Error("Identity spec must contain at least one clientKeys entry");
  }
  if (options.clientKeys.some((key) => typeof key !== "string" || !key.startsWith("player_") || key.startsWith("player_server_"))) {
    throw new Error("Every identity spec clientKeys entry must start with player_ but not player_server_");
  }
  if (new Set(options.clientKeys).size !== options.clientKeys.length) {
    throw new Error("Identity spec contains duplicate clientKeys entries");
  }
  if (!/^[0-9a-f]{64}$/.test(options.expectedSourceSha256 ?? "")) {
    throw new Error("Identity spec expectedSourceSha256 must be exactly 64 hexadecimal characters");
  }

  const workingWorld = safeRealpath(options.workingWorld, "Working world");
  const identityWorld = safeRealpath(options.identityWorld, "Identity world");
  const workingDbPath = safeRealpath(path.join(workingWorld, "db"), "Working world database");
  const identityDbPath = safeRealpath(path.join(identityWorld, "db"), "Identity world database");
  if (workingDbPath === identityDbPath) throw new Error("Working and identity databases must be different copies");

  const outputPath = path.resolve(options.output);
  const outputParent = path.dirname(outputPath);
  try {
    if (!fs.statSync(outputParent).isDirectory()) throw new Error("not-directory");
  } catch {
    throw new Error("Private report parent must be an existing writable directory");
  }

  let outputFd;
  try {
    outputFd = fs.openSync(outputPath, "wx", 0o600);
    fs.fchmodSync(outputFd, 0o600);
  } catch {
    throw new Error("Cannot create private report; use a new path in a writable directory");
  }

  const workingDb = new LevelDB(workingDbPath, { bufferKeys: true, createIfMissing: false });
  const identityDb = new LevelDB(identityDbPath, { bufferKeys: true, createIfMissing: false });
  let workingDbOpen = false;
  let identityDbOpen = false;

  const writePrivateReport = (report) => {
    try {
      fs.writeFileSync(outputFd, `${JSON.stringify(report, null, 2)}\n`, { encoding: "utf8" });
      fs.fsyncSync(outputFd);
    } catch {
      throw new Error("Cannot write private migration report");
    }
    console.error(`Wrote a mode-0600 migration report: ${path.basename(outputPath)}`);
  };

  try {
    try {
      await workingDb.open();
      workingDbOpen = true;
      await identityDb.open();
      identityDbOpen = true;
    } catch {
      throw new Error("Cannot open one of the offline LevelDB copies");
    }

    const sourceValue = await maybeGet(workingDb, options.sourceKey);
    if (!sourceValue) throw new Error(`Missing source player record fingerprint: ${fingerprint(options.sourceKey)}`);
    const source = Buffer.from(sourceValue);
    await validateLocalOwnerRecord(source);
    const sourceDigest = sha256(source);
    if (sourceDigest !== options.expectedSourceSha256) {
      throw new Error(`Source hash mismatch: expected ${options.expectedSourceSha256}, got ${sourceDigest}`);
    }

    const identityTarget = await maybeGet(identityDb, options.targetKey);
    if (!identityTarget) {
      throw new Error(`Target record does not exist in identity snapshot; fingerprint: ${fingerprint(options.targetKey)}`);
    }
    if (await maybeGet(workingDb, options.targetKey)) {
      throw new Error(`Target record already exists in working world; fingerprint: ${fingerprint(options.targetKey)}`);
    }

    const operations = [{ type: "put", key: options.targetKey, value: source }];
    const mappings = [];
    for (const key of [...options.clientKeys].sort()) {
      if (await maybeGet(workingDb, key)) {
        throw new Error(`Client mapping already exists in working world; fingerprint: ${fingerprint(key)}`);
      }
      const identityValue = await maybeGet(identityDb, key);
      if (!identityValue) {
        throw new Error(`Missing client mapping in identity snapshot; fingerprint: ${fingerprint(key)}`);
      }
      const mappingValue = Buffer.from(identityValue);
      const parsedMapping = await parseMapping(mappingValue, key);
      if (parsedMapping.serverId !== options.targetKey) {
        throw new Error(`Client mapping points to a different ServerId; fingerprint: ${fingerprint(key)}`);
      }
      operations.push({ type: "put", key, value: mappingValue });
      mappings.push({
        key,
        bytes: mappingValue.length,
        sha256: sha256(mappingValue),
        serverId: parsedMapping.serverId,
        msaIdSha256: parsedMapping.msaId ? sha256(Buffer.from(parsedMapping.msaId)) : null,
        selfSignedIdSha256: parsedMapping.selfSignedId ? sha256(Buffer.from(parsedMapping.selfSignedId)) : null,
      });
    }

    if (new Set(mappings.map((mapping) => mapping.serverId)).size !== 1) {
      throw new Error("Client mappings do not all point to one ServerId");
    }
    for (const field of ["msaIdSha256", "selfSignedIdSha256"]) {
      const fieldValues = mappings.map((mapping) => mapping[field]);
      const presentCount = fieldValues.filter(Boolean).length;
      if (presentCount > 0 && presentCount !== mappings.length) {
        throw new Error(`Client mappings disagree on presence of ${field}`);
      }
      if (new Set(fieldValues.filter(Boolean)).size > 1) {
        throw new Error(`Client mappings disagree on ${field}`);
      }
    }

    const plan = {
      planVersion: PLAN_VERSION,
      toolSha256: currentToolSha256(),
      runtime: currentRuntimeBinding(),
      workingWorld,
      identityWorld,
      source: { key: options.sourceKey, bytes: source.length, sha256: sourceDigest },
      identityTarget: {
        key: options.targetKey,
        bytes: Buffer.from(identityTarget).length,
        sha256: sha256(Buffer.from(identityTarget)),
      },
      destination: { key: options.targetKey, expectedBytes: source.length, expectedSha256: sourceDigest },
      clientMappings: mappings,
    };
    const digest = planDigest(plan);
    const report = { mode: options.apply ? "apply" : "dry-run", planDigest: digest, plan };

    if (!options.apply) {
      writePrivateReport(report);
      console.error(`DRY RUN ONLY: review the private report, then apply with --apply-plan-sha256 ${digest}`);
      process.exitCode = 3;
      return;
    }

    if (options.applyPlanSha256 !== digest) {
      throw new Error(`Plan digest mismatch: reviewed ${options.applyPlanSha256}, current ${digest}`);
    }
    try {
      await workingDb.batch(operations, { sync: true });
    } catch {
      throw new Error("Synchronous LevelDB migration batch failed");
    }
    const migrated = await maybeGet(workingDb, options.targetKey);
    if (!migrated || sha256(Buffer.from(migrated)) !== sourceDigest) {
      throw new Error("Post-write target hash verification failed");
    }
    for (const mapping of mappings) {
      const written = await maybeGet(workingDb, mapping.key);
      if (!written || sha256(Buffer.from(written)) !== mapping.sha256) {
        throw new Error(`Post-write mapping verification failed; fingerprint: ${fingerprint(mapping.key)}`);
      }
    }
    report.verification = "source, target, mapping, ServerId, identity fingerprints, and plan digest verified";
    writePrivateReport(report);
  } finally {
    if (identityDbOpen) await identityDb.close().catch(() => {});
    if (workingDbOpen) await workingDb.close().catch(() => {});
    fs.closeSync(outputFd);
  }
}

main().catch((error) => {
  console.error(`Migration refused: ${error?.message ?? "unknown error"}`);
  process.exitCode = 1;
});
