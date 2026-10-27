#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic navigateur de tous les sites d'un dossier (tableau final)."""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/home/user/migration/sites"
BASE = "http://localhost:8090"

CHECK_JS = """() => {
  const out = {};
  const banner = document.getElementById('content-cookie');
  out.bannerExiste = !!banner;
  if (banner) {
    const cs = getComputedStyle(banner);
    out.bannerAffiche = cs.display !== 'none' && cs.visibility !== 'hidden';
    // la bannière est-elle l'élément visible au centre de l'écran ?
    const top = document.elementFromPoint(innerWidth/2, innerHeight/2);
    out.bannerAuDessus = !!(top && (top.closest && top.closest('#content-cookie')));
    out.bannerZIndex = cs.zIndex;
  }
  const bannerVisible = !!(banner && getComputedStyle(banner).display !== 'none');
  out.pageAdefiler = document.documentElement.scrollHeight > innerHeight;
  out.scrollPossible = !out.pageAdefiler
      || getComputedStyle(document.body).overflow !== 'hidden'
      || bannerVisible;  // banniere ouverte = verrou normal
  out.bodyInlineOverflow = document.body.style.overflow || '';
  // handlers de submit sur les formulaires ?
  let orphelins = 0;
  document.querySelectorAll('form').forEach(f => {
    const ev = (window.jQuery && jQuery._data) ? jQuery._data(f, 'events') : null;
    const jquerySubmit = !!(ev && ev.submit);
    const webflowAjax = f.hasAttribute('data-wf-page-id');
    const formly = f.closest('[data-form="multistep"]') || f.querySelector('[data-form="multistep"]');
    const direct = !!f.onsubmit;
    if (!(jquerySubmit || webflowAjax || formly || direct)) orphelins++;
  });
  out.formulairesOrphelins = orphelins;
  return out;
}"""


async def diag_one(page, url):
    errors, failed = [], []
    handlers = []
    page.on("pageerror", lambda e: errors.append(str(e)[:150]))
    page.on("console", lambda m: errors.append(m.text[:150]) if (m.type == "error" and "counter" not in m.text) else None)
    page.on("requestfailed", lambda r: failed.append(r.url[:100]) if "videsigns" not in r.url else None)
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
    except Exception as e:
        return {"chargement": f"ERREUR {e}"}
    await page.wait_for_timeout(1800)
    # repartir d'un contexte vierge : effacer le consentement mémorisé
    state = await page.evaluate(CHECK_JS)
    jq_errors = [e for e in errors if "$" in e or "jQuery" in e or "is not defined" in e]
    state["erreursPage"] = errors[:4]
    state["erreurJQ"] = bool(jq_errors)
    state["requetesKO"] = len(failed)
    return state


async def main():
    sites = sorted(d for d in os.listdir(ROOT)
                   if os.path.isdir(os.path.join(ROOT, d))
                   and os.path.isfile(os.path.join(ROOT, d, "index.html")))
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1366, "height": 900})
        print(f"{'site':44} {'bann.':6} {'au-des.':8} {'scroll':7} {'form∞':6} {'errJQ':6} erreurs")
        print("-" * 110)
        for s in sites:
            # contexte vierge à chaque site (pas de consentement mémorisé)
            await page.goto("about:blank")
            url = f"{BASE}/{s}/index.html"
            st = await diag_one(page, url)
            if "chargement" in st:
                print(f"{s:44} !! {st['chargement'][:60]}")
                continue
            print(f"{s:44} "
                  f"{'oui' if st.get('bannerAffiche') else ('non' if st.get('bannerExiste') else 'n/a'):6} "
                  f"{'oui' if st.get('bannerAuDessus') else 'non':8} "
                  f"{'oui' if st.get('scrollPossible') else 'NON':7} "
                  f"{st.get('formulairesOrphelins', '?'):6} "
                  f"{'OUI' if st.get('erreurJQ') else 'non':6} "
                  f"{'; '.join(st.get('erreursPage', [])[:2])[:45]}")
        await browser.close()


asyncio.run(main())
