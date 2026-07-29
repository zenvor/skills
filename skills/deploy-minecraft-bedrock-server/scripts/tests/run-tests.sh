#!/usr/bin/env bash
set -euo pipefail

scripts_dir=$(cd "$(dirname "$0")/.." && pwd)
if [[ ! -d "${scripts_dir}/node_modules" ]]; then
  printf 'Run npm ci in an isolated copy of %s before running tests.\n' "${scripts_dir}" >&2
  exit 2
fi

test_root=$(mktemp -d /tmp/deploy-minecraft-skill-tests.XXXXXX)
cleanup() {
  case "${test_root}" in
    /tmp/deploy-minecraft-skill-tests.*|/private/tmp/deploy-minecraft-skill-tests.*) rm -rf -- "${test_root}" ;;
  esac
}
trap cleanup EXIT

fixture_json=$(node "${scripts_dir}/tests/create-leveldb-fixtures.mjs" "${test_root}")
working_world=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.workingWorld)' "${fixture_json}")
identity_world=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.identityWorld)' "${fixture_json}")
source_hash=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.sourceSha256)' "${fixture_json}")
target_key=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.targetKey)' "${fixture_json}")
client_one=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.clientKeys[0])' "${fixture_json}")
client_two=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.clientKeys[1])' "${fixture_json}")
wrong_client=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.wrongClientKey)' "${fixture_json}")
missing_identity_client=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.missingIdentityClientKey)' "${fixture_json}")

identity_spec="${test_root}/identity-spec.json"
wrong_identity_spec="${test_root}/wrong-identity-spec.json"
missing_identity_spec="${test_root}/missing-identity-spec.json"
bad_source_spec="${test_root}/bad-source-spec.json"
python3 - "${identity_spec}" "${wrong_identity_spec}" "${missing_identity_spec}" "${bad_source_spec}" \
  "${target_key}" "${client_one}" "${client_two}" "${wrong_client}" "${missing_identity_client}" "${source_hash}" <<'PY'
import json, os, pathlib, sys
base, wrong, missing, bad_source, target, one, two, wrong_client, missing_client, source_hash = sys.argv[1:]
for output, clients in ((base, [one, two]), (wrong, [wrong_client]), (missing, [missing_client])):
    pathlib.Path(output).write_text(json.dumps({
        "targetKey": target,
        "clientKeys": clients,
        "expectedSourceSha256": source_hash,
    }), encoding="utf-8")
    os.chmod(output, 0o600)
pathlib.Path(bad_source).write_text(json.dumps({
    "sourceKey": "metadata_record",
    "targetKey": target,
    "clientKeys": [one, two],
    "expectedSourceSha256": source_hash,
}), encoding="utf-8")
os.chmod(bad_source, 0o600)
PY

node "${scripts_dir}/inspect-bedrock-players.mjs" "${working_world}" > "${test_root}/inspect-redacted.json"
if grep -q 'player_server_\|fixture-msa-id\|working-world' "${test_root}/inspect-redacted.json"; then
  printf 'Default inspector output leaked identifiers\n' >&2
  exit 1
fi
grep -q 'worldPathFingerprint' "${test_root}/inspect-redacted.json"
node "${scripts_dir}/inspect-bedrock-players.mjs" "${identity_world}" --include-identifiers --output "${test_root}/inspect-private.json"
[[ "$(stat -f '%Lp' "${test_root}/inspect-private.json" 2>/dev/null || stat -c '%a' "${test_root}/inspect-private.json")" == "600" ]]
grep -q 'worldName' "${test_root}/inspect-private.json"
set +e
node "${scripts_dir}/inspect-bedrock-players.mjs" "${identity_world}" --include-identifiers > "${test_root}/inspect-unsafe.out" 2> "${test_root}/inspect-unsafe.err"
unsafe_inspect_status=$?
missing_inspector_path="${test_root}/private-inspector-path-marker"
node "${scripts_dir}/inspect-bedrock-players.mjs" "${missing_inspector_path}" > "${test_root}/inspect-missing.out" 2> "${test_root}/inspect-missing.err"
missing_inspector_status=$?
private_inspector_argument="${test_root}/private-inspector-extra-marker"
node "${scripts_dir}/inspect-bedrock-players.mjs" "${working_world}" "${private_inspector_argument}" \
  > "${test_root}/inspect-extra.out" 2> "${test_root}/inspect-extra.err"
extra_inspector_status=$?
set -e
[[ "${unsafe_inspect_status}" -ne 0 ]]
[[ "${missing_inspector_status}" -ne 0 ]]
[[ "${extra_inspector_status}" -ne 0 ]]
if grep -q "${missing_inspector_path}" "${test_root}/inspect-missing.err"; then
  printf 'Inspector error leaked a full private path\n' >&2
  exit 1
fi
if grep -q "${private_inspector_argument}" "${test_root}/inspect-extra.err"; then
  printf 'Inspector error echoed a private extra argument\n' >&2
  exit 1
fi

set +e
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${working_world}" --identity-world "${identity_world}" \
  --identity-spec "${identity_spec}" --output "${test_root}/wrong-digest.json" \
  --apply-plan-sha256 "$(printf '0%.0s' {1..64})" \
  --acknowledge-community-migration --apply \
  > "${test_root}/wrong-digest.out" 2> "${test_root}/wrong-digest.err"
wrong_digest_status=$?
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${working_world}" --identity-world "${identity_world}" \
  --identity-spec "${identity_spec}" --output "${test_root}/plan.json" \
  > "${test_root}/plan.stdout" 2> "${test_root}/plan.stderr"
dry_status=$?
set -e
[[ "${dry_status}" -eq 3 ]]
[[ ! -s "${test_root}/plan.stdout" ]]
[[ "$(stat -f '%Lp' "${test_root}/plan.json" 2>/dev/null || stat -c '%a' "${test_root}/plan.json")" == "600" ]]
plan_digest=$(node -e 'const x=JSON.parse(require("fs").readFileSync(process.argv[1])); process.stdout.write(x.planDigest)' "${test_root}/plan.json")
node - "${test_root}/plan.json" "${scripts_dir}/migrate-bedrock-local-player.mjs" "${scripts_dir}/package-lock.json" <<'NODE'
const crypto = require("crypto");
const fs = require("fs");
const [planPath, toolPath, packageLockPath] = process.argv.slice(2);
const report = JSON.parse(fs.readFileSync(planPath));
const toolSha256 = crypto.createHash("sha256").update(fs.readFileSync(toolPath)).digest("hex");
const packageLockSha256 = crypto.createHash("sha256").update(fs.readFileSync(packageLockPath)).digest("hex");
if (report.plan.planVersion !== "bedrock-local-player-migration-v3") process.exit(1);
if (report.plan.toolSha256 !== toolSha256) process.exit(1);
if (report.plan.runtime.nodeVersion !== process.version) process.exit(1);
if (report.plan.runtime.platform !== process.platform) process.exit(1);
if (report.plan.runtime.arch !== process.arch) process.exit(1);
if (report.plan.runtime.packageLockSha256 !== packageLockSha256) process.exit(1);
NODE

set +e
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${working_world}" --identity-world "${identity_world}" \
  --identity-spec "${bad_source_spec}" --output "${test_root}/bad-source-report.json" \
  > "${test_root}/bad-source.out" 2> "${test_root}/bad-source.err"
bad_source_status=$?
set -e
[[ "${bad_source_status}" -ne 0 ]]

private_migration_argument="${test_root}/private-migration-extra-marker"
set +e
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${working_world}" --identity-world "${identity_world}" \
  --identity-spec "${identity_spec}" --output "${test_root}/extra-argument-report.json" \
  "${private_migration_argument}" \
  > "${test_root}/migration-extra.out" 2> "${test_root}/migration-extra.err"
extra_migration_status=$?
set -e
[[ "${extra_migration_status}" -ne 0 ]]
if grep -q "${private_migration_argument}" "${test_root}/migration-extra.err"; then
  printf 'Migration error echoed a private extra argument\n' >&2
  exit 1
fi

insecure_spec="${test_root}/insecure-identity-spec.json"
cp "${identity_spec}" "${insecure_spec}"
chmod 0644 "${insecure_spec}"
missing_world="${test_root}/private-world-marker-does-not-exist"
set +e
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${working_world}" --identity-world "${identity_world}" \
  --identity-spec "${insecure_spec}" --output "${test_root}/insecure-spec-report.json" \
  > "${test_root}/insecure-spec.out" 2> "${test_root}/insecure-spec.err"
insecure_spec_status=$?
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${missing_world}" --identity-world "${identity_world}" \
  --identity-spec "${identity_spec}" --output "${test_root}/missing-world-report.json" \
  > "${test_root}/missing-world.out" 2> "${test_root}/missing-world.err"
missing_world_status=$?
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${working_world}" --identity-world "${identity_world}" \
  --identity-spec "${identity_spec}" --output "${test_root}/plan.json" \
  > "${test_root}/existing-report.out" 2> "${test_root}/existing-report.err"
existing_report_status=$?
set -e
[[ "${insecure_spec_status}" -ne 0 ]]
[[ "${missing_world_status}" -ne 0 ]]
[[ "${existing_report_status}" -ne 0 ]]
if grep -q "${missing_world}\|${test_root}/plan.json" \
  "${test_root}/missing-world.err" "${test_root}/existing-report.err"; then
  printf 'Migration filesystem error leaked a full private path\n' >&2
  exit 1
fi

set +e
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${working_world}" --identity-world "${identity_world}" \
  --identity-spec "${identity_spec}" --output "${test_root}/missing-digest.json" \
  --acknowledge-community-migration --apply \
  > "${test_root}/missing-digest.out" 2> "${test_root}/missing-digest.err"
missing_digest_status=$?
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${working_world}" --identity-world "${identity_world}" \
  --identity-spec "${wrong_identity_spec}" --output "${test_root}/wrong-map.json" \
  > "${test_root}/wrong-map.out" 2> "${test_root}/wrong-map.err"
wrong_map_status=$?
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${working_world}" --identity-world "${identity_world}" \
  --identity-spec "${missing_identity_spec}" --output "${test_root}/missing-identity.json" \
  > "${test_root}/missing-identity.out" 2> "${test_root}/missing-identity.err"
missing_identity_status=$?
set -e
[[ "${wrong_digest_status}" -ne 0 ]]
[[ "${missing_digest_status}" -ne 0 ]]
[[ "${wrong_map_status}" -ne 0 ]]
[[ "${missing_identity_status}" -ne 0 ]]
if grep -q "${target_key}\|${wrong_client}\|${missing_identity_client}" \
  "${test_root}/wrong-map.err" "${test_root}/missing-identity.err"; then
  printf 'Migration error output leaked full player keys\n' >&2
  exit 1
fi

source_mutation_root="${test_root}/source-mutation"
source_mutation_json=$(node "${scripts_dir}/tests/create-leveldb-fixtures.mjs" "${source_mutation_root}")
source_mutation_working=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.workingWorld)' "${source_mutation_json}")
source_mutation_identity=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.identityWorld)' "${source_mutation_json}")
source_mutation_hash=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.sourceSha256)' "${source_mutation_json}")
source_mutation_target=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.targetKey)' "${source_mutation_json}")
source_mutation_one=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.clientKeys[0])' "${source_mutation_json}")
source_mutation_two=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.clientKeys[1])' "${source_mutation_json}")
source_mutation_spec="${source_mutation_root}/spec.json"
python3 - "${source_mutation_spec}" "${source_mutation_target}" "${source_mutation_one}" "${source_mutation_two}" "${source_mutation_hash}" <<'PY'
import json, os, pathlib, sys
output, target, one, two, source_hash = sys.argv[1:]
pathlib.Path(output).write_text(json.dumps({
    "targetKey": target,
    "clientKeys": [one, two],
    "expectedSourceSha256": source_hash,
}), encoding="utf-8")
os.chmod(output, 0o600)
PY
set +e
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${source_mutation_working}" --identity-world "${source_mutation_identity}" \
  --identity-spec "${source_mutation_spec}" --output "${source_mutation_root}/plan.json" \
  > "${source_mutation_root}/plan.out" 2> "${source_mutation_root}/plan.err"
source_mutation_dry_status=$?
set -e
[[ "${source_mutation_dry_status}" -eq 3 ]]
source_mutation_digest=$(node -e 'const x=JSON.parse(require("fs").readFileSync(process.argv[1])); process.stdout.write(x.planDigest)' "${source_mutation_root}/plan.json")
changed_source_hash=$(node "${scripts_dir}/tests/exercise-leveldb-fixture.mjs" mutate-source "${source_mutation_working}")
python3 - "${source_mutation_spec}" "${changed_source_hash}" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
data["expectedSourceSha256"] = sys.argv[2]
path.write_text(json.dumps(data), encoding="utf-8")
PY
set +e
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${source_mutation_working}" --identity-world "${source_mutation_identity}" \
  --identity-spec "${source_mutation_spec}" --output "${source_mutation_root}/apply.json" \
  --apply-plan-sha256 "${source_mutation_digest}" --acknowledge-community-migration --apply \
  > "${source_mutation_root}/apply.out" 2> "${source_mutation_root}/apply.err"
source_mutation_apply_status=$?
set -e
[[ "${source_mutation_apply_status}" -ne 0 ]]
grep -q 'Plan digest mismatch' "${source_mutation_root}/apply.err"

mapping_mutation_root="${test_root}/mapping-mutation"
mapping_mutation_json=$(node "${scripts_dir}/tests/create-leveldb-fixtures.mjs" "${mapping_mutation_root}")
mapping_mutation_working=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.workingWorld)' "${mapping_mutation_json}")
mapping_mutation_identity=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.identityWorld)' "${mapping_mutation_json}")
mapping_mutation_hash=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.sourceSha256)' "${mapping_mutation_json}")
mapping_mutation_target=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.targetKey)' "${mapping_mutation_json}")
mapping_mutation_one=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.clientKeys[0])' "${mapping_mutation_json}")
mapping_mutation_two=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.clientKeys[1])' "${mapping_mutation_json}")
mapping_mutation_spec="${mapping_mutation_root}/spec.json"
python3 - "${mapping_mutation_spec}" "${mapping_mutation_target}" "${mapping_mutation_one}" "${mapping_mutation_two}" "${mapping_mutation_hash}" <<'PY'
import json, os, pathlib, sys
output, target, one, two, source_hash = sys.argv[1:]
pathlib.Path(output).write_text(json.dumps({
    "targetKey": target,
    "clientKeys": [one, two],
    "expectedSourceSha256": source_hash,
}), encoding="utf-8")
os.chmod(output, 0o600)
PY
set +e
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${mapping_mutation_working}" --identity-world "${mapping_mutation_identity}" \
  --identity-spec "${mapping_mutation_spec}" --output "${mapping_mutation_root}/plan.json" \
  > "${mapping_mutation_root}/plan.out" 2> "${mapping_mutation_root}/plan.err"
mapping_mutation_dry_status=$?
set -e
[[ "${mapping_mutation_dry_status}" -eq 3 ]]
mapping_mutation_digest=$(node -e 'const x=JSON.parse(require("fs").readFileSync(process.argv[1])); process.stdout.write(x.planDigest)' "${mapping_mutation_root}/plan.json")
node "${scripts_dir}/tests/exercise-leveldb-fixture.mjs" mutate-mappings \
  "${mapping_mutation_identity}" "${mapping_mutation_target}" "${mapping_mutation_one}" "${mapping_mutation_two}"
set +e
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${mapping_mutation_working}" --identity-world "${mapping_mutation_identity}" \
  --identity-spec "${mapping_mutation_spec}" --output "${mapping_mutation_root}/apply.json" \
  --apply-plan-sha256 "${mapping_mutation_digest}" --acknowledge-community-migration --apply \
  > "${mapping_mutation_root}/apply.out" 2> "${mapping_mutation_root}/apply.err"
mapping_mutation_apply_status=$?
set -e
[[ "${mapping_mutation_apply_status}" -ne 0 ]]
grep -q 'Plan digest mismatch' "${mapping_mutation_root}/apply.err"

node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${working_world}" --identity-world "${identity_world}" \
  --identity-spec "${identity_spec}" --apply-plan-sha256 "${plan_digest}" \
  --output "${test_root}/apply.json" --acknowledge-community-migration --apply \
  > "${test_root}/apply.stdout"
node -e 'const x=JSON.parse(require("fs").readFileSync(process.argv[1])); if (!x.verification) process.exit(1)' "${test_root}/apply.json"
verification_json=$(node "${scripts_dir}/tests/exercise-leveldb-fixture.mjs" verify \
  "${working_world}" "${identity_world}" "${target_key}" "${client_one}" "${client_two}")
node -e 'const x=JSON.parse(process.argv[1]); if (!x.sourceTargetBytesEqual || !x.sourceTargetSha256Equal || !x.mappingsEqual) process.exit(1)' "${verification_json}"
before_repeat_digest=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.relevantWorkingRecordsSha256)' "${verification_json}")
set +e
node "${scripts_dir}/migrate-bedrock-local-player.mjs" \
  --working-world "${working_world}" --identity-world "${identity_world}" \
  --identity-spec "${identity_spec}" --apply-plan-sha256 "${plan_digest}" \
  --output "${test_root}/repeat-apply.json" --acknowledge-community-migration --apply \
  > "${test_root}/repeat-apply.out" 2> "${test_root}/repeat-apply.err"
repeat_apply_status=$?
set -e
[[ "${repeat_apply_status}" -ne 0 ]]
after_repeat_json=$(node "${scripts_dir}/tests/exercise-leveldb-fixture.mjs" verify \
  "${working_world}" "${identity_world}" "${target_key}" "${client_one}" "${client_two}")
after_repeat_digest=$(node -e 'const x=JSON.parse(process.argv[1]); process.stdout.write(x.relevantWorkingRecordsSha256)' "${after_repeat_json}")
[[ "${before_repeat_digest}" == "${after_repeat_digest}" ]]

pack_world="${test_root}/pack-world"
mkdir -p "${pack_world}/db" "${pack_world}/behavior_packs/bp" "${pack_world}/resource_packs/rp"
: > "${pack_world}/level.dat"
python3 - "${pack_world}" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
behavior = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
resource = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
(root / "behavior_packs/bp/manifest.json").write_text(json.dumps({
    "format_version": 2,
    "header": {"name": "bp", "uuid": behavior, "version": [1, 0, 0]},
    "modules": [{"type": "data", "uuid": "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "version": [1, 0, 0]}],
    "dependencies": [{"uuid": resource, "version": [1, 0, 0]}],
}), encoding="utf-8")
(root / "resource_packs/rp/manifest.json").write_text(json.dumps({
    "format_version": 2,
    "header": {"name": "rp", "uuid": resource, "version": [1, 0, 0]},
    "modules": [{"type": "resources", "uuid": "dddddddd-dddd-4ddd-8ddd-dddddddddddd", "version": [1, 0, 0]}],
}), encoding="utf-8")
(root / "world_behavior_packs.json").write_text(json.dumps([{"pack_id": behavior, "version": [1, 0, 0]}]), encoding="utf-8")
(root / "world_resource_packs.json").write_text(json.dumps([{"pack_id": resource, "version": [1, 0, 0]}]), encoding="utf-8")
PY
python3 "${scripts_dir}/check-bedrock-pack-bindings.py" "${pack_world}" > "${test_root}/pack-ok.out"
python3 - "${pack_world}" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1]) / "world_behavior_packs.json"
data = json.loads(path.read_text())
data.append(dict(data[0]))
path.write_text(json.dumps(data))
PY
set +e
python3 "${scripts_dir}/check-bedrock-pack-bindings.py" "${pack_world}" > "${test_root}/pack-duplicate.out" 2> "${test_root}/pack-duplicate.err"
duplicate_status=$?
set -e
[[ "${duplicate_status}" -ne 0 ]]

secret='fixture-secret-value'
python3 -c 'import time; time.sleep(20)' --token "${secret}" &
secret_pid=$!
"${scripts_dir}/audit-linux-minecraft-host.sh" > "${test_root}/audit-default.out"
"${scripts_dir}/audit-linux-minecraft-host.sh" --include-command-lines > "${test_root}/audit-command-lines.out"
kill "${secret_pid}" 2>/dev/null || true
wait "${secret_pid}" 2>/dev/null || true
if grep -q "${secret}" "${test_root}/audit-default.out" "${test_root}/audit-command-lines.out"; then
  printf 'Audit output leaked a command-line secret\n' >&2
  exit 1
fi
printf '%s\n' \
  "123 user proxy --token ${secret}" \
  "124 user proxy --password=${secret}" \
  "125 user proxy https://example.invalid/subscription?token=${secret}" \
  "126 user proxy Authorization Bearer ${secret}" \
  | awk -f "${scripts_dir}/redact-command-lines.awk" > "${test_root}/redaction-fixture.out"
if grep -q "${secret}" "${test_root}/redaction-fixture.out"; then
  printf 'Command-line redactor leaked a fixture secret\n' >&2
  exit 1
fi
[[ "$(grep -o '\[REDACTED\]\|\[REDACTED_URL\]' "${test_root}/redaction-fixture.out" | wc -l | tr -d ' ')" -ge 4 ]]

if [[ "${SKIP_RAKNET_TESTS:-false}" != true ]]; then
  valid_port_file="${test_root}/valid-port"
  python3 "${scripts_dir}/tests/fake-raknet-server.py" --port-file "${valid_port_file}" --mode valid &
  valid_pid=$!
  while [[ ! -s "${valid_port_file}" ]]; do sleep 0.05; done
  python3 "${scripts_dir}/probe-bedrock.py" 127.0.0.1 "$(cat "${valid_port_file}")" > "${test_root}/probe-valid.out"
  wait "${valid_pid}"

  truncated_port_file="${test_root}/truncated-port"
  python3 "${scripts_dir}/tests/fake-raknet-server.py" --port-file "${truncated_port_file}" --mode truncated &
  truncated_pid=$!
  while [[ ! -s "${truncated_port_file}" ]]; do sleep 0.05; done
  set +e
  python3 "${scripts_dir}/probe-bedrock.py" 127.0.0.1 "$(cat "${truncated_port_file}")" > "${test_root}/probe-truncated.out" 2> "${test_root}/probe-truncated.err"
  truncated_status=$?
  set -e
  wait "${truncated_pid}"
  [[ "${truncated_status}" -eq 2 ]]
else
  printf 'Skipped RakNet socket tests because SKIP_RAKNET_TESTS=true.\n'
fi

printf 'All deploy-minecraft-bedrock-server regression tests passed.\n'
