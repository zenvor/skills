import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import leveldbPackage from "@8crafter/leveldb-zlib";
import nbt from "prismarine-nbt";

const { LevelDB } = leveldbPackage;
const root = process.argv[2];
if (!root) throw new Error("Usage: node create-leveldb-fixtures.mjs <empty-test-root>");

const workingWorld = path.join(root, "working-world");
const identityWorld = path.join(root, "identity-world");
fs.mkdirSync(path.join(workingWorld, "db"), { recursive: true });
fs.mkdirSync(path.join(identityWorld, "db"), { recursive: true });

const sourceKey = "~local_player";
const targetKey = "player_server_11111111-1111-4111-8111-111111111111";
const otherTargetKey = "player_server_22222222-2222-4222-8222-222222222222";
const clientKeys = [
  "player_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "player_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
];
const wrongClientKey = "player_cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const missingIdentityClientKey = "player_dddddddd-dddd-4ddd-8ddd-dddddddddddd";

const sourceValue = nbt.writeUncompressed(
  nbt.comp({
    PlayerLevel: nbt.int(21),
    SyntheticMarker: nbt.string("fixture-owner-data"),
  }),
  "little",
);
const emptyTargetValue = nbt.writeUncompressed(nbt.comp({ PlayerLevel: nbt.int(0) }), "little");
const mappingValues = ["MsaId", "MSAId"].map((msaField) =>
  nbt.writeUncompressed(
    nbt.comp({
      ServerId: nbt.string(targetKey),
      [msaField]: nbt.string("fixture-msa-id"),
      SelfSignedId: nbt.string("fixture-self-signed-id"),
    }),
    "little",
  ),
);
const wrongMappingValue = nbt.writeUncompressed(
  nbt.comp({
    ServerId: nbt.string(otherTargetKey),
    MsaId: nbt.string("fixture-other-msa-id"),
    SelfSignedId: nbt.string("fixture-other-self-signed-id"),
  }),
  "little",
);
const missingIdentityMappingValue = nbt.writeUncompressed(
  nbt.comp({ ServerId: nbt.string(targetKey) }),
  "little",
);

const workingDb = new LevelDB(path.join(workingWorld, "db"), { bufferKeys: true, createIfMissing: true });
const identityDb = new LevelDB(path.join(identityWorld, "db"), { bufferKeys: true, createIfMissing: true });
await workingDb.open();
await identityDb.open();
try {
  await workingDb.put(sourceKey, sourceValue, { sync: true });
  await identityDb.batch(
    [
      { type: "put", key: targetKey, value: emptyTargetValue },
      { type: "put", key: otherTargetKey, value: emptyTargetValue },
      ...clientKeys.map((key, index) => ({ type: "put", key, value: mappingValues[index] })),
      { type: "put", key: wrongClientKey, value: wrongMappingValue },
      { type: "put", key: missingIdentityClientKey, value: missingIdentityMappingValue },
    ],
    { sync: true },
  );
} finally {
  await identityDb.close();
  await workingDb.close();
}

console.log(
  JSON.stringify({
    workingWorld,
    identityWorld,
    sourceKey,
    sourceSha256: crypto.createHash("sha256").update(sourceValue).digest("hex"),
    targetKey,
    clientKeys,
    wrongClientKey,
    missingIdentityClientKey,
  }),
);
