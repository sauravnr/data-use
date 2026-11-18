"""Checks data files before the apps get them (run by .github/workflows/check-data.yml).

- Every data/*.json given on the command line must be valid JSON with a whole-number
  "version" (the apps only take a file whose version went up).
- data/announcements*.json must carry a valid signature from the Sahaj Patro notices
  key. The full rules for a notice live in the app (src/utils/noticesCore.js) and its
  publishing script (scripts/notices.mjs), which refuses to sign a bad notice; the app
  also skips any notice that breaks them.

Exit code 1 (red run, no CDN refresh) when something is wrong.
"""
import base64
import glob
import json
import os
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Public half of the notices key (same as src/constants/noticesKey.js in the app).
NOTICES_PUBLIC_KEY = 'K+HmITjyHe5GfzK/laszTr2kILvB7ULjkbA5K1UwKk8='

# Files the scrapers rewrite every few minutes; they carry no "version".
NO_VERSION = {
    'dhm.json', 'dhm_history.json', 'forex.json', 'fuel.json', 'gold_silver.json',
    'gold_silver_history.json', 'issues_current.json', 'issues_upcoming.json',
    'metar.json', 'sectors.json', 'vegetables.json', 'rashifal.json', 'weather.json',
}


def signed_text(data):
    # Same bytes as canonicalJson() in noticesCore.js: sorted keys, no spaces,
    # UTF-8 text without \\u escapes for non-ASCII characters.
    body = {'version': data['version'], 'updatedAt': data['updatedAt'], 'items': data['items']}
    return json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def check_announcements(path, data):
    problems = []
    if not isinstance(data.get('items'), list):
        problems.append('items must be a list')
    if not isinstance(data.get('updatedAt'), str):
        problems.append('updatedAt is missing')
    if problems:
        return problems
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(NOTICES_PUBLIC_KEY))
        key.verify(base64.b64decode(data.get('signature', ''), validate=True), signed_text(data))
    except (InvalidSignature, ValueError, TypeError):
        problems.append('signature is missing or wrong: sign it with "node scripts/notices.mjs sign" in the app folder')
    return problems


def check(path):
    name = os.path.basename(path)
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return [f'not valid JSON: {e}']
    problems = []
    if name not in NO_VERSION and not name.startswith('weather'):
        v = data.get('version') if isinstance(data, dict) else None
        if not isinstance(v, int) or isinstance(v, bool):
            problems.append('"version" must be a whole number')
    if name.startswith('announcements'):
        problems += check_announcements(path, data)
    return problems


def main(paths):
    # The notices files are always checked; other files when they changed.
    targets = sorted(set(os.path.normpath(p) for p in paths if p.endswith('.json') and os.path.exists(p))
                     | set(os.path.normpath(p) for p in glob.glob('data/announcements*.json')))
    failed = False
    for p in targets:
        problems = check(p)
        if problems:
            failed = True
            for x in problems:
                print(f'::error file={p}::{x}')
        else:
            print(f'ok  {p}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
