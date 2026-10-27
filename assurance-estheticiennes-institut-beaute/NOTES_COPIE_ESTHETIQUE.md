# Copie « Esthéticiennes & instituts de beauté » — notes de production

Copie de `assurance-consultant-conseil-v2.zip`. **Le design, la structure et toute la mécanique sont strictement identiques** (même HTML balise par balise : 418 nœuds, mêmes `id`, mêmes classes, même CSS, même `main.js` non modifié). Seuls les **textes métier** et les **5 images** ont été remplacés.

---

## 1. Ce qui a été modifié

### Textes (contenu uniquement)

| Zone | Avant | Après |
|---|---|---|
| `<title>` / meta description | consultants et sociétés de conseil | esthéticiennes et instituts de beauté |
| Kicker du hero | Consultants & sociétés de conseil | Esthéticiennes & instituts de beauté |
| Accroche hero | Dirigeants, consultants indépendants ou sociétés de conseil… | Esthéticiennes indépendantes, instituts de beauté ou spas… |
| Puces hero | Santé, prévoyance et retraite **individuelle** | Santé, prévoyance et retraite, **individuelle ou collective** |
| Étape 1 — sous-titres des 2 garanties prioritaires | « Dommages causés à vos clients… », « Locaux, matériel, informatique… » | « Soins et prestations : dommages causés à vos clientes… », « Institut, cabines de soin, matériel et produits… » |
| Placeholders | `prenom@cabinet.fr`, `Nom de votre cabinet` | `prenom@institut.fr`, `Nom de votre institut` |
| Section « Vos assurances professionnelles » | RC Pro / multirisque pour consultants | formulations soins, cabines, stocks de produits, plateformes de réservation |
| Article de fond | erreur de conseil, mission, client | soin inadapté, réaction cutanée, prestation, cliente |
| Cartes santé / prévoyance / retraite | retraite individuelle | **retraite individuelle ou collective** + mention du contrat collectif pour les salariées |
| Section accompagnement | métiers du conseil | métiers de la beauté |
| FAQ (4 questions) | consultant, activité de conseil | esthéticienne, soins et prestations |
| CTA final | consultants et entreprises de conseil | esthéticiennes et instituts de beauté |
| `data-source` du formulaire | `LP CONSULTANTS` | `LP ESTHETIQUE` |

**Les axes prioritaires demandés sont respectés** : RC Pro et Multirisque restent les deux cartes `box-priority` en tête du formulaire et de la section garanties ; santé, prévoyance et retraite (individuelle **ou** collective) restent en second rideau, comme dans l'original.

### Images (5 remplacées, 1 supprimée)

| Fichier | Rôle | Note |
|---|---|---|
| `img/hero-estheticienne.jpg` | visuel du hero (remplace `hero-consultant.jpg`) | **recadré à la source en 4:3 (960×720)** pour que le visage reste entièrement dans le cadre, alors que l'original était un portrait rogné par `object-fit: cover` |
| `img/equipe-institut.jpg` | section accompagnement (remplace `equipe-conseil.jpg`) | même ratio 16:9 |
| `img/hero-background.jpg` | fond CSS du hero | institut moderne, zone gauche dégagée ; **luminosité recalée sur l'original (0,676 vs 0,692)** pour préserver le contraste du texte blanc |
| `img/conseillere.jpg` | CTA final | même cadrage portrait |
| `img/signature-contrat.jpg` | article + image | signature dans un institut |
| `img/icon-protection.png` | — | **supprimée** (elle n'était référencée nulle part : −518 Ko) |

Les deux icônes de garanties sont conservées telles quelles : `icon-rc-pro.png` (bouclier) et `icon-multirisque.png` (parapluie au-dessus d'un bâtiment) restent pertinentes et neutres. **Poids total des images : 1,45 Mo** (contre 2,02 Mo dans la v2 d'origine, soit −28 %).

---

## 2. Ce qui n'a volontairement PAS été touché

- `css/style.css` : **aucune modification** (0 octet changé).
- `js/main.js` : **aucune modification** (0 octet changé) — formulaire 7 étapes, validation, groupes conditionnels, SMS, honeypot, bridge `postMessage`, consentement, tracking : comportement identique à la v2.
- `id` des champs, `name`, `data-*` techniques, libellés des `question_*` et `reponse_lib_*` envoyés au CRM : inchangés, donc **le mapping CRM / Google Sheets reste valide**.
- GTM `GTM-53SH7D7F`, Consent Mode, bandeau cookies : inchangés.

---

## 3. À configurer avant mise en ligne (sinon mélange de leads)

| # | Point | Valeur actuelle | À faire |
|---|---|---|---|
| 1 | `data-form-id` | `ADW_LP_ASSURANCE_CONSULTANT` (inchangé volontairement pour ne rien casser) | Si le CRM peut enregistrer un nouveau formulaire, passer à `ADW_LP_ASSURANCE_ESTHETIQUE` **dans le HTML** et dans `DEFAULT_CONFIG` de `main.js`. Sinon les leads arrivent dans le même formulaire et se distinguent par `source = LP ESTHETIQUE`. |
| 2 | Google Sheets | URL Apps Script de la feuille AGV/AMR (celle des consultants) | Créer une feuille dédiée « esthétique » et remplacer `data-google-script-url`, sinon les leads se mélangent dans la feuille existante. |
| 3 | Chemin public de l'iframe | `https://ubepro.helloleadpreprod.fr/assurance-esthetique-institut-beaute/` | Publier l'archive à ce chemin **ou** corriger le `src` dans `WEBFLOW_EMBED.md`. |
| 4 | Détection d'URL directe (dans `main.js`) | `pathname === '/assurance-consultant-societe-conseil'` | Si la LP est ouverte hors iframe sur `comparateurpro.fr`, actualiser ce chemin. Sans impact en iframe. |
| 5 | Code Embed Webflow | `src` déjà mis à jour vers la nouvelle arborescence | Coller le bloc de `WEBFLOW_EMBED.md` dans une **nouvelle page** Webflow, sans toucher à celle des consultants. |
| 6 | `noindex, nofollow` | conservé | Ne pas retirer sans décision SEO explicite. |

> Les points 1 à 3 sont les seuls à traiter réellement. Le reste fonctionne tel quel.

---

## 4. Points de vigilance déjà identifiés dans l'audit de la v2 (toujours valables ici)

Ces défauts sont **hérités à l'identique** — la copie ne les corrige pas, conformément à la consigne « ne pas modifier la fonctionnalité » :

- 🔴 Le succès est affiché même quand le lead n'a pas pu être stocké (CRM en `no-cors`).
- 🔴 Google Sheets tronque le récapitulatif à 500 caractères → l'effectif, le statut et l'état de la société sont perdus côté feuille.
- 🔴 Vérification SMS obligatoire : si l'API SMS tombe, aucun lead n'est possible.
- 🔴 Mentions légales et politique de confidentialité toujours en `href="#"` ; aucune mention ORIAS ; consentement qui ne cite pas la transmission aux partenaires (problème plus sensible encore sur une cible de TPE/professions libérales).
- 🟠 Poppins chargée via Google Fonts ; pas de CSP.

Voir `ANALYSE_ASSURANCE_CONSULTANT_V2.md` pour le détail et les correctifs prêts à coller.

---

## 5. Contrôles effectués sur la copie

- Structure HTML **identique balise par balise** à l'original (418 nœuds, mêmes attributs hors texte/`src`/`alt`) — vérifié par parsing.
- CSS et JS : identiques au bit près.
- 0 image manquante, 0 image non référencée, 0 `id` en doublon, 0 champ sans label.
- Aucune occurrence résiduelle de « consultant / conseil / cabinet / mission » dans les textes visibles.

---

## 6. Correctifs v3 (2026-10-21)

Contrairement à la v2, cette version **modifie le HTML et le JS** pour corriger des bugs et le copywriting. Détail complet dans `rapport-corrections-v3.md` (hors archive).

- **A — bug corrigé** : la sous-question « Êtes-vous auto-entrepreneur ? » ne s'affiche désormais que si `Dirigeant non salarié (TNS)` est coché. Les deux radios portaient `data-statut-dirigeant="true"` ; elles portent maintenant `"salarie"` / `"tns"`, et `syncConditions()` + `validateStep()` testent `data-statut-dirigeant="tns"`.
- **B** : message de confirmation réécrit (« quelle(s) compagnie(s) d'assurances prendront contact avec vous »), titre aligné sur « Merci, votre demande a bien été reçue ! », et doublon supprimé entre le H3 et le paragraphe (HTML + JS).
- **C** : étape 2 du « Comment ça marche » remplacée par « Des compagnies d'assurance vous sont proposées » ; étape 1 accordée (« vos besoins »).
- **D** : féminisation systématique supprimée, ajout explicite des **salons de coiffure** et des **esthéticiens** dans le title, la meta, le hero, les garanties, l'article, la FAQ et le CTA ; « gérante » → « responsable », « salariées » → « salariés ».
- **E** : « vos clientes / une cliente / votre cliente » → « vos clients / un client / votre client ».

Les avertissements de la section 3 (formId, Google Sheets, chemin public) restent valables.
