# CONVERSION-SPEC — Chaque LP devient un site autonome

> Spec de référence du dépôt `servicegraphique/comparateurpr`.
> Toute session (humaine ou agent) doit lire ce fichier AVANT de convertir une page.
> La règle est simple : **une LP = un site autonome, fonctionnel hors-ligne**.

---

## 1. Objectif

Convertir **CHAQUE** landing page, page et formulaire du dépôt en un site statique
autonome, déployable et fonctionnel **hors-ligne**, sans aucune dépendance CDN
pour l'affichage. Aucune page ne doit être laissée de côté.

Une page est considérée « convertie » uniquement si elle s'ouvre correctement
en double-cliquant sur son `index.html`, sans réseau.

---

## 2. Structure obligatoire, par page

```
<slug>/
├── index.html      la page, nettoyée et localisée
├── style.css       tout le CSS utile, local
├── script.js       jQuery + runtime Webflow + scripts de la page
├── img/            toutes les images réellement utilisées (HTML ET CSS)
└── fonts/          uniquement si des polices sont utilisées
```

Règles de nommage (aucune collision, aucun doublon) :

| Source                     | Dossier produit      |
|----------------------------|----------------------|
| `index.html` (racine)      | `accueil/`           |
| `foo.html`                 | `foo/`               |
| `sous-dir/foo.html`        | `sous-dir/foo/`      |

Chaque page reçoit **son propre** `style.css`, `script.js` et `img/`.
Aucune page ne partage un asset avec une autre : l'autonomie prime sur le poids.

---

## 3. `index.html`

### 3.1 Liens
- Uniquement des chemins **relatifs** : `style.css`, `script.js` (avec `defer`),
  `img/...`, `fonts/...`.
- **Zéro** requête CDN pour l'affichage :
  `cdn.prod.website-files.com`, `d3e54v103j8qbb.cloudfront.net`,
  `fonts.googleapis.com`, `fonts.gstatic.com`, `ajax.googleapis.com`,
  `unpkg.com`, `cdnjs.cloudflare.com`.
- Chaque URL distante utilisée par le rendu est **rapatriée** dans `img/`
  (ou `fonts/`), puis réécrite en relatif.

### 3.2 À conserver tel quel dans `<head>`
- Google Tag Manager, `dataLayer`, JSON-LD, meta SEO, favicon.
- Le contenu éditorial (titres, textes, ordre des sections, images) :
  **on migre, on ne refait pas**.

### 3.3 Formulaires
- Remplacer **le token de classe** `w-form` par `form-autonome`.
- Méthode sûre : découper `class="..."` sur les espaces et comparer le token
  exact. Ne JAMAIS utiliser un regex `\bw-form\b` (il casse `w-form-done`
  et `w-form-fail` car `-` est une frontière de mot).
- Conserver intacts : `w-form-done`, `w-form-fail`, `w-form-label`,
  `w-input`, `w-select`, `w-button`, `w-checkbox`, `w-radio`.

### 3.4 Iframes
- Les iframes internes (formulaires TYP, Audi, tests) pointent vers la version
  locale (`../<dossier>/index.html`), jamais vers `https://www.ubepro.fr/...`.

---

## 4. `style.css`

- Concaténer dans cet ordre : `normalize.css` → `webflow.css` → CSS de la page
  → blocs `<style>` inline de la page.
- Réécrire **toutes** les `url(...)` vers `img/...` ou `fonts/...`
  (y compris dans les `@font-face` et les `background-image`).
- Purge **conservatrice** : au moindre doute sur une classe, on garde.
  Classes pilotées par JS/IX2 et préfixes `w-` : toujours conservés.
- Supprimer uniquement les commentaires Webflow, pas les règles.

---

## 5. `script.js`

Ordre d'assemblage :

1. jQuery
2. runtime `webflow.js` (interactions IX2, formulaire, lazy-load)
3. animations IX2 propres à la page
4. scripts inline d'origine de la page
5. logique multi-étapes (`[data-form="step"]`)
6. Inputmask
7. moteur de leads
8. `ticker.js` si la page en a besoin

### 5.1 Multi-étapes
- Conserver les classes de masquage d'étapes appliquées sur `[data-form="step"]` :
  `hide-step`, `hide-step-rn`, `hide-car`, `hide-etape-ass`, `hide`,
  `hide-agv-v2`, `hide-step-newton`, `hide-devis`, `hide-nett`.
- Validation par étape avant passage à la suivante (champs requis, téléphone,
  email, code postal).

### 5.2 Masques de saisie (Inputmask)
`.phone`, `.zipcode`, `.numerique`, `.name`, `.m-name`, `.m-zipcode`,
`.chiffre`, `.lettre`.

### 5.3 Aucun blocage
- Supprimer le blocage de vérification SMS (`smspartner`, `.btn-verification`) :
  la validation doit fonctionner localement dès l'acceptation du consentement.

### 5.4 Moteur de leads local
- Collecte **tous** les champs du `FormData` (pas de liste figée).
- Alias de champs canoniques pour rester compatible CRM/Sheets.
- Persistance `localStorage` pour le pré-remplissage des pages
  `remerciements-*` et TYP.
- Push `dataLayer` (événement de conversion).
- Affichage immédiat du message de succès (`.w-form-done` ou équivalent local) :
  **jamais** de « Oops! Something went wrong » hors-ligne.
- Envoi asynchrone **non bloquant** vers CRM helloLead
  (`https://mc.hellolead.pro/mon_compte/api/webflow/get_information.php`)
  et Google Sheets (Apps Script) : si le réseau absent, l'utilisateur voit
  quand même sa confirmation.
- Groupes `data-checkbox`, redirections `data-redirect`, `ltm_typ` supportés.

---

## 6. `img/` et `fonts/`

- Ne rapatrier **que** les assets réellement référencés (HTML + CSS + srcset).
- Réparer les noms cassés de l'export Webflow (assets manquants) par un
  fallback sur un fichier existant équivalent.
- Gérer les variantes Unicode des accents (NFC / NFD) dans les noms de fichiers.
- Normaliser les noms en ASCII slug quand c'est possible
  (`téléchargement.png` → `telechargement.png`).
- Optimiser : images > 40 Ko redimensionnées (max ~540 px), JPEG/WEBP qualité
  ~55, PNG 64 couleurs — sans dégradation visible.

---

## 7. Audit obligatoire avant livraison

Aucune livraison sans ces contrôles, tous verts :

- [ ] 0 dossier manquant (1 dossier par `.html` source)
- [ ] 0 asset manquant (balayage HTML **et** CSS)
- [ ] `node --check` OK sur **chaque** `script.js`
- [ ] Tests JSDOM sur un échantillon représentatif :
      LP classique, formulaire multi-étapes, page de remerciement
      → `errors = 0` et `form = PASS`
- [ ] Aucune URL CDN restante dans `index.html` / `style.css` / `script.js`
      pour les ressources d'affichage
- [ ] Ouverture d'une page en `file://` sans erreur console bloquante

---

## 8. Livrables

1. **Un dossier autonome par page** (structure du §2).
2. **Un portail `index.html` à la racine** : liste des pages + barre de
   recherche filtrante, chaque entrée pointant vers `<slug>/index.html`.
3. **`comparateur-local.rar`** : archive finale contenant tous les dossiers
   autonomes **et** le portail, directement fonctionnelle en local.
4. **`RAPPORT-CONVERSION.md`** : nombre de pages converties, poids total,
   résultats d'audit, et liste des pages écartées avec justification.

---

## 9. Definition of Done

La mission est terminée quand :

- toutes les pages du dépôt ont leur dossier autonome ;
- le portail `index.html` liste 100 % des pages ;
- `comparateur-local.rar` se décompresse et chaque page s'ouvre hors-ligne ;
- l'audit du §7 est entièrement vert ;
- `RAPPORT-CONVERSION.md` est commité.
