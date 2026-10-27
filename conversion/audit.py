#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit statique des sites autonomes (CONVERSION-SPEC §7, hors tests JSDOM)."""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'comparateur-local')
DISPLAY_CDN = ('website-files.com', 'd3e54v103j8qbb.cloudfront.net',
               'fonts.googleapis.com', 'fonts.gstatic.com', 'ajax.googleapis.com',
               'unpkg.com', 'cdnjs.cloudflare.com', 'cdn.jsdelivr.net',
               'cdn.tailwindcss.com', 'uploads-ssl.webflow.com')
# URL tolorées dans le JS : tracking, endpoints métier (spec §3.2 / §5.4), doc
JS_ALLOWED_HOSTS = ('googletagmanager.com', 'google-analytics.com', 'mc.hellolead.pro',
                    'webflow.com', 'formdata.webflow.com', 'challenges.cloudflare.com',
                    'script.google.com', 'smartarget.online', 'tailwindcss.com/docs',
                    'www.w3.org', 'use.typekit.net', 'github.com', 'apache.org',
                    'videsigns-staging.co.uk')
URL_RE = re.compile(r"""url\(\s*(?:"([^"]*)"|'([^']*)'|([^'")\s]+))\s*\)""")
ATTR_RE = re.compile(r'(?:src|href|poster|data-src|data-poster-url)\s*=\s*"([^"]+)"')


def css_url(m):
    return m.group(1) if m.group(1) is not None else (
        m.group(2) if m.group(2) is not None else m.group(3))


def main():
    stats = json.load(open(os.path.join(ROOT, 'conversion', 'stats.json'), encoding='utf-8'))
    slug_map = stats['slug_map']
    problems = []
    sites = sorted(d for d in os.listdir(OUT) if os.path.isdir(os.path.join(OUT, d))
                   or os.path.exists(os.path.join(OUT, d, 'index.html')))
    sites = [d for d in sites if os.path.exists(os.path.join(OUT, d, 'index.html'))]
    # les sites imbriqués (sous-dossiers)
    for dp, ds, fs in os.walk(OUT):
        if 'index.html' in fs:
            rel = os.path.relpath(dp, OUT).replace('\\', '/')
            if rel != '.' and rel not in sites:
                sites.append(rel)

    # 1. dossier manquant
    missing_dirs = []
    for src, slug in slug_map.items():
        if not os.path.isfile(os.path.join(OUT, slug, 'index.html')):
            missing_dirs.append((src, slug))
    if missing_dirs:
        problems.append(('dossiers manquants', missing_dirs))

    n_sites = len(sites)
    n_assets_missing = 0
    n_cdn = 0
    n_node = 0
    cdn_details, ref_details, node_details = [], [], []

    for slug in sorted(sites):
        site = os.path.join(OUT, slug)
        idx = open(os.path.join(site, 'index.html'), encoding='utf-8').read()
        css = open(os.path.join(site, 'style.css'), encoding='utf-8').read()
        js = open(os.path.join(site, 'script.js'), encoding='utf-8').read()

        # 2. références locales existantes
        refs = set()
        for m in ATTR_RE.finditer(idx):
            v = m.group(1).split('#')[0].split('?')[0]
            if v and not v.startswith(('http', 'data:', '//', 'mailto:', 'tel:', 'javascript:')):
                refs.add(v)
        for m in URL_RE.finditer(idx):
            v = css_url(m).split('#')[0].split('?')[0]
            if v and not v.startswith(('http', 'data:', '//', '#')):
                refs.add(v)
        for m in URL_RE.finditer(css):
            v = css_url(m).split('#')[0].split('?')[0]
            if v and not v.startswith(('http', 'data:', '//', '#')):
                refs.add(v)
        for r in sorted(refs):
            if not os.path.exists(os.path.join(site, r)):
                n_assets_missing += 1
                ref_details.append(f'{slug}: {r}')

        # 3. CDN d'affichage résiduels (html / css : tolérance zéro)
        for host in DISPLAY_CDN:
            if host in idx or host in css:
                n_cdn += 1
                cdn_details.append(f'{slug}: {host} (index/style)')
        # script.js : uniquement des hôtes non listés comme tolérables
        for u in re.findall(r'https?://[^\s"\'`<>\\)]+', js):
            if any(h in u for h in DISPLAY_CDN):
                n_cdn += 1
                cdn_details.append(f'{slug}: {u[:110]}')

        # 4. node --check
        r = subprocess.run(['node', '--check', os.path.join(site, 'script.js')],
                           capture_output=True, text=True)
        if r.returncode != 0:
            n_node += 1
            node_details.append(f'{slug}: {r.stderr.strip()[:160]}')

    # 5. structure obligatoire
    struct_bad = []
    for slug in sites:
        for need in ('index.html', 'style.css', 'script.js', 'img'):
            if not os.path.exists(os.path.join(OUT, slug, need)):
                struct_bad.append(f'{slug}: {need}')

    report = {
        'sites': n_sites,
        'sources': len(slug_map),
        'missing_dirs': missing_dirs,
        'missing_asset_refs': n_assets_missing,
        'cdn_display_refs': n_cdn,
        'node_check_failures': n_node,
        'structure_missing': struct_bad,
        'cdn_details': cdn_details[:20],
        'ref_details': ref_details[:20],
        'node_details': node_details[:20],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    ok = (not missing_dirs and n_assets_missing == 0 and n_cdn == 0
          and n_node == 0 and not struct_bad and n_sites == len(slug_map))
    print('\nAUDIT', 'VERT ✅' if ok else 'ROUGE ❌')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
