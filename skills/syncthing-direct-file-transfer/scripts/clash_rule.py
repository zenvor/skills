#!/usr/bin/env python3
"""Put Syncthing DIRECT first in a standard Clash prepend extension, with backup."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

RULE = 'PROCESS-NAME,syncthing,DIRECT'


def section(lines, name, required=False):
    headers = [i for i, line in enumerate(lines) if re.match(r'^' + name + r'\s*:', line)]
    if not headers and not required:
        return None
    if len(headers) != 1:
        raise ValueError('Expected exactly one ' + name + ' section')
    start = headers[0]
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r'^[A-Za-z_][\w-]*\s*:', lines[i])), len(lines))
    value = lines[start].split(':', 1)[1].strip()
    value, _, comment = value.partition('#')
    if value.strip() not in {'', '[]'}:
        raise ValueError('Unsupported ' + name + ' structure; inspect manually')
    items = []
    for i in range(start + 1, end):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'( *)- +([^\r\n]+)\r?\n?', line)
        if not match or value.strip() == '[]':
            raise ValueError('Unsupported block list in ' + name + '; inspect manually')
        scalar = match.group(2).strip()
        # Decode only single-line scalar entries; never rewrite unrelated entries.
        if scalar.startswith('"'):
            decoder = json.JSONDecoder()
            parsed, offset = decoder.raw_decode(scalar)
            suffix = scalar[offset:].strip()
            if not isinstance(parsed, str) or suffix and not suffix.startswith('#'):
                raise ValueError('Unsupported quoted rule')
        elif scalar.startswith("'"):
            quoted = re.fullmatch(r"'((?:[^']|'')*)'(?:\s+#.*)?", scalar)
            if not quoted:
                raise ValueError('Unsupported quoted rule')
            parsed = quoted.group(1).replace("''", "'")
        else:
            parsed = re.split(r'\s+#', scalar, maxsplit=1)[0].rstrip()
            if parsed.startswith(('&', '*', '!', '[', '{', '|', '>')):
                raise ValueError('Unsupported YAML rule scalar; inspect manually')
        items.append((i, match.group(1), parsed))
    if len({item[1] for item in items}) > 1:
        raise ValueError('Inconsistent list indentation; inspect manually')
    return start, end, items, comment


def revised(text, rule=RULE):
    lines = text.splitlines(keepends=True)
    delete = section(lines, 'delete')
    if delete and any(item[2] == rule for item in delete[2]):
        raise ValueError('DIRECT rule is explicitly in delete; resolve that conflict before applying')
    start, end, items, comment = section(lines, 'prepend', required=True)
    matching = [item[0] for item in items if item[2] == rule]
    if items and items[0][2] == rule and len(matching) == 1:
        return text
    newline = '\r\n' if '\r\n' in text else '\n'
    indent = items[0][1] if items else '  '
    header = 'prepend:' + (' #' + comment if comment else '') + newline
    # Move only this rule; preserve all other rules, ordering and comments.
    remainder = [line for i, line in enumerate(lines[start + 1:end], start + 1) if i not in matching]
    return ''.join(lines[:start] + [header, indent + '- ' + rule + newline] + remainder + lines[end:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True, help='Current profile option.rules extension')
    parser.add_argument('--backup-dir', type=Path, required=True)
    parser.add_argument('--process-name', choices=['syncthing', 'syncthing.exe'], default='syncthing')
    args = parser.parse_args()
    if args.file.is_symlink():
        raise ValueError('Use the actual extension file, not a symlink')
    original = args.file.read_bytes()
    updated = revised(original.decode('utf-8'), 'PROCESS-NAME,' + args.process_name + ',DIRECT').encode('utf-8')
    if original == updated:
        print('DIRECT is already the first prepend rule; no changes made.')
        return
    args.backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = args.backup_dir / (args.file.name + '.' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.bak')
    shutil.copy2(args.file, backup)
    backup.chmod(0o600)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=args.file.parent, prefix=args.file.name + '.', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(args.file.stat().st_mode & 0o777)
        if args.file.read_bytes() != original:
            raise ValueError('Extension changed concurrently; no replacement made')
        os.replace(temporary, args.file)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    print('DIRECT placed first; backup:', backup)
    print('Reapply the current subscription; verify generated order and actual DIRECT traffic.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit('ERROR: ' + str(error))
