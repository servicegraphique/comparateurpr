#!/usr/bin/env python3
"""Audit navigateur réel des 138 sites (Chromium headless via puppeteer-core).
Un process node par site, concurrence 2, sortie JSONL + captures."""
import json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITES = ROOT / "comparateur-local"
TOOLS = ROOT / "conversion" / "tools"
SHOTS = Path("/tmp/shots")
SHOTS.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "conversion" / "browser-audit.jsonl"
PORT = int(os.environ.get("AUDIT_PORT", "8931"))

slugs = sorted(
    p.parent.relative_to(SITES).as_posix()
    for p in SITES.rglob("index.html")
    if p.parent != SITES
)
print(f"{len(slugs)} sites à auditer", flush=True)


def run(slug):
    url = f"http://127.0.0.1:{PORT}/{slug}/"
    prefix = str(SHOTS / slug.replace("/", "__"))
    t0 = time.time()
    data = None
    # reprises : un échec de lancement Chromium est transitoire (concurrence)
    for tentative in range(3):
        try:
            proc = subprocess.run(
                ["node", "browser-check.js", url, f"--shot={prefix}", f"--slug={slug}"],
                cwd=TOOLS, capture_output=True, text=True, timeout=180,
            )
            line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
            data = json.loads(line)
            if "fatal" not in data:
                break
        except Exception as exc:  # JSON invalide / timeout -> on réessaie
            data = {"slug": slug, "fatal": f"tentative {tentative}: {str(exc)[:200]}"}
        time.sleep(2)
    data["elapsed"] = round(time.time() - t0, 1)
    data["tentatives"] = tentative + 1
    return data


results = []
with ThreadPoolExecutor(max_workers=2) as ex:
    futs = {ex.submit(run, s): s for s in slugs}
    for i, fut in enumerate(as_completed(futs), 1):
        d = fut.result()
        results.append(d)
        flag = "OK " if d.get("ok") else "KO "
        ms = d.get("multistep")
        ms_txt = f" multi={'OK' if ms and ms.get('advanced') else ('BLOQUE' if ms and ms.get('clicked') else '-')}" if ms else ""
        extra = d.get("fatal", "") or (
            f"loc={len(d.get('failedLocal', []))} img={d.get('brokenImages', '?')} "
            f"overflow={d.get('horizontalOverflow', '?')} stuck={d.get('stuckHidden', '?')} "
            f"zero={d.get('zeroSizeSections', '?')} font={d.get('fontsLoaded', '?')}/{d.get('fontFamilies', '?')}"
            f"{ms_txt} pageerr={sum(1 for e in d.get('consoleErrors', []) if e.startswith('PAGEERROR'))}"
        )
        print(f"[{i:3d}/{len(slugs)}] {flag}{d.get('slug', '?')[:55]:55s} {extra}", flush=True)

results.sort(key=lambda d: d.get("slug", ""))
with open(OUT, "w", encoding="utf-8") as fh:
    for d in results:
        fh.write(json.dumps(d, ensure_ascii=False) + "\n")

ok = sum(1 for d in results if d.get("ok"))
print(f"\nBROWSER AUDIT: {ok}/{len(results)} sites ok")
print(f"détail: {OUT}")
