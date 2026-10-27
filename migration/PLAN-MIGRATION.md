# 🏗️ Plan de migration — Chaque LP devient un site classique autonome

> **Objectif** : transformer les ~138 landing pages du dépôt `comparateur` en sites statiques
> individuels, autonomes et déployables indépendamment :
>
> ```
> site-<slug>/
> ├── index.html      la page, nettoyée
> ├── style.css       toutes les styles, purgées, locales
> ├── script.js       jQuery + webflow.js + logique de la page
> ├── img/            images réellement utilisées (y compris CDN rapatrié)
> ├── fonts/          polices réellement utilisées
> ├── robots.txt / sitemap.xml
> └── rapport-site.md bilan de conversion + checklist QA
> ```

---

## 1. Pourquoi ce chantier est le bon, maintenant

L'audit du 22/10/2026 a montré un dépôt de 219 Mo où tout est mélangé : 138 pages à plat,
200 Mo d'images communes, une CSS de 1,1 Mo partagée par tout le monde, des assets encore
hébergés sur les CDN Webflow, des v1/v2/tests en racine. Conséquences : pages non
autonomes, déploiement impossible page par page, dette SEO massive, et toute action sur
un fichier partagé risque de casser les 137 autres.

**Une LP = un site autonome** règle mécaniquement : le déploiement unitaire, la
suppression des dépendances CDN Webflow, l'isolation des régressions, le SEO par site,
et la possibilité d'archiver/nettoyer le dépôt d'origine.

## 2. Règles d'or (les décisions d'architecte)

| # | Décision | Justification |
|---|---|---|
| 1 | **`index.html` / `style.css` / `script.js` / `img/` (+ `fonts/` si besoin)** | Structure demandée, standard, compréhensible par n'importe quel développeur ou intégrateur. |
| 2 | **Zéro requête CDN pour l'affichage** : tout asset visuel est rapatrié | Autonomie réelle ; le site rend identiquement même si le CDN Webflow est coupé ou le compte fermé. |
| 3 | **`script.js` = jQuery + webflow.js + scripts inline, dans l'ordre d'origine**, chargé en `defer` avant `</body>` | Le runtime Webflow est nécessaire (interactions IX2, formulaires, lazy-load). Ne pas le réécrire : on migre, on ne refactore pas. |
| 4 | **GTM et `dataLayer` restent inline dans `<head>`** | Position critique pour le tracking ; on n'y touche pas (c'est un choix volontaire, pas un oubli). |
| 5 | **Endpoints métier (CRM hellolead, SMS, Apps Script) inchangés** | La migration est purement statique. Les questions de sécurité serveur (rate-limiting) restent un chantier backend séparé — rappel P0 de l'audit. |
| 6 | **Purge CSS conservatrice** : 1,1 Mo → ~175 Ko | Un sélecteur est conservé au moindre doute (classes utilisées, classes pilotées par webflow.js/IX2, préfixes `w-`). Garde-fou automatique : si une classe stylée disparaît, on conserve la CSS complète. |
| 7 | **`srcset` responsive conservé** (variantes p-500/p-800…) | Ce sont des images déjà optimisées par Webflow — les garder ne coûte que quelques fichiers et préserve le Lighthouse mobile. |
| 8 | **Polices : seules celles réellement utilisées sont embarquées** | Le dépôt en contient 51 (7,4 Mo) — dont des polices de marque sous licence. Chaque site n'embarque que sa nécessité. ⚠ Voir §7 (licences). |
| 9 | **Noms de fichiers slugifiés en ASCII** (`téléchargement.png` → `telechargement.png`) | URLs propres, zéro casse serveur/OS, corrige le mojibake détecté à l'audit. |
| 10 | **SEO mécanique automatique** : meta description (reprise de `og:description` ou dérivée), canonical, sitemap, robots.txt. **H1 et copy : humain** | La description reprise est fiable ; le H1 demande une décision éditoriale (démotion sécurisée des H1 multiples — vérifiable car les classes Webflow portent les styles). |
| 11 | **Thank-you pages fusionnées** dans le site de leur LP (`merci.html`) | Un tunnel = un site. Elles ne deviennent pas des sites séparés. |
| 12 | **Le dépôt d'origine devient l'archive** — on ne convertit pas v1/v2/tests (30 pages) | Le manifest (`manifest.csv`) trace chaque décision : convertir / fusionner / archiver. |

## 3. L'outil : `lp2site.py`

Usine de conversion (Python 3 standard, aucune dépendance) :

```bash
# UNE page (mode pilote)
python3 lp2site.py assurance-tns.html --slug assurance-tns \
    --out sites --domain https://assurance-tns.example.fr

# TOUT le parc, automatiquement
python3 lp2site.py --all --out sites \
    --domain-pattern "https://{slug}.lp.comparateurpro.fr"
```

Le mode `--all` : liste les pages du dépôt via l'API GitHub, les catégorise
automatiquement (**métier → typ → marque → thank-you → variante** ; les
templates/tests de `temlpate-webflow/`, `webflow/`, `nicolas/` sont exclus,
inclusibles avec `--include-templates`), génère un slug unique par page, convertit
dans l'ordre de priorité, s'arrête sur `--budget-mb`, reprend avec `--resume`,
et produit `SYNTHESE.md` + `ordre-sites.txt` + un `rapport-site.md` par site.

Options : `--limit N` (échantillon), `--no-purge`, `--no-selfhost-fonts`.

Pipeline interne (chaque page) :

1. **Collecte** de la page et de ses CSS (liens + `<style>` inline) dans l'ordre cascade.
2. **Extraction des scripts** : externes (jQuery CDN, `js/webflow.js`) + inline (sauf GTM,
   `dataLayer` compact et JSON-LD qui restent en place).
3. **Purge CSS conservatrice** partie par partie (garde-fou anti-régression intégré).
4. **Nettoyage** des `@font-face` cassées des exports Webflow (src `.zip`,
   `format "undefined"`) — bug d'export qui laissait des références mortes.
5. **Collecte des assets** sur la page **et la CSS purgée uniquement** (c'est ce qui fait
   passer le site de 98 Mo à ~7 Mo), y compris les assets restés sur les CDN Webflow.
6. **Téléchargement parallèle** (12 workers) + déduplication par empreinte de contenu.
7. **Réécriture** de toutes les URLs (attributs, `srcset`, `url()` CSS) vers `img/`, `fonts/`.
8. **SEO mécanique** : meta description (reprise de `og:description`, sinon meilleur
   bloc de texte scoré contre le titre, sinon gabarit propre — toujours « à relire »),
   canonical, robots.txt, sitemap.xml + nettoyage des commentaires Webflow.
9. **Vérification stricte** : TOUTE référence locale du `index.html` et du `style.css`
   doit exister sur disque, sinon le rapport l'échoue.
10. **Rapport de conversion** (`rapport-site.md`) avec checklist QA humaine.

## 4. Méthode de production (4 vagues)

| Vague | Contenu | Volume | Durée |
|---|---|---|---|
| **0 — Batch automatique** | ✅ **FAIT** : 131 pages converties d'un coup par `--all` (0 échec) | 131 | ~20 min |
| **1 — QA pilote élargi** | vérification humaine des 12 sites prioritaires (dossier `sites/`) | 12 | 2-3 jours |
| **2 — QA cœur métier** | reste des LP métier + typ | ~60 | 1,5-2 semaines |
| **3 — Marques** | 22 LP véhicules (avec vérification droits marques, §7) | 22 | 1 semaine |
| **4 — Rangement** | fusion des thank-you pages, archivage des 27 variantes | 36 | 2 jours |

> ⚠ **Contrainte de stockage** : le parc complet fait **~989 Mo / ~7 500 fichiers**.
> Le dossier `sites/` de cet espace de travail ne contient que les 12 sites
> prioritaires (~74 Mo) — le reste se régénère à l'identique avec la commande
> `--all` ci-dessus (sur votre machine ou via moi, `--resume` permet de continuer
> au fil des sessions). Les 131 rapports de conversion sont dans `rapports/`.

**QA obligatoire par site** (cf. `rapport-site.md` généré) : comparaison visuelle côte à
côte avec l'original, parcours formulaire complet, OTP SMS sur numéro de test, lead reçu
en CRM/Sheets, Tag Assistant (`formulaire_lead`), Lighthouse mobile, relecture title/description.

## 5. Hébergement & déploiement

- Chaque dossier `site-<slug>/` est déployable tel quel sur n'importe quel hébergeur
  statique (Netlify, Vercel, GitHub Pages, Cloudflare Pages, nginx/VPS).
- **Recommandation** : un sous-domaine par LP (`assurance-tns.lp.comparateurpro.fr`) —
  isolation analytics/SEO totale, ou un chemin par LP si vous préférez consolider le
  domaine. Le `--domain` de l'outil alimente canonical + sitemap + `og:image`.
- Versionner chaque site dans **son propre dépôt privé** (pas un méga-dépôt) — c'est la
  leçon de l'audit. CI recommandée : à chaque push, déploiement + test Lighthouse.

## 6. Ce que l'outil ne fait pas (et ne doit pas faire) à votre place

1. **La copy SEO** : title/description à relire, H1 à valider (l'outil compte et signale).
2. **Les vidéos manquantes** (15 fichiers listés dans `MISSING.txt`) : à ré-exporter depuis
   Webflow ou à supprimer des pages concernées.
3. **Les droits marque/licences** : polices Dacia/Nissan/Toyota/Gotham/Helvetica,
   images Pngtree/Vecteezy/Shutterstock, logos partenaires (voir §7).
4. **Les tests formulaires réels** : les endpoints étant ceux de production, les tests
   OTP/CRM se font avec l'équipe sur des numéros/leads de test.

## 7. Point de vigilance hérité de l'audit (P0 avant toute mise en ligne)

Rappel : le dépôt source est **public** et expose endpoints CRM/SMS + URL Apps Script.
Avant de déployer les sites convertis (qui rendent ces endpoints encore plus faciles à
repérer), faire appliquer les mesures P0 de l'audit : rate-limiting/auth serveur sur les
endpoints, contrôle d'accès Apps Script, et décision sur la visibilité du dépôt d'origine.

## 8. Résultats mesurés sur le pilote `assurance-tns`

| Indicateur | Avant (page du dépôt) | Après (site autonome) |
|---|---|---|
| Dépendances d'affichage CDN | 2 + CSS/JS communs | **0** |
| CSS chargée | 1 127 Ko (3 fichiers) | **175 Ko (1 fichier purgé)** |
| Assets embarqués | — (partagés, 200 Mo) | **44 images + 7 polices (5,8 Mo)** |
| Meta description | absente | **présente** (reprise og:description) |
| Canonical / robots / sitemap | absents | **présents** |
| H1 | 9 | **1** (démotion neutre des 8 autres) |
| Références cassées | 0 | **0** (vérifiée automatiquement) |
| GTM + formulaire + OTP SMS | ✓ | **identiques, intacts** |
