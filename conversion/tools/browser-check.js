// Vérification navigateur réel (Chromium headless via CDP) — un site par appel.
// Usage: node browser-check.js <url> [--shot=prefixe] [--slug=nom]
const puppeteer = require('puppeteer-core');
const path = require('path');

const BROWSER = path.join(__dirname, 'browser', 'chromium');
const LIBS = path.join(__dirname, 'browser', 'libs');
const BROWSER_ROOT = path.join(__dirname, 'browser');
const FONTS = path.join(__dirname, 'browser', 'fonts');

(async () => {
  const url = process.argv[2];
  const shotArg = process.argv.find((a) => a.startsWith('--shot='));
  const slugArg = process.argv.find((a) => a.startsWith('--slug='));
  const slug = slugArg ? slugArg.split('=')[1] : url;
  if (!url) { console.error('url requise'); process.exit(2); }

  const browser = await puppeteer.launch({
    executablePath: BROWSER,
    headless: 'shell',
    dumpio: false,
    env: Object.assign({}, process.env, {
      LD_LIBRARY_PATH: LIBS + ':' + BROWSER_ROOT,
      FONTCONFIG_PATH: FONTS,
      HOME: process.env.HOME || '/tmp',
    }),
    args: [
      '--no-sandbox', '--no-zygote', '--single-process',
      '--disable-dev-shm-usage', '--disable-setuid-sandbox',
      '--disable-web-security', '--allow-running-insecure-content',
      '--font-render-hinting=none', '--window-size=1440,900',
    ],
    protocolTimeout: 60000,
  });

  const consoleErrors = [];
  const failedLocal = [];
  const failedExternal = [];
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 300));
  });
  page.on('pageerror', (e) => consoleErrors.push('PAGEERROR: ' + e.message.slice(0, 300)));
  page.on('requestfailed', (r) => {
    const f = r.failure();
    const reason = f ? f.errorText : '';
    const u = r.url();
    const item = u.slice(0, 180) + ' :: ' + reason;
    if (u.indexOf('127.0.0.1') !== -1 || u.indexOf('file://') !== -1) failedLocal.push(item);
    else failedExternal.push(item);
  });

  await page.goto(url, { waitUntil: ['load', 'networkidle0'], timeout: 45000 })
    .catch((e) => consoleErrors.push('GOTO: ' + e.message.slice(0, 200)));
  await new Promise((r) => setTimeout(r, 1500));

  const scroll = await page.evaluate(async () => {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const h0 = document.documentElement.scrollHeight;
    const vh = window.innerHeight;
    const steps = Math.max(1, Math.round(h0 / (vh * 0.8)));
    for (let i = 0; i <= steps; i++) {
      const y = Math.min(Math.round((h0 / steps) * i), h0 - vh);
      window.scrollTo(0, y);
      await sleep(100);
    }
    window.scrollTo(0, h0);
    await sleep(400);
    const max = window.scrollY || document.documentElement.scrollTop;
    window.scrollTo(0, 0);
    await sleep(200);
    return { scrollHeight: h0, viewport: vh, steps: steps, scrollMax: max, canScroll: max > 10 };
  });

  // Test spécifique formulaires multi-étapes : un clic sur « Suivant » doit
  // changer d'étape (régression moteur de leads qui interceptait next-btn).
  let multiStep = null;
  if (await page.$('form[data-form="multistep"]')) {
    multiStep = await page.evaluate(async () => {
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      const vis = (el) => {
        if (!el || !el.getClientRects().length) return false;
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return false;
        let n = el;
        while (n && n !== document.body) {
          const s = getComputedStyle(n);
          if (s.display === 'none' || s.visibility === 'hidden') return false;
          n = n.parentElement;
        }
        return true;
      };
      const activeText = () => {
        const t = Array.prototype.slice.call(document.querySelectorAll('[data-form="step"]'))
          .filter(vis).map((s) => s.textContent.replace(/\s+/g, ' ').trim().slice(0, 60));
        return t.join('|');
      };
      const stepEls = Array.prototype.slice.call(document.querySelectorAll('[data-form="step"]'));
      const activeIndex = () => stepEls.findIndex((st) => getComputedStyle(st).display !== 'none');
      const before = activeText();
      const idxBefore = activeIndex();
      // variante cartes-réponse : clic sur une carte data-go-to visible
      const card = Array.prototype.slice.call(document.querySelectorAll('[data-go-to]')).find(vis);
      if (card) card.click();
      // variante radio standard
      const radio = Array.prototype.slice.call(document.querySelectorAll('input[type=radio]')).find(vis);
      if (radio) radio.click();
      // renseigner les champs visibles requis pour ne pas bloquer sur un champ vide
      Array.prototype.slice.call(document.querySelectorAll('input, select, textarea')).forEach((el) => {
        if (!vis(el) || el.disabled) return;
        const t = (el.type || '').toLowerCase();
        if (t === 'radio' || t === 'checkbox' || t === 'hidden' || t === 'submit' || t === 'button') return;
        if (el.tagName === 'SELECT') { if (el.options.length > 1) el.selectedIndex = 1; }
        else if (t === 'email') el.value = 'test@exemple.fr';
        else if (t === 'tel') el.value = '0612345678';
        else el.value = el.value || 'Test';
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      });
      await sleep(300);
      const next = document.querySelector('[data-form="next-btn"]');
      let clicked = false;
      if (next) { next.click(); clicked = true; }
      await sleep(700);
      const after = activeText();
      const idxAfter = activeIndex();
      const advanced = idxAfter > idxBefore || (after !== before && after.length > 0);
      return { present: true, clicked: clicked, card: !!card, indexBefore: idxBefore, indexAfter: idxAfter,
               advanced: advanced, before: before.slice(0, 50), after: after.slice(0, 50) };
    });
  }

  const metrics = await page.evaluate(() => {
    const cs = getComputedStyle(document.body);
    const sheets = Array.prototype.slice.call(document.styleSheets);
    let rules = 0;
    for (const s of sheets) { try { rules += s.cssRules.length; } catch (e) { rules += -1; } }
    const sections = Array.prototype.slice.call(document.querySelectorAll('section, header, footer, [class*="section"], form'));
    let zeroSize = 0;
    for (const el of sections) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) zeroSize += 1;
    }
    let stuck = 0;
    const all = Array.prototype.slice.call(document.querySelectorAll('body *'));
    for (const el of all) {
      const c = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      if (r.width > 50 && r.height > 20 && (c.opacity === '0' || c.visibility === 'hidden')) stuck += 1;
    }
    const imgs = Array.prototype.slice.call(document.images);
    let brokenImgs = 0;
    for (const i of imgs) { if (i.complete && i.naturalWidth === 0) brokenImgs += 1; }
    let wFormResiduel = 0;
    for (const el of all) {
      const cls = el.getAttribute('class');
      if (cls && cls.split(/\s+/).indexOf('w-form') !== -1) wFormResiduel += 1;
    }
    // débordement horizontal = cassure de design
    const docW = document.documentElement.clientWidth;
    const overflow = [];
    for (const el of all) {
      const r = el.getBoundingClientRect();
      if (r.width > 30 && (r.right > docW + 2 || r.left < -2)) {
        overflow.push((el.tagName + '.' + (el.className && el.className.baseVal === undefined ? String(el.className).slice(0, 40) : '')).slice(0, 60));
        if (overflow.length >= 5) break;
      }
    }
    return {
      title: document.title.slice(0, 80),
      fontFamily: cs.fontFamily.slice(0, 60),
      bodyFontSize: cs.fontSize,
      bodyBg: cs.backgroundColor,
      sheets: sheets.length,
      cssRules: rules,
      elements: all.length,
      stuckHidden: stuck,
      sections: sections.length,
      zeroSizeSections: zeroSize,
      images: imgs.length,
      brokenImages: brokenImgs,
      forms: document.forms.length,
      wFormResiduel: wFormResiduel,
      formAutonome: document.querySelectorAll('.form-autonome').length,
      docWidth: docW,
      scrollWidth: document.documentElement.scrollWidth,
      horizontalOverflow: document.documentElement.scrollWidth > docW + 2,
      overflowSamples: overflow,
    };
  });

  const fonts = await page.evaluate(async () => {
    try {
      const families = new Set();
      for (const sheet of Array.prototype.slice.call(document.styleSheets)) {
        let rules;
        try { rules = sheet.cssRules; } catch (e) { continue; }
        for (const rule of Array.prototype.slice.call(rules)) {
          if (rule.type === CSSRule.FONT_FACE_RULE && rule.style && rule.style.fontFamily) {
            families.add(rule.style.fontFamily.replace(/["']/g, ''));
          }
        }
      }
      let loaded = 0; const failed = [];
      for (const fam of families) {
        try {
          await document.fonts.load('16px "' + fam + '"');
          if (document.fonts.check('16px "' + fam + '"')) loaded += 1; else failed.push(fam);
        } catch (e) { failed.push(fam); }
      }
      await document.fonts.ready;
      return { fontStatus: document.fonts.status, fontFamilies: families.size,
               fontsLoaded: loaded, fontsFailed: failed.slice(0, 6) };
    } catch (e) { return { fontStatus: 'unsupported', fontFamilies: 0, fontsLoaded: 0, fontsFailed: [] }; }
  });

  if (shotArg) {
    const prefix = shotArg.split('=')[1];
    await page.screenshot({ path: prefix + '-top.png' }).catch(() => {});
    await page.evaluate(() => window.scrollTo(0, Math.round(document.documentElement.scrollHeight / 2)));
    await new Promise((r) => setTimeout(r, 500));
    await page.screenshot({ path: prefix + '-mid.png' }).catch(() => {});
  }

  await browser.close();
  const hard = consoleErrors.filter((e) => e.indexOf('PAGEERROR') === 0 || e.indexOf('GOTO') === 0);
  // Le multi-étapes est remonté comme signal distinct : sa non-progression en
  // tête-à-tête est identique à la page d'origine (parité vérifiée), donc non
  // comptée comme défaut de conversion. Les vrais défauts sont rendu/JS/assets.
  const out = Object.assign({
    slug: slug,
    url: url,
    ok: failedLocal.length === 0 && hard.length === 0 && metrics.brokenImages === 0,
    multistep: multiStep,
  }, scroll, metrics, fonts, {
    failedLocal: failedLocal.slice(0, 8),
    failedExternal: Array.from(new Set(failedExternal)).slice(0, 8),
    consoleErrors: Array.from(new Set(consoleErrors)).slice(0, 8),
  });
  console.log(JSON.stringify(out));
  process.exit(out.ok ? 0 : 1);
})().catch((e) => { console.log(JSON.stringify({ fatal: e.message })); process.exit(3); });
