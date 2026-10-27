# Pipeline de conversion autonome

Reproduit la conversion décrite par `../CONVERSION-SPEC.md` (une LP = un site
statique autonome, fonctionnel hors-ligne).

## Fichiers

| Fichier | Rôle |
|---|---|
| `localiser.py` | Usine de conversion des 138 pages → `../comparateur-local/<slug>/` |
| `moteur-leads.js` | Moteur de leads local spec §5.4 (injecté en fin de chaque `script.js`) |
| `audit.py` | Audit statique §7 (dossiers, refs cassées, CDN, `node --check`, structure) |
| `audit-jsdom-batch.py` | Lance `tools/audit-jsdom.js` par lots de processus Node isolés |
| `tools/audit-jsdom.js` | Tests navigateur headless JSDOM (formulaires, erreurs bloquantes, succès) |
| `stats.json` | Métriques de la dernière conversion complète |
| `audit-jsdom-result.txt` | Résultat du dernier balayage JSDOM 138/138 |
| `vendor/` | Librairies tierces auto-hébergées (voir ci-dessous) |

## Utilisation

```bash
python3 -m venv .venv && .venv/bin/pip install pillow
.venv/bin/python localiser.py --portail          # conversion des 138 pages
.venv/bin/python audit.py                        # audit statique (doit finir VERT)
cd tools && npm i jsdom && cd ..
.venv/bin/python audit-jsdom-batch.py           # 138/138 attendus
```

## Vendor (`vendor/`, aucun CDN à l'exécution)

- `jquery.min.js` — jQuery 3.5.1 (npm `jquery@3.5.1`, MIT)
- `webflow.js` — runtime Webflow IX2 (issu du dépôt, `js/webflow.js`)
- `multi-step.js` — `videsigns/webflow-tools` (GitHub), patch anti-null appliqué au build
- `inputmask.min.js` — RobinHerbots/Inputmask 5.0.9-beta.45 (MIT), variante jQuery
- `webfont.js` — WebFont Loader 1.6.26 (npm `webfontloader`, Apache-2.0) ; ses
  appels Google sont neutralisés au build (`WebFont.load` → no-op)
- `ticker.js` — lumious ticker (présent dans le runtime Webflow du dépôt)
- `tailwind-play.js` — Tailwind Play CDN 3.4.10 (npm `tailwindcss-cdn`, MIT), 1 page
- `gfonts/` — fontes Inter / Poppins `.woff2` réellement utilisées (auto-hébergement)

## Empaquetage RAR

Les binaires `rar`/`unrar` (RARLab 7.12 Linux x64) ne sont pas versionnés ;
les installer côté machine d'empaquetage, puis :

```bash
cd ../comparateur-local
rar a -r -ep1 -m5 -s ../comparateur-local.rar .
unrar t ../comparateur-local.rar      # All OK attendu
```
