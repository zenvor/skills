#!/usr/bin/env python3
import argparse
import json
import sys
import uuid
from pathlib import Path


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def normalize_version(value):
    if not isinstance(value, list) or len(value) != 3:
        return None
    try:
        return tuple(int(part) for part in value)
    except (TypeError, ValueError):
        return None


def normalize_uuid(value):
    try:
        return str(uuid.UUID(str(value))).lower()
    except (ValueError, TypeError, AttributeError):
        return None


def scan_pack_container(container: Path, expected_kind: str, packs: dict, errors: list):
    if not container.is_dir():
        return
    for manifest_path in sorted(container.glob("*/manifest.json")):
        try:
            manifest = read_json(manifest_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        header = manifest.get("header") or {}
        pack_id = normalize_uuid(header.get("uuid"))
        version = normalize_version(header.get("version"))
        module_types = sorted(
            str(module.get("type"))
            for module in manifest.get("modules", [])
            if isinstance(module, dict) and module.get("type")
        )
        if not pack_id or version is None:
            errors.append(f"invalid header uuid/version: {manifest_path}")
            continue
        expected_modules = {"data", "script"} if expected_kind == "behavior" else {"resources"}
        if not expected_modules.intersection(module_types):
            errors.append(
                f"{expected_kind} pack has incompatible module types {module_types}: {manifest_path}"
            )
        if pack_id in packs:
            errors.append(f"duplicate pack UUID {pack_id}: {packs[pack_id]['manifest']} and {manifest_path}")
            continue
        packs[pack_id] = {
            "kind": expected_kind,
            "version": version,
            "manifest": str(manifest_path),
            "name": header.get("name"),
            "modules": module_types,
            "dependencies": manifest.get("dependencies", []),
        }


def load_bindings(path: Path, kind: str, errors: list):
    if not path.exists():
        return []
    try:
        data = read_json(path)
    except ValueError as exc:
        errors.append(str(exc))
        return []
    if not isinstance(data, list):
        errors.append(f"binding file must be an array: {path}")
        return []
    result = []
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            errors.append(f"invalid binding at {path}:{index}")
            continue
        pack_id = normalize_uuid(entry.get("pack_id"))
        version = normalize_version(entry.get("version"))
        if not pack_id or version is None:
            errors.append(f"invalid pack_id/version at {path}:{index}")
            continue
        result.append((kind, pack_id, version, str(path), index))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Bedrock world pack UUID/version bindings")
    parser.add_argument("world", type=Path)
    parser.add_argument(
        "--shared-root",
        type=Path,
        help="Optional BDS root containing shared behavior_packs and resource_packs",
    )
    args = parser.parse_args()
    world = args.world.resolve()
    if not (world / "db").is_dir() or not (world / "level.dat").is_file():
        parser.error(f"not a Bedrock world root: {world}")

    errors = []
    warnings = []
    packs = {}
    scan_pack_container(world / "behavior_packs", "behavior", packs, errors)
    scan_pack_container(world / "resource_packs", "resource", packs, errors)
    if args.shared_root:
        shared = args.shared_root.resolve()
        scan_pack_container(shared / "behavior_packs", "behavior", packs, errors)
        scan_pack_container(shared / "resource_packs", "resource", packs, errors)

    bindings = []
    bindings += load_bindings(world / "world_behavior_packs.json", "behavior", errors)
    bindings += load_bindings(world / "world_resource_packs.json", "resource", errors)
    bound_ids = set()
    seen_bindings = set()

    for kind, pack_id, version, source, index in bindings:
        binding_key = (kind, pack_id)
        if binding_key in seen_bindings:
            errors.append(f"duplicate {kind} binding for {pack_id} ({source}:{index})")
        seen_bindings.add(binding_key)
        bound_ids.add(pack_id)
        pack = packs.get(pack_id)
        if pack is None:
            errors.append(f"bound {kind} pack {pack_id} {version} is missing ({source}:{index})")
            continue
        if pack["kind"] != kind:
            errors.append(f"pack {pack_id} is bound as {kind} but found under {pack['kind']}_packs")
        if pack["version"] != version:
            errors.append(
                f"pack {pack_id} binding version {version} != manifest version {pack['version']}"
            )

    for pack_id, pack in packs.items():
        dependencies = pack.get("dependencies")
        if dependencies is None:
            continue
        if not isinstance(dependencies, list):
            errors.append(f"manifest dependencies must be an array: {pack['manifest']}")
            continue
        for dependency in dependencies:
            if not isinstance(dependency, dict):
                errors.append(f"invalid dependency entry in {pack['manifest']}")
                continue
            if dependency.get("module_name"):
                warnings.append(
                    f"runtime module dependency {dependency['module_name']!r} cannot be validated offline: {pack['manifest']}"
                )
                continue
            dependency_id = normalize_uuid(dependency.get("uuid"))
            dependency_version = normalize_version(dependency.get("version"))
            if not dependency_id or dependency_version is None:
                errors.append(f"invalid UUID dependency in {pack['manifest']}: {dependency!r}")
                continue
            resolved = packs.get(dependency_id)
            if resolved is None:
                errors.append(
                    f"pack {pack_id} requires missing pack {dependency_id} {dependency_version}"
                )
            elif resolved["version"] != dependency_version:
                errors.append(
                    f"pack {pack_id} requires {dependency_id} {dependency_version}, found {resolved['version']}"
                )

    for pack_id, pack in packs.items():
        if pack_id not in bound_ids:
            warnings.append(f"unbound {pack['kind']} pack {pack_id} {pack['version']}: {pack['manifest']}")

    for pack_id, pack in sorted(packs.items()):
        print(
            f"PACK kind={pack['kind']} uuid={pack_id} version={'.'.join(map(str, pack['version']))} "
            f"name={pack['name']!r} modules={','.join(pack['modules'])}"
        )
    for kind, pack_id, version, source, index in bindings:
        print(f"BINDING kind={kind} uuid={pack_id} version={'.'.join(map(str, version))} source={source}:{index}")
    for warning in warnings:
        print(f"WARNING {warning}", file=sys.stderr)
    for error in errors:
        print(f"ERROR {error}", file=sys.stderr)
    print(f"SUMMARY packs={len(packs)} bindings={len(bindings)} warnings={len(warnings)} errors={len(errors)}")
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
