#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Marche réellement dans le formulaire multi-étapes d'un site converti :
remplit chaque étape, gère les boutons ancre+classe disabled, détecte
l'auto-avancée, soumet, et capture tout (réseau, erreurs, états).
L'endpoint SMS est mocké : aucun SMS réel n'est envoyé."""
import asyncio
import json
import sys

from playwright.async_api import async_playwright

SITE = sys.argv[1] if len(sys.argv) > 1 else "assurance-tns"
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8090"
PAGE = "index.html" if "8090" in BASE else "assurance-tns.html"

FILL_JS = """() => {
  const vis = el => !!(el.offsetParent !== null || el.getClientRects().length);
  const log = [];
  const estExclusive = c => /aucun|je ne sais|non concern|pas besoin|non, merci/i.test(
      (c.closest('label') || c.parentElement).innerText);
  // étape courante = dernier step visible
  const step = [...document.querySelectorAll('[data-form=step]')].filter(vis).pop() || document;
  // 1. décocher l'option exclusive si d'autres sont déjà cochées
  const boxes = [...step.querySelectorAll('input[type=checkbox]')].filter(vis);
  const cochees = boxes.filter(c => c.checked);
  const exCochee = cochees.find(estExclusive);
  const autresCochees = cochees.filter(c => !estExclusive(c));
  if (exCochee && autresCochees.length) { exCochee.click(); log.push('decoche:' + exCochee.name); }
  // 2. radios
  for (const r of step.querySelectorAll('input[type=radio]')) {
    if (vis(r) && !document.querySelector('input[name="' + r.name + '"]:checked')) {
      r.click(); log.push('radio:' + r.name); break;
    }
  }
  // 3. cocher des options normales si rien de coché
  const normales = boxes.filter(c => !estExclusive(c));
  if (!boxes.some(c => c.checked) && normales.length) {
    normales.slice(0, 2).forEach(c => { c.click(); log.push('checkbox:' + c.name); });
  }
  // 4. selects
  for (const s of step.querySelectorAll('select')) {
    if (!vis(s)) continue;
    const opt = [...s.options].find(o => o.value && !o.disabled);
    if (opt && !s.value) { s.value = opt.value; s.dispatchEvent(new Event('change', {bubbles:true})); log.push('select:' + s.name); }
  }
  // 5. champs texte
  for (const inp of step.querySelectorAll('input[type=text], input[type=email], input[type=tel], input:not([type]), textarea')) {
    if (!vis(inp) || inp.value.trim()) continue;
    const n = (inp.name + ' ' + (inp.placeholder || '')).toLowerCase();
    let v = 'Test automatisation';
    if (n.includes('mail') || inp.type === 'email') v = 'test.automatisation@example.com';
    else if (n.includes('tel') || n.includes('phone') || inp.type === 'tel') v = '06 01 02 03 04';
    else if (n.includes('postal') || n.includes('code_postal')) v = '75001';
    else if (n.includes('prenom') || n.includes('first')) v = 'Jean';
    else if (n.includes('nom') || n.includes('name')) v = 'TEST Auto';
    else if (n.includes('societe') || n.includes('entreprise') || n.includes('company')) v = 'Societe Test';
    inp.focus(); inp.value = v;
    inp.dispatchEvent(new Event('input', {bubbles:true}));
    inp.dispatchEvent(new KeyboardEvent('keyup', {bubbles:true, key: 'x'}));
    inp.dispatchEvent(new Event('change', {bubbles:true}));
    inp.blur();
    log.push('input:' + (inp.name || inp.type));
  }
  return log;
}"""

STEP_INFO_JS = """() => {
  const vis = el => !!(el.offsetParent !== null || el.getClientRects().length);
  const step = [...document.querySelectorAll('[data-form=step]')].filter(vis).pop();
  const btns = [...document.querySelectorAll('[data-form=next-btn], [data-form=submit-btn]')]
    .filter(vis).map(b => ({form: b.getAttribute('data-form'), disabled: b.className.includes('disabled'),
                            texte: (b.innerText || '').slice(0, 20)}));
  const inputs = step ? [...step.querySelectorAll('input, select, textarea')]
      .filter(vis).map(f => f.name + '(' + (f.type || f.tagName) + ')') : [];
  return {titre: step ? (step.innerText || ' ').split('\\n')[0].slice(0, 65) : null,
          boutons: btns, champs: inputs.slice(0, 8)};
}"""


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1366, "height": 950})

        async def mock_sms(route):
            await route.fulfill(status=200, content_type="application/json",
                                body=json.dumps({"status": "ok", "success": True,
                                                 "code": "123456"}))
        await page.route("**/envoi_code_verification*", mock_sms)

        req_log = []
        page.on("request", lambda r: req_log.append({"m": r.method, "url": r.url[:120],
                                                     "post": (r.post_data or "")[:200]})
                if r.resource_type in ("xhr", "fetch") else None)
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)[:150]))
        page.on("console", lambda m: errs.append(m.text[:150])
                if m.type == "error" and "counter" not in m.text else None)

        await page.goto(f"{BASE}/{PAGE}", wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(1200)
        try:
            await page.click("#continue-without-accepting-btn", timeout=3000)
            print("[bannière] fermée")
        except Exception:
            print("[bannière] absente")

        for step in range(1, 20):
            info = await page.evaluate(STEP_INFO_JS)
            if not info["titre"] and not info["boutons"]:
                print("[fin] plus d'étape visible")
                break
            print(f"[étape {step}] {info['titre']}")
            filled = await page.evaluate(FILL_JS)
            if filled:
                print(f"          rempli: {', '.join(filled[:5])}")

            # attendre l'éventuelle auto-avancée (radio-delay) puis réévaluer
            for tick in range(4):
                await page.wait_for_timeout(800)
                info = await page.evaluate(STEP_INFO_JS)
                sub = next((b for b in info["boutons"] if b["form"] == "submit-btn"), None)
                nxt = next((b for b in info["boutons"] if b["form"] == "next-btn"), None)
                if sub and not sub["disabled"]:
                    break
                if info["titre"] and info["titre"] != (None,) and filled:
                    # une étape est là : si elle a des champs vides, les remplir
                    new_fill = await page.evaluate(FILL_JS)
                    if new_fill:
                        filled = filled + new_fill
                        continue
                if nxt and not nxt["disabled"]:
                    break
            sub = next((b for b in info["boutons"] if b["form"] == "submit-btn"), None)
            nxt = next((b for b in info["boutons"] if b["form"] == "next-btn"), None)

            if sub and not sub["disabled"]:
                print("[SOUMISSION] bouton d'envoi actif — envoi réel, requêtes capturées ci-dessous")
                req_log.clear(); errs.clear()
                try:
                    await page.evaluate(
                        "() => { const vis = el => !!(el.offsetParent !== null);"
                        " const b = [...document.querySelectorAll('[data-form=submit-btn]')].filter(vis).pop();"
                        " if (b) b.click(); }")
                except Exception as e:
                    print("          clic impossible:", str(e)[:90])
                await page.wait_for_timeout(8000)
                break
            if nxt and not nxt["disabled"]:
                await page.evaluate(
                    "() => { const vis = el => !!(el.offsetParent !== null);"
                    " const b = [...document.querySelectorAll('[data-form=next-btn]')].filter(vis).pop();"
                    " if (b) b.click(); }")
                continue
            if info["boutons"]:
                print(f"[BLOQUÉ] étape {step} : {info['boutons']} | champs: {info['champs']}")
                await page.screenshot(path=f"/home/user/migration/formtest-{SITE}-bloque.png")
                break

        print("\n========== REQUÊTES RÉSEAU (soumission) ==========")
        for r in [x for x in req_log if x]:
            print(f"  {r['m']} {r['url']}")
            if r["post"]:
                print(f"      POST: {r['post']}")
        print("\n========== ERREURS CONSOLE ==========")
        for e in errs[:10]:
            print("  ", e)
        state = await page.evaluate("""() => ({
            url: location.href,
            succes: (document.querySelector('.w-form-done') || {}).offsetParent !== null,
            echec: (document.querySelector('.w-form-fail') || {}).offsetParent !== null,
            texteEchec: ((document.querySelector('.w-form-fail') || {}).innerText || '').slice(0, 90)
        })""")
        print("\n========== ÉTAT FINAL ==========")
        for k, v in state.items():
            print(f"  {k}: {v}")
        await page.screenshot(path=f"/home/user/migration/formtest-{SITE}-apres.png")
        await browser.close()


asyncio.run(main())
