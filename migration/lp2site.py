#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lp2site.py — Usine de migration : LP Webflow -> site statique autonome
=======================================================================
Transforme une landing page d'un export Webflow (dépôt GitHub) en site
classique totalement autonome :

    site/
    ├── index.html      (HTML nettoyé, SEO de base, 1 seule feuille de style)
    ├── style.css       (normalize + webflow.css + css du site + styles inline, purgé)
    ├── script.js       (jQuery + webflow.js + scripts inline, ordre conservé)
    ├── img/            (toutes les images réellement utilisées, y compris CDN)
    ├── fonts/          (polices locales + Google Fonts auto-hébergées)
    ├── robots.txt
    ├── sitemap.xml
    └── rapport-site.md (bilan de conversion + checklist QA)

Principes :
  - AUCUNE dépendance résiduelle aux CDN Webflow (images/JS/CSS rapatriés).
  - Purge CSS conservatrice (un sélecteur est conservé au moindre doute).
  - Le tracking (GTM) et les endpoints métier (CRM/SMS) restent INTACTS.
  - Dépendances : Python 3.8+ standard uniquement.

Usage :
  # une seule page
  python3 lp2site.py assurance-tns.html --slug assurance-tns \
      --out sites --domain https://assurance-tns.example.fr

  # TOUT le parc, automatiquement (catégorisation, ordre de priorité,
  # reprise, budget, synthèse globale dans SYNTHESE.md)
  python3 lp2site.py --all --out sites \
      --domain-pattern "https://{slug}.lp.comparateurpro.fr" [--resume] \
      [--budget-mb 500] [--include-templates] [--limit 10]
"""

import argparse
import concurrent.futures
import hashlib
import html as html_mod
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from datetime import date

RAW_BASE = "https://raw.githubusercontent.com/manajahelvin-ux/comparateur/main/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

IMG_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.avif', '.gif', '.svg', '.ico'}
FONT_EXT = {'.woff', '.woff2', '.ttf', '.otf', '.eot'}
VID_EXT = {'.mp4', '.webm', '.ogg', '.mov'}

GTM_MARKERS = ('googletagmanager', 'dataLayer', 'gtag(')
KEEP_INLINE_TYPES = {'application/ld+json', 'application/json'}

_log_indent = 0
def log(msg):
    txt = '  ' * _log_indent + msg
    try:
        print(txt, flush=True)
    except UnicodeEncodeError:
        # consoles Windows en codepage héritée (cp850/cp1252)
        enc = sys.stdout.encoding or 'ascii'
        print(txt.encode(enc, 'replace').decode(enc), flush=True)


# ----------------------------------------------------------------------
# Réseau
# ----------------------------------------------------------------------
_cache = {}

def fetch(url, binary=True, timeout=40):
    if url in _cache:
        return _cache[url]
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    # Cache en RAM limité : textes partagés (css/js) et petits fichiers
    # (logos réutilisés entre pages). Les gros fichiers uniques ne sont pas gardés.
    if url.endswith(('.css', '.js', '.html')) or len(data) <= 512 * 1024:
        _cache[url] = data
    return data


def repo_url(path):
    return RAW_BASE + urllib.parse.quote(path.lstrip('/'), safe='/')


def normalize_repo_path(p, base_dir):
    """Résout un chemin relatif (vu depuis base_dir) en chemin dépôt normalisé."""
    q = p.split('?')[0].split('#')[0]
    q = urllib.parse.unquote(q)
    if q.startswith('/'):
        full = q.lstrip('/')
    else:
        full = os.path.normpath(os.path.join(base_dir, q))
    return full.replace('\\', '/')


def resolve_key(value, base_dir):
    """Clé canonique d'une référence d'asset (URL absolue ou chemin dépôt)."""
    v = html_mod.unescape(value.strip())        # &quot;…&quot; → "…"
    if len(v) > 1 and v[0] == v[-1] and v[0] in ('"', "'"):
        v = v[1:-1]                              # guillemets résiduels
    if not v or v.startswith(('data:', '#', 'mailto:', 'tel:', 'javascript:')):
        return None
    if v.startswith('//'):
        v = 'https:' + v
    if v.startswith(('http://', 'https://')):
        return v
    return normalize_repo_path(v, base_dir)


def slugify(name):
    base, ext = os.path.splitext(name)
    b = unicodedata.normalize('NFKD', base).encode('ascii', 'ignore').decode('ascii')
    b = re.sub(r'[^A-Za-z0-9._-]+', '-', b).strip('-.')
    return (b or 'asset') + ext.lower()


# ----------------------------------------------------------------------
# Découpage / purge CSS
# ----------------------------------------------------------------------
def split_css(css):
    """Découpe une feuille de style en blocs de niveau supérieur."""
    chunks, i, n = [], 0, len(css)
    start, depth = 0, 0
    instr, com = None, False
    while i < n:
        c = css[i]
        if com:
            if c == '*' and css.startswith('/', i + 1):
                com = False
                i += 2
                continue
        elif instr:
            if c == '\\':
                i += 2
                continue
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
                chunks.append(css[start:i + 1])
                start = i + 1
        i += 1
    tail = css[start:]
    if tail.strip():
        chunks.append(tail)
    return chunks


def _sel_of(chunk):
    sel = chunk.split('{', 1)[0]
    return re.sub(r'/\*.*?\*/', '', sel, flags=re.S).strip()


def _font_family(chunk):
    m = re.search(r"font-family\s*:\s*['\"]?([^;'\"]+)", chunk)
    return m.group(1).strip().lower() if m else None


def is_assetish(value):
    """Une référence est un asset téléchargeable si elle a une extension
    d'image/police/vidéo (évite de traiter les preconnect, pages, scripts…)."""
    path = value.split('?')[0].split('#')[0]
    ext = os.path.splitext(path)[1].lower()
    if ext in (IMG_EXT | FONT_EXT | VID_EXT):
        return True
    return bool(re.search(r'/(images|videos|fonts)/', path)) and ext != '.zip'


def purge_parts(parts, page_text, classes, ids):
    """Purge conservatrice, partie par partie (préserve le répertoire d'origine
    de chaque morceau pour la résolution des url()). Un sélecteur est conservé
    au moindre doute. Retourne la liste des textes purgés, ou parts inchangé
    si le garde-fou détecte une perte."""
    ctx = {'fontfaces': []}   # (index_partie, chunk)

    def keep_sel(sel):
        toks = re.findall(r'([.#])([-\w]+)', sel)
        if not toks:
            return True  # sélecteur d'élément / universel
        for kind, name in toks:
            if kind == '.':
                if name in classes or ('.' + name) in page_text or name.startswith('w-'):
                    return True
            else:
                if name in ids or ('#' + name) in page_text:
                    return True
        return False

    def filt(chunk, idx):
        sel = _sel_of(chunk)
        if not sel:
            return chunk  # déclaration orpheline (@charset, usage)
        if sel.startswith('@font-face'):
            ctx['fontfaces'].append((idx, chunk))
            return None
        if sel.startswith(('@keyframes', '@-webkit-keyframes', '@import', '@charset')):
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

    # 2e passe : @font-face réellement utilisés (toutes parties confondues)
    kept_all = '\n'.join(purged)
    used = set()
    for src_txt in (kept_all, page_text):
        for fam in re.findall(r"font-family\s*:\s*['\"]?([^;'\"]+)", src_txt):
            for one in fam.split(','):   # "Poppins, sans-serif" → 2 familles
                one = one.strip().strip("'\"").lower()
                if one:
                    used.add(one)
    ff_by_part = {}
    for idx, ff in ctx['fontfaces']:
        if _font_family(ff) in used:
            ff_by_part.setdefault(idx, []).append(ff)
    out = []
    for i, txt in enumerate(purged):
        ffs = ff_by_part.get(i)
        out.append(txt + ('\n' + '\n'.join(ffs) if ffs else ''))

    # Garde-fou : une classe utilisée dans la page (ou pilotée par script)
    # et stylée dans la CSS complète doit rester présente dans la CSS purgée.
    full = '\n'.join(parts)
    result = '\n'.join(out)
    for cls in classes:
        pat = re.compile(r'\.' + re.escape(cls) + r'(?![\w-])')
        if pat.search(full) and not pat.search(result):
            log(f"  ⚠ purge non sûre (.{cls} perdu) → conservation de la CSS complète")
            return parts
    return out


# ----------------------------------------------------------------------
# Téléchargement des assets
# ----------------------------------------------------------------------
class AssetStore:
    def __init__(self, outdir):
        self.outdir = outdir
        self.mapping = {}      # clé canonique -> chemin local final (img/x.png)
        self.missing = {}      # clé -> message d'erreur
        self.by_hash = {}      # md5 -> chemin local (déduplication de contenu)
        self.taken = set()     # noms locaux déjà attribués
        self.sizes = {}

    def _target_for(self, key):
        path = key.split('?')[0]
        name = slugify(os.path.basename(urllib.parse.unquote(path)))
        ext = os.path.splitext(name)[1].lower()
        if ext in FONT_EXT:
            folder = 'fonts'
        elif ext in VID_EXT:
            folder = 'videos'
        elif ext in IMG_EXT:
            folder = 'img'
        else:
            folder = 'assets'
        return folder, name

    def download(self, key):
        # Les noms mojibake du dépôt existent sous plusieurs normalisations
        # Unicode (ě composé/décomposé) : on essaie chacune.
        if key.startswith('http'):
            candidates = [key]
        else:
            candidates = [key]
            for norm in ('NFC', 'NFD', 'NFKC', 'NFKD'):
                n = unicodedata.normalize(norm, key)
                if n not in candidates:
                    candidates.append(n)
        data = None
        last_err = None
        for k in candidates:
            try:
                data = fetch(k if k.startswith('http') else repo_url(k))
                break
            except Exception as e:
                last_err = e
        if data is None:
            self.missing[key] = f"{getattr(last_err, 'code', last_err)}"
            return key, False

        folder, name = self._target_for(key)
        h = hashlib.md5(data).hexdigest()
        if h in self.by_hash:                      # contenu identique déjà stocké
            self.mapping[key] = self.by_hash[h]
            return key, True
        local = f"{folder}/{name}"
        if local in self.taken:                    # collision de nom, contenu différent
            stem, ext = os.path.splitext(name)
            local = f"{folder}/{stem}-{h[:6]}{ext}"
        self.taken.add(local)
        dest = os.path.join(self.outdir, local)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'wb') as f:
            f.write(data)
        self.mapping[key] = local
        self.by_hash[h] = local
        self.sizes[local] = len(data)
        return key, True

    def download_all(self, keys, workers=12):
        keys = sorted(k for k in keys if k and k not in self.mapping)
        if not keys:
            return
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            for _ in ex.map(self.download, keys):
                pass


# ----------------------------------------------------------------------
# Réécriture de références
# ----------------------------------------------------------------------
URL_IN_CSS = re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)")

def rewrite_css_urls(css_text, css_base_dir, store):
    def repl(m):
        key = resolve_key(m.group(2), css_base_dir)
        if key and key in store.mapping:
            return "url('%s')" % store.mapping[key]
        return m.group(0)
    return URL_IN_CSS.sub(repl, css_text)


def rewrite_srcset(value, base_dir, store):
    out = []
    for tok in value.split(','):
        tok = tok.strip()
        if not tok:
            continue
        parts = tok.split()
        key = resolve_key(parts[0], base_dir)
        if key and key in store.mapping:
            parts[0] = store.mapping[key]
        out.append(' '.join(parts))
    return ', '.join(out)


def rewrite_html_assets(html, base_dir, store):
    # attributs simples
    def attr_repl(m):
        val = m.group(2)
        key = resolve_key(val, base_dir)
        if key and key in store.mapping:
            return m.group(1) + '="' + store.mapping[key] + '"'
        return m.group(0)
    html = re.sub(r'\b(src|href|poster|data-poster-url|data-src|content)\s*=\s*"([^"]*)"',
                  attr_repl, html)
    # srcset / data-srcset
    def ss_repl(m):
        return m.group(1) + '="' + rewrite_srcset(m.group(2), base_dir, store) + '"'
    html = re.sub(r'\b(srcset|data-srcset)\s*=\s*"([^"]*)"',
                  lambda m: m.group(1) + '="' + rewrite_srcset(m.group(2), base_dir, store) + '"',
                  html)
    # url() dans les attributs style=""
    def style_repl(m):
        attr = m.group(0)
        return URL_IN_CSS.sub(
            lambda u: "url('%s')" % store.mapping[resolve_key(u.group(2), base_dir)]
            if resolve_key(u.group(2), base_dir) in store.mapping else u.group(0),
            attr)
    html = re.sub(r'style\s*=\s*"[^"]*"', style_repl, html)
    return html


def collect_refs(html, base_dir):
    """Références d'assets présentes dans le HTML (avant réécriture)."""
    refs = []
    for m in re.finditer(r'\b(?:src|href|poster|data-poster-url|data-src)\s*=\s*"([^"]*)"', html):
        if is_assetish(m.group(1)):
            k = resolve_key(m.group(1), base_dir)
            if k:
                refs.append(k)
    for m in re.finditer(r'\b(?:srcset|data-srcset)\s*=\s*"([^"]*)"', html):
        for tok in m.group(1).split(','):
            tok = tok.strip().split()
            if tok:
                k = resolve_key(tok[0], base_dir)
                if k:
                    refs.append(k)
    for m in URL_IN_CSS.finditer(html):
        if is_assetish(m.group(2)):
            k = resolve_key(m.group(2), base_dir)
            if k:
                refs.append(k)
    return refs


# ----------------------------------------------------------------------
# Conversion principale
# ----------------------------------------------------------------------
def derive_description(html):
    """Description de secours pour les LP Webflow (ni <p>, ni og:description) :
    meilleur bloc de texte scoré par recoupement avec les mots du <title>,
    filtré du boilerplate (cookies, consentement, questions de formulaire),
    sinon gabarit propre à partir du titre. Toujours signalée « à relire »."""
    title_m = re.search(r'<title>(.*?)</title>', html, re.S | re.I)
    title = html_mod.unescape(title_m.group(1)).strip() if title_m else ''
    stop = set('les des pour avec votre vous nos notre dans temps plus moins sans être avoir '
               'fait faire a à au aux et ou en d un une de du la le l s c qu que qui quoi'.split())
    tw = {w for w in re.findall(r"[a-zà-ÿ]{4,}", title.lower())} - stop

    black = re.compile(
        r'(oops|something went wrong|thank you|form submission|en soumettant|en cliquant|'
        r'j.accepte|cookie|consent|droits réservés|mentions légales|politique de '
        r'confidentialité|rgpd|merci pour|dans combien|encore quelques questions|'
        r'améliorer l|mesurer|publicités|statistiques|analytique|trafic|'
        r'vous êtes contacté|les informations que vous nous)', re.I)
    quest = re.compile(r'^(pour quel|à quel|a quel|quel |quels |quelles |combien |où |'
                       r'êtes-vous|voulez-vous|souhaitez-vous|disposez|sélectionnez|'
                       r'choisissez|renseignez|indiquez|entrez |tapez )', re.I)

    mbody = re.search(r'<body\b.*>', html, re.I | re.S)
    body = html[mbody.start():] if mbody else html
    best = None
    for thresh in (50, 40):
        for m in re.finditer(r'<(div|p|h2|h3|blockquote)\b[^>]*>([^<]{%d,})</\1>' % thresh, body):
            t = html_mod.unescape(m.group(2)).strip()
            if not t or black.search(t) or t.endswith('?') or quest.search(t):
                continue
            w = {x for x in re.findall(r"[a-zà-ÿ]{4,}", t.lower())} - stop
            score = len(w & tw) * 10 + min(len(t), 160) // 40
            if best is None or score > best[0]:
                best = (score, t)
        if best:
            break
    if best and best[0] >= 10:
        return best[1][:158]
    generic_titles = {'accueil', 'home', 'index', 'comparateurpro', 'comparateur'}
    slugish = re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)+', title.lower())
    if title.lower() not in generic_titles and not slugish and len(title) > 3:
        sep = ' — ' if (':' in title or '—' in title) else ' : '
        return (title + sep + 'comparez les offres des meilleurs partenaires du marché, '
                'adaptées à votre activité professionnelle.')[:200]
    return ('Comparez les offres des meilleurs partenaires pour votre activité '
            'professionnelle. Devis gratuit, réponse rapide.')


def strip_broken_fontfaces(css_text):
    """Retire les @font-face cassées des exports Webflow (src en .zip ou
    format \"undefined\") — elles ne se chargent jamais et laissent des
    références mortes."""
    removed = []

    def repl(m):
        block = m.group(0)
        if '.zip' in block or 'format("undefined")' in block or "format('undefined')" in block:
            removed.append(block)
            return ''
        return block

    out = re.sub(r'@font-face\s*\{[^}]*\}', repl, css_text)
    return out, removed



def _top_level_names(chunk):
    return set(re.findall(r'(?:^|[\n;])[ \t]*(?:const|let|var|function)[ \t]+([\w$]+)', chunk))


FORM_GUARD_JS = """/* [lp2site-doctor] garde formulaire v2 — 3 correctifs de robustesse :
   1. champs required caches : retires des que ils deviennent caches (Formly
      masque les etapes apres son init), sinon le bouton Valider reste bloque
   2. option exclusive (Non, merci / Aucun...) : decocher automatiquement l'exclusive
   3. sans ?ltm_typ=, afficher un retour de succes au lieu de l'echec muet */
(function () {
  function stripHiddenRequired() {
    document.querySelectorAll('form [required]').forEach(function (f) {
      if (f.offsetParent === null) f.removeAttribute('required');
    });
  }
  stripHiddenRequired();
  document.addEventListener('DOMContentLoaded', stripHiddenRequired);
  // Formly masque les etapes APRES son init : surveiller et nettoyer
  var passes = [300, 800, 1500, 2500, 4000];
  passes.forEach(function (t) { setTimeout(stripHiddenRequired, t); });
  try {
    var form = document.querySelector('form');
    if (form && window.MutationObserver) {
      new MutationObserver(function () { stripHiddenRequired(); })
        .observe(form, { subtree: true, attributes: true, attributeFilter: ['style', 'class'] });
    }
  } catch (e) {}
  var EXCL = /aucun|je ne sais|non concern|pas besoin|non, merci/i;
  document.addEventListener('change', function (e) {
    var c = e.target;
    if (!c || c.type !== 'checkbox' || !c.name) { stripHiddenRequired(); return; }
    var boxes = Array.prototype.slice.call(
      document.querySelectorAll('input[type=checkbox][name="' + c.name + '"]'));
    if (boxes.length < 2) return;
    var excl = null;
    for (var i = 0; i < boxes.length; i++) {
      var lbl = boxes[i].closest('label') || boxes[i].parentElement;
      if (EXCL.test(lbl ? lbl.innerText || '' : '')) { excl = boxes[i]; break; }
    }
    if (!excl) return;
    if (c === excl && c.checked) {
      boxes.forEach(function (b) {
        if (b !== excl && b.checked) {
          b.checked = false;
          b.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
    } else if (c !== excl && c.checked && excl.checked) {
      excl.checked = false;
      excl.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });
  document.addEventListener('submit', function (e) {
    if (!e.target || !e.target.classList || !e.target.classList.contains('form-redirect')) return;
    swapFailIfNeeded();
  }, true);
  // Formly déclenche le submit via jQuery (invisible aux listeners natifs) :
  // observer directement l'affichage du message d'échec
  function swapFailIfNeeded() {
    if (new URLSearchParams(window.location.search).get('ltm_typ')) return;
    var fail = document.querySelector('.w-form-fail');
    var done = document.querySelector('.w-form-done');
    if (fail && fail.offsetParent !== null) fail.style.display = 'none';
    if (done && done.offsetParent === null) { done.style.display = 'block'; return; }
    if (!document.getElementById('lp2site-merci')) {
      var d = document.createElement('div');
      d.id = 'lp2site-merci';
      d.style.cssText = 'position:fixed;inset:auto 0 0 0;z-index:9999;background:#0b7a5b;'
        + 'color:#fff;padding:18px;text-align:center;font-family:sans-serif;font-size:17px';
      d.textContent = 'Merci ! Vos réponses ont bien été enregistrées.';
      document.body.appendChild(d);
      setTimeout(function () { d.remove(); }, 9000);
    }
  }
  document.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || !t.closest || !t.closest('[data-form="submit-btn"]')) return;
    if (new URLSearchParams(window.location.search).get('ltm_typ')) return;
    [3500, 4500, 6000].forEach(function (d) { setTimeout(swapFailIfNeeded, d); });
  }, true);
  var passes2 = [3200, 4000, 5000, 6500];
  passes2.forEach(function (t) { setTimeout(swapFailIfNeeded, t); });
  try {
    if (window.MutationObserver) {
      var mo = new MutationObserver(function () { swapFailIfNeeded(); });
      ['w-form-fail', 'w-form-done'].forEach(function (cls) {
        document.querySelectorAll('.' + cls).forEach(function (el) {
          mo.observe(el, { attributes: true, attributeFilter: ['style', 'class'] });
        });
      });
    }
  } catch (e) {}
})();
"""

def build_script_js(script_chunks):
    """script.js : chaque script d'origine est isolé dans son try/catch —
    une exception (ex. Formly sur une page sans formulaire multistep) ne tue
    plus les scripts suivants, comme les balises <script> séparées."""
    chunks = [c for _, c in script_chunks]
    groups, current, declared = [], [], set()
    for ch in chunks:
        if current and any(re.search(r'\b' + re.escape(n) + r'\b', ch) for n in declared):
            current.append(ch)
        else:
            if current:
                groups.append(current)
            current = [ch]
        declared |= _top_level_names(ch)
    if current:
        groups.append(current)
    out = ['/* script.js — jQuery + webflow.js + scripts de la page (ordre conservé,\n'
           '   isolés par try/catch : un script en échec ne bloque pas les autres) */\n']
    for i, g in enumerate(groups):
        body = '\n;\n'.join(g)
        if re.match(r"\s*(['\"])use strict\1", body):
            out.append(f'/* chunk {i} (use strict, non isolé) */\n' + body + '\n;\n')
        else:
            out.append(f'/* chunk {i} */\ntry {{\n' + body +
                       f'\n}} catch (e) {{ console.error("[lp2site] script {i} en échec :", e); }}\n;\n')
    js = ''.join(out).rstrip('\n;') + '\n'
    # garde formulaire (required cachés, exclusivité, retour sans ltm_typ)
    js = FORM_GUARD_JS + '\n' + js
    # garde cookies : pages sans bannière → ni verrou de scroll ni crash
    js = re.sub(r"(const|var)\s+cookieBanner\s*=\s*document\.getElementById\('content-cookie'\);",
                lambda m: m.group(0) + "\n        /* garde : pas de bannière cookies dans cette page */\n"
                          "        if (!cookieBanner) { return; }",
                js, count=1)
    # patch Formly : null-déréférencements sur pages sans formulaire multistep
    js = re.sub(r"(const\s+multistepForm\s*=\s*document\[[\w$()'\"]{1,60}\]\(\s*"
                r'"form\[data-form=\\x22multistep\\x22\]"\s*,?\s*\))',
                r'\1 || document.createElement("form")', js, count=1)
    js = re.sub(r"(const\s+multistepContainer\s*=\s*document\[[\w$()\'\".]{1,80}\]\([^,;]*?\))\s*(?=,|;)",
                r'\1 || document.createElement("div")', js, count=1)
    return js


def convert(page, slug, outdir, domain, do_purge=True, selfhost_fonts=True):
    global _log_indent
    base_dir = os.path.dirname(page)
    site = os.path.join(outdir, slug)
    os.makedirs(site, exist_ok=True)
    store = AssetStore(site)
    warnings, notes = [], []

    log(f"▸ Conversion de « {page} » → site « {slug} »")
    html = fetch(repo_url(page)).decode('utf-8', 'replace')
    orig_len = len(html)

    # ---------- 1. Feuilles de style (liens + <style> inline) ----------
    css_parts = []          # (position, texte, base_dir)
    link_tags = []          # (match, kind)
    for m in re.finditer(r'<link\b[^>]*>', html, re.I):
        tag = m.group(0)
        href = re.search(r'href\s*=\s*"([^"]+)"', tag)
        rel = re.search(r'rel\s*=\s*"([^"]+)"', tag)
        if not (href and rel and rel.group(1) == 'stylesheet'):
            continue
        h = href.group(1)
        if 'fonts.googleapis.com' in h:
            link_tags.append((m, 'gfonts'))
        elif h.endswith('.css'):
            link_tags.append((m, 'local'))

    gfonts_css = ''
    for m, kind in link_tags:
        if kind == 'local':
            href = re.search(r'href\s*=\s*"([^"]+)"', m.group(0)).group(1)
            key = resolve_key(href, base_dir)
            try:
                txt = fetch(repo_url(key)).decode('utf-8', 'replace')
                css_parts.append((m.start(), txt, os.path.dirname(key)))
            except Exception as e:
                warnings.append(f"CSS introuvable : {key} ({e})")
        else:  # gfonts
            href = re.search(r'href\s*=\s*"([^"]+)"', m.group(0)).group(1)
            if selfhost_fonts:
                try:
                    txt = fetch(href).decode('utf-8', 'replace')
                    gfonts_css += txt + '\n'
                except Exception as e:
                    warnings.append(f"Google Fonts non récupérable ({e}) → lien conservé")
                    css_parts.append((m.start(), f"@import url('{href}');", base_dir))
            else:
                css_parts.append((m.start(), f"@import url('{href}');", base_dir))

    for m in re.finditer(r'<style\b[^>]*>(.*?)</style>', html, re.S | re.I):
        css_parts.append((m.start(), m.group(1), base_dir))

    css_parts.sort(key=lambda x: x[0])
    combined_css = '\n'.join(t for _, t, _ in css_parts)

    # ---------- 2. Scripts (externes + inline) ----------
    script_chunks = []      # (position, contenu)
    script_tags_to_remove = []
    for m in re.finditer(r'<script\b([^>]*)>(.*?)</script>', html, re.S | re.I):
        attrs, body = m.group(1), m.group(2)
        src = re.search(r'\bsrc\s*=\s*"([^"]+)"', attrs)
        typ = re.search(r'type\s*=\s*"([^"]+)"', attrs)
        typ = typ.group(1).strip().lower() if typ else ''
        if src:
            key = resolve_key(src.group(1), base_dir)
            try:
                content = fetch(key if key.startswith('http') else repo_url(key)).decode('utf-8', 'replace')
                script_chunks.append((m.start(), content))
                script_tags_to_remove.append(m)
                if 'async' in attrs:
                    warnings.append("script externe en async → ordre de concaténation à vérifier")
            except Exception as e:
                warnings.append(f"script externe introuvable : {src.group(1)} ({e})")
        else:
            if typ in KEEP_INLINE_TYPES:
                continue  # JSON-LD etc. → reste en place
            if 'googletagmanager' in body:
                continue  # loader GTM → reste en place (position critique)
            uses_jquery = bool(re.search(r'\$\(|\bjQuery\b', body))
            if ('dataLayer' in body or 'gtag(' in body) and len(body) < 2000 and not uses_jquery:
                continue  # init dataLayer compact → reste en place
            # NB : un script inline utilisant jQuery DOIT rejoindre script.js
            # (sinon il s'exécute avant le script.js différé → « $ is not defined »)
            script_chunks.append((m.start(), body))
            script_tags_to_remove.append(m)

    script_chunks.sort(key=lambda x: x[0])

    # ---------- 3. Purge CSS (AVANT la collecte : détermine les assets utiles) ----------
    classes = set()
    for m in re.finditer(r'class\s*=\s*"([^"]*)"', html):
        classes.update(m.group(1).split())
    ids = set(re.findall(r'\bid\s*=\s*"([^"]+)"', html))
    # Le texte de référence inclut les scripts : les classes pilotées par
    # webflow.js (interactions IX2) ou par les scripts inline doivent
    # conserver leurs règles CSS.
    page_text = html + '\n' + '\n'.join(c for _, c in script_chunks)
    if do_purge:
        before = sum(len(t) for _, t, _ in css_parts)
        try:
            purged = purge_parts([t for _, t, _ in css_parts], page_text, classes, ids)
        except Exception as e:
            warnings.append(f"purge CSS échouée ({e}) → CSS complète conservée")
            purged = [t for _, t, _ in css_parts]
        after = sum(len(t) for t in purged)
        log(f"Purge CSS : {before/1024:.0f} Ko → {after/1024:.0f} Ko")
    else:
        purged = [t for _, t, _ in css_parts]

    # ---------- 4. Collecte + téléchargement des assets ----------
    refs = set(collect_refs(html, base_dir))
    for (_, _, bdir), ptxt in zip(css_parts, purged):
        for u in URL_IN_CSS.finditer(ptxt):
            if is_assetish(u.group(2)):
                k = resolve_key(u.group(2), bdir)
                if k:
                    refs.add(k)
    if gfonts_css:
        for u in URL_IN_CSS.finditer(gfonts_css):
            refs.add(u.group(2))
    # références 'images/...' construites dans les scripts inline
    for _, body, in script_chunks:
        for mm in re.finditer(r"['\"]((?:\.\./)*(?:images|videos|fonts)/[^'\"]+)['\"]", body):
            refs.add(resolve_key(mm.group(1), base_dir))

    _log_indent += 1
    log(f"{len(refs)} références d'assets à rapatrier…")
    store.download_all(refs)
    ok = len(store.mapping)
    log(f"✔ {ok} rapatriés, {len(store.missing)} introuvables")
    for k, err in sorted(store.missing.items()):
        warnings.append(f"asset manquant (référence conservée telle quelle) : {k} [{err}]")
    _log_indent -= 1

    # ---------- 5. Réécritures ----------
    # @font-face cassées (export Webflow → .zip) retirées
    n_broken_ff = 0
    cleaned = []
    for (_, _, bdir), ptxt in zip(css_parts, purged):
        txt, removed = strip_broken_fontfaces(ptxt)
        n_broken_ff += len(removed)
        cleaned.append(txt)
    if n_broken_ff:
        warnings.append(f"{n_broken_ff} @font-face cassée(s) (src .zip / format \"undefined\" "
                        f"— bug d'export Webflow) retirée(s) ; la police retombe sur sa "
                        f"pile système de secours")
        purged = cleaned

    # CSS : urls → chemins locaux (par partie, selon son répertoire d'origine)
    rewritten_parts = []
    for (pos, _, bdir), ptxt in zip(css_parts, purged):
        rewritten_parts.append((pos, rewrite_css_urls(ptxt, bdir, store)))
    rewritten_parts.sort(key=lambda x: x[0])
    final_css = '\n'.join(t for _, t in rewritten_parts)
    if gfonts_css:
        final_css = rewrite_css_urls(gfonts_css, '', store) + '\n' + final_css

    # HTML : édition par plages
    edits = []
    first_link_done = False
    for m, kind in link_tags:
        if not first_link_done:
            edits.append((m.start(), m.end(), '<link rel="stylesheet" href="style.css">'))
            first_link_done = True
        else:
            edits.append((m.start(), m.end(), ''))
    if selfhost_fonts:
        for m in re.finditer(r'<link\b[^>]*>', html, re.I):
            tag = m.group(0)
            if 'fonts.gstatic.com' in tag or 'fonts.googleapis.com' in tag:
                if (m.start(), m.end(), '') not in edits and 'stylesheet' not in tag:
                    edits.append((m.start(), m.end(), ''))
    for m in re.finditer(r'<style\b[^>]*>.*?</style>', html, re.S | re.I):
        edits.append((m.start(), m.end(), ''))
    for m in script_tags_to_remove:
        edits.append((m.start(), m.end(), ''))
    # script.js avant </body>
    mbody = list(re.finditer(r'</body>', html, re.I))
    if mbody:
        edits.append((mbody[-1].start(), mbody[-1].start(),
                      '<script src="script.js" defer></script>\n'))
    edits.sort(key=lambda e: -e[0])
    for start, end, txt in edits:
        html = html[:start] + txt + html[end:]

    # assets du HTML
    html = rewrite_html_assets(html, base_dir, store)

    # nettoyage : commentaires de générateur Webflow
    html = re.sub(r'<!--\s*This site was created in Webflow\.[^>]*?-->\s*'
                  r'<!--\s*Last Published:[^>]*?-->', '', html, count=1, flags=re.S)

    # ---------- 6. SEO de base ----------
    seo_added = []
    title_m = re.search(r'<title>(.*?)</title>', html, re.S | re.I)
    title_txt = html_mod.unescape(title_m.group(1).strip()) if title_m else ''
    insert_after = title_m.end() if title_m else False
    if not insert_after:
        hm = re.search(r'</head>', html, re.I)
        insert_after = hm.start()
    block = ''
    desc = ''
    if not re.search(r'<meta\s+name\s*=\s*"description"', html, re.I):
        ogd = re.search(r'<meta\s+content="([^"]*)"\s+property="og:description"'
                        r'|property="og:description"\s+content="([^"]*)"'
                        r'|name="description"\s+content="([^"]*)"', html, re.I)
        if ogd:
            desc = next(g for g in ogd.groups() if g)
            src = 'reprise de og:description'
        else:
            desc = derive_description(html)
            src = 'auto — à relire'
        if desc:
            desc_attr = desc.replace('&', '&amp;').replace('"', '&quot;')
            block += f'\n  <meta name="description" content="{desc_attr}">'
            seo_added.append(f'meta description ({src})')
    if domain and not re.search(r'rel\s*=\s*"canonical"', html, re.I):
        block += f'\n  <link rel="canonical" href="{domain.rstrip("/")}/">'
        seo_added.append('canonical')
    if not re.search(r'property\s*=\s*"og:title"', html, re.I):
        og_img = next((p for p in store.mapping.values()
                       if p.startswith('img/') and p.endswith(tuple(IMG_EXT - {'.ico', '.svg'}))
                       and not re.search(r'favicon|webclip|logo|icon', p, re.I)), '')
        t = title_txt.replace('&', '&amp;').replace('"', '&quot;')
        d = desc.replace('&', '&amp;').replace('"', '&quot;') if desc else ''
        block += (f'\n  <meta property="og:title" content="{t}">'
                  f'\n  <meta property="og:type" content="website">'
                  f'\n  <meta property="og:locale" content="fr_FR">'
                  f'\n  <meta property="og:description" content="{d}">'
                  f'\n  <meta property="og:image" content="{domain.rstrip("/")}/{og_img}">'
                  f'\n  <meta name="twitter:card" content="summary_large_image">')
        seo_added.append('Open Graph + Twitter Card')
    if block:
        html = html[:insert_after] + block + html[insert_after:]

    # ---------- 7. Écriture des fichiers ----------
    with open(os.path.join(site, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    with open(os.path.join(site, 'style.css'), 'w', encoding='utf-8') as f:
        f.write('/* style.css — généré par lp2site.py (normalize + webflow + site + inline) */\n'
                + final_css)
    script_js = build_script_js(script_chunks)
    with open(os.path.join(site, 'script.js'), 'w', encoding='utf-8') as f:
        f.write(script_js)

    if domain:
        with open(os.path.join(site, 'robots.txt'), 'w') as f:
            f.write(f"User-agent: *\nAllow: /\n\nSitemap: {domain.rstrip('/')}/sitemap.xml\n")
        with open(os.path.join(site, 'sitemap.xml'), 'w', encoding='utf-8') as f:
            f.write(f'<?xml version="1.0" encoding="UTF-8"?>\n'
                    f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                    f'  <url><loc>{domain.rstrip("/")}/</loc>'
                    f'<lastmod>{date.today().isoformat()}</lastmod>'
                    f'<changefreq>monthly</changefreq><priority>1.0</priority></url>\n'
                    f'</urlset>\n')

    # ---------- 8. Vérification ----------
    problems = verify_site(site)
    write_report(site, slug, page, domain, store, warnings, seo_added,
                 problems, orig_len, final_css, script_js)

    n_files, size_b = 0, 0
    for root, _, names in os.walk(site):
        for n in names:
            p = os.path.join(root, n)
            try:
                size_b += os.path.getsize(p)
                n_files += 1
            except OSError:
                pass

    _log_indent += 1
    log(f"✔ Site écrit dans {site} ({size_b/1e6:.1f} Mo, {n_files} fichiers)")
    if problems:
        log(f"✘ {len(problems)} problème(s) de vérification :")
        for p in problems[:10]:
            log(f"   - {p}")
    _log_indent -= 1
    return {'slug': slug, 'page': page, 'status': 'ok',
            'size_mb': round(size_b / 1e6, 2), 'files': n_files,
            'images': len([p for p in store.mapping.values() if p.startswith('img/')]),
            'fonts': len([p for p in store.mapping.values() if p.startswith('fonts/')]),
            'missing': len(store.missing),
            'warnings': warnings, 'problems': problems}


def verify_site(site):
    """Contrôle final : TOUTE référence locale (relative) doit exister sur disque."""
    problems = []
    idx = open(os.path.join(site, 'index.html'), encoding='utf-8').read()
    css = open(os.path.join(site, 'style.css'), encoding='utf-8').read()
    refs = set()
    for src in (idx, css):
        for m in re.finditer(r'(?:src|href|poster|data-src)\s*=\s*"([^"]+)"', src):
            v = m.group(1)
            if v.startswith(('http', 'data:', '#', 'mailto:', 'tel:', 'javascript:', '//')):
                continue
            v = v.split('#')[0].split('?')[0]
            if v:
                refs.add(v)
        for m in URL_IN_CSS.finditer(src):
            v = m.group(2)
            if v.startswith(('http', 'data:', '//', '#')):
                continue
            v = v.split('#')[0].split('?')[0]
            if v:
                refs.add(v)
    for r in sorted(refs):
        if r in ('style.css', 'script.js'):
            continue
        target = os.path.normpath(os.path.join(site, r))
        if not os.path.exists(target):
            problems.append(f"référence locale manquante : {r}")
    return problems


def write_report(site, slug, page, domain, store, warnings, seo_added,
                 problems, orig_len, final_css, script_js):
    import glob
    files = []
    for root, _, names in os.walk(site):
        for n in names:
            p = os.path.join(root, n)
            files.append((os.path.relpath(p, site), os.path.getsize(p)))
    total = sum(s for _, s in files)
    imgs = [f for f, _ in files if f.startswith('img/')]
    fnts = [f for f, _ in files if f.startswith('fonts/')]

    idx = open(os.path.join(site, 'index.html'), encoding='utf-8').read()
    gtm = re.findall(r'GTM-[A-Z0-9]+', idx)
    h1s = len(re.findall(r'<h1\b', idx))
    ext_hosts = sorted(set(re.findall(r'https?://([a-z0-9.-]+)', idx)))
    internal_html_links = sorted(set(
        m for m in re.findall(r'href\s*=\s*"([^"]*\.html[^"]*)"', idx)
        if not m.startswith('http')))

    lines = [
        f"# Rapport de conversion — `{slug}`",
        f"",
        f"- **Page source** : `{page}` (dépot GitHub, export Webflow)",
        f"- **Domaine cible** : {domain or '_(non fourni — canonical/sitemap omis)_'}",
        f"- **Date** : {date.today().isoformat()}",
        "",
        "## Résultat",
        f"| Indicateur | Valeur |",
        f"|---|---|",
        f"| Fichiers totaux | {len(files)} |",
        f"| Poids total | {total/1e6:.2f} Mo |",
        f"| Images rapatriées | {len(imgs)} |",
        f"| Polices rapatriées | {len(fnts)} |",
        f"| CSS finale | {len(final_css)/1024:.0f} Ko |",
        f"| JS finale | {len(script_js)/1024:.0f} Ko |",
        f"| Assets introuvables | {len(store.missing)} |",
        "",
        "## SEO",
        f"- H1 : **{h1s}** {'⚠ à corriger (0 ou plusieurs)' if h1s != 1 else '✔'}",
        f"- GTM : {', '.join(sorted(set(gtm))) or 'absent'}",
        f"- Éléments ajoutés automatiquement : {', '.join(seo_added) or 'aucun'}",
        f"- Liens vers d'autres pages du dépôt (à trancher) : {internal_html_links or 'aucun'}",
        "",
        "## Hôtes externes encore appelés par la page",
        ', '.join(ext_hosts) or 'aucun',
        "",
    ]
    if warnings:
        lines.append("## ⚠ Avertissements")
        lines += [f"- {w}" for w in warnings]
    if problems:
        lines.append("\n## ✘ Problèmes détectés par la vérification")
        lines += [f"- {p}" for p in problems]
    if not warnings and not problems:
        lines.append("\n✔ Aucun avertissement, aucune référence cassée.")
    lines += [
        "",
        "## Checklist QA humaine avant mise en ligne",
        "1. Comparaison visuelle côte à côte avec la page Webflow d'origine.",
        "2. Parcours complet du formulaire (toutes les étapes, champs obligatoires, erreurs).",
        "3. Test OTP SMS avec un numéro de test.",
        "4. Vérification de la réception du lead en CRM / Google Sheets.",
        "5. Tag Assistant : déclenchement GTM et de l'événement `formulaire_lead`.",
        "6. Lighthouse mobile : performance et accessibilité.",
        "7. Relire meta description (générée automatiquement) et titre.",
        "",
        "_Généré par lp2site.py_",
    ]
    with open(os.path.join(site, 'rapport-site.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def main():
    ap = argparse.ArgumentParser(description="LP Webflow → site statique autonome")
    ap.add_argument('page', nargs='?', help="chemin de la page dans le dépôt (mode simple)")
    ap.add_argument('--all', action='store_true',
                    help='convertir automatiquement TOUT le parc du dépôt')
    ap.add_argument('--slug', help="nom du dossier site (défaut: nom de fichier sans .html)")
    ap.add_argument('--out', default='sites', help="dossier racine des sites générés")
    ap.add_argument('--domain', default=None,
                    help="domaine final (mode simple : canonical + sitemap + og:image)")
    ap.add_argument('--domain-pattern', default=None,
                    help="mode batch : domaine par site, ex: https://{slug}.lp.exemple.fr")
    ap.add_argument('--budget-mb', type=float, default=None,
                    help="arrêter la conversion au-delà de ce poids total (Mo)")
    ap.add_argument('--resume', action='store_true',
                    help="ignorer les sites déjà convertis (reprise de batch)")
    ap.add_argument('--include-templates', action='store_true',
                    help='inclure aussi les pages template/test (exclues par défaut)')
    ap.add_argument('--limit', type=int, default=None, help="ne traiter que les N premières pages")
    ap.add_argument('--no-purge', action='store_true', help="désactiver la purge CSS")
    ap.add_argument('--no-selfhost-fonts', action='store_true',
                    help="conserver le lien Google Fonts au lieu de l'auto-héberger")
    args = ap.parse_args()

    if args.all:
        batch(args.out, domain_pattern=args.domain_pattern, budget_mb=args.budget_mb,
              resume=args.resume, include_templates=args.include_templates,
              limit=args.limit, do_purge=not args.no_purge,
              selfhost_fonts=not args.no_selfhost_fonts)
    elif args.page:
        slug = args.slug or os.path.splitext(os.path.basename(args.page))[0]
        convert(args.page, slug, args.out, args.domain,
                do_purge=not args.no_purge, selfhost_fonts=not args.no_selfhost_fonts)
    else:
        ap.error("indiquez une page (ex: assurance-tns.html) ou --all")


# ----------------------------------------------------------------------
# Mode batch : conversion automatique de tout le parc
# ----------------------------------------------------------------------
TEMPLATE_DIRS = ('temlpate-webflow/', 'webflow/', 'nicolas/')
CATEGORY_ORDER = ['métier', 'typ', 'marque', 'thank-you', 'variante', 'template/test']


def categorize(path):
    """Catégorie d'une page — sert à l'ordre de traitement et à la synthèse."""
    p = path.lower()
    if path.startswith(TEMPLATE_DIRS):
        return 'template/test'
    if p.startswith('typ-formulaires/') or re.search(r'(^|[-/])typ([-.]|$)', p):
        return 'typ'
    if re.search(r'(remerciement|merci|thank)', p):
        return 'thank-you'
    if re.search(r'(lexus|nissan|toyota|dacia|hyundai|fiat|mercedes|alfaromeo|volvo|'
                 r'mitsubishi|ayvens|ecomobility|still|juke|ariya|capture|jogger|kona|'
                 r'tucson|tonale|lbx|sprinter|ecitan|evito|fuso|voiture|canal)', p):
        return 'marque'
    if re.search(r'(-v\d|adw|test)', p):
        return 'variante'
    return 'métier'


def slug_for(path, used):
    """Slug unique et lisible : pages en sous-dossier préfixées par leur dossier."""
    base = natural_slug(path)
    slug, n = base, 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def natural_slug(path):
    parts = path.split('/')
    base = parts[-1][:-5]                      # sans .html
    if base == 'index':
        base = parts[-2] if len(parts) > 1 else 'site'
    elif len(parts) > 1:
        base = '-'.join(parts[:-1]) + '-' + base
    return base


def existing_site_pages(outdir):
    """Cartographie page → slug des sites déjà convertis (lue dans les
    rapport-site.md) — fiabilise la reprise, même en cas de collision de slug."""
    done = {}
    if not os.path.isdir(outdir):
        return done
    for name in sorted(os.listdir(outdir)):
        rp = os.path.join(outdir, name, 'rapport-site.md')
        if not os.path.isfile(rp):
            continue
        try:
            head = open(rp, encoding='utf-8', errors='replace').read(2000)
        except OSError:
            continue
        m = re.search(r'\*\*Page source\*\* : `([^`]+)`', head)
        if m:
            done[m.group(1)] = name
    return done


def dir_size(path):
    total = 0
    for root, _, names in os.walk(path):
        for n in names:
            try:
                total += os.path.getsize(os.path.join(root, n))
            except OSError:
                pass
    return total


def list_repo_pages():
    api = ('https://api.github.com/repos/manajahelvin-ux/comparateur/'
           'git/trees/main?recursive=1')
    data = json.loads(fetch(api))
    return [t['path'] for t in data.get('tree', [])
            if t.get('type') == 'blob' and t['path'].endswith('.html')]


def batch(outdir, domain_pattern=None, budget_mb=None, resume=False,
          include_templates=False, limit=None, do_purge=True, selfhost_fonts=True):
    pages = list_repo_pages()
    todo = [(p, categorize(p)) for p in sorted(pages)]
    if not include_templates:
        todo = [(p, c) for p, c in todo if c != 'template/test']
    todo.sort(key=lambda pc: (CATEGORY_ORDER.index(pc[1]), pc[0]))
    if limit:
        todo = todo[:limit]
    os.makedirs(outdir, exist_ok=True)

    done = existing_site_pages(outdir) if resume else {}
    used = set(done.values())
    results = []
    n = len(todo)
    log(f"Batch : {n} pages à convertir → {outdir}/ "
        f"(ordre : {' > '.join(c for c in CATEGORY_ORDER if any(x[1] == c for x in todo))})")
    if resume and done:
        log(f"Reprise : {len(done)} site(s) déjà convertis seront ignorés")
    budget_stopped = False
    for i, (page, cat) in enumerate(todo, 1):
        if resume and page in done:
            slug = done[page]
            log(f"[{i}/{n}] ⏭  {slug} — déjà converti, ignoré")
            results.append({'slug': slug, 'page': page, 'cat': cat,
                            'status': 'déjà converti (reprise)'})
            continue
        slug = slug_for(page, used)
        site_dir = os.path.join(outdir, slug)
        if budget_mb and dir_size(outdir) >= budget_mb * 1_000_000:
            log(f"⏹ Budget de {budget_mb:.0f} Mo atteint — arrêt avant « {slug} » "
                f"(relancez avec --resume pour continuer)")
            budget_stopped = True
            break
        domain = domain_pattern.format(slug=slug) if domain_pattern else None
        log(f"[{i}/{n}] [{cat}] {page} → {slug}/")
        try:
            stats = convert(page, slug, outdir, domain,
                            do_purge=do_purge, selfhost_fonts=selfhost_fonts)
            stats['cat'] = cat
            results.append(stats)
        except Exception as e:
            log(f"  ✘ ÉCHEC {page} : {type(e).__name__}: {e}")
            results.append({'slug': slug, 'page': page, 'cat': cat,
                            'status': f'échec — {type(e).__name__}: {e}',
                            'warnings': [], 'problems': []})

    # ordre de traitement (utile pour copier les sites par priorité)
    with open(os.path.join(outdir, 'ordre-sites.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(r['slug'] for r in results) + '\n')
    write_synthesis(outdir, results, todo, domain_pattern, budget_stopped)


def write_synthesis(outdir, results, todo, domain_pattern, budget_stopped):
    done = {r['page'] for r in results}
    remaining = [(p, c) for p, c in todo if p not in done]
    ok = [r for r in results if r.get('status') == 'ok']
    skipped = [r for r in results if r.get('status', '').startswith('déjà converti')]
    failed = [r for r in results if r.get('status', '').startswith('échec')]
    total_size = dir_size(outdir)

    from collections import Counter
    cats = Counter(r.get('cat') for r in ok)

    lines = [
        '# 🏭 Synthèse de la migration batch',
        '',
        f'> Généré automatiquement le {date.today().isoformat()} par `lp2site.py --all`',
        '',
        '## Bilan',
        '',
        f"- Pages à convertir : **{len(todo)}**",
        f"- ✅ Converties avec succès : **{len(ok)}**",
        f"- ⏭ Déjà converties (reprise) : **{len(skipped)}**",
        f"- ❌ Échecs : **{len(failed)}**",
        f"- ⏳ Restantes : **{len(remaining)}**"
        + (" *(arrêt sur budget — relancer avec `--resume`)*" if budget_stopped else ""),
        f"- 💾 Poids total généré : **{total_size/1e6:.1f} Mo**",
        f"- 🌐 Modèle de domaine : `{domain_pattern or '—'}`",
        '',
        '## Répartition par catégorie',
        '',
    ]
    for c in CATEGORY_ORDER:
        if cats.get(c):
            lines.append(f"- **{c}** : {cats[c]} sites")
    lines += ['', '## Sites générés', '',
              '| Site | Page source | Catégorie | Poids | Images | Polices | Assets manquants | Alertes |',
              '|---|---|---|---|---|---|---|---|']
    for r in sorted(ok, key=lambda r: (CATEGORY_ORDER.index(r.get('cat', 'variante')), r['slug'])):
        alerts = len(r.get('warnings', [])) + len(r.get('problems', []))
        lines.append(f"| `{r['slug']}/` | `{r['page']}` | {r['cat']} | {r['size_mb']} Mo "
                     f"| {r['images']} | {r['fonts']} | {r.get('missing', 0)} | {alerts} |")
    if failed:
        lines += ['', '## ❌ Échecs', '']
        lines += [f"- `{r['page']}` → {r['status']}" for r in failed]
    if remaining:
        lines += ['', '## ⏳ Pages restantes', '']
        lines += [f"- `{p}` ({c})" for p, c in remaining]
    lines += [
        '',
        '## Relancer / continuer',
        '',
        '```bash',
        'python3 lp2site.py --all --out ' + outdir + ' \\',
        '  --domain-pattern "' + (domain_pattern or 'https://{slug}.exemple.fr') + '" --resume',
        '```',
        '',
        '_Chaque site contient son `rapport-site.md` (bilan détaillé + checklist QA). '
        'Les colonnes « Assets manquants » et « Alertes » signalent les pages à '
        'réexporter depuis Webflow (vidéos notamment) ou à vérifier en priorité._',
    ]
    path = os.path.join(outdir, 'SYNTHESE.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    log(f"Synthèse écrite : {path}")


if __name__ == '__main__':
    main()
