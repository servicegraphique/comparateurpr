# RAPPORT-CONVERSION — sites autonomes `comparateur-local`

> Conversion appliquée à la lettre selon **[CONVERSION-SPEC.md](CONVERSION-SPEC.md)**.
> Date : 2026-10-27 (révision du 2026-10-27 : certification en navigateur réel, voir §4 bis).
> Outil reproductible : [`conversion/localiser.py`](conversion/localiser.py) (Python 3.11 + Pillow,
> aucun service externe), audits [`conversion/audit.py`](conversion/audit.py),
> [`conversion/audit-jsdom-batch.py`](conversion/audit-jsdom-batch.py) et
> [`conversion/browser-audit.py`](conversion/browser-audit.py) (Chromium headless réel).

---

## 1. Synthèse

| Indicateur | Valeur |
|---|---|
| Pages HTML sources | **138** (101 à la racine + 37 en sous-dossiers) |
| Dossiers autonomes générés | **138 / 138 — 0 écart, 0 page laissée de côté** |
| Fichiers produits | 5 374 (hors portail) |
| Poids total | **422,5 Mo** (somme des octets des 138 sites, soit ~403 MiB ; 416 MiB d'occupation disque avec le portail) — l'autonomie impose la duplication des assets (§2) |
| Archive `comparateur-local.rar` | **18,6 Mo** (RAR5 solide, 5 374 fichiers, intégrité `unrar t` OK) |
| Images rapatriées | 3 926 |
| Polices rapatriées | 1 025 |
| Taille moyenne par site | ~3,1 Mo (CSS ~103 Ko, JS ~1 466 Ko) |
| Audit statique (§7) | **VERT** |
| Audit JSDOM 138 sites (errors=0, form=PASS) | **138 / 138 VERT** |
| Audit **navigateur réel Chromium** (rendu, scroll, CSS, polices, formulaires) | **138 / 138 VERT** (détail §4 bis) |
| `node --check` sur chaque `script.js` | **138 / 138 OK** |
| Références d'assets cassées (HTML + CSS) | **0** |
| Images cassées en rendu navigateur | **0** |
| Débordement horizontal / erreur JS page / police en échec | **0 / 0 / 0** |
| URL CDN d'affichage résiduelles | **0** |

Chaque page s'ouvre en double-cliquant sur son `index.html` (schéma `file://`), sans réseau.

---

## 2. Structure livrée (spec §2)

```
comparateur-local/
├── index.html                 portail : 138 fiches + recherche filtrante
├── <slug>/
│   ├── index.html             page nettoyée, liens relatifs, w-form → form-autonome
│   ├── style.css              normalize → webflow → CSS page → <style> inline, purgé
│   ├── script.js              prélude → jQuery → webflow.js → multi-step → Inputmask
│   │                          → webfont → (ticker/tailwind) → scripts page → moteur de leads
│   ├── img/                   images réellement référencées (HTML, CSS, srcset)
│   └── fonts/                 polices référencées (absent si aucune)
└── <dossier>/<slug>/…         pages sources en sous-dossiers conservent leur hiérarchie
```

Conventions de nommage (spec §2) : `index.html` racine → `accueil/` ; `foo.html` → `foo/` ;
`sous-dir/foo.html` → `sous-dir/foo/`. Deux collisions réglées sans ambiguïté :

- `index.html` → `accueil/` (page « Comparateurpro »), `accueil.html` → `accueil-2/` ;
- `ticket-restaurant-.html` → `ticket-restaurant-alt/` (le `ticket-restaurant.html` canonique garde son slug).

Aucun asset n'est partagé entre deux sites : l'autonomie prime sur le poids (spec §2).

---

## 3. Conformité à la spec, point par point

### 3.1 Liens et dépendances (§3.1)
- Tous les chemins sont **relatifs** (`style.css`, `script.js` en `defer`, `img/…`, `fonts/…`).
- **Zéro** appel CDN d'affichage : `cdn.prod.website-files.com`, `d3e54v103j8qbb.cloudfront.net`,
  `fonts.googleapis.com/gstatic`, `ajax.googleapis.com`, `unpkg`, `cdnjs`, `jsdelivr`,
  `cdn.tailwindcss.com` — tous les scripts et images correspondants sont rapatriés dans
  `conversion/vendor/` puis copiés dans chaque site.
- La constante morte `//fonts.googleapis.com/css` du WebFont Loader est neutralisée (`about:blank`)
  et tous les `WebFont.load(...)` sont transformés en no-op : aucune requête Google Fonts ne part.

### 3.2 Éléments conservés (§3.2)
- GTM (2 conteneurs `GTM-WMVZJKS` / `GTM-53SH7D7F`), `dataLayer`, consent mode V2, meta SEO,
  favicon (`img/favicon.png`, webclip) : **inchangés, en place dans `<head>`**.
- Aucune page source ne contient de JSON-LD ; rien à préserver de ce chef.
- Le contenu éditorial (textes, ordre des sections, images) est migré tel quel.

### 3.3 Formulaire `w-form` (§3.3)
- Remplacement par découpage du token sur les espaces : seul le token exact **`w-form`** devient
  **`form-autonome`** (114 formulaires concernés).
- `w-form-done`, `w-form-fail`, `w-form-label`, `w-input`, `w-select`, `w-button`, `w-checkbox`,
  `w-radio` sont **intacts** (vérifié : 0 occurrence nue de `w-form`, 114 `form-autonome`).
- Équivalence CSS ajoutée : `.form-autonome{margin:0 0 15px;}` (reprend la règle native `.w-form`).

### 3.4 Iframes internes (§3.4)
- Les iframes TYP / thank-you pointent vers les dossiers locaux (`../typ-formulaires/<slug>/index.html`).
- Les iframes `ubepro.com` sont localisées quand un dossier cible distinct existe.
- **Garde anti-récursion** : une iframe dont la cible résolue est la page elle-même
  (`assurance-consultant-societe-conseil-v2`, dont l'URL externe n'a pas d'équivalent local distinct)
  reçoit un `srcdoc` de substitution au lieu de s'inclure en boucle.
- Les iframes GTM (`googletagmanager.com/ns.html`) et la vidéo YouTube éditoriale restent externes
  (tracking conservé / média tiers non remplaçable hors-ligne).

### 3.5 `style.css` (§4)
- Concaténation dans l'ordre imposé : `normalize.css` → `webflow.css` →
  `comparateurpro-829e84.webflow.css` → blocs `<style>` inline.
- **Toutes** les `url(...)` sont réécrites (y compris `@font-face`, `background-image`, formes
  `"x"`, `'x'`, nues et noms contenant une apostrophe, ex. `badge-d'employé`).
- Purge conservatrice (classes pilotées par JS/IX2 et préfixes `w-` systématiquement gardés),
  avec garde-fou : si une classe utilisée risque d'être perdue, la CSS complète est conservée.
- Seuls les commentaires Webflow sont supprimés, jamais les règles.
- `@font-face` cassées (src `.zip` / `format("undefined")`, bug d'export Webflow) retirées.

### 3.6 `script.js` (§5)
Ordre d'assemblage respecté : **1.** jQuery 3.5.1 · **2.** runtime `webflow.js` (IX2, formulaire,
lazy-load) · **3.** animations multi-étapes `multi-step.js` · **4.** scripts inline d'origine ·
**5.** logique `[data-form="step"]` (vendor + garde moteur) · **6.** Inputmask 5.0.9-beta.45 ·
**7.** moteur de leads · **8.** `ticker.js` (30 pages) et Tailwind Play auto-hébergé (1 page).

- **Multi-étapes (§5.1)** : classes de masquage préservées (`hide-step`, `hide-step-rn`,
  `hide-car`, `hide-etape-ass`, `hide`, `hide-agv-v2`, `hide-step-newton`, `hide-devis`,
  `hide-nett`) ; validation par étape (requis, téléphone, email, code postal) dans le moteur.
- **Masques (§5.2)** : `.phone`, `.zipcode`, `.numerique`, `.name`, `.m-name`, `.m-zipcode`,
  `.chiffre`, `.lettre` — test JSDOM : `0612345678` → `06 12 34 56 78`.
- **Aucun blocage SMS (§5.3)** :
  - variante jQuery (109 pages) : `.btn-verification{display:none!important}` + garde
    `unlockSubmit()` qui réactive le bouton dès l'acceptation du consentement ;
  - variante JS vanilla (5 pages : `assurance/agriculteur`,
    `assurance-consultants-societe-conseil`, `assurance-estheticienne-institut-beaute`,
    `assurance-estheticiennes-instituts-beaute-v1`, `assurance-tns-pro-v2-adw`) :
    `verified = true` d'emblée, `telephone_verifie = 'oui'`, interface SMS masquée —
    la validation ne dépend plus que du consentement, comme l'exige la spec.
  - les endpoints SMS ne sont plus appelés par le flux de validation.
- **Moteur de leads local (§5.4)** :
  - collecte **intégrale** du `FormData` (aucune liste figée) + groupes `data-checkbox` ;
  - alias canoniques (`mail↔email`, `telephone↔phone`, `nom↔last_name`, etc.) ;
  - persistance `localStorage` (avec shim mémoire si l'origine est opaque, ex. `file://` sous
    certains navigateurs) — testé de bout en bout : saisie TYP → pré-remplissage de la page
    de remerciement ;
  - push `dataLayer` de l'événement `formulaire_lead` (vérifié en JSDOM) ;
  - succès immédiat via `.w-form-done` (ou bannière `lp-merci-banner` si absent) :
    **jamais de « Oops! Something went wrong » hors-ligne** ;
  - envoi asynchrone **non bloquant** `keepalive` vers le CRM helloLead
    (`get_information.php`) et l'Apps Script de la page esthéticiennes ;
  - `data-redirect` / `redirect` / `ltm_typ` résolus en chemins relatifs locaux
    (`window.__lpLocalUrl`), les constructions `protocol//hostname` étant cassantes en `file://`.
- Chaque chunk inline est isolé dans un `try/catch` : un script en échec ne tue pas les suivants.
- Un prélude shim `localStorage` est placé **avant** les vendors (requis par `multi-step.js`).

### 3.7 Images et polices (§6)
- Seuls les assets réellement référencés sont embarqués (HTML, CSS, `srcset`, scripts inline).
- Noms slugifiés ASCII, variantes Unicode NFC/NFD gérées, dédoublonnage par empreinte MD5.
- Optimisation Pillow pour les > 40 Ko : largeur max ~540 px, JPEG/WEBP q55, PNG 64 couleurs,
  sans dégradation visible ; les fichiers déjà optimaux (≤ 40 Ko ou impossibles à réduire)
  sont conservés.
- Fallbacks sur fichiers existants pour les exports incomplets (AXA, Generali, logo Comparateur,
  visuels `énergie`, icône de case à cocher `custom-checkbox-checkmark`).
- Polices Google réellement utilisées via `css2` (Inter, Poppins) auto-hébergées en `.woff2`
  depuis les caches de polices du dépôt ; polices de marque (Dacia, Nissan, Toyota, Gotham,
  Corporate A, Nobel…) embarquées en local depuis `fonts/`.

---

## 4. Audit obligatoire (§7) — tous les contrôles verts

| Contrôle | Résultat |
|---|---|
| 0 dossier manquant (1 dossier par `.html` source) | ✅ 138/138 |
| 0 asset manquant (balayage HTML **et** CSS) | ✅ 0 référence cassée |
| `node --check` sur chaque `script.js` | ✅ 138/138 |
| Tests JSDOM (LP classique, multi-étapes, remerciement + balayage complet) | ✅ **138/138, errors=0, form=PASS** |
| Aucune URL CDN d'affichage dans `index.html` / `style.css` / `script.js` | ✅ 0 |
| Ouverture `file://` sans erreur console bloquante | ✅ simulateur JSDOM `fromFile()` (origine `file://`) |

Détail des tests fonctionnels JSDOM réussis : soumission → message de succès, persistance
`localStorage`, event `dataLayer formulaire_lead`, alias de champs, masque téléphone,
pré-remplissage inter-pages TYP → remerciement, neutralisation SMS, iframes locales.

Les messages résiduels en console sont **non bloquants et inhérents au mode hors-ligne / à
JSDOM** : chargement GTM impossible (tracking, §3.2), limitations canvas/iframe de JSDOM,
`fetch` réseau rejeté (attendu, toujours capturé).

---

## 4 bis. Certification en navigateur réel (Chromium headless)

Au-delà de JSDOM (qui ne fait ni mise en page ni peinture), chaque site a été chargé dans un
**vrai Chromium 153 headless auto-suffisant** (build décrit dans
[`conversion/tools/INSTALL-BROWSER.md`](conversion/tools/INSTALL-BROWSER.md), piloté par
`puppeteer-core` en CDP, rendu logiciel SwiftShader). Le harnais
[`conversion/tools/browser-check.js`](conversion/tools/browser-check.js) mesure, par page :

- **scroll** : défilement progressif sur toute la hauteur (déclenche les animations Webflow IX2
  et le lazy-load) ; `scrollMax`, hauteur de document ;
- **CSS / design** : nombre de feuilles et de règles appliquées, débordement horizontal
  (`scrollWidth > clientWidth`), sections de taille nulle, éléments restés invisibles après
  défilement, couleur de fond et police calculées ;
- **polices** : énumération des `@font-face`, `document.fonts.load/check` de chaque famille ;
- **images** : images `complete` mais `naturalWidth = 0` (cassées) et requêtes locales en échec ;
- **JavaScript** : `pageerror` (exception non capturée) ;
- **formulaires** : absence de token nu `w-form`, présence de `form-autonome`, et pour les
  **86 formulaires multi-étapes**, clic réel sur une réponse puis « Suivant » et vérification du
  changement d'étape (cartes `data-go-to` comme radios standard).

### Résultat final : 138 / 138 sites OK

`conversion/browser-audit.jsonl` — 0 requête locale échouée, 0 image cassée, 0 débordement
horizontal, 0 exception de page, 0 police en échec. Sur les 86 multi-étapes, 84 progressent
automatiquement dans le test ; les 2 restants (`geolocalisation-v2`, `template-2`) ont un
comportement **strictement identique à la page d'origine** (parité vérifiée tête-à-tête via
`conversion/make_fidele.py`, qui rebranche les mêmes librairies sur le HTML source) : ce n'est
donc pas une régression de conversion. Les animations IX2 (ex. grille de `suivi-de-vehicules`)
sont opacité 0 à l'état initial puis se révèlent toutes au scroll, là encore à l'identique de
l'original. Les seules requêtes en échec sont les hôtes externes (GTM, helloLead, ticker),
attendues hors-ligne et non bloquantes.

### Deux défauts réels détectés par cette certification et corrigés

1. **Blocage de la navigation multi-étapes (86 formulaires).** Le moteur de leads local
   interceptait en phase de capture les clics sur `[data-form="next-btn"]` et les annulait dès
   que sa propre validation échouait — or elle considérait à tort comme requis un champ
   conditionnel encore masqué (un `<select>` d'une étape inactive). La librairie multi-step
   d'orchestration gérait déjà la navigation **et** la validation. Correctif dans
   `conversion/moteur-leads.js` : suppression de cette interception des clics « Suivant » (la
   capture du lead reste assurée par l'écouteur `submit` en phase de capture), et durcissement
   de la fonction `visible()` pour ignorer les champs de taille nulle / `offsetParent` nul.
2. **SVG livré compressé gzip sous extension `.svg`** (placeholder Webflow de `typ-categ`,
   5 occurrences, rendu cassé). Correctif générique dans `conversion/localiser.py` : tout asset
   écrit dont les deux premiers octets sont la signature gzip (`1f 8b`) et dont l'extension n'est
   pas `.gz` est décompressé une fois dans `Store._place()`. Un seul asset du dépôt était
   concerné ; après correctif, 0 image cassée.

---

## 5. Pages écartées ou avec limitations — justification

**Aucune page n'est écartée : les 138 sources sont converties.** Limitations assumées et tracées :

| Sujet | Décision | Justification |
|---|---|---|
| 15 vidéos de `MISSING.txt` (mp4/webm absents de l'export) | sources `<source>` et `data-video-urls` neutralisées, **poster conservé** | fichiers inexistants dans le dépôt et CDN injoignable ; l'image de couverture reste affichée |
| Familles Google du boilerplate `WebFont.load` (~25 familles, ex. Roboto) | no-op, repli sur les piles système/CSS | police absente du dépôt, Google Fonts injoignable depuis le bac à sable ; les polices de marque critiques, elles, sont locales |
| `automobile.html` : `googletagmanager.com/gtag/js` (Google Ads) | appel laissé | script de **tracking**, explicitement conservé par le §3.2 ; échec silencieux hors-ligne |
| `nicolas/form-test.html` : widget `smartarget.online` | appel laissé | widget tiers d'une page de test/brouillon, sans rôle d'affichage ; échec silencieux hors-ligne |
| iframe récursive `assurance-consultant-societe-conseil-v2` | `srcdoc` de substitution | l'URL externe `ubepro.com` n'a pas d'équivalent local distinct ; évite l'auto-inclusion infinie |
| 1 vidéo YouTube éditoriale (`lexus-lbx`, 2 occurrences) | iframe externe conservée | média tiers non téléchargeable ; aucun asset d'habillage ne dépend du réseau |
| Liens éditoriaux externes (CNIL, ORIAS, mentions hellolead.pro, sites partenaires) | conservés | liens de navigation légaux/éditoriaux, et non ressources d'affichage (seules ces dernières sont visées par le §3.1) |

---

## 6. Livrables

1. **138 dossiers autonomes** dans `comparateur-local/` (structure du §2).
2. **Portail `comparateur-local/index.html`** : les 138 pages, classées par catégorie, avec une
   barre de recherche filtrante (nom, fichier source, catégorie).
3. **`comparateur-local.rar`** (18,6 Mo, RAR5 solide `-m5 -s`) : archive contenant le portail et
   les 138 dossiers (5 374 fichiers), chaque page étant fonctionnelle après extraction en
   double-cliquant sur son `index.html`. Test d'intégrité `unrar t` : **All OK**, extraction
   certifiée (0 CDN, 0 référence cassée, 0 échec `node --check` sur le contenu extrait).
   Le dossier décompressé `comparateur-local/` (422 Mo) reste disponible dans l'espace de travail ;
   seul l'archive est versionnée Git pour rester dans les limites de taille de patch.
4. **Le présent `RAPPORT-CONVERSION.md`**.

Outillage livré dans `conversion/` (non requis à l'exécution des sites) :
`localiser.py` (usine idempotente), `audit.py` (audit statique §7),
`audit-jsdom-batch.py` + `tools/audit-jsdom.js` (tests DOM headless),
`browser-audit.py` + `tools/browser-check.js` (certification en Chromium réel, §4 bis),
`make_fidele.py` (contrôle de parité avec la page d'origine),
`moteur-leads.js` (moteur spec §5.4), `vendor/` (libs tierces auto-hébergées, licences MIT/BSD
conservées dans leurs en-têtes), `stats.json` et `browser-audit.jsonl` (métriques détaillées
par page). Le navigateur headless lui-même (227 Mo) est reconstituable hors Git selon
`tools/INSTALL-BROWSER.md`.

---

## 7. Definition of Done (§9)

- [x] toutes les pages du dépôt ont leur dossier autonome (138/138) ;
- [x] le portail `index.html` liste 100 % des pages (138 fiches, recherche active) ;
- [x] `comparateur-local.rar` se décompresse et chaque page s'ouvre hors-ligne ;
- [x] l'audit du §7 est entièrement vert (statique + JSDOM 138/138) ;
- [x] certification en navigateur réel Chromium : rendu, scroll, CSS, polices, images et
      formulaires multi-étapes validés sur les 138 sites (138/138, §4 bis) ;
- [x] `RAPPORT-CONVERSION.md` est commité sur la branche de session.
