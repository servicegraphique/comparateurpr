# Navigateur headless auto-suffisant pour l'audit de rendu

Le dossier `conversion/tools/browser/` (**non versionné**, ~227 Mo) contient un
Chromium headless capable de tourner sur un hôte minimal sans bibliothèques
graphiques ni accès aux CDN navigateurs. Il est piloté par `puppeteer-core`
(dans `node_modules/`) via le protocole CDP.

## Pourquoi cette construction

L'hôte de conversion est un Debian 12 épuré :

- aucun navigateur préinstallé, aucune lib `libnss3`/`libnspr4`/GTK ;
- seuls `registry.npmjs.org`, `api.github.com`, `codeload.github.com`,
  `github.com` et `pypi.org` sont joignables (les CDN Playwright/Google/
  objets GitHub sont bloqués), donc `npx playwright install` est impossible ;
- les PID namespaces sont interdits (`unshare --pid` → EPERM), ce qui impose
  `--no-zygote --single-process`.

## Constitution (reproductible)

1. **Chromium + SwiftShader + libs AL2023 + polices** — package npm
   `@sparticuz/chromium@153.0.0` (téléchargeable via npm, donc autorisé).
   `npm pack @sparticuz/chromium@153.0.0`, décompression Brotli des artefacts
   `bin/*.br` (`brotli` installé via pip) :
   - `chromium` → `browser/chromium` (binaire 209 Mo, Chromium 153.0.8010.0) ;
   - `al2023.tar` → `browser/libs/` (bibliothèques Amazon Linux 2023) ;
   - `swiftshader.tar` → `browser/` (`libEGL.so`, `libGLESv2.so`,
     `libvk_swiftshader.so`, `libvulkan.so.1`, `vk_swiftshader_icd.json`) :
     rendu logiciel sans GPU ;
   - `fonts.tar` → `browser/fonts/`.
2. **NSS/NSPR** — l'hôte n'a pas `libnss3.so`/`libnspr4.so`. Compilation depuis
   les sources Mozilla (`github.com/mozilla`) :
   - NSPR tag `NSPR_4_39_RTM`, NSS tag `NSS_3_109_RTM` ;
   - NSPR : `configure --disable-debug` puis forcer le 64 bits (le miroir GitHub
     n'embarque pas `config.guess/config.sub` : les fournir en stubs dans
     `build/autoconf/`, puis remplacer `-m32`/`-Di386=1`/`os_Linux_x86.s` par
     les équivalents x86_64 dans `config/autoconf.mk`) ;
   - NSS : `make nss_build_all USE_64=1 NSPR_INCLUDE_DIR=… NSPR_LIB_DIR=…`
     (le sous-système `cmd/` échoue faute de `zlib.h`, sans impact : seules les
     bibliothèques de `dist/.../lib` sont copiées) ;
   - copier `libnss3`, `libnssutil3`, `libssl3`, `libsmime3`, `libsoftokn3`
     (+`.chk`), `libfreebl*`, `libnssdbm3`, `libnssckbi`, `libnsssysinit`,
     `libsqlite3`, `libnspr4`, `libplc4`, `libplds4` dans `browser/libs/`.
   - Vérification : un programme C appelant `NSS_NoDB_Init` +
     `SSL_VersionRangeGetDefault` retourne 0 (TLS 1.2/1.3).
3. **Fontconfig** — réécrire `browser/fonts/fonts.conf` : le fichier d'origine
   pointe vers des chemins Lambda (`/var/task`, `/tmp/fonts`). Le remplacer par
   le chemin réel de `browser/fonts/fonts` et un `cachedir` accessible en
   écriture (`/tmp/fonts-cache`), avec alias sans-serif → Open Sans. Sans cela
   le renderer s'arrête sur `FATAL SkFontMgr_FontConfigInterface: Not implemented`.

## Lancement type (déjà encapsulé dans browser-check.js)

```
LD_LIBRARY_PATH=browser/libs:browser \
FONTCONFIG_PATH=browser/fonts \
browser/chromium --headless=shell --no-sandbox --no-zygote --single-process \
  --disable-dev-shm-usage --disable-setuid-sandbox --font-render-hinting=none \
  --remote-debugging-port=9222 about:blank
```

`puppeteer-core` se connecte ensuite au binaire via `executablePath` (aucun
téléchargement de navigateur par puppeteer).

## Audit

- `node browser-check.js <url> [--shot=prefixe] [--slug=nom]` : vérifie une page
  (scroll, règles CSS, polices, images cassées, débordement, formulaire,
  progression multi-étapes, requêtes locales échouées, erreurs JS).
- `python ../../browser-audit.py` : lance les 138 sites (concurrence 2, 3
  reprises en cas d'échec transitoire de lancement) et écrit
  `conversion/browser-audit.jsonl`.
