#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Finition SEO H1 : conserve le premier <h1> (hero) et démové les suivants en <h2>.

Sécurité : la démotion n'est appliquée que si TOUS les <h1> de la page portent
une classe — sur ce parc, les classes Webflow (.h1-xxx) portent font-size,
line-height et marges, la démotion est donc visuellement neutre. Sinon, la page
est signalée pour traitement manuel.

Met aussi à jour la ligne H1 du rapport-site.md.

Usage : python3 finition-h1.py site-a/ site-b/ ...
"""
import os
import re
import sys


def process(site):
    p = os.path.join(site, 'index.html')
    if not os.path.isfile(p):
        print(f"{site}: index.html introuvable")
        return
    h = open(p, encoding='utf-8').read()
    h1s = list(re.finditer(r'<h1\b[^>]*>', h))
    if len(h1s) <= 1:
        print(f"{site}: {len(h1s)} H1 — rien à faire")
        return
    if any('class=' not in m.group(0) for m in h1s):
        print(f"{site}: ⚠ au moins un H1 sans classe — démotion NON appliquée "
              f"(styles de balise possibles → à traiter à la main)")
        return
    first_end = h1s[0].end()
    head, tail = h[:first_end], h[first_end:]
    tail = tail.replace('</h1>', '</h2>')
    tail = re.sub(r'<h1\b', '<h2', tail)
    open(p, 'w', encoding='utf-8').write(head + tail)
    print(f"{site}: ✔ 1 H1 conservé, {len(h1s) - 1} démové(s) en H2")

    rp = os.path.join(site, 'rapport-site.md')
    if os.path.isfile(rp):
        r = open(rp, encoding='utf-8').read()
        r = re.sub(r"- H1 : \*\*\d+\*\*.*",
                   f"- H1 : **1** ✔ (finition appliquée : {len(h1s) - 1} H1 secondaires "
                   f"démovés en H2, sans impact visuel — les classes Webflow portent les styles)",
                   r, count=1)
        open(rp, 'w', encoding='utf-8').write(r)


if __name__ == '__main__':
    for site in sys.argv[1:]:
        process(site)
