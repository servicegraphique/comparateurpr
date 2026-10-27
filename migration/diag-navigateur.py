#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostic navigateur d'un site converti : erreurs console, bannière cookies,
scroll, formulaire. Usage: python3 diag-navigateur.py <url>"""
import asyncio
import json
import sys

from playwright.async_api import async_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8090/assurance-tns/index.html"


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1366, "height": 900})

        console_msgs, failed_requests, console_errors = [], [], []
        page.on("console", lambda m: (console_msgs.append(f"[{m.type}] {m.text[:300]}"),
                                      console_errors.append(m.text) if m.type == "error" else None))
        page.on("requestfailed", lambda r: failed_requests.append(
            f"{r.url[:120]} → {r.failure}"))
        page.on("pageerror", lambda e: console_errors.append(f"PAGEERROR: {e}"))

        await page.goto(URL, wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(2500)

        state = await page.evaluate("""() => {
            const banner = document.getElementById('content-cookie');
            const cs = banner ? getComputedStyle(banner) : null;
            return {
                bannerExiste: !!banner,
                bannerDisplay: cs ? cs.display : null,
                bannerVisibilite: cs ? cs.visibility : null,
                bannerOpacity: cs ? cs.opacity : null,
                bannerZIndex: cs ? cs.zIndex : null,
                bannerTaille: banner ? banner.offsetWidth + 'x' + banner.offsetHeight : null,
                bodyOverflow: getComputedStyle(document.body).overflow,
                bodyInlineOverflow: document.body.style.overflow,
                htmlOverflow: getComputedStyle(document.documentElement).overflow,
                scrollable: document.documentElement.scrollHeight > document.documentElement.clientHeight,
                scrollHeight: document.documentElement.scrollHeight,
                innerHeight: window.innerHeight,
                jqueryCharge: typeof window.jQuery !== 'undefined',
                webflowCharge: typeof window.Webflow !== 'undefined',
                nbEcouteursForm: document.querySelectorAll('form').length,
            };
        }""")
        print("=== ÉTAT DE LA PAGE ===")
        for k, v in state.items():
            print(f"  {k}: {v}")

        print("\n=== ERREURS CONSOLE (pageerror + error) ===")
        if console_errors:
            for e in console_errors[:15]:
                print("  ", e[:250])
        else:
            print("   aucune")

        print("\n=== REQUÊTES ÉCHOUÉES ===")
        if failed_requests:
            for f in failed_requests[:15]:
                print("  ", f)
        else:
            print("   aucune")

        # screenshot pour vérification visuelle
        out = URL.split("//")[1].replace("/", "_").replace(":", "_")
        path = f"/home/user/migration/diag-{out}.png"
        await page.screenshot(path=path, full_page=False)
        print(f"\nScreenshot: {path}")
        await browser.close()


asyncio.run(main())
