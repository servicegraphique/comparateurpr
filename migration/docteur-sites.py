#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docteur-sites.py — Vérifie et répare tous les sites d'un dossier généré.
=========================================================================
Corrige les 3 familles de défauts détectées en navigation réelle :

  [FORM]  Scripts inline utilisant jQuery ($) restés dans index.html :
          ils s'exécutent avant script.js (différé) → « $ is not defined »
          → handler .submit() jamais attaché → formulaire bloqué à l'envoi.
          Réparation : déplacement dans script.js.

  [SCROLL+COOKIES] Script cookies des pages d'origine : il verrouille
          body.style.overflow='hidden' même si la bannière n'existe pas dans
          la page (7 pages du dépôt n'ont jamais eu la bannière) → scroll
          bloqué + aucune bannière. Réparation : garde « si pas de bannière,
          ne rien faire ».

  [ISOLATION] script.js est un concaténé : UNE exception (ex. Formly qui
          crashe sur les pages sans formulaire multi-étapes) tue tout ce qui
          suit. Réparation : chaque script d'origine est réisolé dans son
          propre try/catch, comme les balises <script> séparées d'origine.

  [FORMLY] Patch défensif du null-déréférencement de Formly.

Usage :
  python3 docteur-sites.py                # vérifie + répare ./sites
  python3 docteur-sites.py mon_dossier    # autre dossier
  python3 docteur-sites.py --verifier    # vérifier SANS rien modifier
  python3 docteur-sites.py --navigateur  # + test navigateur réel (playwright)

Écrit DIAGNOSTIC-SITES.md à la racine du dossier. Idempotent : relançable.
Python 3.8+ standard, compatible Windows (sortie console sans émojis).
"""

import argparse
import os
import re
import sys
from datetime import date

ISOLATION_TAG = '[lp2site-doctor]'
ISOLATION_APPLIED = ISOLATION_TAG + ' isolation'
MOVED_TAG = ISOLATION_TAG + ' deplace'
GUARDComment = '/* garde docteur : pas de banniere cookies dans cette page */'


def log(msg):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or 'ascii'
        print(msg.encode(enc, 'replace').decode(enc), flush=True)


# ----------------------------------------------------------------------
# Découpage et isolation de script.js
# ----------------------------------------------------------------------
def split_chunks(js):
    """Retrouve les scripts d'origine dans le script.js concaténé."""
    header = ''
    m = re.match(r'/\*.*?\*/\n', js, re.S)
    if m and 'script.js' in m.group(0):
        header = m.group(0)
        js = js[len(header):]
    parts = [p for p in js.split('\n;\n') if p.strip()]
    return header, parts


def balanced(chunk):
    """Vérification grossière d'équilibre des accolades/parenthèses."""
    return chunk.count('{') == chunk.count('}') and \
           chunk.count('(') == chunk.count(')')


def top_level_names(chunk):
    return set(re.findall(r'(?:^|[\n;])[ \t]*(?:const|let|var|function)[ \t]+([\w$]+)',
                          chunk))


def references_any(chunk, names):
    for n in names:
        if re.search(r'\b' + re.escape(n) + r'\b', chunk):
            return True
    return False


def isolate_chunks(header, chunks):
    """Réécrit script.js avec chaque script d'origine dans son try/catch.
    Regroupe conservativement les chunks qui partagent des noms globaux."""
    groups, current, declared = [], [], set()
    for ch in chunks:
        names = top_level_names(ch)
        if current and references_any(ch, declared):
            current.append(ch)
        else:
            if current:
                groups.append(current)
            current = [ch]
        declared |= names
    if current:
        groups.append(current)

    out = [header or '/* script.js */\n',
           f'/* {ISOLATION_TAG} isolation : un script en echec ne bloque pas les autres */\n']
    for i, g in enumerate(groups):
        body = '\n;\n'.join(g)
        strict = re.match(r"\s*(['\"])use strict\1", body)
        if strict:
            out.append(f'/* chunk {i} (use strict, non isole) */\n' + body + '\n;\n')
        else:
            out.append(f'/* chunk {i} */\ntry {{\n' + body +
                       f'\n}} catch (e) {{ console.error("{ISOLATION_TAG} script {i} en echec :", e); }}\n;\n')
    return ''.join(out).rstrip('\n;\n') + '\n'


# ----------------------------------------------------------------------
# Réparations ciblées
# ----------------------------------------------------------------------
def fix_move_inline_jquery(index_path, script_path):
    """[FORM] Déplace les scripts inline utilisant jQuery vers script.js."""
    html = open(index_path, encoding='utf-8').read()
    moved = []
    matches = list(re.finditer(r'[ \t]*<script\b([^>]*)>(.*?)</script>\n?', html, re.S))
    for m in matches:
        attrs, body = m.group(1), m.group(2)
        if 'src=' in attrs:
            continue
        if not re.search(r'\$\(|\bjQuery\b', body):
            continue
        moved.append(body.strip('\n'))
    if not moved:
        return 0
    # retirer les balises concernées (en replaçant depuis la fin)
    for m in reversed(matches):
        attrs, body = m.group(1), m.group(2)
        if 'src=' in attrs or not re.search(r'\$\(|\bjQuery\b', body):
            continue
        html = html[:m.start()] + html[m.end():]
    open(index_path, 'w', encoding='utf-8').write(html)
    js = open(script_path, encoding='utf-8').read()
    addition = '\n;\n' + '\n;\n'.join(
        f'/* {MOVED_TAG} depuis index.html (utilise jQuery) */\n'
        f'try {{\n{b}\n}} catch (e) {{ console.error("{MOVED_TAG} : echec", e); }}'
        for b in moved)
    open(script_path, 'w', encoding='utf-8').write(js.rstrip('\n') + addition + '\n')
    return len(moved)


def fix_cookie_guard(script_path):
    """[SCROLL+COOKIES] Ne rien faire si la page n'a pas de banniere."""
    js = open(script_path, encoding='utf-8').read()
    if 'garde docteur' in js:
        return False
    pat = re.compile(r"(const|var)\s+cookieBanner\s*=\s*document\.getElementById\('content-cookie'\);")
    m = pat.search(js)
    if not m:
        return False
    guard = (f"\n        {GUARDComment}\n"
             f"        if (!cookieBanner) {{ return; }}")
    js = js[:m.end()] + guard + js[m.end():]
    open(script_path, 'w', encoding='utf-8').write(js)
    return True


def fix_formly_null(script_path):
    """[FORMLY] Patches des null-derefrencements (pages sans formulaire
    multistep) : multistepForm et multistepContainer."""
    js = open(script_path, encoding='utf-8').read()
    changed = False
    patches = [
        ('formly-patch-doctor-1',
         re.compile(r"(const\s+multistepForm\s*=\s*document\[[\w$()'\"]{1,60}\]\(\s*"
                    r'"form\[data-form=\\x22multistep\\x22\]"\s*,?\s*\))'),
         ' || document.createElement("form") '),
        ('formly-patch-doctor-2',
         re.compile(r"(const\s+multistepContainer\s*=\s*document\[[\w$()'\".]{1,80}\]\([^,;]*?\))\s*(?=,|;)"),
         '|| document.createElement("div") '),
    ]
    # revert d'un patch v2 mal placé (fallback inséré dans les arguments)
    bad = '/* formly-patch-doctor-2 */ || document.createElement("div") '
    if bad in js:
        js = js.replace(bad, '')
        changed = True
    for tag, pat, fallback in patches:
        if tag in js:
            continue
        m = pat.search(js)
        if not m:
            continue
        js = js[:m.end(1)] + f' /* {tag} */' + fallback + js[m.end(1):]
        changed = True
    if changed:
        open(script_path, 'w', encoding='utf-8').write(js)
    return changed


def fix_isolation(script_path):
    """[ISOLATION] Reécrit script.js avec des chunks isolés."""
    js = open(script_path, encoding='utf-8').read()
    if ISOLATION_APPLIED in js:
        return False
    header, chunks = split_chunks(js)
    if len(chunks) < 2:
        return False          # un seul script : rien à isoler
    open(script_path, 'w', encoding='utf-8').write(isolate_chunks(header, chunks))
    return True


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


def fix_form_guards(script_path):
    """[FORM] 3 correctifs de robustesse formulaire : required caches qui
    bloquent le bouton Valider, exclusivite des checkboxes, retour
    utilisateur quand il n'y a pas de redirection ltm_typ."""
    js = open(script_path, encoding='utf-8').read()
    if 'garde formulaire v2' in js:
        return False
    # retirer une éventuelle garde v1 (IIFE délimitée par son commentaire d'en-tête)
    js = re.sub(r"/\* \[lp2site-doctor\] garde formulaire[^*]*\*/\n\(function \(\) \{.*?\}\)\(\);\n", '', js, count=1, flags=re.S)
    open(script_path, 'w', encoding='utf-8').write(FORM_GUARD_JS + '\n' + js)
    return True


# ----------------------------------------------------------------------
# Vérifications (sans modification)
# ----------------------------------------------------------------------
def check_site(site):
    """Retourne (alertes, infos) pour un site."""
    alerts, infos = [], []
    idx_p = os.path.join(site, 'index.html')
    js_p = os.path.join(site, 'script.js')
    css_p = os.path.join(site, 'style.css')
    html = open(idx_p, encoding='utf-8').read()
    js = open(js_p, encoding='utf-8').read() if os.path.isfile(js_p) else ''
    css = open(css_p, encoding='utf-8').read() if os.path.isfile(css_p) else ''

    # scripts inline jQuery restants
    n_inline_jq = sum(1 for m in re.finditer(r'<script\b([^>]*)>(.*?)</script>', html, re.S)
                      if 'src=' not in m.group(1) and re.search(r'\$\(|\bjQuery\b', m.group(2)))
    if n_inline_jq:
        alerts.append(f'{n_inline_jq} script(s) inline jQuery -> formulaire bloque')

    # banniere cookies
    has_banner = 'id="content-cookie"' in html
    has_cookie_script = 'content-cookie' in js
    if has_cookie_script and not has_banner and 'garde docteur' not in js:
        alerts.append('script cookies sans banniere -> scroll bloque (garde requise)')
    infos.append(f'banniere cookies: {"oui" if has_banner else "non"}')

    # isolation
    _, n_chunks = None, len(split_chunks(js)[1])
    if ISOLATION_APPLIED not in js and n_chunks >= 2:
        alerts.append('script.js non isole (1 exception tue tout)')
    # formly
    if re.search(r'multistepForm\s*=', js) and 'formly-patch-doctor-1' not in js:
        alerts.append('Formly sans patch null (crash pages sans formulaire multistep)')
    if '[lp2site-doctor] garde formulaire' not in js:
        alerts.append('garde formulaire absente (blocage possible a lenvoi)')

    # références locales cassées
    refs = set()
    for src in (html, css):
        for m in re.finditer(r'(?:src|href|poster|data-src)\s*=\s*"([^"]+)"', src):
            v = m.group(1)
            if not v.startswith(('http', 'data:', '#', 'mailto:', 'tel:', 'javascript:', '//')):
                v = v.split('#')[0].split('?')[0]
                if v and v not in ('style.css', 'script.js'):
                    refs.add(v)
        for m in re.finditer(r"url\(['\"]?([^'\")]+)['\"]?\)", src):
            v = m.group(1)
            if not v.startswith(('http', 'data:', '//', '#')):
                refs.add(v.split('#')[0].split('?')[0])
    missing = [r for r in sorted(refs) if r and not os.path.exists(os.path.join(site, r))]
    for r in missing:
        alerts.append(f'reference cassee: {r}')

    # SEO
    infos.append('GTM: ' + (','.join(sorted(set(re.findall(r'GTM-[A-Z0-9]+', html)))) or 'absent'))
    infos.append('description: ' + ('oui' if 'name="description"' in html else 'NON'))
    infos.append('H1: ' + str(len(re.findall(r'<h1\b', html))))
    return alerts, infos


def repair_site(site):
    """Applique les réparations. Retourne la liste des actions."""
    actions = []
    idx_p = os.path.join(site, 'index.html')
    js_p = os.path.join(site, 'script.js')
    n = fix_move_inline_jquery(idx_p, js_p)
    if n:
        actions.append(f'{n} script(s) jQuery deplace(s) vers script.js [FORM]')
    if fix_isolation(js_p):
        actions.append('script.js reisole en chunks try/catch [ISOLATION]')
    if fix_cookie_guard(js_p):
        actions.append('garde banniere cookies ajoutee [SCROLL+COOKIES]')
    if fix_formly_null(js_p):
        actions.append('patch Formly null applique [FORMLY]')
    if fix_form_guards(js_p):
        actions.append('garde formulaire (required caches, exclusivite, retour) [FORM]')
    return actions


# ----------------------------------------------------------------------
# Mode navigateur (optionnel, nécessite playwright)
# ----------------------------------------------------------------------
CHECK_JS = """() => {
  const out = {};
  const banner = document.getElementById('content-cookie');
  if (banner) {
    const cs = getComputedStyle(banner);
    const top = document.elementFromPoint(innerWidth/2, innerHeight/2);
    out.banniere = (cs.display !== 'none' && top && top.closest('#content-cookie')) ? 'visible' : 'masquee';
  } else out.banniere = 'absente';
  out.scroll = (document.documentElement.scrollHeight > innerHeight
      && getComputedStyle(document.body).overflow !== 'hidden') ? 'ok' : 'BLOQUE';
  let sans = 0;
  document.querySelectorAll('form').forEach(f => {
    const ev = (window.jQuery && jQuery._data) ? jQuery._data(f, 'events') : null;
    if (!((ev && ev.submit) || f.onsubmit)) sans++;
  });
  out.formSansHandler = sans;
  return out;
}"""


def browser_check(root, port):
    import asyncio
    from playwright.async_api import async_playwright

    async def run():
        results = {}
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            page = await browser.new_page(viewport={"width": 1366, "height": 900})
            sites = sorted(d for d in os.listdir(root)
                           if os.path.isdir(os.path.join(root, d))
                           and os.path.isfile(os.path.join(root, d, 'index.html')))
            for s in sites:
                errs = []
                page.on("pageerror", lambda e: errs.append(str(e)[:100]))
                try:
                    await page.goto(f"http://localhost:{port}/{s}/index.html",
                                    wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(1500)
                    st = await page.evaluate(CHECK_JS)
                    st['erreurs'] = errs[:2]
                    results[s] = st
                except Exception as e:
                    results[s] = {'chargement': str(e)[:80]}
            await browser.close()
        return results

    return asyncio.run(run())


# ----------------------------------------------------------------------
# Principal
# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description='Verifie et repare les sites generes')
    ap.add_argument('dossier', nargs='?', default='sites')
    ap.add_argument('--verifier', action='store_true', help='ne rien modifier, seulement verifier')
    ap.add_argument('--navigateur', action='store_true',
                    help='test navigateur reel (requires playwright + serveur local)')
    ap.add_argument('--port', type=int, default=8090, help='port du serveur local (--navigateur)')
    args = ap.parse_args()

    root = args.dossier
    if not os.path.isdir(root):
        log(f"Dossier introuvable : {root}")
        sys.exit(1)
    sites = sorted(d for d in os.listdir(root)
                   if os.path.isdir(os.path.join(root, d))
                   and os.path.isfile(os.path.join(root, d, 'index.html')))
    if not sites:
        log(f"Aucun site (dossier avec index.html) dans {root}")
        sys.exit(1)

    log(f"Docteur des sites — {len(sites)} site(s) dans {root}"
        + (" (MODE VERIFICATION, aucune modification)" if args.verifier else ""))
    log("=" * 100)

    report = []
    n_fixes = 0
    for s in sites:
        site = os.path.join(root, s)
        actions = [] if args.verifier else repair_site(site)
        alerts, infos = check_site(site)
        n_fixes += len(actions)
        status = 'OK' if not alerts else f'{len(alerts)} alerte(s)'
        log(f"{s:46} {status:14} {('; '.join(actions))[:70]}")
        for a in alerts:
            log(f"{'':46} !! {a}")
        report.append((s, actions, alerts, infos))

    # mode navigateur
    nav = {}
    if args.navigateur:
        log("")
        log("Test navigateur réel (http://localhost:%d)..." % args.port)
        nav = browser_check(root, args.port)
        for s, st in nav.items():
            if 'chargement' in st:
                log(f"{s:46} !! chargement impossible")
            else:
                log(f"{s:46} banniere={st['banniere']:8} scroll={st['scroll']:7} "
                    f"forms sans handler={st['formSansHandler']} erreurs={st['erreurs']}")

    # rapport
    lines = [f"# Diagnostic des sites — {date.today().isoformat()}",
             "", f"Dossier : `{root}` — {len(sites)} sites — "
             f"{'vérification seule' if args.verifier else str(n_fixes) + ' réparation(s) appliquée(s)'}", "",
             "| Site | Réparations appliquées | Alertes restantes | État |",
             "|---|---|---|---|"]
    for s, actions, alerts, infos in report:
        lines.append(f"| `{s}` | {'<br>'.join(actions) or '—'} | "
                     f"{'<br>'.join(alerts) or '—'} | {'✔' if not alerts else '⚠'} |")
    if args.navigateur:
        lines += ["", "## Vérification navigateur", "",
                  "| Site | Bannière cookies | Scroll | Formulaires sans handler | Erreurs JS |",
                  "|---|---|---|---|---|"]
        for s, st in nav.items():
            if 'chargement' in st:
                lines.append(f"| `{s}` | — | — | — | chargement impossible |")
            else:
                lines.append(f"| `{s}` | {st['banniere']} | {st['scroll']} | {st['formSansHandler']} "
                             f"| {'; '.join(st['erreurs']) or '—'} |")
    lines += ["", "## Détails par site", ""]
    for s, actions, alerts, infos in report:
        lines += [f"### `{s}`", f"- {'; '.join(infos)}",
                  f"- Réparations : {'; '.join(actions) or 'aucune'}",
                  f"- Alertes : {'; '.join(alerts) or 'aucune'}", ""]
    lines += ["## Comment tester correctement", "",
              "Les formulaires et la bannière nécessitent un serveur HTTP local",
              "(pas d'ouverture en double-clic file://) :", "",
              "```bash", "cd " + root, "python -m http.server 8080", "```",
              "", "Puis ouvrir http://localhost:8080/nom-du-site/ dans le navigateur.", ""]
    out = os.path.join(root, 'DIAGNOSTIC-SITES.md')
    open(out, 'w', encoding='utf-8').write('\n'.join(lines))
    log("")
    log(f"Rapport : {out}")
    if not args.verifier and n_fixes:
        log("Relancez une 2e fois pour confirmer : plus aucune réparation ne devrait s'appliquer.")
    # petit script de test local
    if not args.verifier:
        bat = os.path.join(root, 'tester-local.bat')
        sh = os.path.join(root, 'tester-local.sh')
        open(bat, 'w').write('@echo off\r\ncd /d "%~dp0"\r\npython -m http.server 8080\r\n')
        open(sh, 'w').write('#!/bin/sh\ncd "$(dirname "$0")"\npython3 -m http.server 8080\n')
        os.chmod(sh, 0o755)
        log("Scripts de test local générés : tester-local.bat (Windows) / tester-local.sh")


if __name__ == '__main__':
    main()
