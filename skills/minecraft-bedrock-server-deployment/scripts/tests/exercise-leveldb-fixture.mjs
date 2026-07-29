import crypto from "node:crypto";
import path from "node:path";
import leveldbPackage from "@8crafter/leveldb-zlib";
import nbt from "prismarine-nbt";

const { LevelDB } = leveldbPackage;
const sha256 = (value) => crypto.createHash("sha256").update(value).digest("hex");
const [command, ...args] = process.argv.slice(2);

async function withDatabase(worldPath, callback) {
  const database = new LevelDB(path.join(worldPath, "db"), { bufferKeys: true, createIfMissing: false });
  await database.open();
  try {
    return await callback(database);
  } finally {
    await database.close();
  }
}

if (command === "mutate-source") {
  const [workingWorld] = args;
  if (!workingWorld) throw new Error("mutate-source requires <working-world>");
  const value = nbt.writeUncompressed(
    nbt.comp({
      PlayerLevel: nbt.int(22),
      SyntheticMarker: nbt.string("fixture-source-changed-after-dry-run"),
    }),
    "little",
  );
  await withDatabase(workingWorld, (database) => database.put("~local_player", value, { sync: true }));
  process.stdout.write(sha256(value));
} else if (command === "mutate-mappings") {
  const [identityWorld, targetKey, ...clientKeys] = args;
  if (!identityWorld || !targetKey || clientKeys.length === 0) {
    throw new Error("mutate-mappings requires <identity-world> <target-key> <client-key...>");
  }
  const value = nbt.writeUncompressed(
    nbt.comp({
      ServerId: nbt.string(targetKey),
      MsaId: nbt.string("fixture-msa-id-changed-after-dry-run"),
      SelfSignedId: nbt.string("fixture-self-signed-id-changed-after-dry-run"),
    }),
    "little",
  );
  await withDatabase(identityWorld, (database) =>
    database.batch(clientKeys.map((key) => ({ type: "put", key, value })), { sync: true }),
  );
} else if (command === "verify") {
  const [workingWorld, identityWorld, targetKey, ...clientKeys] = args;
  if (!workingWorld || !identityWorld || !targetKey || clientKeys.length === 0) {
    throw new Error("verify requires <working-world> <identity-world> <target-key> <client-key...>");
  }
  const working = new LevelDB(path.join(workingWorld, "db"), { bufferKeys: true, createIfMissing: false });
  const identity = new LevelDB(path.join(identityWorld, "db"), { bufferKeys: true, createIfMissing: false });
  await working.open();
  await identity.open();
  try {
    const source = Buffer.from(await working.get("~local_player"));
    const target = Buffer.from(await working.get(targetKey));
    const digestParts = [Buffer.from("~local_player"), source, Buffer.from(targetKey), target];
    let mappingsEqual = true;
    for (const key of [...clientKeys].sort()) {
      const workingValue = Buffer.from(await working.get(key));
      const identityValue = Buffer.from(await identity.get(key));
      if (!workingValue.equals(identityValue)) mappingsEqual = false;
      digestParts.push(Buffer.from(key), workingValue);
    }
    console.log(
      JSON.stringify({
        sourceTargetBytesEqual: source.equals(target),
        sourceTargetSha256Equal: sha256(source) === sha256(target),
        mappingsEqual,
        relevantWorkingRecordsSha256: sha256(Buffer.concat(digestParts)),
      }),
    );
  } finally {
    await identity.close();
    await working.close();
  }
} else {
  throw new Error("Usage: exercise-leveldb-fixture.mjs <mutate-source|mutate-mappings|verify> ...");
}
