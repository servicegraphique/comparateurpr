# LP statique — Assurance consultants

Cette version met à jour **la page statique d’origine**. Elle ne dépend pas de Webflow et ne modifie aucun PHP. Le formulaire est piloté par `index.html` et `js/main.js`; ses styles sont dans `css/style.css`.

## Fonctionnalités intégrées

- Formulaire multi-étapes à 7 étapes, validation des réponses et groupes conditionnels.
- Vérification du mobile français par SMS : 10 chiffres en 06/07, envoi et vérification par `URLSearchParams`, code à 6 chiffres, états d’erreur 422/404/410/409/429/502 et renvoi après 120 s. L’expiration de 10 min, l’usage unique et le remplacement du code sont des garanties serveur à confirmer en préproduction.
- Honeypot anti-spam invisible.
- Envoi direct au CRM avec l’enveloppe indicative `{ payload: { formId, id, data } }`.
- Envoi parallèle au Google Apps Script confirmé par l’utilisateur, avec les champs plats `application/x-www-form-urlencoded`; la réponse JSON doit inclure `status: "ok"`.
- Mapping Sheets selon le schéma AGV/AMR existant : q1–q3 conservées, `solution` reçoit les types d’assurance, `enjeu` reçoit le récapitulatif complet `autre_info_fj` (dont effectif/statut/société). `site`, `ville` et `civilite` restent vides car la LP ne collecte pas ces données.
- `source` CRM/Sheets vient d’abord de `ltm_source` (puis `utm_source`/`source`); `data-source="LP CONSULTANTS"` reste la valeur de secours si aucune source de campagne n’est disponible. Comme convenu, la valeur `ltm_source` est transmise uniquement avec le consentement analytics.
- Google Tag Manager `GTM-53SH7D7F` installé avec le script standard dans le `<head>` et le bloc `noscript` juste après `<body>`.
- Événement `formulaire_lead` déclenché à la validation finale. URL/UTM/`ltm_*` ne sont inclus qu’avec le consentement analytics; `gclid`/`msclkid`/`fbclid` ne sont inclus qu’avec le consentement marketing.

## Configuration actuelle

- API CRM de production, configurée à la demande : `https://mc.hellolead.pro/mon_compte/api/webflow/get_information.php`. Une fois publiée, même si la LP est toujours servie par l’hôte préproduction, ses soumissions viseront le CRM de production.
- `formId` proposé : `ADW_LP_ASSURANCE_CONSULTANT`, à confirmer/enregistrer côté CRM.
- Le CRM ne renvoie pas d’`Access-Control-Allow-Origin` au contrôle OPTIONS; le transport `data-api-mode="nocors"` utilise `sendBeacon`/`fetch` en `text/plain`. Cela met une requête en file, sans confirmer l’insertion.
- API SMS : `https://mc.hellolead.pro/mon_compte/api/smspartner/envoi_code_verification.php`. Les OPTIONS passifs autorisent `https://www.comparateurpro.fr` et `https://comparateurpro.fr`; cela confirme CORS, pas la livraison d’un SMS. Aucun SMS réel n’a été envoyé.
- Google Sheets utilise l’URL Apps Script `/exec` confirmée par l’utilisateur pour la feuille AGV/AMR. Une sonde avec le seul champ honeypot a retourné `status: "ok"`; le script fourni répond à ce honeypot avant l’écriture. Aucun lead ni aucune ligne réelle n’a été envoyé.
- GTM est chargé sans condition comme demandé. Le bloc `noscript` n’applique pas les préférences JavaScript; vérifier les réglages de consentement des balises dans le conteneur.

## Intégration au Webflow public

La LP reste hébergée à l’URL indiquée dans l’iframe (`ubepro.helloleadpreprod.fr` dans le code Embed communiqué). Le fichier `WEBFLOW_EMBED.md` contient le remplacement du code Embed : il transmet à la LP l’URL de campagne publique selon les consentements, puis fait transiter les requêtes SMS par la page parente. Les POST SMS partent ainsi avec l’origine navigateur `https://www.comparateurpro.fr`; le CRM et Sheets reçoivent `page_url` publique quand le consentement analytics est accordé.

Le code Embed doit être remplacé dans Webflow et la nouvelle archive statique doit être publiée sur l’hébergement de l’iframe. Les fichiers du workspace ne mettent pas eux-mêmes à jour la page en ligne. Le `src` de l’iframe reste une URL de contenu hébergé; ne pas le remplacer par l’URL Webflow du wrapper, sous peine de boucle d’iframes. Le corps des appels SMS ne contient pas `page_url`; le service voit l’origine `www.comparateurpro.fr`, mais ne stockera l’URL/campagne complète que si son API est explicitement prévue pour recevoir ce champ.

## Avant le lancement

1. Confirmer/enregistrer le `formId` côté CRM et vérifier avec l’équipe API le contrat d’entrée production; ne pas interpréter un `sendBeacon` accepté comme une confirmation de stockage.
2. Vérifier en préproduction le Google Apps Script, ses colonnes et les troncatures éventuelles dans `enjeu` (500 caractères max dans le script fourni).
3. Valider l’origine statique et le service SMS avec un numéro de test autorisé; ne pas envoyer de SMS réel sans autorisation.
4. Vérifier GTM/Tag Assistant, les consentements et l’événement `formulaire_lead`.
5. Décider si `noindex, nofollow` doit être retiré avant publication publique, et corriger le titre/langue/métadonnées du wrapper Webflow.
