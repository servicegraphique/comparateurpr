#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Balaie les 138 sites JSDOM par lots de processus Node isolés (mémoire bornée)."""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'comparateur-local')
HARNESS = os.path.join(ROOT, 'conversion', 'tools', 'audit-jsdom.js')
BATCH = 2
NODE_ARGS = ['--max-old-space-size=1100']


def all_slugs():
    out = []
    for d in sorted(os.listdir(OUT)):
        p = os.path.join(OUT, d)
        if not os.path.isdir(p):
            continue
        if os.path.isfile(os.path.join(p, 'index.html')):
            out.append(d)
        for sub in sorted(os.listdir(p)):
            sp = os.path.join(p, sub)
            if os.path.isdir(sp) and os.path.isfile(os.path.join(sp, 'index.html')):
                out.append(d + '/' + sub)
    return out


def main():
    slugs = all_slugs()
    failures, lines = [], []
    for i in range(0, len(slugs), BATCH):
        batch = slugs[i:i + BATCH]
        r = subprocess.run(['node', *NODE_ARGS, HARNESS, *batch], capture_output=True,
                           text=True, timeout=240)
        out = r.stdout.strip().splitlines()
        for ln in out:
            if re.match(r'^[✅❌]', ln):
                lines.append(ln)
                if ln.startswith('❌'):
                    failures.append(ln)
        if r.returncode != 0 and not any(l.startswith('❌') for l in out):
            failures.append('LOT ' + ' '.join(batch) + ' : ' + r.stderr[:200])
        print(f'lot {i // BATCH + 1}/{(len(slugs) + BATCH - 1) // BATCH} traité', flush=True)
    print('\n'.join(lines))
    ok = len(lines) - len(failures)
    print(f'\nJSDOM : {ok}/{len(slugs)} sites validés (errors=0, form=PASS)')
    if failures:
        print('\nÉCHECS :')
        print('\n'.join(failures))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
