# 🔍 Audit complet du dépôt `manajahelvin-ux/comparateur`

> **Méthode** : inspection à distance via l'API GitHub et flux HTTP (aucun clonage, aucun téléchargement persisté). 148 fichiers texte (HTML/JS/CSS/MD, ~9 Mo) analysés en flux éphémère, arborescence complète des 1 672 fichiers parcourue.
> **Date de l'audit** : 22/10/2026 — Dépôt inspecté : `https://github.com/manajahelvin-ux/comparateur` (branche `main`)

---

## 1. Synthèse exécutive

**Note globale : 3,5 / 10** 🔴 — Dépôt public à risques immédiats.

Le projet est un ensemble de **~138 landing pages "générateur de leads" B2B** (export/développement Webflow) pour le compte de **ComparateurPro** (marque de la société *Hellodevis*, CRM *hellolead.pro*), couvrant l'assurance pro, l'énergie, la téléphonie, les véhicules utilitaires, les titres-restaurant, etc., ainsi que des pages pour des marques tierces (Lexus, Nissan, Toyota, Edenred, Primagaz, Sage…).

| Dimension | Note | Verdict |
|---|:---:|---|
| 🔐 Sécurité & exposition de données | **3/10** | 🔴 Endpoints de production + URL Apps Script exposés publiquement |
| ⚖️ RGPD / légal (licences) | **4/10** | 🔴 Polices propriétaires & images stock dans un dépôt public |
| 🔎 SEO | **2/10** | 🔴 95 % sans meta description, 100 % sans canonical, 93 % sans H1 |
| ⚡ Performance / poids | **4/10** | 🟠 219 Mo dont 200 Mo d'images ; dépendance persistante aux CDN Webflow |
| 🧹 Hygiène & maintenabilité | **3/10** | 🟠 1 seul commit, 34 fichiers v1/v2/test en racine, mojibake, typos |
| ♿ Accessibilité | **5/10** | 🟡 alt quasi complets, mais H1 manquants et aria quasi absent |

**Les 3 actions les plus urgentes** :
1. **Rendre le dépôt privé** (il expose l'infrastructure de production d'un business de leads).
2. **Roter/révoquer l'URL Google Apps Script** (`script.google.com/macros/s/AKfycb…/exec`) : n'importe qui peut y écrire.
3. **Faire auditer la protection serveur de l'endpoint SMS** (`mc.hellolead.pro/api/axialys/envoi_code_verification.php`) utilisé par 137 pages.

---

## 2. Fiche d'identité du dépôt

| Propriété | Valeur |
|---|---|
| Répository | `manajahelvin-ux/comparateur` — **public** |
| Créé le | 22/10/2026 à 07:08 UTC (aujourd'hui) |
| Dernier push | 22/10/2026 à 07:23 UTC |
| Commits | **1 seul** (« Initial commit », auteur *servicegraphique*) |
| Branches | 1 (`main`) — pas de branches de dev |
| Description / topics / homepage | absents |
| Licence | **aucune** |
| Taille | **~219 Mo** (1 672 fichiers) |
| Langages | HTML ~96 % (6,85 Mo), CSS (1,14 Mo), JS (1,14 Mo) + ~200 Mo d'images |

---

## 3. Cartographie du dépôt

```
comparateur/                        219 Mo, 1 672 fichiers
├── (racine)          102 fichiers, 5,1 Mo   ← ~90 pages HTML éparpillées à plat
├── images/         1 451 fichiers, 200,5 Mo  ← 92 % du poids du dépôt
├── fonts/             51 fichiers, 7,4 Mo    ← polices de marques incluses
├── css/                3 fichiers, 1,1 Mo    ← dont webflow.css de 1,07 Mo
├── js/                 1 fichier,  1,1 Mo    ← webflow.js (runtime minifié)
├── assurance*/…        8 fichiers            ← pages assurance dupliquées
├── assurance-estheticiennes-institut-beaute/ ← seule LP « propre » (js/main.js, README)
├── typ-formulaires/   12 fichiers            ← formulaires + thank-you pages
├── alfaromeo/ lexus/ mercedes-benz/ voiture/ nicolas/ temlpate-webflow/ webflow/
├── videos/             5 posters JPG         ← ⚠️ les vidéos elles-mêmes manquent
├── documents/          1 zip de police       ← doublon de fonts/
└── MISSING.txt                               ← 15 fichiers vidéo non exportés
```

**Contenu métier** : pages d'atterrissage multi-verticalités — assurance (RC pro, multirisque, TNS, prévoyance, agricole, IARD…), énergie (Primagaz, panneaux photovoltaïques), téléphonie/internet pro, géolocalisation de flotte, cartes carburant, titres-restaurant Edenred, paie Sage, véhicules (Lexus LBX, Nissan Juke/Ariya, Dacia Jogger, Hyundai, Mercedes eVito/Sprinter, Alfa Romeo Tonale, Range Rover, Volvo, Mitsubishi Fuso, Fiat Pro, Ayvens…), et pages « remerciement » (thank-you pages).

---

## 4. 🔐 Sécurité & exposition de données (critique)

### 4.1 Ce qui est exposé publiquement (dépôt public)

| Élément exposé | Localisation | Risque |
|---|---|---|
| **URL Google Apps Script complète** (`/macros/s/AKfycbwrbyCb9…/exec`) | LP esthéticiennes | 🔴 N'importe qui peut POSTer de fausses lignes dans le Google Sheet AGV/AMR (spam, pollution de données, DoS du quota Apps Script) |
| **Endpoint CRM de production** `mc.hellolead.pro/mon_compte/api/webflow/get_information.php` | main.js + README | 🔴 Injection de leads falsifiés possible si pas de contrôle serveur |
| **Endpoint SMS** `mc.hellolead.pro/api/axialys/envoi_code_verification.php` — référencé **274 fois, dans 137 pages** | toutes les pages | 🔴 Abus possible (SMS facturés, harcèlement de numéros tiers) si l'API n'a pas de rate-limiting/auth serveur |
| **Endpoint SMS de préprod** `…/smspartner/envoi_code_verification.php` | 8 pages | 🟠 Idem |
| **Architecture complète documentée** (README : mapping CRM, formId `ADW_LP_ASSURANCE_CONSULTANT`, schéma Sheets, GTM, logique honeypot, URLs préprod `ubepro.helloleadpreprod.fr`) | README/MD | 🔴 Carte bleue offerte à des attaquants |
| **2 conteneurs GTM** : `GTM-WMVZJKS` (19 pages) et `GTM-53SH7D7F` (15 pages) | HTML | 🟡 Incohérence prod/préprod ; injection de tags possible si conteneurs mal sécurisés |
| E-mails professionnels (DPO ComparateurPro, Dataventure, Toyota/Nissan Europe, freelances `harrys@avent-media.fr`…) et numéros de téléphone | pages | 🟢 Standard pour des mentions légales, mais à connaître |

### 4.2 Points positifs de sécurité
- ✅ **Aucune clé API / mot de passe / token en dur** détecté (scan de motifs `api_key`, `secret`, `Bearer`… négatif).
- ✅ Honeypot anti-spam présent sur la LP custom.
- ✅ Vérification de numéro mobile par SMS (code 6 chiffres, gestion des erreurs 422/404/410/409/429/502, renvoi après 120 s) — travail soigné.
- ⚠️ MAIS : les 131 `<form>` n'ont **aucune action HTML** (tout repose sur le JS) et l'envoi CRM se fait en mode `no-cors`/`sendBeacon` « fire-and-forget » — **aucune confirmation d'insertion** (reconnu dans le README).
- ⚠️ Le README précise que **GTM est chargé sans condition de consentement** et que le `noscript` contourne les préférences.

---

## 5. ⚖️ RGPD & conformité légale

### 5.1 Ce qui est en place ✅
- Page `mentions-legales.html` et `politique-de-confidentialite-donnees-personnelles.html` présentes.
- Références CNIL, Bloctel, ORIAS (courtier), liens RGPD Edenred.
- E-mails DPO identifiés ; logique de consentement analytics/marketing implémentée sur la LP custom (UTM/`gclid` filtrés selon consentement).
- Éditeur identifié : « ComparateurPro est une marque digitale de la société Hellodevis ».
- ⚠️ Aucun n° SIREN/SIRET détecté au scan automatique dans les mentions légales (à vérifier manuellement — obligatoire en France).

### 5.2 Risques de licences (spécifique à un dépôt **public**) 🔴
- **Polices propriétaires de marques automobiles redistribuées** : `Corporate-A` (Mercedes-Benz), `Dacia-Block` (5 fichiers), `NissanBrand`, `Toyota-Type`/`ToyotaType`, `NouvelR` (Renault), `Nobel` (Lexus), `Gotham` (Monotype), `Helvetica Neue LT Pro` (Monotype), `Charter`. Certaines proviennent de **`fonnts.com-*.ttf`** (site de téléchargement de polices, licence incertaine).
- **Images stock** aux noms révélateurs : `—Pngtree—confetti…`, `—Pngtree—luxury-5-star…`, `vecteezy_data-protection…`, `600nw-2389537541` (Shutterstock), `removebg-preview`, `pexels-…` → droits d'utilisation à prouver.
- **Logos d'assureurs** (Allianz, AXA, Generali, Groupama, Hiscox, Macif, Mercer, MMA) dans `img/partenaires/` → usage de marques sans accord visible.
- **Zip de police dupliqué** (`helvetica-neue-lt-pro-47…zip` dans `documents/` ET `fonts/`).

---

## 6. 🔎 SEO — très défaillant

Sur les **138 pages HTML** analysées :

| Critère | Résultat | Gravité |
|---|---|---|
| `<meta name="description">` | **131 pages sur 138 sans** (95 %) | 🔴 |
| `<link rel="canonical">` | **138/138 sans** (100 %) | 🔴 |
| `<h1>` | **129 pages sans H1** (93 %) ; 4 pages avec plusieurs H1 | 🔴 |
| `robots.txt` / `sitemap.xml` | **absents du dépôt** | 🔴 |
| `favicon.ico` / `404.html` | absents (favicon.png + webclip.png présents, référencés sur les 138 pages ✅) | 🟡 |
| Titres dupliqués | 8 titres identiques ×2 (`Energie`, `Primagaz`, `Ticket Restaurant`…) | 🟠 |
| Contenu dupliqué | `index.html` ≈ `accueil.html` à **98 %** ; `lexus-lbx.html` ≈ `lexus/lbx.html` à 96 % ; 24+ fichiers `v1/v2/v4` en racine | 🟠 |
| Page noindex | `assurance-estheticiennes-institut-beaute/index.html` (documenté « à retirer avant publication ») | 🟡 |
| `<html lang>` | présent partout ✅ | 🟢 |
| Liens internes cassés | **0** ✅ | 🟢 |
| Assets référencés introuvables | **4** (ex. `02_Remboursement-de-la-diffeĚrence-20.jpg` — mojibake) | 🟡 |

**Conséquence** : en l'état, la majorité des pages sont quasi invisibles/indifférenciables pour les moteurs, et les doublons v1/v2 créent du contenu dupliqué massif.

---

## 7. ⚡ Performance & poids

- **219 Mo au total**, dont `images/` = **200,5 Mo (92 %)** pour 1 451 fichiers — dont **835 variantes responsive Webflow** (`-p-500`, `-p-800`…) committées en plus des originaux.
- **39 fichiers > 1 Mo** ; top : `OP_240218_FIAT_05398-2.png` (3,49 Mo), `Trac_2.png` (3,45 Mo), `pexels-kindel-media-9800031.jpg` (3,43 Mo), `BG_panneaux_photovoltaiques.png` (3,40 Mo).
- `css/comparateurpro-829e84.webflow.css` : **1,07 Mo** ; `js/webflow.js` : **1,09 Mo** (runtime Webflow complet chargé sur chaque page).
- **Le dépôt n'est pas autonome** : 137 pages référencent encore des assets sur le CDN Webflow (`d3e54v103j8qbb.cloudfront.net`), 18 sur `cdn.prod.website-files.com`, 5 sur `uploads-ssl.webflow.com`.
- CDN multiples par page (jsdelivr, cdnjs, Google Fonts, ajax.googleapis) — typique Webflow, mais many round-trips.
- **jQuery 3.5.1** (juin 2020) chargé sur 137 pages — pas de CVE XSS majeure connue pour cette version, mais vieillissant et remplaçable.
- 18 liens `http://` non sécurisés (`rgpd.myedenred.fr`, `plugandtel.com`, `bloctel.gouv.fr`…) — contenu mixte à corriger.
- `MISSING.txt` signale **15 fichiers vidéo manquants** (mp4/webm) → vidéos cassées sur `volvo.html`, `nissan-juke.html`, `lexus/lbx.html`, `canal.html` (seuls les posters JPG sont présents).
- 💡 Le dépôt GitHub approche les seuils de confort (recommandation GitHub < 1 Go, warning dès 50 Mo pour un dépôt « normal » ; ici 219 Mo d'assetsbinaires).

---

## 8. 🧹 Hygiène du dépôt & maintenabilité

- **1 seul commit** (« Initial commit ») → aucun historique, impossible de retracer les évolutions ; auteur « servicegraphique ».
- **Pas de README à la racine** (la documentation utile est enfouie dans `assurance-estheticiennes-institut-beaute/`).
- **Pas de `.gitignore`**, pas de LICENSE, pas de CI/CD, pas de tests, pas de lintage.
- **Nommage** :
  - 🟠 dossier `temlpate-webflow/` (**faute de frappe** de « template ») ;
  - 🟠 dossier `nicolas/` (prénom d'une personne — pages de test `form-test.html`, `formly.html`) ;
  - 🟠 7 fichiers `téléchargement.png`…`téléchargement6.png` + `_1`, numérotation opaque ;
  - 🟠 **mojibake et caractères non-ASCII** dans 32 noms de fichiers (`—Pngtree—…`, `diffeěrence`, `Emblème`, `suivie-de-véhicuile` [faute]) → URLs encodées moches, casse sur certains serveurs/OS ;
  - 🟠 34 fichiers `v1/v2/v4/adw/test/template/typ` (~1,8 Mo) mélangés aux pages finales en racine ;
  - 🟠 pages dupliquées racine/dossiers (`lexus-lbx.html` vs `lexus/lbx.html` ; `index.html` vs `accueil.html`).
- **Logique applicative dupliquée** : la mécanique formulaire/SMS est inlinée dans chacune des 137 pages (274 références à l'endpoint SMS) au lieu d'un JS partagé — seule la LP « esthéticiennes » a un `js/main.js` propre et documenté.
- **Le sous-dossier esthéticiennes est le modèle à suivre** : README détaillé, NOTES de production, WEBFLOW_EMBED.md, js/css séparés, formulaire multi-étapes robuste.

---

## 9. ♿ Accessibilité

- `<img>` sans `alt` : **13 sur 1 254 (1 %)** — très bon ✅
- `lang` présent sur 100 % des pages ✅
- ⚠️ Attributs `aria-*` : **seulement 22 au total sur 138 pages** — navigation clavier, labels de formulaires et rôles ARIA quasi absents.
- ⚠️ 129 pages sans H1 → structure sémantique invalide, préjudiciable aussi au SEO et aux lecteurs d'écran.
- Titres d'iframe présents sur la LP custom ✅.

---

## 10. 🟢 Points forts à conserver

1. **Zéro secret dur** (clé API/mot de passe) dans le code.
2. **Aucun lien interne cassé** sur 138 pages.
3. Mentions légales + politique de confidentialité + références CNIL/Bloctel/ORIAS présentes.
4. La LP « esthéticiennes » : formulaire multi-étapes avec validation, honeypot, vérification SMS robuste (gestion fine des codes d'erreur, expiration, renvoi), consentement granulaire analytics/marketing, documentation exemplaire.
5. Thank-you pages dédiées (bonne pratique lead-gen et tracking conversion).
6. `lang`, alt quasi systématiques, favicon/webclip en place.

---

## 11. 📋 Plan d'action priorisé

### 🔴 P0 — Immédiat (aujourd'hui)
1. **Rendre le dépôt privé** (Settings → Danger Zone → Change visibility) — c'est un dépôt de travail contenant l'infra de production d'un business.
2. **Révoquer/ré deploying le Google Apps Script** et faire vérifier le contrôle d'accès (token secret, honeypot côté serveur, rate-limit).
3. Vérifier avec l'équipe API que `envoi_code_verification.php` (SMS) et `get_information.php` (CRM) ont un **rate-limiting + auth serveur + validation** — le code client est public désormais.
4. Ajouter un **CAPTCHA serveur ou validation d'origine** sur les endpoints exposés.

### 🟠 P1 — Court terme (cette semaine)
5. Ajouter `.gitignore`, `README.md` à la racine, `LICENSE` (ou justification), `robots.txt`, `sitemap.xml`, `404.html`.
6. Supprimer les **doublons** : trancher `index.html` vs `accueil.html`, pages v1/v2 en racine, dossiers `nicolas/`, `temlpate-webflow/`, `webflow/`, zip dupliqué.
7. Corriger les noms de fichiers mojibake/non-ASCII (renommage + mise à jour des références).
8. Réintégrer les **15 vidéos manquantes** ou supprimer les blocs `<video>`.
9. Retirer le `noindex` de la LP esthéticiennes **au moment de la mise en ligne** + corriger son `lang`/titre wrapper (déjà noté dans le README).
10. Unifier le tracking : **un seul conteneur GTM**, déployé sur les 104 pages non équipées, avec mode consentement (et retirer le `noscript` non conforme).

### 🟡 P2 — Moyen terme
11. **SEO de base** : meta description unique (131 pages), canonical, un H1 par page, Open Graph.
12. **Performance** : compresser/convertir les 39 images > 1 Mo en WebP/AVIF (gain estimé > 60 Mo), supprimer les variantes Webflow non référencées, rapatrier ou assumer les assets CDN Webflow.
13. **Licences** : auditer les polices de marque (remplacer par des polices libres type Inter/Source Sans), prouver les licences Pngtree/Vecteezy/Shutterstock, obtenir les accords d'usage des logos partenaires — ou retirer du dépôt public.
14. **Refactoring** : extraire la logique formulaire en un `main.js` partagé (au lieu de 137 copies inline).
15. Accessibilité : H1, labels de formulaires, `aria`, focus visible.
16. Process Git : branches + PR + revues, commits atomiques (le « Initial commit » de 219 Mo est un point de non-retour).

---

## 12. Annexes — chiffres détaillés

**Répartition par type** : .png 679 (89,0 Mo) · .jpg 597 (104,6 Mo) · .html 138 (6,85 Mo) · .webp 80 (2,4 Mo) · .svg 47 (1,7 Mo) · .avif 46 (2,9 Mo) · .ttf 28 (4,2 Mo) · .otf 21 (2,5 Mo) · .jpeg 21 (1,8 Mo) · .css 4 (1,1 Mo) · .js 2 (1,1 Mo) · .gif 3 · .zip 2 · .md 3 · .txt 1

**Domaines externes les plus référencés** : hellolead.pro (627) · cdn.jsdelivr.net (169) · d3e54v103j8qbb.cloudfront.net/CDN Webflow (144) · fonts.googleapis.com (142) · webflow.com (141) · cdnjs.cloudflare.com (140) · ajax.googleapis.com (137) · googletagmanager.com (61) · comparateurpro.fr (54)

**Pages sans meta description** : 131/138 · **sans canonical** : 138/138 · **sans H1** : 129/138 · **sans GTM** : 104/138 · **formulaire sans action HTML** : 131

**Assets manquants référencés** : 4 (lexus/lbx.html, paritel-vous-rembourse{,-v2}.html, typ-categ.html) · **vidéos manquantes** : 15 (MISSING.txt)

---

*Rapport généré par inspection distante (API GitHub + flux HTTP) — aucun clonage du dépôt. Arborescence complète conservée dans `audit/tree.json`.*
