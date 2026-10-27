# Code à coller dans le Embed Webflow

Remplacer l’ancien code Embed par le bloc ci-dessous. Il conserve la LP servie sur l’hébergement actuel, mais fait passer les demandes SMS par la page parente `www.comparateurpro.fr`. La page parente ne transmet l’URL de campagne à l’iframe qu’après consentement, avec les paramètres filtrés selon les choix analytics/marketing.

```html
<style>
  .lp-assurance-frame {
    display: block;
    width: 100%;
    height: 100vh;
    height: 100dvh;
    border: 0;
  }
</style>

<iframe
  id="lp-assurance-frame"
  class="lp-assurance-frame"
  src="https://ubepro.helloleadpreprod.fr/assurance-esthetique-institut-beaute/"
  title="Assurance professionnelle pour esthéticiennes, esthéticiens, salons de coiffure et instituts de beauté"
  loading="eager"
  referrerpolicy="strict-origin-when-cross-origin">
</iframe>

<script>
(function () {
  'use strict';

  var frame = document.getElementById('lp-assurance-frame');
  var parentOrigins = ['https://www.comparateurpro.fr'];
  var channel = 'ubepro-assurance-v1';
  var smsEndpoint = 'https://mc.hellolead.pro/mon_compte/api/smspartner/envoi_code_verification.php';
  if (!frame || parentOrigins.indexOf(window.location.origin) === -1) return;

  var frameOrigin;
  try {
    frameOrigin = new URL(frame.getAttribute('src'), window.location.href).origin;
  } catch (error) {
    return;
  }

  var nonce = '';

  function makeNonce() {
    try {
      if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    } catch (error) {}
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (char) {
      var random = Math.random() * 16 | 0;
      var value = char === 'x' ? random : (random & 3 | 8);
      return value.toString(16);
    });
  }

  function postToFrame(message) {
    if (!nonce || !frame.contentWindow) return;
    var payload = Object.assign({ channel: channel, nonce: nonce }, message || {});
    frame.contentWindow.postMessage(payload, frameOrigin);
  }

  function isAnalyticsParam(key) {
    var normalized = String(key || '').toLowerCase();
    return /^(utm_|ltm_)/.test(normalized) ||
      ['source', 'categorie', 'category', 'medium', 'campaign', 'content', 'term', 'user', 'campaign_id'].indexOf(normalized) !== -1;
  }

  function campaignUrlForConsent(analytics, marketing) {
    var current = new URL(window.location.href);
    var result = new URL(current.origin + current.pathname);
    current.searchParams.forEach(function (value, key) {
      var normalized = key.toLowerCase();
      var clickId = ['gclid', 'msclkid', 'fbclid'].indexOf(normalized) !== -1;
      if ((analytics && isAnalyticsParam(normalized)) || (marketing && clickId)) {
        result.searchParams.append(key, value);
      }
    });
    return result.href;
  }

  function sendSmsResponse(requestId, status, ok, data) {
    postToFrame({
      type: 'sms-response',
      requestId: requestId,
      status: Number(status) || 0,
      ok: ok === true,
      data: data && typeof data === 'object' ? data : {}
    });
  }

  function handleSmsRequest(message) {
    var requestId = String(message.requestId || '');
    var params = message.params || {};
    var action = String(params.action || '');
    var telephone = String(params.telephone || '').replace(/\D/g, '');
    var code = String(params.code || '').replace(/\D/g, '');

    if (!requestId || requestId.length > 100 || !/^0[67]\d{8}$/.test(telephone) ||
        (action !== 'envoyer_code' && action !== 'verifier_code') ||
        (action === 'verifier_code' && !/^\d{6}$/.test(code))) {
      sendSmsResponse(requestId, 422, false, { message: 'Numéro, action ou code invalide.' });
      return;
    }

    var body = new URLSearchParams();
    body.set('action', action);
    body.set('telephone', telephone);
    if (action === 'verifier_code') body.set('code', code);

    fetch(smsEndpoint, {
      method: 'POST',
      mode: 'cors',
      credentials: 'omit',
      body: body
    }).then(function (response) {
      return response.text().then(function (text) {
        var data = {};
        try { data = text ? JSON.parse(text) : {}; }
        catch (error) { data = text ? { message: text.slice(0, 500) } : {}; }
        sendSmsResponse(requestId, response.status, response.ok, data);
      });
    }).catch(function () {
      sendSmsResponse(requestId, 0, false, { message: 'Connexion impossible au service SMS.' });
    });
  }

  function startBridge() {
    if (!nonce) nonce = makeNonce();
    postToFrame({ type: 'bridge-init' });
  }

  window.addEventListener('message', function (event) {
    if (event.source !== frame.contentWindow || event.origin !== frameOrigin) return;
    var message = event.data;
    if (!message || message.channel !== channel) return;

    if (message.type === 'bridge-ready') {
      startBridge();
      return;
    }

    if (!nonce || message.nonce !== nonce) return;

    if (message.type === 'consent-state') {
      var analytics = message.choiceMade === true && message.analytics === true;
      var marketing = message.choiceMade === true && message.marketing === true;
      if (!analytics && !marketing) return;
      postToFrame({ type: 'landing-url', url: campaignUrlForConsent(analytics, marketing) });
    } else if (message.type === 'sms-request') {
      handleSmsRequest(message);
    }
  });

  frame.addEventListener('load', startBridge);
  window.setTimeout(startBridge, 0);
})();
</script>
```

## Résultat attendu

- Le formulaire continue à être chargé dans l’iframe hébergée sur l’URL indiquée dans `src`.
- Après consentement analytics, la LP reçoit l’URL de campagne publique (`www.comparateurpro.fr`) et les paramètres `utm_*`/`ltm_*`; ils alimentent `page_url`, les champs de tracking et l’événement GTM `formulaire_lead`. Le champ `source` CRM/Sheets prend `ltm_source` en priorité (par exemple `ADW`); `data-source="LP CONSULTANTS"` sert de valeur de secours.
- Les paramètres `gclid`, `msclkid` et `fbclid` sont transmis seulement après consentement marketing.
- Les POST SMS `envoyer_code` et `verifier_code` sont exécutés par la page Webflow parente. Leur en-tête navigateur `Origin` est donc `https://www.comparateurpro.fr`, et non l’origine de l’iframe.
- Les requêtes SMS n’ajoutent pas le champ `page_url` au corps. Si le serveur SMS doit enregistrer la campagne complète, il faut que son API accepte et stocke explicitement un tel champ.

Ce pont est prévu pour la LP Assurance Esthéticiennes & instituts de beauté et son chemin public actuel. Ne pas remplacer le `src` de l’iframe par l’URL Webflow du wrapper : cela créerait une boucle d’iframes.
