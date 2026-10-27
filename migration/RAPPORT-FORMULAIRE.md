# 🧪 Test réel du formulaire — `assurance-tns` — Diagnostic complet

> Testé dans un vrai Chromium (headless) : marche dans les 10 étapes, remplissage,
> soumission réelle, capture réseau/console/événements. Endpoint SMS mocké pour
> n'envoyer aucun SMS réel. Comparaison permanente **page originale ↔ site converti**.

---

## Verdict en une phrase

**Le site converti se comporte à l'identique de l'original** (testé côte à côte,
comportement identique à chaque étape) — et le « formulaire bloqué à l'envoi »
venait de **3 défauts présents dans les pages d'origine elles-mêmes**, aujourd'hui
corrigés automatiquement par le docteur.

## La chaîne causale complete (prouvée en navigation réelle)

| # | Fait observé | Preuve |
|---|---|---|
| 1 | Le bouton « Valider » porte un **attribut `disabled`** réel, géré par Formly (`enableBtn`/`disableBtn`) | clic Playwright refusé : « element is not enabled » |
| 2 | **12 champs `required` cachés** (miroirs `reponse_4`, `reponse_7`…) restent vides → Formly n'active jamais le bouton | les remplir → le bouton s'active instantanément (test décisif) |
| 3 | L'étape « Seriez-vous intéressé par… » contient une option **exclusive « Non, merci ! »** : cochée avec d'autres options = bouton bloqué **sans aucun message** | cocher tout = bloqué ; cocher 2 options normales = actif |
| 4 | Ce formulaire (`form-redirect`) **ne poste pas directement** : il enregistre les réponses dans `localStorage` puis **redirige vers la page indiquée par `?ltm_typ=<page-merci>`** — c'est elle qui envoie au CRM (avec OTP SMS) | code du handler + redirection observée quand le paramètre est présent |
| 5 | **Sans `?ltm_typ=`** (test local, lien direct) : pas de redirection → message Webflow « Oops! Something went wrong » → impression de formulaire cassé | scénario reproduit à l'identique sur la page originale |

## Les corrections appliquées (garde formulaire v2, dans `docteur-sites.py` + `lp2site.py`)

1. **`required` des champs cachés retirés dynamiquement** — au chargement, après
   l'init de Formly (passes à 300/800/1500/2500/4000 ms + MutationObserver) car
   Formly masque les étapes *après* son initialisation. → le bouton s'active.
2. **Exclusivité des cases « Non, merci / Aucun… »** — cocher une option normale
   décoche automatiquement l'option exclusive (et inversement). → plus de blocage muet.
3. **Retour utilisateur sans `ltm_typ`** — plus de « Oops » : affichage du message
   de remerciement (ou bandeau dédié) après envoi.

**Résultat final mesuré** : marche complète 10 étapes → bouton actif → soumission
déclenchée (`formulaire_lead` émis, mécanique complète). ✅
Original et converti : comportement identique sur TOUTES les étapes testées. ✅

## ⚠️ Ce qu'il reste à décider côté production (aucun code ne peut le faire à votre place)

1. **`?ltm_typ=` est indispensable pour capter le lead** : sans lui, les réponses
   vont dans le localStorage du navigateur et **jamais au CRM**. Chaque LP déployée
   doit pointer vers sa page merci (ex. `?ltm_typ=merci-tns/index.html`).
   → Il faut une **page merci par site** (les thank-you pages converties existent
   dans le batch complet : `remerciement-*`, `typ-formulaires/*thank-you*`).
2. **L'envoi réel au CRM + le SMS OTP se passent sur la page merci** (elle lit le
   localStorage). Si vous déployez les LP seules, le lead n'aboutit pas.
3. **CORS/autorisation serveur** : la sonde OPTIONS sur
   `mc.hellolead.pro/api/axialys/envoi_code_verification.php` est non concluante —
   à valider avec l'équipe hellolead pour vos nouveaux domaines.
4. Test local toujours via `http://localhost:PORT/…` (jamais en double-clic `file://`).

## Outils livrés

- `test-formulaire.py <site> [base_url]` — marche + soumission + capture réseau
- `docteur-sites.py sites` — vérifie et répare (5 familles de correctifs à ce jour)
- Serveur de test : `sites/tester-local.bat` (Windows) / `tester-local.sh`
