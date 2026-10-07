/* GrantHub — фронтенд. Те же функции, что у Telegram-бота, на одном экране. */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const I = window.I18N || { lang: 'ru', t: (k) => k, switcher: () => {}, APP: {} };
  const t = I.t, LANG = I.lang;

  // ---------- Переводы статичных элементов (selector -> key) ----------
  const TEXT = {
    '#nav a[data-nav="home"]': 'nav.homeapp', '#nav a[data-nav="catalog"]': 'nav.catalog', '#nav a[data-nav="search"]': 'nav.search',
    '#nav a[data-nav="chat"]': 'nav.chat', '#nav a[data-nav="profile"]': 'nav.profile', '#adminNav': 'nav.admin', '#nav a[data-nav="match"]': 'nav.match',
    '[data-view="match"] .eyebrow': 'match.eyebrow', '[data-view="match"] .vlead': 'match.lead', '#matchNearTitle': 'match.nearTitle', '#matchNearSub': 'match.nearSub',
    '#tgTitle': 'tg.title', '#tgWay1': 'tg.way1', '#tgGetCode': 'tg.get', '#tgOpenBot': 'tg.open', '#tgWay2': 'tg.way2', '#tgConfirm': 'tg.confirm', '#tgLinkedText': 'tg.linked',
    '.topbar-actions .pill--white': 'pill.ask', '#loginBtn': 'login',
    '[data-view="catalog"] .eyebrow': 'catalog.results', '[data-view="catalog"] .vlead': 'catalog.lead',
    '[data-region="kz"] b': 'choice.kz', '[data-region="kz"] > span:nth-of-type(2)': 'choice.kz.desc',
    '[data-region="abroad"] b': 'choice.abroad', '[data-region="abroad"] > span:nth-of-type(2)': 'choice.abroad.desc',
    '[data-degree="bachelor"] b': 'choice.bachelor', '[data-degree="bachelor"] > span:nth-of-type(2)': 'choice.bachelor.desc',
    '[data-degree="master"] b': 'choice.master', '[data-degree="master"] > span:nth-of-type(2)': 'choice.master.desc',
    '[data-degree="all"] b': 'choice.all', '[data-degree="all"] > span:nth-of-type(2)': 'choice.all.desc',
    '[data-back="region"]': 'back.regions', '[data-back="degree"]': 'back.change', '#loadMore': 'loadmore',
    '[data-view="search"] .eyebrow': 'search.eyebrow', '[data-view="search"] .vlead': 'search.lead', '#searchHint': 'search.hint',
    '[data-view="favorites"] .eyebrow': 'fav.eyebrow', '[data-view="favorites"] .vlead': 'fav.lead', '#favEmpty p:not(.empty-why)': 'fav.empty', '#favEmpty .empty-why': 'fav.emptyWhy', '#favEmpty .btn': 'fav.open', '#favCal': 'fav.calendar',
    '[data-view="chat"] .eyebrow': 'chat.eyebrow', '[data-view="chat"] .vlead': 'chat.lead', '.chat-head b': 'chat.name', '#chatStatus': 'chat.status', '#chatLog .msg.ai .bubble': 'chat.hello',
    '[data-view="profile"] .eyebrow': 'profile.eyebrow', '[data-view="profile"] .vlead': 'profile.lead',
    '#profileForm button[type="submit"]': 'save', '#profileClear': 'clear',
    '[data-view="admin"] .eyebrow': 'admin.eyebrow', '[data-view="admin"] .vlead': 'admin.lead',
    '#authModal .eyebrow': 'auth.eyebrow', '#authSub': 'auth.sub',
  };
  const HTML = {
    '[data-view="catalog"] .vtitle': 'catalog.titleAll', '[data-view="search"] .vtitle': 'search.title', '[data-view="favorites"] .vtitle': 'fav.title',
    '[data-view="chat"] .vtitle': 'chat.title', '[data-view="profile"] .vtitle': 'profile.title', '[data-view="admin"] .vtitle': 'admin.title', '[data-view="match"] .vtitle': 'match.title',
    '.bullets li:nth-child(1)': 'profile.b1', '.bullets li:nth-child(2)': 'profile.b2', '.bullets li:nth-child(3)': 'profile.b3', '.footer > span:first-child': 'foot.words',
  };
  const PH = { '#searchInput': 'search.placeholder', '#chatInput': 'chat.placeholder', '#profileForm input[name="ielts"]': 'profile.ielts.ph', '#profileForm input[name="gpa"]': 'profile.gpa.ph', '#profileForm input[name="field_of_interest"]': 'profile.field.ph', '#authForm input[name="name"]': 'auth.name.ph', '#authForm input[name="password"]': 'auth.password.ph' };
  const applyI18n = () => {
    Object.entries(TEXT).forEach(([sel, key]) => $$(sel).forEach(el => { if (LANG !== 'ru' || el.textContent.trim() === '') el.textContent = t(key); else el.textContent = t(key); }));
    Object.entries(HTML).forEach(([sel, key]) => $$(sel).forEach(el => { el.innerHTML = t(key); }));
    Object.entries(PH).forEach(([sel, key]) => $$(sel).forEach(el => { el.placeholder = t(key); }));
    // элементы с вложенной разметкой: метка + подсказка
    const lbl = (sel, key) => { const el = $(sel); if (el && el.firstChild && el.firstChild.nodeType === 3) el.firstChild.textContent = t(key) + ' '; };
    lbl('#profileForm label:nth-of-type(3)', 'profile.field'); lbl('#nameField', 'auth.name'); lbl('#authForm label:nth-of-type(2)', 'auth.email'); lbl('#authForm label:nth-of-type(3)', 'auth.password');
    const navFav = $('#nav a[data-nav="favorites"]'); if (navFav && navFav.firstChild) navFav.firstChild.textContent = t('nav.favorites') + ' ';
    const pillOnline = $('.topbar-actions .pill--dark'); if (pillOnline && pillOnline.lastChild) pillOnline.lastChild.textContent = t('pill.online');
    const quick = $('#quickSearch'); if (quick) quick.innerHTML = t('quick').map(q => `<button>${q}</button>`).join('');
    const sug = $('#suggestions'); if (sug) sug.innerHTML = t('suggestions').map(q => `<button>${q}</button>`).join('');
    $('#logoutBtn')?.setAttribute('title', t('logout'));
    $('#paletteBtn')?.setAttribute('title', t('palette')); $('#paletteInput') && ($('#paletteInput').placeholder = t('palette.ph'));
    $('#cmpOpen') && ($('#cmpOpen').textContent = t('cmp.bar')); $('#cmpClear') && ($('#cmpClear').textContent = t('cmp.clear')); $('#cmpEyebrow') && ($('#cmpEyebrow').textContent = t('cmp.title'));
    $('#homeAll') && ($('#homeAll').textContent = t('home.all'));
    document.title = LANG === 'kz' ? 'GrantHub — гранттар каталогы және ЖИ-кеңесші' : LANG === 'en' ? 'GrantHub — grant catalog and AI advisor' : 'GrantHub — каталог грантов и ИИ-консультант';
    I.switcher($('#langBox'));
  };
  applyI18n();

  // ---------- API ----------
  const api = async (path, opts = {}) => {
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    if (state.adminToken) headers['X-Admin-Token'] = state.adminToken;
    const res = await fetch(path, { ...opts, headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      let msg = data.detail || data.message || `Ошибка ${res.status}`;
      if (Array.isArray(msg)) msg = msg.map(d => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ');
      throw new Error(msg);
    }
    return data;
  };

  const state = {
    view: 'home', region: 'all', degree: 'all', cursor: null, shown: 0, total: 0, favIds: new Set(),
    filters: { country: '', funding: '', deadline: '', req: '' }, sort: 'new', countries: [], searchScope: 'all', alertIds: new Set(),
    adminToken: localStorage.getItem('gh_admin') || '', scanTimer: null, profile: {}, compare: new Set(), grants: new Map(),
    telegramLinked: false, botUsername: null, linkTimer: null,
  };

  // ---------- Toasts ----------
  const toast = (text, kind = '') => {
    const el = document.createElement('div');
    el.className = `toast ${kind}`; el.textContent = text;
    $('#toasts').appendChild(el);
    setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 320); }, 2800);
  };

  // ---------- Theme: dark по умолчанию, light по кнопке (запоминается) ----------
  const root = document.documentElement;
  let savedTheme = null; try { savedTheme = localStorage.getItem('gh_theme'); } catch { }
  root.dataset.theme = savedTheme === 'light' ? 'light' : 'dark';
  $('#themeToggle')?.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'light' ? 'dark' : 'light';
    try { localStorage.setItem('gh_theme', root.dataset.theme); } catch { }
  });

  // ---------- Navigation ----------
  const views = $$('.view');
  const navLinks = $$('#nav a');
  const moveInk = () => {
    const a = $('#nav a.active'); const ink = $('#navInk'); if (!a || !ink) return;
    ink.style.left = a.offsetLeft + 'px'; ink.style.width = a.offsetWidth + 'px';
  };
  const show = (name, push = true) => {
    if (!views.some(v => v.dataset.view === name)) name = 'home';
    const cur = views.find(v => !v.hidden);
    const next = views.find(v => v.dataset.view === name);
    if (cur === next) { onEnter(name); return; }
    const swap = () => {
      views.forEach(v => { v.hidden = v !== next; v.classList.remove('leaving'); });
      next.style.animation = 'none'; void next.offsetHeight; next.style.animation = '';
      window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });
      onEnter(name);
    };
    if (cur && !reduced) { cur.classList.add('leaving'); setTimeout(swap, 220); } else swap();
    navLinks.forEach(a => a.classList.toggle('active', a.dataset.nav === name));
    moveInk();
    $('#nav').classList.remove('open');
    state.view = name;
    if (push && location.hash !== '#' + name) history.pushState(null, '', '#' + name);
  };
  document.addEventListener('click', (e) => {
    const a = e.target.closest('[data-nav]'); if (!a) return;
    e.preventDefault(); show(a.dataset.nav);
  });
  window.addEventListener('popstate', () => show(location.hash.slice(1) || 'home', false));
  window.addEventListener('resize', moveInk);
  window.addEventListener('load', moveInk);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(moveInk);
  $('#menuBtn').addEventListener('click', () => $('#nav').classList.toggle('open'));

  const onEnter = (name) => {
    if (name === 'home') loadHome();
    if (name === 'catalog') loadCatalog(true);
    if (name === 'favorites') loadFavorites();
    if (name === 'match') loadMatch();
    if (name === 'profile') { fillProfile(); renderTelegram(); }
    if (name !== 'profile' && state.linkTimer) { clearInterval(state.linkTimer); state.linkTimer = null; }
    if (name === 'search') setTimeout(() => $('#searchInput').focus(), 300);
    if (name === 'chat') setTimeout(() => $('#chatInput').focus(), 300);
    if (name === 'admin' && state.adminToken) adminEnter();
  };

  // ---------- Reveal on scroll ----------
  const io = new IntersectionObserver((entries) => entries.forEach(en => {
    if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
  }), { threshold: .15 });
  $$('.reveal').forEach((el, i) => { el.style.transitionDelay = (i % 6) * 70 + 'ms'; io.observe(el); });

  // ---------- Hero tilt & counters ----------
  const heroCard = $('#heroCard');
  if (heroCard && !reduced && matchMedia('(hover:hover)').matches) {
    heroCard.parentElement.addEventListener('pointermove', (e) => {
      const r = heroCard.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
      heroCard.style.transform = `rotateY(${x * 10}deg) rotateX(${-y * 10}deg)`;
    });
    heroCard.parentElement.addEventListener('pointerleave', () => heroCard.style.transform = '');
  }
  const countUp = (el, to) => {
    if (reduced) { el.textContent = to; return; }
    const start = performance.now(), dur = 1200;
    const tick = (t) => {
      const p = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(to * e);
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };
  // Кнопка в состоянии загрузки: спиннер вместо текста, ширина сохраняется
  const busy = async (btn, fn) => {
    if (!btn) return fn();
    btn.classList.add('is-loading'); btn.setAttribute('aria-busy', 'true');
    try { return await fn(); } finally { btn.classList.remove('is-loading'); btn.removeAttribute('aria-busy'); }
  };
  const loadPublicStats = async () => {
    try {
      const s = await api('/api/stats/public');
      $$('[data-count]').forEach(el => countUp(el, s[el.dataset.count] || 0));
      const last = s.last_checked ? new Date(s.last_checked).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }) : 'ещё не было';
      const hf = $('#heroFoot');
      const u = s.users || {};
      const ppl = u.people ? ' · ' + t('home.people', { n: u.people }) + (u.week_delta > 0 ? ' (' + t('home.peopleDelta', { d: u.week_delta }) + ')' : '') : '';
      if (hf) hf.textContent = `Последняя проверка: ${last} · план: ${s.scan_hours.map(h => String(h).padStart(2, '0') + ':00').join(' и ')} (${s.timezone})${ppl}`;
    } catch { /* тихо */ }
  };

  // ---------- Grant card ----------
  const svg = (d, extra = '') => `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"${extra}>${d}</svg>`;
  const ui = {
    globe: svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>'),
    search: svg('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'),
    clock: svg('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
    bell: svg('<path d="M6 9a6 6 0 1 1 12 0c0 5 2 6 2 7H4c0-1 2-2 2-7Z"/><path d="M10 20a2 2 0 0 0 4 0"/>'),
    home: svg('<path d="M3 11 12 4l9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>'),
    book: svg('<path d="M4 4h6a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H4zM20 4h-6a3 3 0 0 0-3 3v13a2 2 0 0 1 2-2h7z"/>'),
    star: svg('<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9L12 3Z"/>'),
    chat: svg('<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>'),
    user: svg('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>'),
    theme: svg('<path d="M12 3a9 9 0 1 0 9 9 7 7 0 0 1-9-9z"/>'),
    lang: svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>'),
    warn: svg('<path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4M12 17h.01"/>'),
    building: svg('<path d="M3 21h18M5 21V8l7-5 7 5v13"/><path d="M9 21v-6h6v6"/>'),
  };
  const icon = {
    money: '<svg viewBox="0 0 24 24"><rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/></svg>',
    list: '<svg viewBox="0 0 24 24"><path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/></svg>',
    clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    pin: '<svg viewBox="0 0 24 24"><path d="M3 21h18M5 21V8l7-5 7 5v13"/><path d="M9 21v-6h6v6"/></svg>',
    star: '<svg viewBox="0 0 24 24"><path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9L12 3Z"/></svg>',
    bell: '<svg viewBox="0 0 24 24"><path d="M6 9a6 6 0 1 1 12 0c0 5 2 6 2 7H4c0-1 2-2 2-7Z"/><path d="M10 20a2 2 0 0 0 4 0"/></svg>',
    ext: '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></svg>',
  };
  const statusTag = (g) => g.status === 'open' ? `<span class="tag open">${t('tag.open')}</span>` : g.status === 'upcoming' ? `<span class="tag upcoming">${t('tag.upcoming')}${g.application_start_date ? ' · ' + t('tag.from') + ' ' + esc(g.application_start_date) : ''}</span>` : '';
  const urgentTag = (g) => (g.days_left !== null && g.days_left >= 0 && g.days_left <= 7) ? `<span class="tag urgent">${g.days_left === 0 ? t('tag.today') : g.days_left + ' ' + t('tag.days')}</span>` : '';
  const degreeLabel = { bachelor: t('degree.bachelor'), master: t('degree.master'), phd: t('degree.phd'), language: t('degree.language'), all: t('degree.all') };
  const scopeLabel = { kz: t('scope.kz'), abroad: t('scope.abroad'), all: t('scope.all') };
  // Название страны по коду ISO — на языке интерфейса
  let regionNames = null; try { regionNames = new Intl.DisplayNames([LANG === 'kz' ? 'kk' : LANG], { type: 'region' }); } catch { }
  const countryName = (code) => { if (!code) return ''; try { return regionNames ? regionNames.of(code) : code; } catch { return code; } };
  const fundingTag = (g) => (g.funding === 'full' || g.funding === 'partial') ? `<span class="tag">${t('funding.' + g.funding)}</span>` : '';
  // Флаг — эмодзи из кода страны ISO (региональные символы Unicode): 'KZ' -> 🇰🇿. Без кода — несколько стран
  const flagEmoji = (code) => /^[A-Za-z]{2}$/.test(code || '') ? code.toUpperCase().replace(/./g, c => String.fromCodePoint(127397 + c.charCodeAt(0))) : '';
  const flagOf = (g) => `<span class="flag">${flagEmoji(g.country_code) || ui.globe}</span>`;
  const placeOf = (g) => g.source || countryName(g.country_code) || (g.category === 'kz' ? t('region.kz') : t('region.abroad'));
  const plural = (n) => { if (LANG !== 'ru') return n === 1 ? t('card.day1') : t('card.days'); const m10 = n % 10, m100 = n % 100; if (m10 === 1 && m100 !== 11) return t('card.day1'); if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return t('card.days2'); return t('card.days'); };
  const deadlineBlock = (g) => {
    const d = g.days_left;
    if (g.is_ongoing) return `<div class="g-dl"><b class="tbd">${t('card.ongoing')}</b><span>${esc(g.deadline)}</span></div>`;
    if (d === null || d === undefined) return `<div class="g-dl"><b class="tbd">${g.recurrence_period === 'yearly' ? t('card.yearly') : t('card.tbd')}</b><span>${esc(g.deadline)}</span></div>`;
    if (d < 0) return `<div class="g-dl"><b class="tbd">${t('card.expired')}</b><span>${esc(g.deadline_date)}</span></div>`;
    const cls = d <= 7 ? 'hot' : d <= 30 ? 'soon' : '';
    return `<div class="g-dl"><b class="${cls}">${d === 0 ? t('card.today') : d}</b><span>${d === 0 ? esc(g.deadline_date) : plural(d) + ' · ' + esc(g.deadline_date)}</span></div>`;
  };
  const cardHTML = (g, i = 0) => {
    const inCmp = state.compare.has(g.id);
    return `
    <article class="gcard" data-id="${g.id}" style="--i:${i}">
      <div class="g-head"><span class="g-src" title="${esc(placeOf(g))}">${esc(placeOf(g))}</span>${flagOf(g)}</div>
      <div class="g-main"><h3 class="g-title"><a href="/grant/${g.id}">${esc(g.name)}</a></h3>${deadlineBlock(g)}</div>
      <div class="g-tags"><span class="tag">${degreeLabel[g.degree] || g.degree}</span>${statusTag(g)}${urgentTag(g)}${fundingTag(g)}${(g.why || []).map(w => `<span class="tag open">${t('why.' + w)}</span>`).join('')}${Object.entries(g.gaps || {}).map(([k, n]) => `<span class="tag gap">${t('gap.' + k, { n })}</span>`).join('')}</div>
      <div class="g-row">${icon.money}<div><b>${t('card.coverage')}:</b> ${esc(g.coverage)}</div></div>
      <div class="g-row g-req" data-more="${t('card.more')}">${icon.list}<div><b>${t('card.requirements')}:</b> ${esc(g.requirements)}</div></div>
      <div class="g-foot">
        <a class="g-apply" href="${/^https?:\/\//i.test(g.link) ? esc(g.link) : '#'}" target="_blank" rel="noopener nofollow">${t('card.apply')} ${icon.ext}</a>
        <div class="g-actions">
          ${g.status === 'upcoming' ? `<button class="fav bell ${state.alertIds.has(g.id) ? 'on' : ''}" data-bell="${g.id}" aria-label="${t('bell.title')}" title="${t('bell.title')}">${icon.bell}</button>` : ''}
          <button class="cmp-check ${inCmp ? 'on' : ''}" data-cmp="${g.id}" title="${t('card.compare')}" aria-label="${t('card.compare')}"><svg viewBox="0 0 24 24"><path d="M4 6h7v12H4zM13 6h7v12h-7z"/></svg><em>${t('card.compare')}</em></button>
          <button class="fav share" data-share="${g.id}" aria-label="${t('card.share')}" title="${t('card.share')}"><svg viewBox="0 0 24 24"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4M15.4 6.5l-6.8 4"/></svg><em>${t('card.share')}</em></button>
          <button class="fav ${g.is_favorite ? 'on' : ''}" data-fav="${g.id}" aria-label="${t('fav.btn')}" title="${t('fav.btn')}">${icon.star}<em>${t('card.save')}</em></button>
        </div>
      </div>
      ${g.fav_status ? `<label class="fav-status"><span>${t('fav.status')}</span><select data-status="${g.id}">${['saved', 'preparing', 'submitted', 'result'].map(s => `<option value="${s}" ${g.fav_status === s ? 'selected' : ''}>${t('fav.status.' + s)}</option>`).join('')}</select></label>` : ''}
    </article>`;
  };
  const renderGrid = (grid, items, append = false) => {
    if (!append) grid.innerHTML = '';
    const base = append ? grid.children.length : 0;
    items.forEach(g => state.grants.set(g.id, g));
    grid.insertAdjacentHTML('beforeend', items.map((g, i) => cardHTML(g, Math.min(i, 10))).join(''));
    // длинные требования: обрезка до трёх строк, раскрытие по клику — только если текст действительно не влез
    requestAnimationFrame(() => grid.querySelectorAll('.g-req:not(.clamped):not(.open) > div').forEach(el => {
      if (el.scrollHeight > el.clientHeight + 1) el.parentElement.classList.add('clamped');
    }));
    void base;
  };
  const skeletons = (grid, n = 6) => grid.innerHTML = Array.from({ length: n }, () => '<div class="skeleton"></div>').join('');

  // ---------- Favorites toggle (delegated) ----------
  const updateFavBadge = () => {
    const b = $('#favBadge'); b.textContent = state.favIds.size; b.hidden = state.favIds.size === 0;
  };
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-fav]'); if (!btn) return;
    const id = Number(btn.dataset.fav); const on = btn.classList.contains('on');
    btn.classList.toggle('on', !on);
    try {
      await api(`/api/favorites/${id}`, { method: on ? 'DELETE' : 'POST' });
      on ? state.favIds.delete(id) : state.favIds.add(id);
      updateFavBadge();
      toast(on ? t('fav.removed') : t('fav.added'), on ? '' : 'ok');
      if (state.view === 'favorites' && on) {
        const card = btn.closest('.gcard'); card.classList.add('removing');
        setTimeout(() => { card.remove(); if (!$('#favGrid').children.length) $('#favEmpty').hidden = false; }, 300);
      }
      $$(`[data-fav="${id}"]`).forEach(b => b.classList.toggle('on', !on));
      loadReminders();
    } catch (err) { btn.classList.toggle('on', on); toast(err.message, 'err'); }
  });

  // ---------- «Уведомить об открытии» для будущих грантов ----------
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-bell]'); if (!btn) return;
    const id = Number(btn.dataset.bell); const on = btn.classList.contains('on');
    try {
      await api(`/api/alerts/${id}`, { method: on ? 'DELETE' : 'POST' });
      on ? state.alertIds.delete(id) : state.alertIds.add(id);
      $$(`[data-bell="${id}"]`).forEach(b => b.classList.toggle('on', !on));
      toast(on ? t('bell.removed') : t('bell.added'), on ? '' : 'ok');
    } catch (err) { toast(err.message, 'err'); }
  });

  // ---------- Catalog ----------
  // Каталог — один экран: фильтры сверху, сетка сразу под ними. Заголовок следует за выбранным разделом.
  const setStep = () => {
    $('#catalogSub').textContent = t('catalog.results');
    $('#catalogTitle').innerHTML = { kz: t('catalog.titleKz'), abroad: t('catalog.titleAbroad') }[state.region] || t('catalog.titleAll');
  };
  // Фильтры каталога: раздел (Казахстан | Зарубеж | Все) и уточнения. Всё уходит в API параметрами.
  const fillSelect = (el, label, options, value) => {
    el.innerHTML = `<option value="">${esc(label)}</option>` + options.map(([v, text]) => `<option value="${esc(v)}">${esc(text)}</option>`).join('');
    el.value = value || ''; el.classList.toggle('is-set', !!el.value);
    dressSelect(el);
  };
  // Выпадающий список в стиле сайта вместо системного. Сам <select> остаётся источником значения:
  // выбор пункта меняет его и шлёт обычное событие change.
  const chevron = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
  const closeDropdowns = (except) => $$('.dd.open').forEach(d => { if (d !== except) { d.classList.remove('open'); d.querySelector('.dd-btn').setAttribute('aria-expanded', 'false'); } });
  const dressSelect = (el) => {
    let dd = el.nextElementSibling;
    if (!dd || !dd.classList.contains('dd')) { dd = document.createElement('div'); dd.className = 'dd'; el.after(dd); el.classList.add('dd-native'); }
    dd.hidden = el.hidden; dd.classList.remove('open'); dd.classList.toggle('is-set', !!el.value);
    const cur = el.options[el.selectedIndex];
    dd.innerHTML = `<button type="button" class="dd-btn" aria-haspopup="listbox" aria-expanded="false"><span>${esc(cur ? cur.text : '')}</span>${chevron}</button>`
      + `<div class="dd-menu" role="listbox">${[...el.options].map(o => `<button type="button" class="dd-opt ${o.selected ? 'is-on' : ''}" role="option" aria-selected="${o.selected}" data-v="${esc(o.value)}">${esc(o.text)}</button>`).join('')}</div>`;
  };
  document.addEventListener('click', (e) => {
    const opt = e.target.closest('.dd-opt'), btn = e.target.closest('.dd-btn');
    if (opt) {
      const dd = opt.closest('.dd'), sel = dd.previousElementSibling; closeDropdowns();
      if (sel.value !== opt.dataset.v) { sel.value = opt.dataset.v; sel.dispatchEvent(new Event('change', { bubbles: true })); }
      return;
    }
    if (btn) { const dd = btn.closest('.dd'); closeDropdowns(dd); const open = dd.classList.toggle('open'); btn.setAttribute('aria-expanded', String(open)); if (open) (dd.querySelector('.dd-opt.is-on') || dd.querySelector('.dd-opt')).focus({ preventScroll: true }); return; }
    closeDropdowns();
  });
  document.addEventListener('keydown', (e) => {
    const dd = document.activeElement && document.activeElement.closest ? document.activeElement.closest('.dd.open') : null; if (!dd) return;
    if (e.key === 'Escape') { closeDropdowns(); dd.querySelector('.dd-btn').focus(); return; }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault(); const opts = [...dd.querySelectorAll('.dd-opt')]; const i = opts.indexOf(document.activeElement);
    opts[Math.max(0, Math.min(opts.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))].focus();
  });
  const syncFilters = () => {
    const f = state.filters;
    $$('#scopeSeg button').forEach(b => { b.textContent = scopeLabel[b.dataset.scope]; b.classList.toggle('is-on', b.dataset.scope === state.region); });
    fillSelect($('#fDegree'), t('degree.all'), ['bachelor', 'master', 'phd', 'language'].map(d => [d, degreeLabel[d]]), state.degree === 'all' ? '' : state.degree);
    if (state.region === 'kz') f.country = '';
    $('#fCountry').hidden = state.region === 'kz' || !state.countries.length;
    fillSelect($('#fCountry'), t('filter.country'), state.countries.map(c => [c.code, `${flagEmoji(c.code)} ${countryName(c.code)} · ${c.count}`]), f.country);
    fillSelect($('#fFunding'), t('filter.funding'), ['full', 'partial'].map(v => [v, t('funding.' + v)]), f.funding);
    fillSelect($('#fDeadline'), t('filter.deadline'), ['open', 'upcoming'].map(v => [v, t('deadline.' + v)]), f.deadline);
    fillSelect($('#fReq'), t('filter.req'), [['ielts', 'IELTS'], ['toefl', 'TOEFL'], ['sat', 'SAT'], ['gpa', 'GPA'], ['ent', t('req.ent')]], f.req);
    fillSelect($('#fSort'), t('sort.new'), [['deadline', t('sort.deadline')], ['funding', t('sort.funding')]], state.sort === 'new' ? '' : state.sort);
    $('#fReset').textContent = t('filter.reset');
    $('#fReset').hidden = !Object.values(f).some(Boolean);
  };
  $('#scopeSeg').addEventListener('click', (e) => { const b = e.target.closest('[data-scope]'); if (!b || b.dataset.scope === state.region) return; state.region = b.dataset.scope; loadCatalog(true); });
  $('#filters').addEventListener('change', (e) => {
    const key = e.target.dataset.filter; if (!key) return;
    if (key === 'degree') state.degree = e.target.value || 'all'; else if (key === 'sort') state.sort = e.target.value || 'new'; else state.filters[key] = e.target.value;
    loadCatalog(true);
  });
  $('#fReset').addEventListener('click', () => { state.filters = { country: '', funding: '', deadline: '', req: '' }; loadCatalog(true); });
  const loadCatalog = async (reset) => {
    const grid = $('#catalogGrid'), more = $('#loadMore');
    if (reset) { state.cursor = null; state.shown = 0; setStep(); syncFilters(); skeletons(grid); more.hidden = true; }
    $('#crumbs').innerHTML = `<span>${state.region === 'kz' ? flagEmoji('KZ') + ' ' : ui.globe}${scopeLabel[state.region]}</span><span>${degreeLabel[state.degree]}</span>`;
    try {
      const q = new URLSearchParams({ category: state.region, degree: state.degree, limit: 12 });
      Object.entries(state.filters).forEach(([k, v]) => { if (v) q.set(k, v); });
      if (state.sort !== 'new') q.set('sort', state.sort);
      if (state.cursor) q.set('cursor', state.cursor); else if (state.shown) q.set('offset', state.shown);
      const d = await api(`/api/grants?${q}`);
      state.total = d.total;
      $('#crumbs').insertAdjacentHTML('beforeend', `<span>${t('total')}: ${d.total}</span>`);
      if (reset && !d.items.length) {
        const filtered = Object.values(state.filters).some(Boolean) || state.degree !== 'all';
        grid.innerHTML = `<div class="empty"><div class="empty-icon">${ui.search}</div><p>${filtered ? t('catalog.emptyFiltered') : t('catalog.empty')}</p>${filtered ? `<button class="btn btn-ghost btn-sm" id="emptyReset">${t('filter.reset')}</button>` : ''}</div>`;
        $('#emptyReset')?.addEventListener('click', () => { state.filters = { country: '', funding: '', deadline: '', req: '' }; state.degree = 'all'; loadCatalog(true); });
        return;
      }
      renderGrid(grid, d.items, !reset);
      state.shown += d.items.length; state.cursor = d.next_cursor;
      more.hidden = d.next_offset == null;
      more.textContent = `${t('loadmore')} (${d.total - state.shown})`;
    } catch (err) { grid.innerHTML = ''; toast(err.message, 'err'); }
  };
  $('#loadMore').addEventListener('click', () => loadCatalog(false));

  // ---------- Search ----------
  let searchTimer = null, searchSeq = 0;
  $('#searchInput').addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    const q = e.target.value.trim(); const grid = $('#searchGrid'), hint = $('#searchHint');
    if (q.length < 2) { grid.innerHTML = ''; hint.hidden = false; hint.textContent = t('search.hint'); return; }
    searchTimer = setTimeout(async () => {
      const seq = ++searchSeq; $('#searchSpinner').hidden = false;
      try {
        const d = await api(`/api/grants/search?q=${encodeURIComponent(q)}&scope=${state.searchScope}`);
        if (seq !== searchSeq) return;
        hint.hidden = false;
        hint.textContent = d.items.length ? `${t('search.found')}: ${d.items.length}` : t('search.none', { q });
        renderGrid(grid, d.items);
      } catch (err) { toast(err.message, 'err'); }
      finally { if (seq === searchSeq) $('#searchSpinner').hidden = true; }
    }, 350);
  });

  // Раздел поиска — отдельный фильтр, а не слово в запросе
  $$('#searchScope button').forEach(b => { b.textContent = scopeLabel[b.dataset.scope]; });
  $('#searchScope').addEventListener('click', (e) => {
    const b = e.target.closest('[data-scope]'); if (!b) return;
    state.searchScope = b.dataset.scope; $$('#searchScope button').forEach(x => x.classList.toggle('is-on', x === b));
    $('#searchInput').dispatchEvent(new Event('input'));
  });

  const quick = $('#quickSearch');
  if (quick) quick.addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return;
    const inp = $('#searchInput'); inp.value = b.textContent; inp.dispatchEvent(new Event('input')); inp.focus();
  });

  // ---------- Favorites ----------
  document.addEventListener('click', (e) => {
    const row = e.target.closest('.g-req.clamped'); if (!row || e.target.closest('a')) return;
    row.classList.toggle('open');
  });
  // ---------- Поделиться: ссылка на страницу гранта (с превью для Telegram и WhatsApp) ----------
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-share]'); if (!btn) return;
    const g = state.grants.get(Number(btn.dataset.share)); const url = `${location.origin}/grant/${btn.dataset.share}`;
    try {
      if (navigator.share) await navigator.share({ title: g?.name || 'GrantHub', text: g?.name || '', url });
      else { await navigator.clipboard.writeText(url); toast(t('card.shareCopied'), 'ok'); }
      api('/api/events/share', { method: 'POST', body: { grant_id: Number(btn.dataset.share) } }).catch(() => {});
    } catch (err) { if (err?.name !== 'AbortError') toast(err.message, 'err'); }
  });
  // ---------- Статус заявки по избранному гранту ----------
  document.addEventListener('change', async (e) => {
    const sel = e.target.closest('select[data-status]'); if (!sel) return;
    try { await api(`/api/favorites/${sel.dataset.status}/status`, { method: 'PATCH', body: { status: sel.value } }); toast(t('fav.statusSaved'), 'ok'); }
    catch (err) { toast(err.message, 'err'); }
  });
  const loadFavorites = async () => {
    const grid = $('#favGrid'); skeletons(grid, 3); $('#favEmpty').hidden = true;
    try {
      const d = await api('/api/favorites');
      grid.innerHTML = '';
      if (!d.items.length) { $('#favEmpty').hidden = false; $('#favCal').hidden = true; return; }
      renderGrid(grid, d.items);
      $('#favCal').hidden = !d.items.some(g => g.deadline_date);
    } catch (err) { grid.innerHTML = ''; toast(err.message, 'err'); }
  };

  // ---------- Reminders ----------
  const loadReminders = async () => {
    try {
      const d = await api('/api/reminders'); const box = $('#reminders');
      box.hidden = !d.items.length;
      box.innerHTML = d.items.map(r => r.kind === 'opened' ? `<div class="rem">${ui.bell}<div>${t('rem.opened', { name: esc(r.name) })}</div><a href="${esc(r.link)}" target="_blank" rel="noopener">${t('rem.open')}</a></div>` : `<div class="rem">${ui.clock} <div>${t('rem.text', { name: esc(r.name) })} <b>${r.days_left === 0 ? t('rem.lessday') : r.days_left + ' ' + t('tag.days')}</b></div><a href="${esc(r.link)}" target="_blank" rel="noopener">${t('rem.open')}</a></div>`).join('');
    } catch { /* тихо */ }
  };

  // ---------- Profile ----------
  const fillProfile = () => {
    const f = $('#profileForm');
    f.ielts.value = state.profile.ielts ?? ''; f.gpa.value = state.profile.gpa ?? ''; f.field_of_interest.value = state.profile.field_of_interest ?? '';
  };
  $('#profileForm').addEventListener('submit', async (e) => {
    e.preventDefault(); const f = e.target;
    const body = {
      ielts: f.ielts.value === '' ? null : Number(f.ielts.value),
      gpa: f.gpa.value === '' ? null : Number(f.gpa.value),
      field_of_interest: f.field_of_interest.value.trim() || null,
    };
    try { const d = await busy(e.submitter || f.querySelector('[type=submit]'), () => api('/api/profile', { method: 'POST', body })); state.profile = d.profile; toast(t('profile.saved'), 'ok'); }
    catch (err) { toast(err.message, 'err'); }
  });
  $('#profileClear').addEventListener('click', async () => {
    try { const d = await api('/api/profile', { method: 'POST', body: { ielts: null, gpa: null, field_of_interest: null } }); state.profile = d.profile; fillProfile(); toast(t('profile.cleared')); }
    catch (err) { toast(err.message, 'err'); }
  });

  // ---------- «Мне подходит» ----------
  const loadMatch = async () => {
    const grid = $('#matchGrid'), near = $('#matchNearGrid'), empty = $('#matchEmpty'), sum = $('#matchSummary');
    skeletons(grid, 3); near.innerHTML = ''; empty.hidden = true; sum.hidden = true; $('#matchNearHead').hidden = true;
    try {
      const d = await api('/api/match');
      grid.innerHTML = '';
      if (!d.has_profile) {
        $('#matchEmptyText').textContent = t('match.empty'); const b = $('#matchEmptyBtn'); b.textContent = t('match.emptyBtn'); b.dataset.nav = 'profile'; b.href = '#profile';
        empty.hidden = false; return;
      }
      sum.hidden = false;
      sum.innerHTML = [[d.total, t('match.total'), 'brand'], [d.strong, t('match.strong')], [d.near.length, t('match.near')]]
        .map(([v, l, cls]) => `<div class="tile"><b class="${cls || ''}">${v}</b><span>${l}</span></div>`).join('');
      if (!d.items.length) {
        $('#matchEmptyText').textContent = t('match.none'); const b = $('#matchEmptyBtn'); b.textContent = t('match.noneBtn'); b.dataset.nav = 'catalog'; b.href = '#catalog';
        empty.hidden = false;
      } else renderGrid(grid, d.items);
      if (d.near.length) { $('#matchNearHead').hidden = false; renderGrid(near, d.near); }
    } catch (err) { grid.innerHTML = ''; toast(err.message, 'err'); }
  };

  // ---------- Привязка Telegram (карточка в профиле) ----------
  const renderTelegram = () => {
    const bot = state.botUsername;
    $('#tgLead').textContent = bot ? t('tg.lead', { bot }) : t('tg.leadNoBot');
    $('#tgLinked').hidden = !state.telegramLinked; $('#tgUnlinked').hidden = state.telegramLinked;
  };
  const afterLinked = async () => {
    if (state.linkTimer) { clearInterval(state.linkTimer); state.linkTimer = null; }
    state.telegramLinked = true; renderTelegram(); toast(t('tg.done'), 'ok');
    try {
      const me = await api('/api/me'); state.profile = me.profile || {}; state.alertIds = new Set(me.alerts || []); fillProfile();
      const favs = await api('/api/favorites'); state.favIds = new Set(favs.items.map(g => g.id)); updateFavBadge(); loadReminders();
    } catch { }
  };
  $('#tgGetCode').addEventListener('click', async () => {
    const btn = $('#tgGetCode'); btn.disabled = true;
    try {
      const d = await busy(btn, () => api('/api/link/code', { method: 'POST' }));
      $('#tgCode').textContent = d.code; $('#tgCodeHint').textContent = t('tg.hint'); $('#tgCodeBox').hidden = false;
      const a = $('#tgOpenBot'); if (d.bot_url) { a.href = d.bot_url; a.hidden = false; } else a.hidden = true;
      if (state.linkTimer) clearInterval(state.linkTimer);
      state.linkTimer = setInterval(async () => {
        try {
          const s = await api(`/api/link/status?code=${encodeURIComponent(d.code)}`);
          if (s.linked) { $('#tgCodeBox').hidden = true; await afterLinked(); }
          else if (s.expired) { clearInterval(state.linkTimer); state.linkTimer = null; $('#tgCodeHint').textContent = t('tg.expired'); btn.disabled = false; }
        } catch { }
      }, 3000);
    } catch (err) { toast(err.message, 'err'); btn.disabled = false; }
  });
  $('#tgForm').addEventListener('submit', async (e) => {
    e.preventDefault(); const code = $('#tgInput').value.trim().toUpperCase(); if (!code) return;
    $('#tgConfirm').disabled = true;
    try { await busy($('#tgConfirm'), () => api('/api/link/confirm', { method: 'POST', body: { code } })); $('#tgInput').value = ''; await afterLinked(); }
    catch (err) { toast(err.message, 'err'); }
    finally { $('#tgConfirm').disabled = false; }
  });

  // ---------- Chat ----------
  const log = $('#chatLog'), input = $('#chatInput'), sendBtn = $('#sendBtn');
  // Markdown -> HTML с очисткой: оставляем только безопасные теги, ссылки только http(s)
  const SAFE_TAGS = new Set(['P', 'BR', 'STRONG', 'B', 'EM', 'I', 'UL', 'OL', 'LI', 'A', 'CODE', 'PRE', 'H1', 'H2', 'H3', 'H4', 'BLOCKQUOTE', 'HR', 'TABLE', 'THEAD', 'TBODY', 'TR', 'TH', 'TD']);
  const sanitize = (html) => {
    const tpl = document.createElement('template'); tpl.innerHTML = html;
    const walk = (node) => {
      [...node.children].forEach(el => {
        if (!SAFE_TAGS.has(el.tagName)) { el.replaceWith(document.createTextNode(el.textContent)); return; }
        [...el.attributes].forEach(a => { if (!(el.tagName === 'A' && a.name === 'href')) el.removeAttribute(a.name); });
        if (el.tagName === 'A') {
          const href = el.getAttribute('href') || '';
          if (!/^https?:\/\//i.test(href)) el.removeAttribute('href'); else { el.setAttribute('target', '_blank'); el.setAttribute('rel', 'noopener nofollow'); }
        }
        walk(el);
      });
    };
    walk(tpl.content);
    return tpl.innerHTML;
  };
  const md = (t) => { try { return sanitize(window.marked ? marked.parse(t, { breaks: true }) : esc(t).replace(/\n/g, '<br>')); } catch { return esc(t); } };
  const addMsg = (who, html) => {
    const el = document.createElement('div'); el.className = `msg ${who}`; el.innerHTML = `<div class="bubble">${html}</div>`;
    log.appendChild(el); log.scrollTo({ top: log.scrollHeight, behavior: reduced ? 'auto' : 'smooth' }); return el;
  };
  const typewrite = (el, html) => {
    if (reduced) { el.innerHTML = html; return Promise.resolve(); }
    return new Promise(res => {
      el.innerHTML = html; const full = el.innerHTML; const text = el.textContent; el.innerHTML = '';
      let i = 0; const step = Math.max(1, Math.ceil(text.length / 400));
      const t = setInterval(() => {
        i += step; el.textContent = text.slice(0, i); log.scrollTop = log.scrollHeight;
        if (i >= text.length) { clearInterval(t); el.innerHTML = full; res(); }
      }, 12);
    });
  };
  const ask = async (q) => {
    q = q.trim(); if (!q) return;
    addMsg('user', esc(q)); input.value = ''; autosize(); sendBtn.disabled = true; sendBtn.classList.add('is-loading');
    $('#suggestions').hidden = true; $('#chatStatus').textContent = t('chat.thinking');
    const ai = addMsg('ai', '<span class="typing"><i></i><i></i><i></i></span>');
    const bubble = ai.querySelector('.bubble');
    try {
      // Потоковый ответ: текст появляется по мере генерации, без ожидания всего ответа
      const res = await fetch('/api/ask/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: q, lang: LANG }) });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || `Ошибка ${res.status}`); }
      const reader = res.body.getReader(), decoder = new TextDecoder();
      let text = '', pending = '', answerId = null, started = false;
      const stream = document.createElement('span'); stream.className = 'stream';
      while (true) {
        const { value, done } = await reader.read(); if (done) break;
        pending += decoder.decode(value, { stream: true });
        const lines = pending.split('\n'); pending = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          let msg; try { msg = JSON.parse(line); } catch { continue; }
          if (msg.delta) {
            if (!started) { started = true; bubble.innerHTML = ''; bubble.appendChild(stream); $('#chatStatus').textContent = t('chat.typing'); }
            text += msg.delta; stream.textContent = text; log.scrollTop = log.scrollHeight;
          }
          if (msg.done) answerId = msg.answer_id;
        }
      }
      bubble.innerHTML = md(text || t('chat.empty'));
      if (answerId) bubble.insertAdjacentHTML('beforeend', `<div class="fb" data-answer="${answerId}"><button data-rate="1" title="${t('fb.up')}">👍</button><button data-rate="-1" title="${t('fb.down')}">👎</button></div>`);
    } catch (err) { bubble.innerHTML = `${ui.warn} ${esc(err.message)}`; }
    finally { sendBtn.disabled = false; sendBtn.classList.remove('is-loading'); $('#chatStatus').textContent = t('chat.status'); input.focus(); }
  };
  $('#chatForm').addEventListener('submit', (e) => { e.preventDefault(); ask(input.value); });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(input.value); } });
  const autosize = () => { input.style.height = 'auto'; input.style.height = Math.min(140, input.scrollHeight) + 'px'; };
  input.addEventListener('input', autosize);
  $('#suggestions').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) ask(b.textContent); });
  log.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-rate]'); if (!b) return;
    const fb = b.closest('.fb'); if (fb.classList.contains('done')) return;
    fb.classList.add('done'); b.classList.add('picked');
    try { await api('/api/feedback', { method: 'POST', body: { answer_id: Number(fb.dataset.answer), rating: Number(b.dataset.rate) } }); toast(t('fb.thanks'), 'ok'); }
    catch (err) { toast(err.message, 'err'); }
  });

  // ---------- Admin ----------
  const adminEnter = async () => {
    try {
      await busy($('#adminLoginBtn'), () => api('/api/admin/login', { method: 'POST' }));
      $('#adminLogin').hidden = true; $('#adminPanel').hidden = false;
      localStorage.setItem('gh_admin', state.adminToken);
      loadAdmin();
    } catch (err) { state.adminToken = ''; localStorage.removeItem('gh_admin'); $('#adminLogin').hidden = false; $('#adminPanel').hidden = true; toast(err.message, 'err'); }
  };
  $('#adminLoginBtn').addEventListener('click', () => { state.adminToken = $('#adminToken').value.trim(); adminEnter(); });
  $('#adminToken').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('#adminLoginBtn').click(); });
  $('#adminLogout').addEventListener('click', () => { state.adminToken = ''; localStorage.removeItem('gh_admin'); $('#adminLogin').hidden = false; $('#adminPanel').hidden = true; clearInterval(state.scanTimer); });

  const loadAdmin = async () => {
    try {
      const [llm, mon, st, scan, review, runs, syn] = await Promise.all([api('/api/admin/llm'), api('/api/admin/monitor'), api('/api/admin/stats'), api('/api/admin/scan/status'), api('/api/admin/review'), api('/api/admin/runs'), api('/api/admin/synonyms')]);
      $('#llmInfo').innerHTML = `<div>Основной провайдер: <b>${esc(llm.provider)}</b></div><div>Запасной: <b>${esc(llm.fallback || 'нет')}</b></div><div>Ollama: сканер <b>${esc(llm.ollama_model)}</b>, чат <b>${esc(llm.ollama_chat_model || llm.ollama_model)}</b></div>${llm.gemini_model ? `<div>Gemini: ${esc(llm.gemini_model)}</div>` : '<div>Gemini: отключён</div>'}<div style="margin-top:8px">${esc(llm.ollama_status)}</div>`;
      renderMonitor(mon); renderStats(st); renderScan(scan); renderReview(review); renderRuns(runs); renderSynonyms(syn);
    } catch (err) { toast(err.message, 'err'); }
  };
  // Очередь на проверку: записи с неподтверждённой страной ждут решения оператора
  const renderReview = (r) => {
    $('#reviewList').innerHTML = r.items.length ? r.items.map(g => `
      <div class="review-item" data-review="${g.id}">
        <div><b>#${g.id} · ${esc(g.name)}</b><div class="muted">${esc(g.source || '—')} · <a href="${/^https?:\/\//i.test(g.link) ? esc(g.link) : '#'}" target="_blank" rel="noopener nofollow">${esc(g.link)}</a></div><div>${ui.warn} ${esc(g.review_note || 'новая запись')}</div><div class="muted">Дедлайн: ${esc(g.deadline_date || '—')}${g.deadline_confirmed ? ' ✓' : ' (не подтверждён)'} · ${esc(g.deadline)}</div></div>
        <div class="inline-form"><input type="text" maxlength="2" value="${esc(g.country_code || '')}" placeholder="ISO" aria-label="Код страны"><input type="date" class="rv-date" value="${esc(g.deadline_date || '')}" aria-label="Дедлайн"><button class="btn btn-primary btn-sm" data-approve="1">Одобрить</button><button class="btn btn-danger btn-sm" data-approve="0">Отклонить</button></div>
      </div>`).join('') : 'Очередь пуста — все записи прошли проверку автоматически.';
  };
  $('#reviewList').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-approve]'); if (!b) return;
    const item = b.closest('[data-review]'), approve = b.dataset.approve === '1';
    try {
      await api(`/api/admin/review/${item.dataset.review}`, { method: 'POST', body: { approve, country_code: approve ? item.querySelector('input').value.trim() : null, deadline_date: approve ? (item.querySelector('.rv-date').value || null) : null } });
      toast(approve ? 'Запись опубликована' : 'Запись отклонена', 'ok'); item.remove();
      if (!$('#reviewList').children.length) renderReview({ items: [] });
    } catch (err) { toast(err.message, 'err'); }
  });
  const renderRuns = (r) => {
    $('#runsInfo').innerHTML = r.items.length
      ? `<table class="mon-table"><tr><th>Начало</th><th>Конец</th><th>Создано</th><th>Обновлено</th><th>Без изменений</th><th>На проверку</th><th>В архив</th><th>Ошибок поиска</th></tr>${r.items.map(x => `<tr><td>${esc(String(x.started_at).replace('T', ' '))}</td><td>${esc(String(x.finished_at || '—').replace('T', ' ').slice(11))}</td><td>${x.created}</td><td>${x.updated}</td><td>${x.unchanged}</td><td>${x.flagged}</td><td>${x.archived}</td><td>${x.errors}</td></tr>`).join('')}</table>`
      : 'Запусков с журналом ещё не было.';
  };
  const renderSynonyms = (r) => {
    $('#synList').innerHTML = r.items.map(x => `<span class="tag">${esc(x.alias)} → ${esc(x.canonical)} <button data-syn="${x.id}" aria-label="Удалить синоним" title="Удалить">×</button></span> `).join('');
  };
  $('#synAdd').addEventListener('click', async () => {
    const alias = $('#synAlias').value.trim(), canonical = $('#synCanonical').value.trim(); if (alias.length < 2 || canonical.length < 2) return;
    try { await api('/api/admin/synonyms', { method: 'POST', body: { alias, canonical } }); $('#synAlias').value = ''; renderSynonyms(await api('/api/admin/synonyms')); toast('Синоним добавлен', 'ok'); }
    catch (err) { toast(err.message, 'err'); }
  });
  $('#synList').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-syn]'); if (!b) return;
    try { await api(`/api/admin/synonyms/${b.dataset.syn}`, { method: 'DELETE' }); b.closest('.tag').remove(); } catch (err) { toast(err.message, 'err'); }
  });
  const kindLabel = { university: `${ui.building} Университеты`, program: `${ui.globe} Международные конкурсы`, broad: `${ui.search} Общие запросы` };
  const renderMonitor = (m) => {
    const rows = Object.entries(m.by_kind).map(([k, r]) => `<tr><td>${kindLabel[k] || k}</td><td>${r.n}</td><td>${r.last ? esc(r.last.replace('T', ' ')) : '—'}</td><td>${r.found || 0}</td><td>${r.new || 0}</td><td>${r.total || 0}</td><td>${r.errors || 0}</td></tr>`).join('');
    const top = m.top.length ? `<p class="muted" style="margin:12px 0 4px">Самые результативные источники:</p><div>${m.top.map(t => `<span class="tag">${esc(t.name)} — ${t.total_new}</span> `).join('')}</div>` : '';
    const st = m.by_status || {};
    $('#monitorInfo').innerHTML = rows
      ? `<table class="mon-table"><tr><th>Вид</th><th>Источников</th><th>Проверено</th><th>Найдено</th><th>Новых</th><th>Всего новых</th><th>Ошибок</th></tr>${rows}</table>
         <p style="margin:10px 0 0">Активных грантов: 🟢 открыт ${st.open || 0} · 🟡 скоро ${st.upcoming || 0} · ⚪ не определён ${st.unknown || 0}</p>${top}
         <p class="muted" style="margin:8px 0 0">Расписание: ежедневно в ${m.scan_hours.map(h => String(h).padStart(2, '0') + ':00').join(', ')} (${esc(m.timezone)})</p>`
      : 'Ещё ни одного сканирования не было. Запустите его кнопкой выше.';
  };
  const labels = { start: 'Запусков', browse_catalog: 'Просмотров каталога', favorite_add: 'В избранное', favorite_remove: 'Из избранного', ai_question: 'Вопросов к ИИ', ai_feedback: 'Оценок ответов', unsubscribe: 'Отписок', manual_scan: 'Ручных сканирований', search: 'Поисковых запросов', profile_saved: 'Сохранений профиля', match_view: 'Просмотров подбора', telegram_linked: 'Привязок Telegram', web_visit: 'Заходов на сайт', register: 'Регистраций', login: 'Входов в аккаунт' };
  const renderStats = (s) => {
    const items = [`<div class="stat"><b>${s.active_users}</b><span>Активных пользователей</span></div>`, `<div class="stat"><b>${s.users_total}</b><span>Всего пользователей</span></div>`]
      .concat(Object.entries(s.events).map(([k, v]) => `<div class="stat"><b>${v}</b><span>${labels[k] || k}</span></div>`));
    $('#statsInfo').innerHTML = items.join('');
    if (s.audience) renderAudience(s.audience);
  };
  const renderAudience = (a) => {
    const u = a.users, act = a.active, nw = a.new;
    const stat = (v, label, sub = '') => `<div class="stat"><b>${v}</b><span>${label}</span>${sub ? `<small>${sub}</small>` : ''}</div>`;
    $('#audienceInfo').innerHTML = [
      stat(u.total, 'Всего людей', `Telegram ${u.telegram} · сайт ${u.site}`),
      stat(act.today.total, 'Активны сегодня', `бот ${act.today.telegram} · сайт ${act.today.site}`),
      stat(act['7d'].total, 'Активны за 7 дней', `бот ${act['7d'].telegram} · сайт ${act['7d'].site}`),
      stat(act['30d'].total, 'Активны за 30 дней', `бот ${act['30d'].telegram} · сайт ${act['30d'].site}`),
      stat(nw.today, 'Новых сегодня', `за 7 дней ${nw['7d']} · за 30 дней ${nw['30d']}`),
      stat(u.accounts, 'Аккаунтов на сайте', `привязано к Telegram ${u.linked}`),
      stat(u.subscribed, 'Подписаны на рассылку', 'пользователи бота'),
      stat(u.with_profile, 'Заполнили профиль', `с избранным ${u.with_favorites}`),
    ].join('');
    const f = a.funnel, tri = (k) => `${f.today[k]} · ${f['7d'][k]} · ${f['30d'][k]}`;
    $('#funnelInfo').innerHTML = [
      stat(f['7d'].visitors, 'Заходили на сайт', `сегодня · 7 дн · 30 дн: ${tri('visitors')}`),
      stat(f['7d'].from_bot, 'Пришли из бота', tri('from_bot')),
      stat(f['7d'].site_open, 'Нажали «сайт» в боте', tri('site_open')),
      stat(f['7d'].registered, 'Зарегистрировались', tri('registered')),
      stat(f['7d'].logins, 'Входили в аккаунт', tri('logins')),
      stat(f['7d'].bot_starts, 'Запускали бота', tri('bot_starts')),
    ].join('');
    const evLabel = { web_visit: 'зашёл на сайт', register: 'зарегистрировался', login: 'вошёл', site_open: 'открыл ссылку на сайт', start: 'запустил бота', telegram_linked: 'привязал Telegram' };
    $('#recentInfo').innerHTML = a.recent.length ? `<table class="recent"><thead><tr><th>Когда</th><th>Кто</th><th>Откуда</th><th>Что сделал</th></tr></thead><tbody>` + a.recent.map(r =>
      `<tr><td>${esc(r.at.slice(5, 16))}</td><td>${r.email ? esc(r.email) : (r.source === 'telegram' ? 'tg ' : 'web ') + r.user_id}${r.linked ? ' <span class="tag">связан</span>' : ''}</td><td>${r.source === 'telegram' ? 'Telegram' : 'сайт'}${r.from === 'bot' ? ' ← бот' : ''}</td><td>${evLabel[r.event] || esc(r.event)}</td></tr>`).join('') + '</tbody></table>' : '<p class="muted small">Пока никто не заходил.</p>';
    const max = Math.max(1, ...a.daily.map(d => Math.max(d.active, d.new)));
    $('#audienceChart').innerHTML = a.daily.map(d => `<div class="aud-col" title="${d.date}: активных ${d.active}, новых ${d.new}"><div class="aud-bars"><i class="a" style="height:${Math.round(100 * d.active / max)}%"></i><i class="n" style="height:${Math.round(100 * d.new / max)}%"></i></div><span>${d.date.slice(8)}</span></div>`).join('')
      + `<div class="aud-legend" style="grid-column:1/-1"><span><i style="background:var(--brand)"></i>активных за день</span><span><i style="background:rgba(42,171,238,.8)"></i>новых за день</span></div>`;
  };
  const renderScan = (s) => {
    const status = $('#scanStatus'), prog = $('#scanProgress'), res = $('#scanResult'), btn = $('#scanBtn');
    prog.hidden = !s.running; btn.disabled = s.running;
    if (s.running) { status.textContent = `Идёт с ${s.started_at.replace('T', ' ')}… бот и сайт продолжают работать`; return; }
    if (s.error) { status.textContent = 'Ошибка'; res.textContent = s.error; return; }
    if (s.result) {
      status.textContent = `Завершено ${s.finished_at.replace('T', ' ')}`;
      const st = s.stats || {};
      res.innerHTML = `Новых программ: <b>${s.result.new}</b>, удалено с прошедшим дедлайном: <b>${s.result.expired}</b>${st.snippets ? ` · сниппетов ${st.snippets}, кандидатов ${st.candidates}, прошло проверку ${st.valid}, за ${st.elapsed_sec}с` : ''}${st.updated != null ? ` · обновлено ${st.updated}, на проверку ${st.flagged}, автоочисткой в архив ${st.archived}` : ''}`
        + (s.result.grants.length ? `<div class="grid" style="margin-top:14px">${s.result.grants.map((g, i) => cardHTML(g, i)).join('')}</div>` : '');
    } else status.textContent = 'Не запускалось';
  };
  $('#audienceCsv')?.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/admin/users.csv', { headers: { 'X-Admin-Token': state.adminToken } });
      if (!res.ok) throw new Error(`Ошибка ${res.status}`);
      const blob = await res.blob(), a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || 'audience.csv';
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(a.href);
    } catch (err) { toast(err.message, 'err'); }
  });
  $('#scanBtn').addEventListener('click', async () => {
    try {
      const d = await busy($('#scanBtn'), () => api('/api/admin/scan', { method: 'POST' })); toast(d.message, 'ok');
      renderScan({ running: true, started_at: new Date().toISOString().slice(0, 19) });
      clearInterval(state.scanTimer);
      state.scanTimer = setInterval(async () => {
        try { const s = await api('/api/admin/scan/status'); renderScan(s); if (!s.running) { clearInterval(state.scanTimer); loadAdmin(); loadPublicStats(); } } catch { }
      }, 5000);
    } catch (err) { toast(err.message, 'err'); }
  });
  $('#deactBtn').addEventListener('click', async () => {
    const id = Number($('#deactId').value); if (!id) return;
    try { await api(`/api/admin/deactivate/${id}`, { method: 'POST' }); toast(`Грант #${id} снят с публикации`, 'ok'); $('#deactId').value = ''; }
    catch (err) { toast(err.message, 'err'); }
  });

  // ---------- Auth ----------
  const authModal = $('#authModal');
  let authMode = 'login';
  const renderUser = (u) => {
    $('#loginBtn').hidden = !!u; $('#userChip').hidden = !u;
    if (!u) return;
    const av = $('#userAvatar'), ini = $('#userInitial');
    if (u.avatar) { av.src = u.avatar; av.hidden = false; ini.hidden = true; } else { av.hidden = true; ini.hidden = false; ini.textContent = (u.name || u.email || '?').trim()[0].toUpperCase(); }
    $('#userName').textContent = u.name || u.email;
  };
  const setAuthMode = (mode) => {
    authMode = mode; const reg = mode === 'register';
    $('#authTitle').textContent = reg ? t('auth.register') : t('auth.login');
    $('#authSubmit').textContent = reg ? t('auth.create') : t('auth.login');
    $('#authSwitch').textContent = reg ? t('auth.tologin') : t('auth.toreg');
    $('.auth-switch').firstChild.textContent = reg ? t('auth.hasacc') : t('auth.noacc');
    $('#nameField').hidden = !reg;
    $('#authForm').password.autocomplete = reg ? 'new-password' : 'current-password';
  };
  const openAuth = (mode = 'login') => { setAuthMode(mode); authModal.hidden = false; setTimeout(() => $('#authForm').email.focus(), 50); };
  const closeAuth = () => { authModal.hidden = true; if (location.hash === '#auth') history.replaceState(null, '', location.pathname + '#' + state.view); };
  $('#loginBtn').addEventListener('click', () => openAuth('login'));
  $('#authClose').addEventListener('click', closeAuth);
  authModal.addEventListener('click', (e) => { if (e.target === authModal) closeAuth(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !authModal.hidden) closeAuth(); });
  $('#authSwitch').addEventListener('click', () => setAuthMode(authMode === 'login' ? 'register' : 'login'));
  $('#authForm').addEventListener('submit', async (e) => {
    e.preventDefault(); const f = e.target; $('#authSubmit').disabled = true;
    try {
      const body = { email: f.email.value.trim(), password: f.password.value };
      if (authMode === 'register') body.name = f.name.value.trim() || null;
      const d = await busy($('#authSubmit'), () => api(authMode === 'register' ? '/api/auth/register' : '/api/auth/login', { method: 'POST', body }));
      renderUser(d.user); closeAuth(); f.reset();
      toast(authMode === 'register' ? t('auth.welcome', { name: d.user.name }) : t('auth.back', { name: d.user.name }), 'ok');
      const favs = await api('/api/favorites'); state.favIds = new Set(favs.items.map(g => g.id)); updateFavBadge();
      const me = await api('/api/me'); state.profile = me.profile || {}; state.alertIds = new Set(me.alerts || []);
      state.telegramLinked = !!me.telegram_linked; if (state.view === 'profile') renderTelegram();
      if (state.view === 'favorites') loadFavorites();
    } catch (err) { toast(err.message, 'err'); }
    finally { $('#authSubmit').disabled = false; }
  });
  $('#logoutBtn').addEventListener('click', async () => {
    try { await api('/api/auth/logout', { method: 'POST' }); } catch { }
    renderUser(null); state.favIds = new Set(); updateFavBadge(); state.profile = {}; state.telegramLinked = false; toast(t('auth.out'));
    if (state.view === 'profile') renderTelegram();
    if (state.view === 'favorites') loadFavorites();
  });
  if (location.hash === '#auth') { history.replaceState(null, '', location.pathname + '#home'); setTimeout(() => openAuth('login'), 400); }
  if (location.hash === '#register') { history.replaceState(null, '', location.pathname + '#home'); setTimeout(() => openAuth('register'), 400); }

  // ---------- Compare (до 3 грантов) ----------
  const cmpBar = $('#cmpBar'), cmpModal = $('#cmpModal');
  const renderCmpBar = () => { const n = state.compare.size; cmpBar.hidden = n === 0; $('#cmpCount').textContent = `${t('cmp.bar')}: ${n}/3`; $$('[data-cmp]').forEach(b => b.classList.toggle('on', state.compare.has(Number(b.dataset.cmp)))); };
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-cmp]'); if (!b) return;
    const id = Number(b.dataset.cmp);
    if (state.compare.has(id)) state.compare.delete(id); else { if (state.compare.size >= 3) { toast(t('cmp.max'), 'err'); return; } state.compare.add(id); }
    renderCmpBar();
  });
  $('#cmpClear').addEventListener('click', () => { state.compare.clear(); renderCmpBar(); });
  $('#cmpClose').addEventListener('click', () => cmpModal.hidden = true);
  cmpModal.addEventListener('click', (e) => { if (e.target === cmpModal) cmpModal.hidden = true; });
  $('#cmpOpen').addEventListener('click', async () => {
    const ids = [...state.compare]; const gs = [];
    for (const id of ids) { let g = state.grants.get(id); if (!g) { try { g = await api(`/api/grants/${id}`); } catch { continue; } } gs.push(g); }
    if (!gs.length) return;
    const row = (label, cells, head = false) => `<div class="cmp-row ${head ? 'head' : ''}" style="--n:${gs.length}"><div>${label}</div>${cells.map(c => `<div>${c}</div>`).join('')}</div>`;
    $('#cmpTable').innerHTML = [
      row('', gs.map(g => `${esc(g.name)} ${flagOf(g)}`), true),
      row(t('cmp.country'), gs.map(g => esc(countryName(g.country_code) || (g.category === 'kz' ? t('region.kz') : t('country.multi'))))),
      row(t('cmp.level'), gs.map(g => degreeLabel[g.degree] || g.degree)),
      row(t('card.deadline'), gs.map(g => `${g.days_left != null && g.days_left >= 0 ? `<b>${g.days_left === 0 ? t('card.today') : g.days_left + ' ' + plural(g.days_left)}</b> · ` : ''}${esc(g.deadline)}`)),
      row(t('filter.funding'), gs.map(g => g.funding === 'full' || g.funding === 'partial' ? t('funding.' + g.funding) : '—')),
      row(t('card.coverage'), gs.map(g => esc(g.coverage))),
      row(t('card.requirements'), gs.map(g => esc(g.requirements))),
      row(t('cmp.status'), gs.map(g => g.status === 'open' ? t('tag.open') : g.status === 'upcoming' ? t('tag.upcoming') : '—')),
      row('', gs.map(g => `<a class="g-apply" href="${/^https?:\/\//i.test(g.link) ? esc(g.link) : '#'}" target="_blank" rel="noopener nofollow">${t('card.apply')}</a>`)),
    ].join('');
    cmpModal.hidden = false;
  });

  // ---------- Command palette (Ctrl K) ----------
  const palette = $('#palette'), pInput = $('#paletteInput'), pList = $('#paletteList');
  let pItems = [], pActive = 0, pTimer = null, pSeq = 0;
  const NAV_ITEMS = () => [
    { ico: ui.home, label: t('nav.homeapp'), run: () => show('home') }, { ico: ui.book, label: t('nav.catalog'), run: () => show('catalog') },
    { ico: ui.search, label: t('nav.search'), run: () => show('search') }, { ico: ui.star, label: t('nav.favorites'), run: () => show('favorites') },
    { ico: ui.chat, label: t('nav.chat'), run: () => show('chat') }, { ico: ui.user, label: t('nav.profile'), run: () => show('profile') }, { ico: ui.star, label: t('nav.match'), run: () => show('match') },
    { ico: ui.theme, label: t('palette.theme'), run: () => $('#themeToggle').click() },
    { ico: ui.lang, label: t('palette.lang') + ' · Рус', run: () => I.setLang('ru') }, { ico: ui.lang, label: t('palette.lang') + ' · Қаз', run: () => I.setLang('kz') }, { ico: ui.lang, label: t('palette.lang') + ' · Eng', run: () => I.setLang('en') },
  ];
  const renderPalette = (groups) => {
    pItems = []; let html = '';
    groups.forEach(([title, items]) => { if (!items.length) return; html += `<div class="palette__group">${title}</div>`; items.forEach(it => { const idx = pItems.length; pItems.push(it); html += `<div class="palette__item ${idx === pActive ? 'is-active' : ''}" data-pi="${idx}"><span class="pi-ico">${it.ico}</span><span>${esc(it.label)}</span>${it.sub ? `<span class="pi-sub">${esc(it.sub)}</span>` : ''}</div>`; }); });
    pList.innerHTML = html || `<div class="palette__empty">${t('palette.none')}</div>`;
  };
  const openPalette = () => { palette.hidden = false; pInput.value = ''; pActive = 0; renderPalette([[t('palette.nav'), NAV_ITEMS()]]); setTimeout(() => pInput.focus(), 30); };
  const closePalette = () => { palette.hidden = true; };
  $('#paletteBtn')?.addEventListener('click', openPalette);
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); palette.hidden ? openPalette() : closePalette(); return; }
    if (palette.hidden) return;
    if (e.key === 'Escape') { closePalette(); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); pActive = Math.min(pItems.length - 1, pActive + 1); $$('.palette__item').forEach((el, i) => el.classList.toggle('is-active', i === pActive)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); pActive = Math.max(0, pActive - 1); $$('.palette__item').forEach((el, i) => el.classList.toggle('is-active', i === pActive)); }
    if (e.key === 'Enter') { e.preventDefault(); const it = pItems[pActive]; if (it) { closePalette(); it.run(); } }
  });
  palette.addEventListener('click', (e) => { if (e.target === palette) closePalette(); const el = e.target.closest('[data-pi]'); if (el) { closePalette(); pItems[Number(el.dataset.pi)].run(); } });
  pInput.addEventListener('input', () => {
    const q = pInput.value.trim().toLowerCase(); pActive = 0;
    const nav = NAV_ITEMS().filter(it => !q || it.label.toLowerCase().includes(q));
    if (q.length < 2) { renderPalette([[t('palette.nav'), nav]]); return; }
    clearTimeout(pTimer);
    pTimer = setTimeout(async () => {
      const seq = ++pSeq;
      try {
        const d = await api(`/api/grants/search?q=${encodeURIComponent(q)}`); if (seq !== pSeq) return;
        const gr = d.items.slice(0, 8).map(g => ({ ico: flagOf(g), label: g.name, sub: g.days_left != null && g.days_left >= 0 ? `${g.days_left} ${plural(g.days_left)}` : g.deadline, run: () => { state.grants.set(g.id, g); show('search'); const inp = $('#searchInput'); inp.value = g.name; inp.dispatchEvent(new Event('input')); } }));
        renderPalette([[t('palette.grants'), gr], [t('palette.nav'), nav]]);
      } catch { renderPalette([[t('palette.nav'), nav]]); }
    }, 250);
  });

  // ---------- Home (персональная главная) ----------
  const dlLine = (g) => { const d = g.days_left; const cls = d != null && d <= 7 ? 'hot' : d != null && d <= 30 ? 'soon' : ''; return `<li data-open="${g.id}"><span class="dl-days ${cls}">${d == null ? '—' : d === 0 ? t('card.today') : d}</span><span class="dl-name">${esc(g.name)} ${flagOf(g)}</span><span class="dl-meta">${esc(g.deadline_date || g.deadline)}</span></li>`; };
  const loadHome = async () => {
    try {
      const h = await api('/api/home');
      const name = h.account?.name;
      $('#homeTitle').textContent = name ? t('home.hiName', { name }) : t('home.hi');
      $('#homeSub').textContent = (name || h.completeness > 0) ? t('home.sub') : t('home.subAnon');
      const sc = h.scan || {};
      const scanning = sc.phase && sc.phase !== 'idle' && sc.phase !== 'done';
      $('#homeScan').innerHTML = scanning ? `<span class="scan-live"><i></i>${t('home.scan')}: ${sc.done}/${sc.total}</span>` : `${t('home.scanIdle')}${sc.last ? ' · ' + t('live.last').toLowerCase() + ' ' + esc(String(sc.last).replace('T', ' ').slice(0, 16)) : ''}`;
      const tiles = [
        [h.strong_matches ?? h.matches.length, t('home.matches'), 'brand'], [h.total_active, t('home.active')], [h.favorites_count, t('home.favs')], [h.completeness + '%', t('home.profile'), '', h.completeness],
      ];
      $('#homeTiles').innerHTML = tiles.map(([v, l, cls, bar]) => `<div class="tile"><b class="${cls || ''}">${v}</b><span>${l}</span>${bar != null ? `<div class="bar"><i style="--w:${bar}%"></i></div>` : ''}</div>`).join('');
      const tipNav = { profile: 'profile', favorites: 'catalog', deadline: 'favorites', chat: 'chat' }[h.tip] || 'catalog';
      $('#homeTip').innerHTML = `<p class="eyebrow">${t('home.tip')}</p><p>${t('home.tip.' + h.tip)}</p><a href="#${tipNav}" data-nav="${tipNav}" class="btn btn-ghost btn-sm">${t('home.tip.' + h.tip + '.btn')}</a>`;
      $('#homeDlTitle').textContent = h.upcoming_is_favorites ? t('home.deadlinesFav') : t('home.deadlines');
      $('#homeDl').innerHTML = h.upcoming.length ? h.upcoming.map(dlLine).join('') : `<li><span class="dl-meta">${t('card.tbd')}</span></li>`;
      h.upcoming.forEach(g => state.grants.set(g.id, g));
      $('#homeForYou').textContent = (h.strong_matches ?? 0) > 0 ? t('home.forYou') : t('home.forYouAnon');
      renderGrid($('#homeGrid'), h.matches);
    } catch (err) { toast(err.message, 'err'); }
  };
  $('#homeDl').addEventListener('click', (e) => { const li = e.target.closest('[data-open]'); if (!li) return; const g = state.grants.get(Number(li.dataset.open)); if (g && /^https?:\/\//i.test(g.link)) window.open(g.link, '_blank', 'noopener'); });

  // ---------- Init ----------
  (async () => {
    try {
      const me = await api('/api/me');
      state.profile = me.profile || {}; state.alertIds = new Set(me.alerts || []);
      state.telegramLinked = !!me.telegram_linked; state.botUsername = me.bot_username || null;
      renderUser(me.account);
      const favs = await api('/api/favorites'); favs.items.forEach(g => state.favIds.add(g.id)); updateFavBadge();
      $('#adminNav').hidden = !me.admin_enabled;
      try { state.countries = (await api('/api/meta')).countries || []; } catch { }
    } catch { /* без сети — покажем статичную часть */ }
    loadReminders();
    show(location.hash.slice(1) || 'home', false);
    requestAnimationFrame(moveInk);
  })();
})();
