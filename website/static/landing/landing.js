/* ================= GrantHub — лендинг: тексты по языку, живые цифры, свежие гранты ================= */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const L = (window.I18N && window.I18N.LANDING) || null;
  const T = (window.I18N && window.I18N.APP) || {};
  const tt = (k, d) => T[k] || d;

  /* ---------- Навигация ---------- */
  const NAV = L ? L.nav.filter(([, href]) => href !== '#contact') : [['Каталог', '/app#catalog'], ['ИИ-консультант', '/app#chat'], ['Избранное', '/app#favorites'], ['Профиль', '/app#profile'], ['Войти', '/app#auth']];
  $('#navLinks').innerHTML = NAV.map(([label, href]) => `<a href="${esc(href)}">${esc(label)}</a>`).join('');
  const burger = $('#burger'), nav = $('#navLinks');
  burger.addEventListener('click', () => { const open = nav.classList.toggle('open'); burger.setAttribute('aria-expanded', String(open)); });

  /* ---------- Тексты по языку ---------- */
  if (L) {
    $('#brandBottom').textContent = L.brandBottom;
    $('#navCta').textContent = L.navCta; $('#cta2').textContent = L.navCta;
    $('#eyebrow').textContent = L.eyebrow;
    $('#titleLine1').textContent = L.titleLine1; $('#titleLine2').textContent = L.titleLine2;
    $('#note').textContent = L.note;
    $('#cta').textContent = L.cta; $('.cta--inline').textContent = L.cta;
    $('#footBrand').textContent = L.footBrand;
    $$('.stat-label').forEach((el, i) => { if (L.stats[i]) el.textContent = L.stats[i]; });
    const heads = $$('.lp-section .sec-eyebrow'), titles = $$('.lp-section .sec-title');
    [L.sec1, L.sec2, L.final].forEach((pair, i) => { if (heads[i]) heads[i].textContent = pair[0]; if (titles[i]) titles[i].innerHTML = pair[1]; });
    $$('.feat').forEach((el, i) => { if (L.feats[i]) { el.querySelector('h3').textContent = L.feats[i][0]; el.querySelector('p').textContent = L.feats[i][1]; } });
    $$('.steps-row li').forEach((el, i) => { if (L.steps[i]) { el.querySelector('h3').textContent = L.steps[i][0]; el.querySelector('p').textContent = L.steps[i][1]; } });
    if (L.contact && L.contact.telegram) $('#contactTg').textContent = L.contact.telegram;
    window.I18N.switcher($('#langBox'));
    document.title = window.I18N.lang === 'kz' ? 'GrantHub — бүкіл әлем бойынша оқу гранттары' : window.I18N.lang === 'en' ? 'GrantHub — study grants around the world' : 'GrantHub — гранты на учёбу по всему миру';
  }
  if (/Windows/.test(navigator.userAgent) && !/Firefox/.test(navigator.userAgent)) document.documentElement.classList.add('flag-font');

  /* ---------- Живые цифры ---------- */
  const countUp = (el, to) => {
    if (reduced) { el.textContent = to; return; }
    const start = performance.now(), dur = 900;
    const tick = (t) => { const p = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - p, 3); el.textContent = Math.round(to * e); if (p < 1) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  };
  fetch('/api/stats/public').then(r => r.ok ? r.json() : null).then(s => {
    if (!s) return;
    $$('[data-count]').forEach(el => countUp(el, s[el.dataset.count] || 0));
    const last = s.last_checked ? new Date(s.last_checked).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }) : (L ? L.never : 'ещё не было');
    $('#statsFoot').textContent = `${L ? L.lastCheck : 'Последняя проверка'}: ${last} · ${L ? L.plan : 'план'}: ${s.scan_hours.map(h => String(h).padStart(2, '0') + ':00').join(', ')} (${s.timezone})`;
  }).catch(() => { });

  /* ---------- Свежие гранты и ход сканирования ---------- */
  const flagEmoji = (code) => /^[A-Za-z]{2}$/.test(code || '') ? code.toUpperCase().replace(/./g, c => String.fromCodePoint(127397 + c.charCodeAt(0))) : '';
  const globe = '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>';
  $('#liveTitle').textContent = tt('live.title', 'Только что найдено');
  fetch('/api/recent-grants?limit=9').then(r => r.ok ? r.json() : null).then(d => {
    if (!d || !d.items.length) { $('#live').hidden = true; return; }
    $('#liveList').innerHTML = d.items.map(g => {
      const dl = g.days_left, cls = dl != null && dl <= 7 ? 'hot' : dl != null && dl <= 30 ? 'soon' : '';
      const dtxt = dl == null ? '' : dl === 0 ? tt('card.today', 'сегодня') : `${dl} ${tt('card.days', 'дн.')}`;
      return `<a href="/grant/${g.id}"><span class="flag">${flagEmoji(g.country_code) || globe}</span><span class="n">${esc(g.name)}</span><span class="d ${cls}">${esc(dtxt)}</span></a>`;
    }).join('');
  }).catch(() => { $('#live').hidden = true; });
  const scanLine = () => fetch('/api/scan/progress').then(r => r.ok ? r.json() : null).then(sp => {
    if (!sp) return;
    const el = $('#liveScan');
    if (sp.phase === 'searching') el.textContent = `${tt('live.scan', 'Сканирую')}: ${sp.done} ${tt('live.of', 'из')} ${sp.total || sp.sources_total} ${tt('live.sources', 'источников')}`;
    else if (sp.phase === 'extracting') el.textContent = `${tt('live.extract', 'ИИ разбирает результаты')} ${sp.done}/${sp.total}`;
    else if (sp.phase === 'checking') el.textContent = tt('live.check', 'Проверяю ссылки');
    else el.textContent = sp.last_finished ? `${tt('live.last', 'Последняя проверка')}: ${String(sp.last_finished).replace('T', ' ').slice(0, 16)}${sp.last_new != null ? ` · +${sp.last_new} ${tt('live.new', 'новых')}` : ''}` : '';
    if (sp.phase && !['idle', 'done'].includes(sp.phase)) setTimeout(scanLine, 8000);
  }).catch(() => { });
  scanLine();
})();
