/* ================= GrantHub landing — config & animations ================= */
(() => {
  'use strict';

  /* ---------- All texts live here: edit freely ---------- */
  const CONTENT = {
    brandTop: 'GrantHub',
    brandBottom: 'Kazakhstan',
    brandLink: '/',
    nav: [
      { label: 'Каталог', href: '/app#catalog', active: true },
      { label: 'ИИ-консультант', href: '/app#chat' },
      { label: 'Избранное', href: '/app#favorites' },
      { label: 'Профиль', href: '/app#profile' },
      { label: 'Контакты', href: '#contact', slide: 'contact' },
      { label: 'Войти', href: '/app#auth' },
    ],
    contact: {
      title: 'Свяжись с нами',
      text: 'Вопросы по грантам, партнёрство, идеи для проекта — пиши, отвечаем в течение дня.',
      email: 'Baigani1928@gmail.com',
      telegram: 'Telegram-бот GrantHub',
      telegramHref: 'https://t.me/grantsmstbot',
      copy: 'Скопировать почту',
      copied: 'Почта скопирована',
      close: 'Закрыть',
    },
    concierge: 'ИИ онлайн 24/7',
    navCta: 'Спросить ИИ',
    navCtaHref: '/app#chat',
    eyebrow: 'ИИ ищет гранты, пока ты спишь',
    titleLine1: 'Гранты на учёбу',
    titleLine2: 'по всему миру',
    cards: [
      { value: '150+', label: 'университетов', statKey: 'universities', suffix: '+' },
      { value: '70', label: 'международных конкурсов', statKey: 'programs' },
      { value: '24/7', label: 'ИИ-мониторинг' },
    ],
    note: 'Для тех, кто не просто поступает, а выбирает лучшее.',
    cta: 'Найти свой грант',
    ctaHref: '/app#catalog',
    footWords: ['Университеты', 'конкурсы', 'дедлайны'],
    footBrand: 'GrantHub Kazakhstan',
    heroImage: '/static/landing/assets/hero.svg',   // replace with /static/landing/assets/hero.png
    statsEndpoint: '/api/stats/public',              // live numbers for cards (optional)
  };

  /* ---------- Язык: тексты берём из i18n.js (ru/kz/en), поверх базового CONTENT ---------- */
  const L = (window.I18N && window.I18N.LANDING) || null;
  if (L) {
    Object.assign(CONTENT, {
      brandBottom: L.brandBottom, concierge: L.concierge, navCta: L.navCta, eyebrow: L.eyebrow,
      titleLine1: L.titleLine1, titleLine2: L.titleLine2, note: L.note, cta: L.cta, footWords: L.footWords, footBrand: L.footBrand,
      nav: L.nav.map(([label, href]) => ({ label, href, active: href === '/app#catalog', slide: href === '#contact' ? 'contact' : undefined })),
      cards: L.cards.map(([value, label], i) => ({ value, label, statKey: CONTENT.cards[i]?.statKey, suffix: CONTENT.cards[i]?.suffix })),
      contact: Object.assign({}, CONTENT.contact, L.contact),
    });
  }
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  // ?static=1 skips the intro (useful for screenshots / QA); prefers-reduced-motion does the same
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches || new URLSearchParams(location.search).has('static');
  const screen = $('#screen');
  if (reduced) document.body.classList.add('no-motion');

  /* ---------- Fill texts ---------- */
  $$('[data-t]').forEach(el => { const v = CONTENT[el.dataset.t]; if (v == null) return; if (el.tagName === 'A' && el.dataset.t === 'brandLink') el.href = v; else el.textContent = v; });
  $('#navCta').href = CONTENT.navCtaHref;
  $('#cta').href = CONTENT.ctaHref;
  $$('.hero__img').forEach(img => { if (img.getAttribute('src') !== CONTENT.heroImage) img.src = CONTENT.heroImage; });
  const navHTML = CONTENT.nav.map(n => `<a href="${n.href}" class="${n.active ? 'is-active' : ''}" ${n.slide ? `data-slide="${n.slide}"` : ''}>${n.label}</a>`).join('');
  $('#navLinks').innerHTML = navHTML; $('#mobileMenu').innerHTML = navHTML;
  $('#cards').innerHTML = CONTENT.cards.map(c => `<div class="card"><b data-stat="${c.statKey || ''}" data-suffix="${c.suffix || ''}">${c.value}</b><span>${c.label}</span></div>`).join('');
  $('#footWords').innerHTML = CONTENT.footWords.map(w => `<li>${w}</li>`).join('');
  if (L) {
    const setAll = (sel, vals, prop = 'textContent') => $$(sel).forEach((el, i) => { if (vals[i] != null) el[prop] = vals[i]; });
    setAll('.stat-label', L.stats);
    const secs = $$('.sec-head'); if (secs[0]) { secs[0].querySelector('.sec-eyebrow').textContent = L.sec1[0]; secs[0].querySelector('.sec-title').innerHTML = L.sec1[1]; }
    if (secs[1]) { secs[1].querySelector('.sec-eyebrow').textContent = L.sec2[0]; secs[1].querySelector('.sec-title').innerHTML = L.sec2[1]; }
    $$('.feat').forEach((el, i) => { if (L.feats[i]) { el.querySelector('h3').textContent = L.feats[i][0]; el.querySelector('p').textContent = L.feats[i][1]; } });
    $$('.steps-row li').forEach((el, i) => { if (L.steps[i]) { el.querySelector('h3').textContent = L.steps[i][0]; el.querySelector('p').textContent = L.steps[i][1]; } });
    const fin = $('.final'); if (fin) { fin.querySelector('.sec-eyebrow').textContent = L.final[0]; fin.querySelector('.sec-title').innerHTML = L.final[1]; fin.querySelector('.cta--inline').textContent = CONTENT.cta; fin.querySelector('.pill--dark').textContent = CONTENT.navCta; }
    $$('.below-foot .foot__words li').forEach((el, i) => { el.textContent = CONTENT.footWords[i] || el.textContent; });
    $('.chip-ol') && ($('.chip-ol').lastChild.textContent = L.contact.badge);
    $$('.slide__meta li').forEach((el, i) => { el.textContent = L.contact.meta[i] || el.textContent; });
    window.I18N.switcher($('#langBox'));
    document.title = window.I18N.lang === 'kz' ? 'GrantHub — бүкіл әлем бойынша оқу гранттары' : window.I18N.lang === 'en' ? 'GrantHub — study grants around the world' : 'GrantHub — гранты на учёбу по всему миру';
  }

  /* ---------- Burger ---------- */
  const burger = $('#burger'), mobileMenu = $('#mobileMenu');
  burger.addEventListener('click', () => { const open = burger.getAttribute('aria-expanded') === 'true'; burger.setAttribute('aria-expanded', String(!open)); mobileMenu.hidden = open; });

  /* ---------- Contact slide ---------- */
  const C = CONTENT.contact, slide = $('#contactSlide');
  $('#contactTitle').textContent = C.title; $('#contactText').textContent = C.text;
  const mail = $('#contactEmail'); mail.textContent = C.email; mail.href = 'mailto:' + C.email;
  const tg = $('#contactTg'); tg.textContent = C.telegram; tg.href = C.telegramHref;
  $('#copyEmail').textContent = C.copy; $('#contactClose').setAttribute('aria-label', C.close);
  const openSlide = () => {
    slide.hidden = false; document.body.classList.add('slide-open');
    if (reduced) slide.classList.add('is-open'); else requestAnimationFrame(() => requestAnimationFrame(() => slide.classList.add('is-open')));
    // focus without scrolling: the panel starts off-screen and would drag the framed screen sideways
    setTimeout(() => $('#contactClose').focus({ preventScroll: true }), reduced ? 0 : 650);
  };
  const closeSlide = () => { slide.classList.remove('is-open'); document.body.classList.remove('slide-open'); setTimeout(() => { slide.hidden = true; }, 550); if (location.hash === '#contact') history.replaceState(null, '', location.pathname); };
  document.addEventListener('click', (e) => {
    const a = e.target.closest('[data-slide="contact"]'); if (!a) return;
    e.preventDefault(); history.replaceState(null, '', '#contact'); openSlide();
    burger.setAttribute('aria-expanded', 'false'); mobileMenu.hidden = true;
  });
  $('#contactClose').addEventListener('click', closeSlide);
  slide.addEventListener('click', (e) => { if (e.target === slide) closeSlide(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !slide.hidden) closeSlide(); });
  $('#copyEmail').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(C.email); $('#copyEmail').textContent = C.copied; setTimeout(() => { $('#copyEmail').textContent = C.copy; }, 1800); }
    catch { location.href = 'mailto:' + C.email; }
  });
  if (location.hash === '#contact') setTimeout(openSlide, 400);

  /* ---------- Live stats (optional, silent on failure) ---------- */
  const countUp = (el, to) => {
    if (reduced) { el.textContent = to; return; }
    const start = performance.now(), dur = 1400;
    const tick = (t) => { const p = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - p, 3); el.textContent = Math.round(to * e); if (p < 1) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  };
  let statsData = null, counted = false;
  const runCounters = () => { if (counted || !statsData) return; counted = true; $$('[data-count]').forEach(el => countUp(el, statsData[el.dataset.count] || 0)); };
  fetch(CONTENT.statsEndpoint).then(r => r.ok ? r.json() : null).then(s => {
    if (!s) return; statsData = s;
    $$('[data-stat]').forEach(el => { const k = el.dataset.stat; if (k && s[k] != null) el.textContent = s[k] + (el.dataset.suffix || ''); });
    const u = s.users || {}, ps = $('#peopleSub');
    if (ps) ps.textContent = [u.week_delta > 0 ? (L ? L.weekDelta : '+{d} за неделю').replace('{d}', u.week_delta) : '', u.active_30d ? (L ? L.active30 : '{n} активны за месяц').replace('{n}', u.active_30d) : ''].filter(Boolean).join(' · ');
    const last = s.last_checked ? new Date(s.last_checked).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' }) : 'ещё не было';
    const lc = L ? L.lastCheck : 'Последняя проверка', pl = L ? L.plan : 'план';
    $('#statsFoot').textContent = `${lc}: ${s.last_checked ? last : (L ? L.never : 'ещё не было')} · ${pl}: ${s.scan_hours.map(h => String(h).padStart(2, '0') + ':00').join(', ')} (${s.timezone})`;
    if ($('#stats').classList.contains('seen')) runCounters();
  }).catch(() => {});

  /* ---------- Live strip: just-found grants + scan progress ---------- */
  const T = (window.I18N && window.I18N.APP) || {};
  const tt = (k, d) => T[k] || d;
  // Флаг — эмодзи из кода страны ISO; без кода (несколько стран) — глобус
  const flagEmoji = (code) => /^[A-Za-z]{2}$/.test(code || '') ? code.toUpperCase().replace(/./g, c => String.fromCodePoint(127397 + c.charCodeAt(0))) : '';
  const flagOf = (g) => `<span class="flag">${flagEmoji(g.country_code) || '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>'}</span>`;
  $('#liveTitle').textContent = tt('live.title', 'Только что найдено');
  fetch('/api/recent-grants?limit=12').then(r => r.ok ? r.json() : null).then(d => {
    if (!d || !d.items.length) { $('#live').hidden = true; return; }
    const item = (g) => { const dl = g.days_left; const cls = dl != null && dl <= 7 ? 'hot' : dl != null && dl <= 30 ? 'soon' : ''; const dtxt = dl == null ? (g.deadline || '') : dl === 0 ? tt('card.today', 'сегодня') : `${dl} ${tt('card.days', 'дн.')}`; return `<a class="live__item" href="/app#search"><span>${g.name.replace(/[<>&]/g, '')} ${flagOf(g)}</span><span class="d ${cls}">${dtxt}</span></a>`; };
    const html = d.items.map(item).join('');
    $('#liveMarquee').innerHTML = html + html; // дублируем для бесшовной прокрутки
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

  /* ---------- Reveal on scroll for the sections below the hero ---------- */
  const io = new IntersectionObserver((entries) => entries.forEach(en => {
    if (!en.isIntersecting) return;
    en.target.classList.add('in'); io.unobserve(en.target);
    if (en.target.closest('#stats')) { $('#stats').classList.add('seen'); runCounters(); }
  }), { threshold: .2 });
  $$('.rv').forEach(el => io.observe(el));
  if (reduced) { $$('.rv').forEach(el => el.classList.add('in')); $('#stats').classList.add('seen'); }

  /* ---------- Mockup background: a darkened, blurred "copy" of the page.
     html2canvas is heavy; we approximate with the hero image + glows so it stays cinematic. ---------- */
  const bg = $('#mockupBg');
  bg.style.backgroundImage = `url("${CONTENT.heroImage}"), radial-gradient(60% 40% at 50% 65%, rgba(255,255,255,.12), transparent 70%), linear-gradient(#0a0a0a, #050505)`;
  bg.style.backgroundSize = '70% auto, cover, cover';
  bg.style.backgroundRepeat = 'no-repeat';
  bg.style.backgroundPosition = '45% 55%, center, center';

  /* ---------- Static fallback (reduced motion) ---------- */
  const heroObject = $('#heroObject'), reflection = $('#reflection'), intro = $('#intro'), cta = $('#cta');
  if (reduced) {
    intro.remove(); screen.classList.add('is-static', 'is-ready'); cta.classList.add('is-in');
    return;
  }

  /* ---------- Intro: whole page blurred & dark -> de-blur 1.2s ---------- */
  screen.classList.add('is-intro');
  requestAnimationFrame(() => requestAnimationFrame(() => {
    intro.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 900, easing: 'ease-out', fill: 'forwards' }).onfinish = () => intro.remove();
    screen.classList.remove('is-intro');   // CSS transition: blur 40px -> 0 over 1.2s
  }));

  /* ---------- Dust / smoke particles ---------- */
  const dust = $('#dust');
  const spawnDust = () => {
    for (let i = 0; i < 26; i++) {
      const p = document.createElement('i');
      const size = 30 + Math.random() * 90;
      p.style.width = p.style.height = size + 'px';
      p.style.left = Math.random() * 60 + '%';
      p.style.bottom = Math.random() * 20 + '%';
      dust.appendChild(p);
      p.animate([
        { opacity: 0, transform: 'translate(0,0) scale(.4)' },
        { opacity: .8, offset: .2 },
        { opacity: 0, transform: `translate(${-120 - Math.random() * 220}px, ${-40 - Math.random() * 120}px) scale(${1.6 + Math.random()})` },
      ], { duration: 1400 + Math.random() * 1200, delay: 250 + Math.random() * 900, easing: 'cubic-bezier(.16,1,.3,1)', fill: 'forwards' }).onfinish = () => p.remove();
    }
  };

  /* ---------- Hero object drives in from the left, motion blur, decelerates ---------- */
  const EASE = 'cubic-bezier(0.16, 1, 0.3, 1)';
  // animate() with the delay applied via setTimeout (robust in headless / virtual-time renderers)
  const anim = (el, frames, { delay = 0, ...opts }, onfinish) => setTimeout(() => {
    const a = el.animate(frames, { easing: EASE, fill: 'forwards', ...opts }); if (onfinish) a.onfinish = onfinish;
  }, delay);
  const START = 400;      // ms after intro starts
  const DRIVE = 2000;     // duration of the drive-in
  const startX = matchMedia('(max-width: 720px)').matches ? -110 : -140; // % of own width

  heroObject.style.opacity = '0';
  setTimeout(() => {
    heroObject.style.opacity = '1';
    spawnDust();
    // horizontal drive with ease-out deceleration (keeps the CSS resting translate)
    heroObject.animate([
      { translate: `${startX}% 0` },
      { translate: '0% 0' },
    ], { duration: DRIVE, easing: EASE, fill: 'forwards' });
    // motion blur + slight skew during acceleration -> sharp on stop
    const img = $('#heroImg');
    img.animate([
      { filter: 'blur(14px) drop-shadow(0 40px 60px rgba(0,0,0,.7))', transform: 'skewX(-4deg) rotate(-1.5deg)' },
      { filter: 'blur(6px) drop-shadow(0 40px 60px rgba(0,0,0,.7))', transform: 'skewX(-2deg) rotate(-.6deg)', offset: .45 },
      { filter: 'blur(0px) drop-shadow(0 40px 60px rgba(0,0,0,.7))', transform: 'skewX(0) rotate(0)' },
    ], { duration: DRIVE, easing: EASE, fill: 'forwards' });
    // reflection fades in synchronously
    setTimeout(() => { reflection.style.opacity = '1'; screen.classList.add('is-ready'); }, DRIVE * 0.35);
  }, START);

  /* ---------- Headline: fade + slide up after the object stops, stagger 0.1s ---------- */
  const afterStop = START + DRIVE - 300;
  setTimeout(() => {
    $$('.hero__line > span').forEach((el, i) => anim(el,
      [{ opacity: 0, transform: 'translateY(110%)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 900, delay: i * 100 }));
    anim($('#eyebrow'), [{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'none' }], { duration: 800, delay: 250 });
  }, afterStop);

  /* ---------- Glass cards slide in from the left, stagger 0.15s ---------- */
  setTimeout(() => {
    $$('.card').forEach((el, i) => anim(el,
      [{ opacity: 0, transform: 'translateX(-40px)' }, { opacity: 1, transform: 'translateX(0)' }], { duration: 800, delay: i * 150 }));
    anim($('#note'), [{ opacity: 0, transform: 'translateY(6px)' }, { opacity: 1, transform: 'none' }], { duration: 800, delay: 450 });
  }, afterStop + 150);

  /* ---------- Navbar (from top), footer & CTA (from bottom) ---------- */
  setTimeout(() => {
    const mobile = matchMedia('(max-width: 720px)').matches;
    anim($('#nav'), [{ opacity: 0, translate: '-50% -16px' }, { opacity: 1, translate: '-50% 0' }], { duration: 900 });
    anim($('#foot'), [{ opacity: 0, translate: mobile ? '0 12px' : '-50% 12px' }, { opacity: 1, translate: mobile ? '0 0' : '-50% 0' }], { duration: 900, delay: 150 });
    anim(cta, [{ opacity: 0, transform: mobile ? 'translateY(24px)' : 'translate(-50%, 24px)' }, { opacity: 1, transform: mobile ? 'none' : 'translate(-50%, 0)' }],
      { duration: 900, delay: 300 }, () => cta.classList.add('is-in'));
  }, START + 700);

  /* ---------- Parallax: object follows mouse 10-15px, headline moves opposite ---------- */
  if (matchMedia('(hover:hover)').matches) {
    const title = $('#title');
    let tx = 0, ty = 0, cx = 0, cy = 0, raf = null;
    const tick = () => {
      cx += (tx - cx) * 0.08; cy += (ty - cy) * 0.08;
      heroObject.style.setProperty('--px', cx); // exposed for debugging
      heroObject.style.transform = `translate(calc(-56% + ${cx}px), calc(-44% + ${cy}px))`;
      title.style.transform = `translate(${-cx * 0.6}px, ${-cy * 0.6}px)`;
      if (Math.abs(tx - cx) > .1 || Math.abs(ty - cy) > .1) raf = requestAnimationFrame(tick); else raf = null;
    };
    const onMove = (e) => {
      const r = screen.getBoundingClientRect();
      tx = ((e.clientX - r.left) / r.width - .5) * 28;   // ±14px
      ty = ((e.clientY - r.top) / r.height - .5) * 20;   // ±10px
      if (!raf) raf = requestAnimationFrame(tick);
    };
    setTimeout(() => { screen.addEventListener('pointermove', onMove); screen.addEventListener('pointerleave', () => { tx = ty = 0; if (!raf) raf = requestAnimationFrame(tick); }); }, START + DRIVE);
  }
})();
