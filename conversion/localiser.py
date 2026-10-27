#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
localiser.py — Convertit CHAQUE page du dépôt en site statique autonome
selon CONVERSION-SPEC.md (une LP = un site fonctionnel hors-ligne).

Sortie : comparateur-local/<slug>/{index.html,style.css,script.js,img,fonts}
         comparateur-local/index.html (portail)

Python 3.11 + Pillow (venv conversion/.venv). Aucune autre dépendance.
"""
import argparse
import hashlib
import html as html_mod
import json
import os
import re
import shutil
import sys
import unicodedata
import urllib.parse
from datetime import date, datetime

try:
    from PIL import Image
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONV = os.path.join(ROOT, 'conversion')
VENDOR = os.path.join(CONV, 'vendor')
GFONTS = os.path.join(VENDOR, 'gfonts')
OUT = os.path.join(ROOT, 'comparateur-local')
STATS_PATH = os.path.join(CONV, 'stats.json')

IMG_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.avif', '.gif', '.svg', '.ico'}
FONT_EXT = {'.woff', '.woff2', '.ttf', '.otf', '.eot'}
VID_EXT = {'.mp4', '.webm', '.ogg', '.mov'}
ASSET_EXT = IMG_EXT | FONT_EXT | VID_EXT

CDN_HOSTS = ('cdn.prod.website-files.com', 'd3e54v103j8qbb.cloudfront.net',
             'uploads-ssl.webflow.com')
SMS_URLS = (
    'https://mc.hellolead.pro/api/axialys/envoi_code_verification.php',
    'https://mc.hellolead.pro/mon_compte/api/smspartner/envoi_code_verification.php',
)
KEEP_INLINE_TYPES = {'application/ld+json', 'application/json'}

# Images réellement introuvables (export Webflow incomplet) -> équivalent local
CURATED_FALLBACKS = {
    '676146e067cf1e2d985311a8': 'images/Hero_background-min-p-500.jpg',
    '676146e067cf1e2d985311ae': 'images/15962021516821.jfif.jpg',
    '676146e067cf1e2d985311b4': 'images/Hero_background-min-p-800.jpg',
    '6862464ac77003b786c3b045': 'images/Comparateur-logo.png',
    # exports Webflow incomplets -> fichier équivalent existant
    '672a138e771c900e36753a99': 'images/Emblème-AXA.png',
    '672a138e771c900e36753a99_1200px': 'images/1200px-Assicurazioni_Generali_logo.svg.avif',
    # icône de case à cocher absente -> checkmark Webflow équivalent (cache migration)
    '692404a10d03edd243186f39': 'migration/sites/accueil/img/custom-checkbox-checkmark.589d534424.svg',
}
CURATED_NAME_FALLBACKS = {
    'images/2-1_12-1.png': 'images/2-1_12 (1).png',
    'images/conso-1_1conso-1.png': 'images/conso-1_1conso (1).png',
}

# ----------------------------------------------------------------------
# Utilitaires
# ----------------------------------------------------------------------
def log(msg):
    print(msg, flush=True)


def slugify(name):
    base, ext = os.path.splitext(name)
    b = unicodedata.normalize('NFKD', base).encode('ascii', 'ignore').decode('ascii')
    b = re.sub(r'[^A-Za-z0-9._-]+', '-', b).strip('-.')
    return (b or 'asset') + ext.lower()


def dehash(name):
    """Ôte le préfixe de hash Webflow : 66504b36..._nissan.jpg -> nissan.jpg"""
    return re.sub(r'^[0-9a-f]{24}_', '', name)


def is_assetish(value):
    path = value.split('?')[0].split('#')[0]
    ext = os.path.splitext(path)[1].lower()
    if ext in ASSET_EXT:
        return True
    return bool(re.search(r'/(images|videos|fonts)/', path)) and ext != '.zip'


def resolve_key(value, base_dir):
    v = html_mod.unescape((value or '').strip())
    if len(v) > 1 and v[0] == v[-1] and v[0] in ('"', "'"):
        v = v[1:-1]
    if not v or v.startswith(('data:', '#', 'mailto:', 'tel:', 'javascript:')):
        return None
    if v.startswith('//'):
        v = 'https:' + v
    if v.startswith(('http://', 'https://')):
        return v
    q = v.split('?')[0].split('#')[0]
    q = urllib.parse.unquote(q)
    full = q.lstrip('/') if q.startswith('/') else os.path.normpath(os.path.join(base_dir, q))
    return full.replace('\\', '/')


# ----------------------------------------------------------------------
# Inventaire des pages et slugs
# ----------------------------------------------------------------------
def list_sources():
    out = []
    for dirpath, dirs, files in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT)
        if rel_dir.split(os.sep)[0] in ('.git', 'conversion', 'comparateur-local',
                                        'migration', 'sites', 'node_modules'):
            dirs[:] = []
            continue
        for f in files:
            if f.endswith('.html'):
                p = os.path.normpath(os.path.join(rel_dir, f)) if rel_dir != '.' else f
                out.append(p.replace('\\', '/'))
    return sorted(out)


def slug_for(src, taken):
    if src == 'index.html':
        slug = 'accueil'                       # règle explicite de la spec
    else:
        d, f = os.path.split(src)
        stem = f[:-5]
        stem = re.sub(r'[.-]+$', '', stem)     # ticket-restaurant-.html
        if src == 'accueil.html':
            stem = 'accueil-2'                 # collision avec la règle ci-dessus
        if src == 'ticket-restaurant-.html':
            stem = 'ticket-restaurant-alt'     # collision avec ticket-restaurant.html
        slug = (d + '/' + stem).strip('/') if d != '.' else stem
    base = slug
    i = 2
    while slug in taken:
        slug = f'{base}-{i}'; i += 1
    taken.add(slug)
    return slug


# ----------------------------------------------------------------------
# Caches d'assets (repo local + anciens sites migration + pilote sites/)
# ----------------------------------------------------------------------
class AssetCaches:
    def __init__(self):
        self.by_name = {}          # basename (NFC et NFD, minuscules) -> chemins
        self.by_suffix = {}        # sans préfixe de hash -> chemins
        for base in ('images', 'fonts', 'videos', 'documents', 'css', 'js'):
            self._index(os.path.join(ROOT, base))
        self._index(os.path.join(ROOT, 'migration', 'sites'), only_media=True)
        self._index(os.path.join(ROOT, 'sites'), only_media=True)

    def _index(self, base, only_media=False):
        if not os.path.isdir(base):
            return
        for dp, dirs, files in os.walk(base):
            for f in files:
                p = os.path.join(dp, f)
                low = f.lower()
                if only_media and not (('/img' + os.sep in p) or ('/fonts' + os.sep in p)
                                       or ('/videos' + os.sep in p)):
                    continue
                for variant in {low, unicodedata.normalize('NFD', low)}:
                    self.by_name.setdefault(variant, []).append(p)
                    suf = dehash(variant)
                    if suf != variant:
                        self.by_suffix.setdefault(suf, []).append(p)

    def lookup(self, name):
        low = name.lower()
        for key in (low, unicodedata.normalize('NFD', low)):
            if key in self.by_name:
                return self.by_name[key][0]
        suf = dehash(low)
        if suf in self.by_suffix:
            return self.by_suffix[suf][0]
        if suf in self.by_name:
            return self.by_name[suf][0]
        return None


# ----------------------------------------------------------------------
# Magasin d'assets d'un site
# ----------------------------------------------------------------------
PLACEHOLDER_SVG = (
    '<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg" '
    'width="540" height="320" viewBox="0 0 540 320"><rect width="100%" height="100%" '
    'fill="#e9edf2"/><text x="50%" y="50%" fill="#8a94a3" font-family="sans-serif" '
    'font-size="22" text-anchor="middle" dominant-baseline="middle">Image indisponible</text></svg>'
)


class Store:
    def __init__(self, site_dir, caches, warnings):
        self.dir = site_dir
        self.caches = caches
        self.warnings = warnings
        self.mapping = {}          # clé -> chemin relatif (img/x.png)
        self.taken = set()
        self.by_hash = {}
        self.missing_video = set()

    def _dest_name(self, src_path, prefer_ext=None):
        name = slugify(os.path.basename(urllib.parse.unquote(src_path.split('?')[0])))
        if prefer_ext and not name.lower().endswith(prefer_ext):
            name = os.path.splitext(name)[0] + prefer_ext
        return name

    def _place(self, data, name, kind):
        h = hashlib.md5(data).hexdigest()
        if h in self.by_hash:
            return self.by_hash[h]
        folder = 'fonts' if kind == 'font' else 'img'
        local = f'{folder}/{name}'
        if local in self.taken:
            stem, ext = os.path.splitext(name)
            local = f'{folder}/{stem}-{h[:6]}{ext}'
        self.taken.add(local)
        dest = os.path.join(self.dir, local)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'wb') as fh:
            fh.write(data)
        self.by_hash[h] = local
        self._optimize(dest, name)
        return local

    def _optimize(self, dest, name):
        """CONVERSION-SPEC §6 : >40 Ko, largeur max ~540 px, JPEG/WEBP q55, PNG 64 couleurs."""
        if not HAVE_PIL:
            return
        try:
            if os.path.getsize(dest) <= 40 * 1024:
                return
            ext = os.path.splitext(name)[1].lower()
            if ext in ('.svg', '.gif', '.ico', '.avif'):
                return
            im = Image.open(dest)
            w, h = im.size
            if w > 540:
                im = im.resize((540, max(1, round(h * 540 / w))), Image.LANCZOS)
            tmp = dest + '.opt'
            if ext in ('.jpg', '.jpeg'):
                im.convert('RGB').save(tmp, 'JPEG', quality=55, optimize=True, progressive=True)
            elif ext == '.webp':
                im.save(tmp, 'WEBP', quality=55, method=6)
            elif ext == '.png':
                q = im.quantize(colors=64, method=Image.FASTOCTREE) if im.mode in ('RGB', 'RGBA', 'P') else im
                q.save(tmp, 'PNG', optimize=True)
            else:
                return
            if os.path.getsize(tmp) < os.path.getsize(dest):
                os.replace(tmp, dest)
            else:
                os.remove(tmp)
        except Exception:
            if os.path.exists(dest + '.opt'):
                try: os.remove(dest + '.opt')
                except OSError: pass

    def _read_local(self, path):
        for cand in (path, unicodedata.normalize('NFC', path),
                     unicodedata.normalize('NFD', path)):
            fp = os.path.join(ROOT, cand)
            if os.path.isfile(fp):
                return fp
        return None

    def get(self, key):
        """Retourne le chemin relatif local pour une clé, ou None."""
        if key in self.mapping:
            return self.mapping[key]
        ext = os.path.splitext(key.split('?')[0])[1].lower()
        kind = 'font' if ext in FONT_EXT else 'media'
        local_path, name = None, None

        if key.startswith(('http://', 'https://')):
            decoded = urllib.parse.unquote(key.split('?')[0]).replace('%2F', '/')
            bn = os.path.basename(decoded)
            if ext in VID_EXT:                       # vidéos manquantes (MISSING.txt)
                self.missing_video.add(key)
                return None
            for hashid, fb in CURATED_FALLBACKS.items():
                if hashid in key:
                    local_path = os.path.join(ROOT, fb)
                    name = self._dest_name(fb); break
            if not local_path:
                hit = self.caches.lookup(bn)
                if hit:
                    local_path, name = hit, self._dest_name(bn)
        else:
            fp = self._read_local(key)
            if fp:
                local_path, name = fp, self._dest_name(key)
            elif key in CURATED_NAME_FALLBACKS:
                fb = CURATED_NAME_FALLBACKS[key]
                fp2 = self._read_local(fb)
                if fp2:
                    local_path, name = fp2, self._dest_name(fb)
            if not local_path:
                bn = os.path.basename(key)
                hit = self.caches.lookup(bn)
                if hit:
                    local_path, name = hit, self._dest_name(bn)

        if local_path and os.path.isfile(local_path):
            with open(local_path, 'rb') as fh:
                data = fh.read()
            rel = self._place(data, name, kind)
            self.mapping[key] = rel
            return rel

        # dernier recours : placeholder pour une image
        if ext in IMG_EXT:
            rel = self._place(PLACEHOLDER_SVG.encode('utf-8'),
                              self._dest_name(key, '.svg'), 'media')
            self.mapping[key] = rel
            self.warnings.append(f'asset introuvable -> placeholder : {key}')
            return rel
        if ext in VID_EXT:
            self.missing_video.add(key)
        self.warnings.append(f'asset introuvable (référence neutralisée) : {key}')
        return None


# ----------------------------------------------------------------------
# CSS : découpage et purge conservatrice (empruntés à l'usine éprouvée)
# ----------------------------------------------------------------------
def split_css(css):
    chunks, i, n = [], 0, len(css)
    start, depth = 0, 0
    instr, com = None, False
    while i < n:
        c = css[i]
        if com:
            if c == '*' and css.startswith('/', i + 1):
                com = False; i += 2; continue
        elif instr:
            if c == '\\':
                i += 2; continue
            if c == instr:
                instr = None
        elif c == '/' and css.startswith('*', i + 1):
            com = True
        elif c in ('"', "'"):
            instr = c
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                chunks.append(css[start:i + 1]); start = i + 1
        i += 1
    tail = css[start:]
    if tail.strip():
        chunks.append(tail)
    return chunks


def _sel_of(chunk):
    sel = chunk.split('{', 1)[0]
    return re.sub(r'/\*.*?\*/', '', sel, flags=re.S).strip()


def purge_parts(parts, page_text, classes, ids):
    ctx = {'ff': []}

    def keep_sel(sel):
        toks = re.findall(r'([.#])([-\w]+)', sel)
        if not toks:
            return True
        for kind, nm in toks:
            if kind == '.':
                if nm in classes or ('.' + nm) in page_text or nm.startswith('w-'):
                    return True
            else:
                if nm in ids or ('#' + nm) in page_text:
                    return True
        return False

    def filt(chunk, idx):
        sel = _sel_of(chunk)
        if not sel:
            return chunk
        if sel.startswith('@font-face'):
            ctx['ff'].append((idx, chunk)); return None
        if sel.startswith(('@keyframes', '@-webkit-keyframes', '@import', '@charset', '@property')):
            return chunk
        if sel.startswith(('@media', '@supports', '@layer', '@container')):
            head, rest = chunk.split('{', 1)
            inner = rest[:rest.rfind('}')]
            kept = [k for k in (filt(c, idx) for c in split_css(inner)) if k]
            if not kept:
                return None
            return head + '{\n' + '\n'.join(kept) + '\n}'
        return chunk if keep_sel(sel) else None

    purged = []
    for i, txt in enumerate(parts):
        kept = [k for k in (filt(c, i) for c in split_css(txt)) if k]
        purged.append('\n'.join(kept))

    kept_all = '\n'.join(purged)
    used = set()
    for src in (kept_all, page_text):
        for fam in re.findall(r"font-family\s*:\s*['\"]?([^;'\"]+)", src):
            for one in fam.split(','):
                one = one.strip().strip("'\"").lower()
                if one:
                    used.add(one)
    ff_by_part = {}
    for idx, ff in ctx['ff']:
        m = re.search(r"font-family\s*:\s*['\"]?([^;'\"]+)", ff)
        if m and m.group(1).strip().lower() in used:
            ff_by_part.setdefault(idx, []).append(ff)
    out = []
    for i, txt in enumerate(purged):
        out.append(txt + ('\n' + '\n'.join(ff_by_part[i]) if i in ff_by_part else ''))

    full, result = '\n'.join(parts), '\n'.join(out)
    for cls in classes:
        pat = re.compile(r'\.' + re.escape(cls) + r'(?![\w-])')
        if pat.search(full) and not pat.search(result):
            return parts           # garde-fou : CSS complète conservée
    return out


URL_IN_CSS = re.compile(r"""url\(\s*(?:"([^"]*)"|'([^']*)'|([^'")\s]+))\s*\)""")


def css_url(m):
    """gère les trois formes url("x"), url('x'), url(x) — y compris les
    noms de fichier contenant une apostrophe (ex. badge-d'employé)."""
    return m.group(1) if m.group(1) is not None else (
        m.group(2) if m.group(2) is not None else m.group(3))


def strip_broken_fontfaces(css):
    return re.sub(r'@font-face\s*\{[^}]*\}',
                  lambda m: '' if ('.zip' in m.group(0) or 'format("undefined")' in m.group(0)
                                   or "format('undefined')" in m.group(0)) else m.group(0), css)


def strip_webflow_comments(css):
    return re.sub(r'/\*!\s*(?:This site was created|Last Published|Made in Webflow)[^*]*\*/', '', css)


# ----------------------------------------------------------------------
# Conversion d'une page
# ----------------------------------------------------------------------
def patch_multistep(txt):
    """Garde anti-null : sur les pages sans formulaire multistep, la lib
    obfusquée déréférence des conteneurs absents. On injecte des éléments
    neutres (form/div de secours) comme dans l'usine de migration éprouvée."""
    txt, n1 = re.subn(
        r'(document\[[^\]]+\]\(\s*"form\[data-form=\\x22multistep\\x22]",?\s*\))',
        r'\1 || document.createElement("form")', txt, count=1, flags=re.S)
    txt, n2 = re.subn(
        r'(const\s+multistepContainer\s*=\s*document\[[^\]]+\]\(.*?\))\s*,',
        r'\1 || document.createElement("div"),', txt, count=1, flags=re.S)
    if not (n1 and n2):
        open(os.path.join(CONV, 'PATCH-MULTISTEP-WARNING.txt'), 'a').write(
            f'match partiel {n1}/{n2}\n')
    return txt


SCRIPT_VENDOR = [
    (re.compile(r'jquery[-\d.]*\.min|jquery-3', re.I), 'jquery.min.js'),
    (re.compile(r'webflow\.js', re.I), 'webflow.js'),
    (re.compile(r'multi-step\.js', re.I), 'multi-step.js'),
    (re.compile(r'inputmask', re.I), 'inputmask.min.js'),
    (re.compile(r'webfont', re.I), 'webfont.js'),
    (re.compile(r'ticker\.js', re.I), 'ticker.js'),
    (re.compile(r'tailwind', re.I), 'tailwind-play.js'),
]


def convert(src, slug, caches, all_slugs, aliases, sheet_urls):
    base_dir = os.path.dirname(src)
    site = os.path.join(OUT, slug)
    if os.path.isdir(site):
        shutil.rmtree(site)
    os.makedirs(site, exist_ok=True)
    warnings = []
    store = Store(site, caches, warnings)

    html = open(os.path.join(ROOT, src), encoding='utf-8', errors='replace').read()
    orig_len = len(html)

    # ---------- 1. CSS : liens + google fonts + styles inline ----------
    css_parts = []          # (position, texte, base_dir, nom)
    link_edits = []         # (start, end, remplacement)
    gfonts_families = []
    for m in re.finditer(r'<link\b[^>]*>', html, re.I):
        tag = m.group(0)
        href_m = re.search(r'href\s*=\s*"([^"]+)"', tag)
        rel_m = re.search(r'rel\s*=\s*"([^"]+)"', tag)
        if not href_m:
            continue
        href = href_m.group(1)
        rel = rel_m.group(1) if rel_m else ''
        if 'fonts.googleapis.com' in href or 'fonts.gstatic.com' in href:
            link_edits.append((m.start(), m.end(), ''))
            fm = re.search(r'family=([A-Za-z+]+)', href)
            if fm:
                gfonts_families.append(fm.group(1).replace('+', ''))
            continue
        if rel == 'stylesheet' and href.split('?')[0].endswith('.css'):
            key = resolve_key(href, base_dir)
            fp = os.path.join(ROOT, key) if key and not key.startswith('http') else None
            if fp and os.path.isfile(fp):
                txt = open(fp, encoding='utf-8', errors='replace').read()
                rank = 0 if 'normalize' in fp else (1 if os.path.basename(fp) == 'webflow.css' else 2)
                css_parts.append((m.start(), rank, txt, os.path.dirname(key), os.path.basename(fp)))
                link_edits.append((m.start(), m.end(), None))   # première -> style.css
            else:
                warnings.append(f'CSS introuvable : {href}')
    style_ranges = []
    for m in re.finditer(r'<style\b[^>]*>(.*?)</style>', html, re.S | re.I):
        css_parts.append((m.start(), 3, m.group(1), base_dir, '<style>'))
        style_ranges.append((m.start(), m.end()))

    # google fonts auto-hébergées (vendor gfonts)
    gfonts_css = ''
    for fam in dict.fromkeys(gfonts_families):
        vp = os.path.join(GFONTS, fam.lower() + '.css')
        if os.path.isfile(vp):
            gfonts_css += open(vp, encoding='utf-8').read() + '\n'
            for um in re.finditer(r"url\('(fonts/[^']+)'\)", gfonts_css):
                srcf = os.path.join(GFONTS, um.group(1))
                if os.path.isfile(srcf):
                    name = slugify(os.path.basename(srcf))
                    dest = os.path.join(site, 'fonts', name)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(srcf, dest)
            gfonts_css = re.sub(r"url\('fonts/([^']+)'\)",
                                lambda mm: "url('fonts/" + slugify(mm.group(1)) + "')", gfonts_css)
        else:
            warnings.append(f'police Google non vendorisée : {fam}')

    css_parts.sort(key=lambda x: (x[1], x[0]))
    classes = set()
    for cm in re.finditer(r'class\s*=\s*"([^"]*)"', html):
        classes.update(cm.group(1).split())
    ids = set(re.findall(r'\bid\s*=\s*"([^"]+)"', html))

    # ---------- 2. JS : vendor + inline ----------
    vendor_used = []
    inline_scripts = []     # (position, corps)
    script_edits = []
    sheet_hits = set(re.findall(r'https://script\.google\.com/macros/s/[A-Za-z0-9_\-]+', html))
    for m in re.finditer(r'<script\b([^>]*)>(.*?)</script>', html, re.S | re.I):
        attrs, body = m.group(1), m.group(2)
        src_m = re.search(r'\bsrc\s*=\s*"([^"]+)"', attrs)
        typ_m = re.search(r'type\s*=\s*"([^"]+)"', attrs)
        typ = typ_m.group(1).strip().lower() if typ_m else ''
        if src_m:
            script_src = src_m.group(1)
            for rx, vendor in SCRIPT_VENDOR:
                if rx.search(script_src):
                    if vendor not in vendor_used:
                        vendor_used.append(vendor)
                    script_edits.append((m.start(), m.end(), ''))
                    break
            else:
                key = resolve_key(script_src, base_dir)
                fp = os.path.join(ROOT, key) if key and not key.startswith('http') else None
                if fp and os.path.isfile(fp):
                    # JS local du dépôt (ex. js/main.js) : inline dans script.js
                    inline_scripts.append((m.start(),
                                           '/* script local: %s */\n' % key +
                                           open(fp, encoding='utf-8', errors='replace').read()))
                    script_edits.append((m.start(), m.end(), ''))
                else:
                    warnings.append(f'script externe non vendorisé (laissé) : {script_src}')
            continue
        if typ in KEEP_INLINE_TYPES:
            continue                       # JSON-LD / JSON : reste en place
        if 'googletagmanager' in body:
            continue                       # loader GTM : reste en place (spec §3.2)
        uses_jq = bool(re.search(r'\$\(|jQuery', body))
        if not uses_jq and ('dataLayer' in body or 'gtag(' in body) and len(body) < 2500:
            continue                       # consent/dataLayer compact : reste en place
        inline_scripts.append((m.start(), body))
        script_edits.append((m.start(), m.end(), ''))
    inline_scripts.sort(key=lambda x: x[0])

    page_text = html + '\n' + '\n'.join(b for _, b in inline_scripts)
    try:
        purged = purge_parts([t[2] for t in css_parts], page_text, classes, ids)
    except Exception as e:
        warnings.append(f'purge CSS échouée ({e}) -> CSS complète')
        purged = [t[2] for t in css_parts]

    # ---------- 3. Collecte des assets (HTML + CSS + JS inline) ----------
    refs = set()
    for am in re.finditer(r'\b(?:src|href|poster|data-poster-url|data-src)\s*=\s*"([^"]*)"', html):
        if is_assetish(am.group(1)):
            k = resolve_key(am.group(1), base_dir)
            if k:
                refs.add(k)
    for am in re.finditer(r'\b(?:srcset|data-srcset)\s*=\s*"([^"]*)"', html):
        for tok in am.group(1).split(','):
            tok = tok.strip().split()
            if tok:
                k = resolve_key(tok[0], base_dir)
                if k:
                    refs.add(k)
    for um in URL_IN_CSS.finditer(html):
        if is_assetish(css_url(um)):
            k = resolve_key(css_url(um), base_dir)
            if k:
                refs.add(k)
    for (_, _, _, bdir, _), ptxt in zip(css_parts, purged):
        for um in URL_IN_CSS.finditer(ptxt):
            if is_assetish(css_url(um)):
                k = resolve_key(css_url(um), bdir)
                if k:
                    refs.add(k)
    for _, body in inline_scripts:
        for mm in re.finditer(r"['\"]((?:\.\./)*(?:images|videos|fonts)/[^'\"]+)['\"]", body):
            k = resolve_key(mm.group(1), base_dir)
            if k:
                refs.add(k)
    for k in sorted(refs):
        store.get(k)

    # ---------- 4. CSS finale ----------
    final_parts = []
    for (pos, rank, _, bdir, name), ptxt in zip(css_parts, purged):
        t = strip_webflow_comments(strip_broken_fontfaces(ptxt))

        def repl(mm, bdir=bdir):
            k = resolve_key(css_url(mm), bdir)
            rel = store.mapping.get(k) if k else None
            return "url('%s')" % rel if rel else mm.group(0)

        final_parts.append(URL_IN_CSS.sub(repl, t))
    final_css = '/* style.css — normalize -> webflow -> CSS page -> styles inline (autonome) */\n'
    if gfonts_css:
        final_css += '/* Polices Google auto-hébergées */\n' + gfonts_css + '\n'
    final_css += '\n'.join(final_parts)
    # neutralisation CSS du blocage SMS (spec §5.3) + équivalence w-form
    final_css += ('\n/* Conversion autonome : équivalence du token w-form -> form-autonome, '
                  'et neutralisation de la vérification SMS (spec §3.3 / §5.3) */\n'
                  '.form-autonome{margin:0 0 15px;}\n'
                  '.btn-verification,.sms-send,.sms-code-wrap{display:none !important;}\n')

    # ---------- 5. script.js ----------
    js_parts = []
    order = ['jquery.min.js', 'webflow.js', 'multi-step.js', 'inputmask.min.js',
             'webfont.js', 'tailwind-play.js', 'ticker.js']
    for v in order:
        if v in vendor_used:
            vtxt = open(os.path.join(VENDOR, v), encoding='utf-8').read()
            if v == 'multi-step.js':
                vtxt = patch_multistep(vtxt)
            js_parts.append(('vendor:' + v, vtxt))
    for pos, body in inline_scripts:
        body = body.strip()
        if not body:
            continue
        for u in SMS_URLS:
            body = body.replace(u, '')
        # WebFont loader -> no-op (zéro appel CDN Google Fonts)
        body = re.sub(r'\bWebFont\.load\s*\(', '__lpWebFontNoop(', body)
        # Variante SMS vanilla (spec §5.3) : numéro réputé vérifié d'emblée,
        # la validation n'est plus bloquée que par le consentement.
        body = body.replace('verified = false', 'verified = true')
        body = body.replace("flag.value = 'non'", "flag.value = 'oui'")
        # Diagnostics éditables non bloquants : dégradés en avertissement
        body = body.replace("console.error('[LP assurance]", "console.warn('[LP assurance]")
        # redirections ltm_typ/hostname -> URL locale relative (file:// safe),
        # variantes simple/double quotes
        body = re.sub(
            r"window\.location\.protocol\s*\+\s*(['\"])//\1\s*\+\s*window\.location\.hostname"
            r"\s*\+\s*(['\"])/\2\s*\+\s*(\w+)",
            r"(window.__lpLocalUrl(\3)||\3)", body)
        js_parts.append(('inline', body))
    engine = open(os.path.join(CONV, 'moteur-leads.js'), encoding='utf-8').read()
    engine = engine.replace('window.__LP_SLUGS__ || []', json.dumps(sorted(all_slugs)))
    engine = engine.replace('window.__LP_ALIASES__ || {}', json.dumps(aliases))
    engine = engine.replace('window.__LP_SHEET_URLS__', json.dumps(sorted(sheet_hits)) or '[]')
    js_parts.append(('engine', engine))

    prelude = """/* Prélude — shim localStorage (origine opaque file://), avant toute lib */
(function () {
  try {
    var __t = '__lp_t__';
    window.localStorage.setItem(__t, '1'); window.localStorage.removeItem(__t);
  } catch (e) {
    var __mem = {};
    Object.defineProperty(window, 'localStorage', { configurable: true, value: {
      getItem: function (k) { return Object.prototype.hasOwnProperty.call(__mem, k) ? __mem[k] : null; },
      setItem: function (k, v) { __mem[k] = String(v); },
      removeItem: function (k) { delete __mem[k]; },
      clear: function () { __mem = {}; },
      key: function (i) { return Object.keys(__mem)[i] || null; },
      get length() { return Object.keys(__mem).length; }
    }});
  }
  /* Neutralise le WebFont Loader : ses familles Google sont un boilerplate
     CDN interdit par la spec ; les polices de marque sont déjà locales. */
  window.__lpWebFontNoop = function () { return Promise.resolve(); };
})();
"""
    out_js = ['/* script.js — assemble selon CONVERSION-SPEC §5 (jQuery, webflow, IX2, inline, moteur de leads) */\n', prelude]
    for i, (kind, body) in enumerate(js_parts):
        if kind.startswith('vendor') or kind == 'engine':
            out_js.append('/* %s */\n%s\n;\n' % (kind, body))
        else:
            if re.match(r"\s*(['\"])use strict\1", body):
                out_js.append('/* chunk inline %d */\n%s\n;\n' % (i, body))
            else:
                out_js.append('/* chunk inline %d */\ntry {\n%s\n} catch (e) { console.error("[conversion] chunk %d:", e); }\n;\n' % (i, body, i))
    script_js = ''.join(out_js)

    # ---------- 6. Réécritures HTML ----------
    edits = list(link_edits) + list(script_edits) + [(a, b, '') for a, b in style_ranges]
    first_css = True
    for idx, (a, b, rep) in enumerate(edits):
        if rep is None:
            edits[idx] = (a, b, '<link rel="stylesheet" href="style.css">' if first_css else '')
            first_css = False
    mb = list(re.finditer(r'</body>', html, re.I))
    if mb:
        edits.append((mb[-1].start(), mb[-1].start(), '<script src="script.js" defer></script>\n'))
    edits.sort(key=lambda e: -e[0])
    for a, b, rep in edits:
        html = html[:a] + rep + html[b:]

    # w-form -> form-autonome (token exact, jamais de regex \bw-form\b)
    def class_repl(mm):
        toks = mm.group(1).split()
        toks = ['form-autonome' if t == 'w-form' else t for t in toks]
        return 'class="%s"' % ' '.join(toks)
    html = re.sub(r'class="([^"]*)"', class_repl, html)

    # assets HTML (attributs, srcset, style inline)
    def attr_repl(mm):
        k = resolve_key(mm.group(2), base_dir)
        rel = store.mapping.get(k) if k else None
        return mm.group(1) + '="' + rel + '"' if rel else mm.group(0)
    html = re.sub(r'\b(src|href|poster|data-poster-url|data-src)\s*=\s*"([^"]*)"', attr_repl, html)

    def srcset_repl(mm):
        out = []
        for tok in mm.group(2).split(','):
            tok = tok.strip()
            if not tok:
                continue
            parts = tok.split()
            k = resolve_key(parts[0], base_dir)
            if k and k in store.mapping:
                parts[0] = store.mapping[k]
            out.append(' '.join(parts))
        return mm.group(1) + '="' + ', '.join(out) + '"'
    html = re.sub(r'\b(srcset|data-srcset)\s*=\s*"([^"]*)"', srcset_repl, html)

    def style_url_repl(mm):
        attr = mm.group(0)
        def u(um):
            k = resolve_key(css_url(um), base_dir)
            rel = store.mapping.get(k) if k else None
            return "url('%s')" % rel if rel else um.group(0)
        return URL_IN_CSS.sub(u, attr)
    html = re.sub(r'style\s*=\s*"[^"]*"', style_url_repl, html)

    # vidéos manquantes (MISSING.txt) : on retire les sources mortes,
    # y compris data-video-urls ; le poster (local) est conservé
    if store.missing_video:
        def video_attr_repl(mm):
            attr, val = mm.group(1), mm.group(2)
            if any(v in val for v in store.missing_video):
                return '%s=""' % attr
            return mm.group(0)
        html = re.sub(r'\b(data-video-urls|src|data-poster-url|poster|href)\s*=\s*"([^"]*)"',
                      video_attr_repl, html)
        html = re.sub(r'<source\b[^>]*>', lambda mm: '' if any(
            v in mm.group(0) for v in store.missing_video) else mm.group(0), html)

    # liens internes / iframes -> pages locales
    html = rewrite_internal_links(html, slug, all_slugs, aliases)

    # commentaires générateur Webflow
    html = re.sub(r'<!--\s*This site was created in Webflow\.[^>]*?-->\s*'
                  r'<!--\s*Last Published:[^>]*?-->', '', html, count=1, flags=re.S)

    # ---------- 7. Écriture ----------
    open(os.path.join(site, 'index.html'), 'w', encoding='utf-8').write(html)
    open(os.path.join(site, 'style.css'), 'w', encoding='utf-8').write(final_css)
    open(os.path.join(site, 'script.js'), 'w', encoding='utf-8').write(script_js)

    n_files = sum(len(fs) for _, _, fs in os.walk(site))
    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(site) for f in fs)
    return {
        'slug': slug, 'source': src, 'files': n_files, 'size_bytes': size,
        'images': len([v for v in store.mapping.values() if v.startswith('img/')]),
        'fonts': len([v for v in store.mapping.values() if v.startswith('fonts/')]),
        'vendor': vendor_used, 'warnings': sorted(set(warnings)),
        'css_kb': round(len(final_css) / 1024), 'js_kb': round(len(script_js) / 1024),
        'gfonts': gfonts_families,
    }


# ----------------------------------------------------------------------
# Liens internes / iframes (spec §3.1 et §3.4)
# ----------------------------------------------------------------------
def build_aliases(all_slugs):
    aliases = {
        'securite': 'securite-professionnels',
        'sage-gestion-de-la-paie-v4': 'sage-gestion-de-la-paie-hd-v4',
        'panneaux-photovoltaiques-passez-a-l-energie-solaire': 'panneaux-photovoltaiques-energie-solaire',
        'energie': 'energie',
        'caisse-enregistreuse': 'typ-formulaires/typ-caisses-enregistreuse',
        'assurance-estheticiennes-institut-beaute': 'assurance-estheticienne-institut-beaute',
        'assurance-consultant-conseil-v2': 'assurance-consultant-societe-conseil-v2',
    }
    return {k: v for k, v in aliases.items() if v in all_slugs}


def local_href(raw, slug, all_slugs, alias):
    """Retourne un chemin relatif vers le dossier autonome cible, ou None."""
    v = html_mod.unescape(raw)
    if v.startswith(('#', 'mailto:', 'tel:', 'javascript:', 'data:')):
        return None
    parsed = urllib.parse.urlparse(v)
    host = (parsed.netloc or '').lower()
    if host and not any(host.endswith(h) for h in
                        ('comparateurpro.fr', 'ubepro.fr', 'ubepro.com')):
        return None
    path = parsed.path
    if not path or not path.lstrip('/'):
        return None
    stem = path.lstrip('/').replace('.html', '').rstrip('/')
    if stem in alias:
        stem = alias[stem]
    if stem not in all_slugs:
        return None
    # relatif depuis comparateur-local/<slug>/index.html
    depth = len([p for p in slug.split('/') if p])
    prefix = '/'.join(['..'] * depth)
    prefix = prefix + '/' if prefix else ''
    suffix = '/index.html'
    if parsed.query:
        suffix += '?' + parsed.query
    return prefix + stem + suffix


IFRAME_PLACEHOLDER = (
    'srcdoc="&lt;!DOCTYPE html&gt;&lt;html lang=&quot;fr&quot;&gt;&lt;head&gt;&lt;meta charset=&quot;utf-8&quot;&gt;'
    '&lt;style&gt;body{margin:0;display:flex;align-items:center;justify-content:center;height:100vh;'
    'font:15px system-ui,sans-serif;color:#64748b;background:#f6f8fb;text-align:center;padding:24px}&lt;/style&gt;'
    '&lt;/head&gt;&lt;body&gt;Formulaire int&amp;eacute;gr&amp;eacute; &amp;mdash; contenu externe non embarqu&amp;eacute; '
    'en mode autonome&lt;/body&gt;&lt;/html&gt;"')


def rewrite_internal_links(html, slug, all_slugs, alias):
    own_index = slug + '/index.html'

    def repl(mm):
        attr, val = mm.group(1), mm.group(2)
        loc = local_href(val, slug, all_slugs, alias)
        if not loc:
            return mm.group(0)
        # garde anti-récursion : une iframe ne peut pas pointer vers elle-même
        if loc.replace('..', '').lstrip('/') == own_index and attr == 'src':
            return IFRAME_PLACEHOLDER
        return '%s="%s"' % (attr, loc)
    # href, src d'iframes, redirect/data-redirect des formulaires ;
    # GTM (googletagmanager) et YouTube restent intacts via local_href
    return re.sub(r'\b(href|src|redirect|data-redirect)\s*=\s*"([^"]+)"', repl, html)


# ----------------------------------------------------------------------
# Portail
# ----------------------------------------------------------------------
CATEGORY_RULES = [
    ('typ-formulaires', 'Formulaires TYP'),
    ('assurance', 'Assurance'),
    ('alfaromeo|lexus|mercedes-benz|voiture', 'Véhicules (marques)'),
    ('webflow|temlpate', 'Templates Webflow'),
    ('nicolas', 'Tests / brouillons'),
]


def categorize(slug, source):
    s = slug + ' ' + source
    for rx, label in CATEGORY_RULES:
        if re.search(rx, s):
            return label
    if re.search(r'assurance|prevoyance|retraite|rc-pro|iard|multirisque', s):
        return 'Assurance'
    if re.search(r'vehicule|voiture|automobile|juke|ariya|tucson|kona|fuso|volvo|fiat|dacia|renault|toyota|hyundai|canal|ayvens|ecomobility|geoloc|suivi|carburant|rayonnage|manutention|still|intuis|sauvie|securite|cle', s):
        return 'Solutions véhicules & équipements'
    if re.search(r'ticket|restaurant|kadeos|edenred|carte-cadeau|primagaz|energie|solaire|photovoltaique|too-good', s):
        return 'Énergie & titres salariés'
    if re.search(r'form|formulaire', s):
        return 'Formulaires'
    if re.search(r'remercie|merci', s):
        return 'Pages de remerciement'
    if re.search(r'typ', s):
        return 'Formulaires TYP'
    return 'Pages générales'


def build_portal(stats):
    cards = []
    for st in stats:
        title = st['slug'].split('/')[-1].replace('-', ' ').capitalize()
        cards.append((st['slug'], title, categorize(st['slug'], st['source']), st['source']))
    cats = {}
    for slug, title, cat, source in cards:
        cats.setdefault(cat, []).append((slug, title, source))
    rows = []
    for cat in sorted(cats):
        rows.append(f'<h2 class="cat">{cat} <span>{len(cats[cat])}</span></h2><div class="grid">')
        for slug, title, source in sorted(cats[cat]):
            rows.append(
                f'<a class="card" href="{slug}/index.html"><b>{title}</b>'
                f'<small>{source}</small></a>')
        rows.append('</div>')
    today = date.today().isoformat()
    html = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Comparateur Pro — portail des sites autonomes</title>
<style>
:root{--blue:#0066cc;--ink:#10233b;--mut:#64748b;--line:#e2e8f0;--bg:#f6f8fb}
*{box-sizing:border-box}body{margin:0;font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
header{background:linear-gradient(135deg,#003d7a,#0066cc);color:#fff;padding:34px 26px 26px}
header h1{margin:0 0 6px;font-size:26px}header p{margin:0;opacity:.9}
.wrap{max-width:1180px;margin:0 auto;padding:24px 20px 60px}
.search{width:100%;padding:14px 18px;font-size:16px;border:1px solid var(--line);border-radius:12px;box-shadow:0 2px 10px rgba(16,35,59,.06)}
.meta{color:var(--mut);margin:14px 2px 4px;font-size:14px}
h2.cat{margin:30px 2px 12px;font-size:18px}h2.cat span{display:inline-block;background:var(--blue);color:#fff;border-radius:999px;padding:1px 10px;font-size:13px;margin-left:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.card{display:flex;flex-direction:column;gap:4px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px;text-decoration:none;color:var(--ink);transition:.15s;box-shadow:0 1px 3px rgba(16,35,59,.05)}
.card:hover{border-color:var(--blue);transform:translateY(-2px);box-shadow:0 8px 22px rgba(0,102,204,.12)}
.card small{color:var(--mut);font-size:12px;word-break:break-all}
footer{color:var(--mut);font-size:13px;margin-top:34px;text-align:center}
</style>
</head>
<body>
<header><h1>Comparateur Pro — sites autonomes</h1>
<p>__N__ pages converties, 100 % hors-ligne — double-cliquez sur une fiche pour ouvrir le site.</p></header>
<div class="wrap">
<input class="search" id="q" type="search" placeholder="Rechercher une page (nom, fichier, catégorie)…" autofocus>
<p class="meta" id="meta"></p>
__BODY__
<footer>Généré le __DATE__ — conversion selon CONVERSION-SPEC.md</footer>
</div>
<script>
const cards = Array.from(document.querySelectorAll('.card'));
const q = document.getElementById('q');
const meta = document.getElementById('meta');
function apply(){
  const term = q.value.trim().toLowerCase();
  let shown = 0;
  cards.forEach(c => {
    const hit = !term || c.textContent.toLowerCase().includes(term);
    c.style.display = hit ? '' : 'none';
    if (hit) shown++;
  });
  document.querySelectorAll('h2.cat').forEach(h => {
    const grid = h.nextElementSibling;
    const vis = Array.from(grid.children).filter(x => x.style.display !== 'none').length;
    h.style.display = vis ? '' : 'none';
  });
  meta.textContent = shown + ' page(s) affichée(s) sur ' + cards.length;
}
q.addEventListener('input', apply); apply();
</script>
</body>
</html>"""
    html = html.replace('__N__', str(len(stats))).replace('__BODY__', '\n'.join(rows)).replace('__DATE__', today)
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(html)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', help='une seule page source (chemin relatif)')
    ap.add_argument('--portail', action='store_true')
    args = ap.parse_args()

    sources = list_sources()
    taken = set()
    slug_map = {s: slug_for(s, taken) for s in sources}
    all_slugs = set(slug_map.values())
    aliases = build_aliases(all_slugs)
    if args.only:
        sources = [s for s in sources if s == args.only]
    log(f'→ {len(sources)} page(s) à convertir, sortie {OUT}')
    caches = AssetCaches()
    stats = []
    for i, src in enumerate(sources, 1):
        slug = slug_map[src]
        try:
            st = convert(src, slug, caches, all_slugs, aliases, set())
            stats.append(st)
            log(f'[{i:3d}/{len(sources)}] OK {src} -> {slug} '
                f'({st["images"]} img, {st["fonts"]} fonts, {st["size_bytes"] // 1024} Ko,'
                f' {len(st["warnings"])} alerte(s))')
        except Exception as e:
            import traceback
            log(f'[{i:3d}/{len(sources)}] ECHEC {src}: {e}')
            traceback.print_exc()
            stats.append({'slug': slug, 'source': src, 'error': str(e)})
    json.dump({'generated': datetime.now().isoformat(timespec='seconds'),
               'pages': stats, 'slug_map': slug_map},
              open(STATS_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if args.portail:
        ok = [s for s in stats if 'error' not in s]
        build_portal(ok)
        log(f'→ portail écrit ({len(ok)} pages)')
    fails = [s for s in stats if 'error' in s]
    log(f'TERMINÉ : {len(stats) - len(fails)} succès, {len(fails)} échecs')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
