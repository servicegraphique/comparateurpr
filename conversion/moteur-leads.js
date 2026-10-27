/* =====================================================================
   Moteur de leads local — autonome (CONVERSION-SPEC.md §5)
   ---------------------------------------------------------------------
   - collecte TOUS les champs FormData (pas de liste figée)
   - alias canoniques compat CRM / Sheets
   - persistance localStorage (pré-remplissage remerciements-* / TYP)
   - push dataLayer (événement de conversion)
   - message de succès immédiat (jamais de "Oops" hors-ligne)
   - envois asynchrones NON bloquants (CRM helloLead + Apps Script)
   - data-checkbox, data-redirect, ltm_typ
   - validation multi-étapes, masques Inputmask, neutralisation SMS
   ===================================================================== */
(function () {
  'use strict';

  var CRM_URL = 'https://mc.hellolead.pro/mon_compte/api/webflow/get_information.php';
  var LEAD_KEY = '__lp_lead__';
  var PREFILL_KEYS = ['nom', 'prenom', 'societe', 'code_postal', 'mail', 'telephone',
    'civilite', 'ville', 'email', 'source'];
  var ALIASES = {
    mail: 'email', email: 'mail',
    telephone: 'phone', phone: 'telephone',
    nom: 'last_name', prenom: 'first_name',
    societe: 'company', company: 'societe',
    code_postal: 'zipcode', zipcode: 'code_postal',
    ville: 'city', city: 'ville'
  };
  var HIDE_STEP_CLASSES = ['hide-step', 'hide-step-rn', 'hide-car', 'hide-etape-ass',
    'hide', 'hide-agv-v2', 'hide-step-newton', 'hide-devis', 'hide-nett'];

  /* Shim localStorage si l'origine est opaque (file:// sur certains
     navigateurs/JSDOM) : les scripts TYP et le moteur ne doivent jamais
     planter sur stockage indisponible. */
  (function ensureStorage() {
    try {
      var t = '__lp_t__';
      window.localStorage.setItem(t, '1');
      window.localStorage.removeItem(t);
    } catch (e) {
      var mem = {};
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        value: {
          getItem: function (k) { return Object.prototype.hasOwnProperty.call(mem, k) ? mem[k] : null; },
          setItem: function (k, v) { mem[k] = String(v); },
          removeItem: function (k) { delete mem[k]; },
          clear: function () { mem = {}; },
          key: function (i) { return Object.keys(mem)[i] || null; },
          get length() { return Object.keys(mem).length; }
        }
      });
    }
  })();

  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else { fn(); }
  }

  function jq() { return window.jQuery || null; }

  /* ------------------------------------------------------------------
   * 1. Pré-remplissage depuis localStorage (TYP / remerciements)
   * ------------------------------------------------------------------ */
  function prefill() {
    var snapshot = {};
    try { snapshot = JSON.parse(localStorage.getItem(LEAD_KEY) || '{}') || {}; } catch (e) {}
    var fields = document.querySelectorAll('form input[name], form select[name], form textarea[name]');
    fields.forEach(function (el) {
      if (el.type === 'hidden' || el.type === 'submit' || el.type === 'button' ||
          el.type === 'checkbox' || el.type === 'radio') return;
      if (el.value && el.value !== '') return;
      var v = null;
      if (Object.prototype.hasOwnProperty.call(snapshot, el.name)) v = snapshot[el.name];
      if (v == null) { try { v = localStorage.getItem(el.name); } catch (e) {} }
      if (v != null && v !== '') {
        el.value = v;
        el.setAttribute('value', v);
      }
    });
  }

  /* ------------------------------------------------------------------
   * 2. Neutralisation du blocage SMS (§5.3)
   *    .btn-verification est masqué en CSS ; on garantit en plus que
   *    le bouton valider se débloque dès l'acceptation du consentement.
   * ------------------------------------------------------------------ */
  function consentAccepted() {
    var radios = document.querySelectorAll('input[type=radio][name="consentement"]');
    if (!radios.length) return true;
    for (var i = 0; i < radios.length; i++) {
      if (radios[i].checked) return String(radios[i].value).toLowerCase() !== 'non';
    }
    return false;
  }

  function unlockSubmit() {
    var blocked = document.querySelectorAll('.bouton-valider[disabled], .bouton-valider[style*="opacity"]');
    blocked.forEach(function (btn) {
      if (consentAccepted()) {
        btn.removeAttribute('disabled');
        btn.style.opacity = '1';
      }
    });
  }

  /* Résout un slug/URL vers le chemin relatif de la page autonome.
     Remplace les constructions protocol//hostname cassantes en file://. */
  window.__lpLocalUrl = function (link) {
    return resolveLocalPage(link);
  };
  window.__lpTypRedirect = function (link) {
    var url = resolveLocalPage(link);
    if (url) { window.location.href = url; return true; }
    return false;
  };

  /* ------------------------------------------------------------------
   * 3. Masques de saisie (§5.2) — uniquement si Inputmask est chargé
   *    et si la page n'a pas déjà masqué le champ.
   * ------------------------------------------------------------------ */
  function initMasks() {
    if (typeof window.Inputmask === 'undefined') return;
    var IM = window.Inputmask;
    function mask(sel, opts) {
      document.querySelectorAll(sel).forEach(function (el) {
        if (el.inputmask && el.inputmask.isValid) return; // déjà masqué
        try { IM(opts).mask(el); } catch (e) {}
      });
    }
    var phone = { mask: '99 99 99 99 99[ 99]', showMaskOnHover: false, clearIncomplete: true };
    mask('.phone', phone);
    mask('.m-name, .name', { regex: "[A-Za-zÀ-ÿ' -]+", showMaskOnHover: false });
    mask('.zipcode, .m-zipcode', { mask: '99999', showMaskOnHover: false });
    mask('.numerique, .chiffre', { mask: '9{0,20}', showMaskOnHover: false });
    mask('.lettre', { regex: '[A-Za-zÀ-ÿ ]+', showMaskOnHover: false });
  }

  /* ------------------------------------------------------------------
   * 4. Validation multi-étapes (§5.1)
   * ------------------------------------------------------------------ */
  function visible(el) {
    if (!el || !el.getClientRects().length) return false;
    // un champ conditionnel non révélé (sous-conteneur display:none ou de
    // taille nulle) ne doit jamais être validé : seuls les champs réellement
    // affichés à l'utilisateur sont pris en compte.
    var rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return false;
    if (el.offsetParent === null && window.getComputedStyle(el).position !== 'fixed') return false;
    var n = el;
    while (n && n !== document.body) {
      var s = window.getComputedStyle(n);
      if (s.display === 'none' || s.visibility === 'hidden' || n.hidden) return false;
      n = n.parentElement;
    }
    return true;
  }

  function badField(el) {
    if (!el.required && !el.dataset.required) return false;
    var t = (el.type || '').toLowerCase();
    if (t === 'checkbox') return !el.checked;
    if (t === 'radio') {
      var group = document.getElementsByName(el.name);
      for (var i = 0; i < group.length; i++) if (group[i].checked) return false;
      return true;
    }
    var v = (el.value || '').trim();
    if (!v || v === '__ __ __ __ __' || v === '_____') return true;
    if (t === 'email' || el.classList.contains('mail') || el.name === 'mail' || el.name === 'email') {
      return !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v);
    }
    if (el.classList.contains('phone') || el.name === 'telephone' || el.name === 'phone') {
      return v.replace(/\D/g, '').length < 10;
    }
    if (el.classList.contains('zipcode') || el.name === 'code_postal' || el.name === 'zipcode') {
      return !/^\d{5}$/.test(v);
    }
    return false;
  }

  function validateVisibleStep(form) {
    var scope = form;
    var steps = form.querySelectorAll('[data-form="step"]');
    if (steps.length) {
      var active = null;
      steps.forEach(function (st) {
        if (!active && visible(st) && !HIDE_STEP_CLASSES.some(function (c) { return st.classList.contains(c); })) {
          active = st;
        }
      });
      if (active) scope = active;
    }
    var fields = scope.querySelectorAll('input, select, textarea');
    for (var i = 0; i < fields.length; i++) {
      var el = fields[i];
      if (!visible(el) || el.disabled) continue;
      if (badField(el)) {
        try { el.focus(); } catch (e) {}
        el.style.outline = '2px solid #d33';
        setTimeout(function (x) { x.style.outline = ''; }, 2500, el);
        return false;
      }
    }
    return true;
  }

  function initMultiStep() {
    // Aucune interception des clics « Suivant/Précédent » : la navigation entre
    // étapes et la validation requise associée sont entièrement pilotées par la
    // librairie multi-step d'origine (qui active/désactive elle-même next-btn).
    // Recâter ces clics en phase de capture bloquait la progression sur les
    // formulaires multi-étapes (champ conditionnel révélé tardivement jugé vide).
    // La capture du lead reste assurée par l'écouteur `submit` en phase de capture.
  }

  /* ------------------------------------------------------------------
   * 5. Résolution d'une page locale (slugs injectés au build)
   * ------------------------------------------------------------------ */
  var SLUGS = window.__LP_SLUGS__ || [];
  var SLUG_SET = {};
  SLUGS.forEach(function (s) { SLUG_SET[s] = true; });
  var UBEPRO_ALIASES = window.__LP_ALIASES__ || {};

  function resolveLocalPage(link) {
    if (!link) return null;
    link = String(link).trim();
    // déjà un chemin relatif vers un dossier autonome (réécrit au build)
    if (/^(\.\.?\/)+[^/].*index\.html/.test(link) || /^[a-z0-9_\-/.]+\/index\.html/i.test(link)) {
      return link;
    }
    link = link.replace(/^https?:\/\/[^/]+/i, '').replace(/^\//, '');
    var q = '';
    var qi = link.indexOf('?');
    if (qi >= 0) { q = link.slice(qi); link = link.slice(0, qi); }
    link = link.replace(/\.html?$/i, '').replace(/\/+$/, '');
    if (UBEPRO_ALIASES[link]) link = UBEPRO_ALIASES[link];
    if (SLUG_SET[link]) {
      var depth = (window.location.pathname.match(/\//g) || []).length;
      var prefix = '';
      // depuis <slug>/index.html (ou sous-dossier), remonter à la racine du portail
      var here = window.location.pathname.split('/');
      here.pop(); // retire index.html
      var ups = here.filter(function (p) { return p && p.length; }).length;
      prefix = new Array(ups).fill('..').join('/');
      if (prefix) prefix += '/';
      return prefix + link + '/index.html' + q;
    }
    return null;
  }

  /* ------------------------------------------------------------------
   * 6. UI succès (jamais d'échec muet hors-ligne)
   * ------------------------------------------------------------------ */
  function showSuccess(form) {
    var block = form.closest('.form-autonome') || form.parentElement || form;
    var done = block.querySelector('.w-form-done');
    var fail = block.querySelector('.w-form-fail');
    if (fail) fail.style.display = 'none';
    if (done) {
      form.style.display = 'none';
      done.style.display = 'block';
      done.removeAttribute('style');
      done.style.display = 'block';
      return;
    }
    var banner = document.getElementById('lp-merci-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'lp-merci-banner';
      banner.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:99999;background:#0b7a5b;' +
        'color:#fff;padding:18px 24px;text-align:center;font:600 17px/1.4 system-ui,sans-serif';
      banner.textContent = 'Merci ! Vos réponses ont bien été enregistrées.';
      document.body.appendChild(banner);
      setTimeout(function () { banner.remove(); }, 9000);
    }
  }

  function collectData(form) {
    var data = {};
    try {
      new FormData(form).forEach(function (v, k) {
        if (Object.prototype.hasOwnProperty.call(data, k)) {
          data[k] = Array.isArray(data[k]) ? data[k].concat(v) : [data[k], v];
        } else data[k] = v;
      });
    } catch (e) {}
    // groupes data-checkbox
    var groups = form.querySelectorAll('[data-checkbox]');
    groups.forEach(function (el) {
      var g = el.getAttribute('data-checkbox');
      var key = el.getAttribute('name') || ('checkbox_' + g);
      var box = form.querySelectorAll('[data-checkbox="' + g + '"]:checked');
      data[key] = Array.prototype.map.call(box, function (b) { return b.value; }).join(', ');
    });
    // alias canoniques
    Object.keys(ALIASES).forEach(function (k) {
      if (data[k] != null && data[ALIASES[k]] == null) data[ALIASES[k]] = data[k];
    });
    if (!data.source) {
      try { var ls = localStorage.getItem('source'); if (ls) data.source = ls; } catch (e) {}
    }
    return data;
  }

  function persist(data) {
    try {
      Object.keys(data).forEach(function (k) {
        if (PREFILL_KEYS.indexOf(k) >= 0 && data[k] != null) {
          localStorage.setItem(k, String(data[k]));
        }
      });
      localStorage.setItem(LEAD_KEY, JSON.stringify(data));
    } catch (e) {}
  }

  function pushDataLayer(data, form) {
    try {
      window.dataLayer = window.dataLayer || [];
      window.dataLayer.push({
        event: 'formulaire_lead',
        form_id: form.id || form.getAttribute('data-name') || 'form-autonome',
        form_data: data
      });
    } catch (e) {}
  }

  function nonBlockingSend(url, data) {
    try {
      var body = new URLSearchParams();
      Object.keys(data).forEach(function (k) { body.append(k, data[k]); });
      var opts = { method: 'POST', body: body, keepalive: true,
        headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' } };
      fetch(url, opts).catch(function () {}); // hors-ligne : silencieux, non bloquant
    } catch (e) {}
  }

  /* ------------------------------------------------------------------
   * 7. Submit : moteur de leads
   * ------------------------------------------------------------------ */
  function onSubmit(form) {
    var data = collectData(form);
    persist(data);
    pushDataLayer(data, form);
    showSuccess(form);

    // envoi CRM non bloquant
    nonBlockingSend(CRM_URL, data);

    // Apps Script éventuel (URL détectée au build et injectée)
    var SHEET_URLS = window.__LP_SHEET_URLS__ || [];
    SHEET_URLS.forEach(function (u) { nonBlockingSend(u, data); });

    // redirections data-redirect / redirect / ltm_typ, en local
    var redirect = form.getAttribute('data-redirect') || form.getAttribute('redirect');
    var ltm = null;
    try { ltm = new URLSearchParams(window.location.search).get('ltm_typ'); } catch (e) {}
    var target = redirect ? resolveLocalPage(redirect) : (ltm ? resolveLocalPage(ltm) : null);
    if (target) setTimeout(function () { window.location.href = target; }, 1200);
  }

  function initForms() {
    // phase de capture : invulnérable aux stopPropagation/stopImmediatePropagation
    // des scripts d'origine (ex. module de vérification SMS neutralisé)
    document.addEventListener('submit', function (e) {
      var form = e.target;
      if (!form || form.tagName !== 'FORM') return;
      // aucune requête réseau bloquante (action distante) ne part en mode autonome
      e.preventDefault();
      if (!validateVisibleStep(form)) return;
      try { onSubmit(form); } catch (err) {
        // quoi qu'il arrive, l'utilisateur voit sa confirmation
        showSuccess(form);
      }
    }, true);
  }

  ready(function () {
    prefill();
    initMasks();
    initMultiStep();
    initForms();
    unlockSubmit();
    document.addEventListener('change', function (e) {
      if (e.target && e.target.name === 'consentement') setTimeout(unlockSubmit, 50);
    });
    // garde-fou : les scripts d'origine peuvent rebloquer après initialisation
    [300, 900, 1800].forEach(function (t) { setTimeout(unlockSubmit, t); });
  });
})();
