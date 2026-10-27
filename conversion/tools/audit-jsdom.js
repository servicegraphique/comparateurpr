/* Audit JSDOM (CONVERSION-SPEC §7) — échantillon représentatif + balayage large.
   Usage : node audit-jsdom.js [--all] */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const ROOT = path.resolve(__dirname, '..', '..');
const OUT = path.join(ROOT, 'comparateur-local');
const REQUIRED = [
  'energie',                                  // LP classique (multi-étapes, SMS neutralisé)
  'typ-formulaires/typ-energie-form',         // formulaire multi-étapes TYP
  'remerciement-ticket-restaurant',           // page de remerciement
];
const EXTRA = [
  'accueil', 'assurances-professionnelles', 'ticket-restaurant',
  'typ-categories', 'rc-pro-consultant-conseil-adw', 'mercedes-benz/sprinter',
];

function makeConsole() {
  const errors = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', (e) => errors.push('jsdomError: ' + (e && e.message)));
  vc.on('error', (...a) => errors.push('console.error: ' + a.map(String).join(' ')));
  return { vc, errors };
}

function installStubs(window) {
  const noopCtx = new Proxy({}, {
    get(t, p) {
      if (p === 'canvas') return null;
      if (p === 'measureText') return () => ({ width: 0, actualBoundingBoxAscent: 0, actualBoundingBoxDescent: 0 });
      if (p === 'getImageData') return () => ({ data: [] });
      if (p === 'createLinearGradient' || p === 'createRadialGradient' || p === 'createPattern') {
        return () => ({ addColorStop() {} });
      }
      return typeof p === 'string' ? () => noopCtx : undefined;
    },
    set() { return true; },
  });
  window.HTMLCanvasElement.prototype.getContext = () => noopCtx;
  window.IntersectionObserver = class {
    constructor(cb) { this.cb = cb; }
    observe() {} unobserve() {} disconnect() {}
    trigger(els) { this.cb(els.map(e => ({ isIntersecting: true, target: e })), this); }
  };
  window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  window.matchMedia = window.matchMedia || ((q) => ({
    matches: false, media: q, addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {}, onchange: null,
  }));
  window.scrollTo = () => {};
  window.scroll = () => {};
  if (!window.fetch) {
    window.fetch = () => Promise.reject(new Error('hors-ligne (attendu)'));
  }
}

function visible(el, window) {
  if (!el || !el.getClientRects().length) return false;
  const s = window.getComputedStyle(el);
  return s.display !== 'none' && s.visibility !== 'hidden' && !el.hidden;
}

async function fillAndSubmit(window, document) {
  const form = document.querySelector('form');
  if (!form) return 'PASS (pas de formulaire)';
  const rnd = String(Math.floor(Math.random() * 90000) + 10000);
  form.querySelectorAll('input, select, textarea').forEach((el) => {
    const t = (el.type || '').toLowerCase();
    if (el.disabled) return;
    if (t === 'hidden' || t === 'submit' || t === 'button') return;
    if (t === 'checkbox' || t === 'radio') { el.checked = true; el.dispatchEvent(new window.Event('change', { bubbles: true })); return; }
    let v = 'Test';
    if (t === 'email' || /mail/i.test(el.name)) v = 'test' + rnd + '@exemple.fr';
    else if (t === 'tel' || /phone|telephone/i.test(el.name) || el.classList.contains('phone')) v = '0612345678';
    else if (/zip|postal/i.test(el.name) || el.classList.contains('zipcode')) v = '75001';
    else if (t === 'number') v = '1';
    else if (el.tagName === 'SELECT') { if (el.options.length) el.selectedIndex = Math.min(1, el.options.length - 1); }
    else v = v + ' ' + rnd;
    el.value = v;
    el.dispatchEvent(new window.Event('input', { bubbles: true }));
    el.dispatchEvent(new window.Event('change', { bubbles: true }));
  });
  // consentement : cocher "oui" si présent
  const consent = [...form.querySelectorAll('input[type=radio][name=consentement]')]
    .find(r => /oui|true|1|accepte/i.test(r.value)) || form.querySelector('input[type=radio][name=consentement]');
  if (consent) { consent.checked = true; consent.dispatchEvent(new window.Event('change', { bubbles: true })); }

  const before = document.querySelector('.w-form-done');
  form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await new Promise(r => setTimeout(r, 300));
  const banner = document.getElementById('lp-merci-banner');
  const doneShown = before && (before.style.display === 'block' || visible(before, window));
  const formHidden = form.style.display === 'none';
  return (doneShown || banner || formHidden) ? 'PASS' : 'FAIL (aucun message de succès)';
}

async function loadSite(slug) {
  const file = path.join(OUT, slug, 'index.html');
  const { vc, errors } = makeConsole();
  const dom = await JSDOM.fromFile(file, {
    runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true,
    virtualConsole: vc, beforeParse: installStubs,   // URL file:// naturelle
  });
  await new Promise(r => dom.window.addEventListener('load', r));
  await new Promise(r => setTimeout(r, 2200));   // timers guards 300/900/1800 ms
  const formResult = await fillAndSubmit(dom.window, dom.window.document);
  // Non bloquants = limites d'environnement JSDOM, pas des bugs navigateur :
  // canvas absent (iframes inclus), GTM/analytics hors-ligne, fetch réseau
  const ENV = /hors-ligne|fetch|Network|load failed|Not implemented|fillStyle|getContext|canvas|googletagmanager|google-analytics|gtag|opaque origin|Could not load (script|iframe|link)|update counter/i;
  const blocking = errors.filter(e => !ENV.test(e));
  const envOnly = errors.length - blocking.length;
  dom.window.close();
  return { slug, errors: blocking, envOnly, form: formResult };
}

function allSlugs() {
  const top = fs.readdirSync(OUT, { withFileTypes: true }).filter(d => d.isDirectory());
  const out = [];
  for (const d of top) {
    if (fs.existsSync(path.join(OUT, d.name, 'index.html'))) out.push(d.name);
    for (const sub of fs.readdirSync(path.join(OUT, d.name), { withFileTypes: true })) {
      if (sub.isDirectory() && fs.existsSync(path.join(OUT, d.name, sub.name, 'index.html'))) {
        out.push(d.name + '/' + sub.name);
      }
    }
  }
  return out.sort();
}

(async () => {
  const args = process.argv.slice(2);
  const explicit = args.filter(a => !a.startsWith('--'));
  const targets = explicit.length
    ? explicit
    : args.includes('--all')
      ? allSlugs()
      : [...REQUIRED, ...EXTRA];
  let fail = 0;
  for (const slug of targets) {
    try {
      const r = await loadSite(slug);
      const status = (r.errors.length === 0 && r.form.startsWith('PASS')) ? '✅' : '❌';
      if (status === '❌') fail++;
      console.log(`${status} ${slug} — erreurs bloquantes=${r.errors.length} (env:${r.envOnly || 0}) form=${r.form}`);
      r.errors.slice(0, 3).forEach(e => console.log('     ' + e.slice(0, 200)));
    } catch (e) {
      fail++;
      console.log(`❌ ${slug} — exception: ${e.message}`);
    }
  }
  console.log(`\n${targets.length - fail}/${targets.length} sites validés`);
  process.exit(fail ? 1 : 0);
})();
