/* GrantHub — переводы: ru / kz / en. Подключается и в приложении, и на лендинге. */
(() => {
  'use strict';
  // Windows не умеет рисовать эмодзи-флаги — для него в CSS подключается шрифт с флагами
  if (/Windows/.test(navigator.userAgent) && !/Firefox/.test(navigator.userAgent)) document.documentElement.classList.add('flag-font');
  // Полоса прокрутки как в iOS: своя «пилюля» поверх страницы, появляется при прокрутке и гаснет через секунду.
  // Родная полоса окна скрыта в CSS, поэтому вид не зависит от браузера (Chrome, Opera GX, Edge, Firefox).
  const root = document.documentElement;
  const sb = document.createElement('div'); sb.className = 'ios-sb'; sb.setAttribute('aria-hidden', 'true');
  const thumb = document.createElement('i'); sb.appendChild(thumb);
  (document.body || root).appendChild(sb);
  let sbTimer = null, sbDrag = null;
  const sbMetrics = () => { const vh = window.innerHeight, sh = root.scrollHeight, track = sb.clientHeight; const h = Math.max(36, track * vh / sh); return { vh, sh, track, h }; };
  const sbPlace = () => {
    const { vh, sh, track, h } = sbMetrics();
    if (sh <= vh + 1) { sb.style.display = 'none'; return; }
    sb.style.display = ''; thumb.style.height = h + 'px';
    thumb.style.transform = `translateY(${(track - h) * window.scrollY / (sh - vh)}px)`;
  };
  const sbShow = () => {
    root.classList.add('is-scrolling'); sb.classList.add('on'); sbPlace();
    clearTimeout(sbTimer);
    sbTimer = setTimeout(() => { if (sbDrag || thumb.matches(':hover')) { sbShow(); return; } root.classList.remove('is-scrolling'); sb.classList.remove('on'); }, 900);
  };
  document.addEventListener('scroll', sbShow, { capture: true, passive: true });
  window.addEventListener('resize', sbPlace);
  thumb.addEventListener('pointerdown', (e) => { sbDrag = { y: e.clientY, top: window.scrollY }; sb.classList.add('drag'); thumb.setPointerCapture(e.pointerId); e.preventDefault(); });
  thumb.addEventListener('pointermove', (e) => {
    if (!sbDrag) return; const { vh, sh, track, h } = sbMetrics();
    window.scrollTo({ top: sbDrag.top + (e.clientY - sbDrag.y) * (sh - vh) / (track - h), behavior: 'instant' });
  });
  const sbEnd = () => { sbDrag = null; sb.classList.remove('drag'); };
  thumb.addEventListener('pointerup', sbEnd); thumb.addEventListener('pointercancel', sbEnd);
  const LANGS = ['ru', 'kz', 'en'];
  const NAMES = { ru: 'Рус', kz: 'Қаз', en: 'Eng' };

  /* ---------------- Приложение (/app) ---------------- */
  const APP = {
    ru: {
      'nav.homeapp': 'Главная', 'theme': 'Тема', 'palette': 'Поиск по всему · Ctrl K', 'palette.ph': 'Найти грант или команду…', 'palette.nav': 'Разделы', 'palette.grants': 'Гранты', 'palette.none': 'Ничего не найдено', 'palette.theme': 'Переключить тему', 'palette.lang': 'Сменить язык',
      'home.hi': 'Привет', 'home.hiName': 'Привет, {name}', 'home.sub': 'Вот что ИИ подобрал для тебя сегодня', 'home.subAnon': 'Заполни профиль или войди — и подборка станет персональной',
      'home.matches': 'Подходит тебе', 'home.active': 'Активных грантов', 'home.favs': 'В избранном', 'home.profile': 'Профиль заполнен',
      'home.tip': 'Совет на сегодня', 'home.tip.profile': 'Заполни IELTS, GPA и направление — тогда я смогу отсечь то, что не подходит, и показать реально твои гранты.', 'home.tip.profile.btn': 'Заполнить профиль',
      'home.tip.favorites': 'Добавь несколько грантов в избранное — я начну напоминать о дедлайнах за 7, 3 и 1 день.', 'home.tip.favorites.btn': 'Открыть каталог',
      'home.tip.deadline': 'У одного из твоих избранных грантов дедлайн меньше чем через две недели. Самое время собирать документы.', 'home.tip.deadline.btn': 'К избранному',
      'home.tip.chat': 'Спроси ИИ-ментора, как усилить заявку: мотивационное письмо, рекомендации, портфолио.', 'home.tip.chat.btn': 'Спросить ИИ',
      'home.deadlines': 'Ближайшие дедлайны', 'home.deadlinesFav': 'Дедлайны в избранном', 'home.forYou': 'Подобрано для тебя', 'home.forYouAnon': 'Свежие программы', 'home.all': 'Весь каталог',
      'home.scan': 'Сканирование сейчас', 'home.scanIdle': 'Следующее сканирование по расписанию', 'why.field': 'по направлению', 'why.ielts_ok': 'IELTS подходит', 'why.gpa_ok': 'GPA подходит', 'why.open': 'приём открыт',
      'card.days': 'дней', 'card.day1': 'день', 'card.days2': 'дня', 'card.today': 'сегодня', 'card.tbd': 'уточняется', 'card.expired': 'прошёл', 'card.apply': 'Подать заявку', 'card.compare': 'Сравнить', 'card.coverageLvl': 'уровень покрытия',
      'cmp.title': 'Сравнение грантов', 'cmp.bar': 'Сравнить', 'cmp.clear': 'Сбросить', 'cmp.max': 'Можно сравнить не больше 3 грантов', 'cmp.country': 'Страна', 'cmp.level': 'Уровень', 'cmp.status': 'Статус',
      'live.title': 'Только что найдено', 'live.scan': 'Сканирую', 'live.of': 'из', 'live.sources': 'источников', 'live.extract': 'ИИ разбирает результаты', 'live.check': 'Проверяю ссылки', 'live.last': 'Последняя проверка', 'live.new': 'новых',
      'nav.home': 'Главная', 'nav.catalog': 'Каталог', 'nav.search': 'Поиск', 'nav.favorites': 'Избранное', 'nav.chat': 'ИИ-консультант', 'nav.profile': 'Профиль', 'nav.admin': 'Админ',
      'pill.online': 'ИИ онлайн 24/7', 'pill.ask': 'Спросить ИИ', 'login': 'Войти', 'logout': 'Выйти',
      'catalog.step1': 'Шаг 1 из 2: выбери регион обучения', 'catalog.step2': 'Шаг 2 из 2: выбери уровень', 'catalog.results': 'Актуальные программы по твоему выбору',
      'catalog.title': 'Где ты хочешь<br>учиться?', 'catalog.title2': 'Какой уровень<br>обучения?', 'catalog.titleKz': 'Гранты в Казахстане', 'catalog.titleAbroad': 'Гранты в мире',
      'catalog.lead': 'Казахстан или весь мир. ИИ проверяет источники дважды в день, здесь только действующие программы.',
      'choice.kz': 'Казахстан', 'choice.kz.desc': 'Государственные гранты по ЕНТ, гранты ректоров, стипендии вузов',
      'choice.abroad': 'За рубежом', 'choice.abroad.desc': 'Международные конкурсы и стипендии университетов мира',
      'choice.bachelor': 'Бакалавриат', 'choice.bachelor.desc': 'Первое высшее после школы или колледжа',
      'choice.master': 'Магистратура', 'choice.master.desc': 'Вторая ступень, обычно 1–2 года',
      'choice.all': 'Показать всё', 'choice.all.desc': 'Все уровни и программы региона',
      'back.regions': '← Назад к регионам', 'back.change': '← Изменить', 'loadmore': 'Показать ещё', 'total': 'Всего',
      'region.kz': 'Казахстан', 'region.abroad': 'За рубежом', 'degree.bachelor': 'Бакалавриат', 'degree.master': 'Магистратура', 'degree.all': 'Все уровни',
      'catalog.empty': 'В этой категории пока ничего нет. ИИ добавит гранты после следующего сканирования.',
      'scope.kz': 'Казахстан', 'scope.abroad': 'Зарубеж', 'scope.all': 'Все', 'catalog.titleAll': 'Все гранты', 'degree.phd': 'PhD', 'degree.language': 'Языковые курсы',
      'filter.degree': 'Уровень', 'filter.country': 'Страна', 'filter.funding': 'Финансирование', 'filter.deadline': 'Приём заявок', 'filter.req': 'Требования', 'filter.reset': 'Сбросить',
      'funding.full': 'Полный грант', 'funding.partial': 'Частичный грант', 'deadline.open': 'Приём открыт', 'deadline.upcoming': 'Скоро откроется', 'deadline.closed': 'Завершён', 'req.ent': 'ЕНТ', 'country.multi': 'Несколько стран', 'sort.new': 'Сначала новые', 'sort.deadline': 'По дедлайну', 'sort.funding': 'По покрытию',
      'search.eyebrow': 'Поиск по базе', 'search.title': 'Найди грант<br>по одному слову', 'search.lead': 'Название, страна, покрытие или требования. Например: IT, Германия, магистратура, IELTS 6.0.',
      'search.placeholder': 'Введи ключевое слово…', 'search.hint': 'Начни вводить — результаты появятся сразу.', 'search.found': 'Найдено', 'search.none': 'По запросу «{q}» ничего не найдено.',
      'quick': ['Германия', 'IT', 'Магистратура', 'Полное покрытие', 'Казахстан'],
      'fav.eyebrow': 'Твоя подборка', 'fav.title': 'Избранное', 'fav.lead': 'Сохранённые гранты и напоминания о дедлайнах за 7, 3 и 1 день.',
      'fav.empty': 'Пока пусто. Отмечай гранты звёздочкой в каталоге, и они появятся здесь.', 'fav.open': 'Открыть каталог',
      'fav.added': 'Добавлено в избранное ⭐', 'fav.removed': 'Убрано из избранного', 'fav.btn': 'В избранное',
      'chat.eyebrow': 'Локальная модель · без лимитов', 'chat.title': 'Спроси ИИ-ментора', 'chat.lead': 'Поступление, гранты, ЕНТ, IELTS, GPA, мотивационные письма. Ответ учитывает твой профиль.',
      'chat.name': 'ИИ-ментор по поступлению', 'chat.status': 'Отвечает с учётом твоего профиля', 'chat.thinking': 'Думаю…', 'chat.typing': 'Печатает…',
      'chat.hello': 'Привет! Я помогу с поступлением, грантами, ЕНТ, IELTS, GPA и мотивационными письмами. Спроси что угодно — например, «какие гранты подойдут для магистратуры по IT в Европе?»',
      'chat.placeholder': 'Напиши вопрос…', 'chat.empty': '⚠️ Пустой ответ.',
      'suggestions': ['Какие гранты сейчас открыты за рубежом?', 'Как написать мотивационное письмо?', 'Что нужно для Болашака?', 'Гранты в Казахстане по ЕНТ'],
      'fb.up': 'Полезно', 'fb.down': 'Не помогло', 'fb.thanks': 'Спасибо за фидбек! 🙌',
      'profile.eyebrow': 'Персонализация', 'profile.title': 'Расскажи<br>о себе', 'profile.lead': 'ИИ будет советовать только то, что реально подходит под твой уровень. Любое поле можно оставить пустым.',
      'profile.b1': '<b>IELTS</b> — отсекает программы с недостижимым языковым порогом', 'profile.b2': '<b>GPA</b> — подбирает гранты по твоей успеваемости', 'profile.b3': '<b>Направление</b> — приоритет программам по твоей специальности',
      'profile.field': 'Направление', 'profile.field.ph': 'Например, Computer Science', 'profile.ielts.ph': 'Например, 6.5', 'profile.gpa.ph': 'Например, 3.7',
      'save': 'Сохранить', 'clear': 'Очистить', 'profile.saved': 'Профиль сохранён. ИИ будет учитывать его в советах.', 'profile.cleared': 'Профиль очищен',
      'admin.eyebrow': 'Только для администратора', 'admin.title': 'Панель управления', 'admin.lead': 'Сканер, мониторинг источников, модель и статистика.',
      'card.coverage': 'Покрытие', 'card.requirements': 'Требования', 'card.deadline': 'Дедлайн', 'card.source': 'Источник', 'card.site': 'Официальный сайт',
      'tag.open': 'приём открыт', 'tag.upcoming': 'скоро откроется', 'tag.today': 'сегодня', 'tag.days': 'дн.',
      'rem.text': 'До подачи заявки на «{name}» осталось', 'rem.lessday': 'меньше дня', 'rem.opened': 'Открылся приём заявок: «{name}»', 'card.ongoing': 'круглый год', 'tag.from': 'с',
      'bell.title': 'Уведомить об открытии', 'bell.added': 'Сообщим, когда откроется приём', 'bell.removed': 'Уведомление отключено', 'rem.open': 'Открыть →',
      'foot.words': 'Университеты &nbsp;&nbsp; конкурсы &nbsp;&nbsp; дедлайны',
      'auth.eyebrow': 'Аккаунт GrantHub', 'auth.login': 'Войти', 'auth.register': 'Регистрация', 'auth.sub': 'Избранное и профиль сохранятся на всех устройствах.',
      'auth.google': 'Продолжить с Google', 'auth.github': 'Продолжить с GitHub', 'auth.or': 'или по почте',
      'auth.name': 'Имя', 'auth.name.ph': 'Как к тебе обращаться', 'auth.email': 'Почта', 'auth.password': 'Пароль', 'auth.password.ph': 'минимум 6 символов',
      'auth.create': 'Создать аккаунт', 'auth.noacc': 'Нет аккаунта? ', 'auth.hasacc': 'Уже есть аккаунт? ', 'auth.toreg': 'Зарегистрироваться', 'auth.tologin': 'Войти',
      'auth.welcome': 'Добро пожаловать, {name}!', 'auth.back': 'С возвращением, {name}!', 'auth.out': 'Вы вышли из аккаунта',
    },
    kz: {
      'nav.homeapp': 'Басты бет', 'theme': 'Тақырып', 'palette': 'Барлығынан іздеу · Ctrl K', 'palette.ph': 'Грант немесе команда іздеу…', 'palette.nav': 'Бөлімдер', 'palette.grants': 'Гранттар', 'palette.none': 'Ештеңе табылмады', 'palette.theme': 'Тақырыпты ауыстыру', 'palette.lang': 'Тілді ауыстыру',
      'home.hi': 'Сәлем', 'home.hiName': 'Сәлем, {name}', 'home.sub': 'Бүгін ЖИ саған таңдағаны', 'home.subAnon': 'Профильді толтыр немесе кір — іріктеу жеке болады',
      'home.matches': 'Саған сай', 'home.active': 'Белсенді гранттар', 'home.favs': 'Таңдаулыда', 'home.profile': 'Профиль толтырылды',
      'home.tip': 'Бүгінгі кеңес', 'home.tip.profile': 'IELTS, GPA және бағытты толтыр — сонда сай келмейтінін алып тастап, нақты өз гранттарыңды көрсете аламын.', 'home.tip.profile.btn': 'Профильді толтыру',
      'home.tip.favorites': 'Бірнеше грантты таңдаулыға қос — дедлайнға 7, 3 және 1 күн қалғанда еске саламын.', 'home.tip.favorites.btn': 'Каталогты ашу',
      'home.tip.deadline': 'Таңдаулы гранттарыңның бірінің дедлайнына екі аптадан аз қалды. Құжат жинайтын кез.', 'home.tip.deadline.btn': 'Таңдаулыға',
      'home.tip.chat': 'ЖИ-менторға өтінімді қалай күшейтуді сұра: мотивациялық хат, ұсынымдар, портфолио.', 'home.tip.chat.btn': 'ЖИ-ден сұрау',
      'home.deadlines': 'Жақын дедлайндар', 'home.deadlinesFav': 'Таңдаулыдағы дедлайндар', 'home.forYou': 'Саған іріктелген', 'home.forYouAnon': 'Жаңа бағдарламалар', 'home.all': 'Бүкіл каталог',
      'home.scan': 'Қазір сканерлеу', 'home.scanIdle': 'Келесі сканерлеу кесте бойынша', 'why.field': 'бағыт бойынша', 'why.ielts_ok': 'IELTS сай', 'why.gpa_ok': 'GPA сай', 'why.open': 'қабылдау ашық',
      'card.days': 'күн', 'card.day1': 'күн', 'card.days2': 'күн', 'card.today': 'бүгін', 'card.tbd': 'нақтыланады', 'card.expired': 'өтті', 'card.apply': 'Өтінім беру', 'card.compare': 'Салыстыру', 'card.coverageLvl': 'жабу деңгейі',
      'cmp.title': 'Гранттарды салыстыру', 'cmp.bar': 'Салыстыру', 'cmp.clear': 'Тазалау', 'cmp.max': '3 гранттан артық салыстыруға болмайды', 'cmp.country': 'Ел', 'cmp.level': 'Деңгей', 'cmp.status': 'Мәртебе',
      'live.title': 'Жаңа ғана табылды', 'live.scan': 'Сканерлеп жатырмын', 'live.of': '/', 'live.sources': 'дереккөз', 'live.extract': 'ЖИ нәтижелерді талдап жатыр', 'live.check': 'Сілтемелерді тексеремін', 'live.last': 'Соңғы тексеру', 'live.new': 'жаңа',
      'nav.home': 'Басты бет', 'nav.catalog': 'Каталог', 'nav.search': 'Іздеу', 'nav.favorites': 'Таңдаулылар', 'nav.chat': 'ЖИ-кеңесші', 'nav.profile': 'Профиль', 'nav.admin': 'Әкімші',
      'pill.online': 'ЖИ онлайн 24/7', 'pill.ask': 'ЖИ-ден сұрау', 'login': 'Кіру', 'logout': 'Шығу',
      'catalog.step1': '1-қадам / 2: оқу аймағын таңда', 'catalog.step2': '2-қадам / 2: деңгейді таңда', 'catalog.results': 'Таңдауың бойынша өзекті бағдарламалар',
      'catalog.title': 'Қай жерде оқығың<br>келеді?', 'catalog.title2': 'Оқу деңгейі<br>қандай?', 'catalog.titleKz': 'Қазақстандағы гранттар', 'catalog.titleAbroad': 'Әлемдегі гранттар',
      'catalog.lead': 'Қазақстан немесе бүкіл әлем. ЖИ дереккөздерді күніне екі рет тексереді, мұнда тек қолданыстағы бағдарламалар.',
      'choice.kz': 'Қазақстан', 'choice.kz.desc': 'ҰБТ бойынша мемлекеттік гранттар, ректор гранттары, ЖОО шәкіртақылары',
      'choice.abroad': 'Шетелде', 'choice.abroad.desc': 'Халықаралық конкурстар мен әлем университеттерінің шәкіртақылары',
      'choice.bachelor': 'Бакалавриат', 'choice.bachelor.desc': 'Мектеп немесе колледжден кейінгі алғашқы жоғары білім',
      'choice.master': 'Магистратура', 'choice.master.desc': 'Екінші саты, әдетте 1–2 жыл',
      'choice.all': 'Барлығын көрсету', 'choice.all.desc': 'Аймақтың барлық деңгейлері мен бағдарламалары',
      'back.regions': '← Аймақтарға оралу', 'back.change': '← Өзгерту', 'loadmore': 'Тағы көрсету', 'total': 'Барлығы',
      'region.kz': 'Қазақстан', 'region.abroad': 'Шетелде', 'degree.bachelor': 'Бакалавриат', 'degree.master': 'Магистратура', 'degree.all': 'Барлық деңгей',
      'catalog.empty': 'Бұл санатта әзірге ештеңе жоқ. ЖИ келесі сканерлеуден кейін гранттарды қосады.',
      'scope.kz': 'Қазақстан', 'scope.abroad': 'Шетел', 'scope.all': 'Барлығы', 'catalog.titleAll': 'Барлық гранттар', 'degree.phd': 'PhD', 'degree.language': 'Тіл курстары',
      'filter.degree': 'Деңгей', 'filter.country': 'Ел', 'filter.funding': 'Қаржыландыру', 'filter.deadline': 'Өтінім қабылдау', 'filter.req': 'Талаптар', 'filter.reset': 'Тазарту',
      'funding.full': 'Толық грант', 'funding.partial': 'Ішінара грант', 'deadline.open': 'Қабылдау ашық', 'deadline.upcoming': 'Жақында ашылады', 'deadline.closed': 'Аяқталды', 'req.ent': 'ҰБТ', 'country.multi': 'Бірнеше ел', 'sort.new': 'Алдымен жаңалары', 'sort.deadline': 'Мерзімі бойынша', 'sort.funding': 'Жабуы бойынша',
      'search.eyebrow': 'Базадан іздеу', 'search.title': 'Грантты бір сөзбен<br>тап', 'search.lead': 'Атауы, елі, жабуы немесе талаптары. Мысалы: IT, Германия, магистратура, IELTS 6.0.',
      'search.placeholder': 'Кілт сөзді енгіз…', 'search.hint': 'Теруді баста — нәтиже бірден шығады.', 'search.found': 'Табылды', 'search.none': '«{q}» сұрауы бойынша ештеңе табылмады.',
      'quick': ['Германия', 'IT', 'Магистратура', 'Толық жабу', 'Қазақстан'],
      'fav.eyebrow': 'Сенің таңдауың', 'fav.title': 'Таңдаулылар', 'fav.lead': 'Сақталған гранттар және 7, 3 және 1 күн бұрынғы дедлайн еске салулары.',
      'fav.empty': 'Әзірге бос. Каталогта гранттарды жұлдызшамен белгіле, олар осында шығады.', 'fav.open': 'Каталогты ашу',
      'fav.added': 'Таңдаулыға қосылды ⭐', 'fav.removed': 'Таңдаулыдан алынды', 'fav.btn': 'Таңдаулыға',
      'chat.eyebrow': 'Жергілікті модель · шексіз', 'chat.title': 'ЖИ-менторға сұрақ қой', 'chat.lead': 'Түсу, гранттар, ҰБТ, IELTS, GPA, мотивациялық хаттар. Жауап профиліңді ескереді.',
      'chat.name': 'Түсу бойынша ЖИ-ментор', 'chat.status': 'Профиліңді ескере отырып жауап береді', 'chat.thinking': 'Ойланып жатырмын…', 'chat.typing': 'Жазып жатыр…',
      'chat.hello': 'Сәлем! Түсу, гранттар, ҰБТ, IELTS, GPA және мотивациялық хаттар бойынша көмектесемін. Кез келген нәрсені сұра — мысалы, «Еуропада IT магистратурасына қандай гранттар сай келеді?»',
      'chat.placeholder': 'Сұрағыңды жаз…', 'chat.empty': '⚠️ Бос жауап.',
      'suggestions': ['Шетелде қазір қандай гранттар ашық?', 'Мотивациялық хатты қалай жазамын?', 'Болашаққа не қажет?', 'ҰБТ бойынша Қазақстандағы гранттар'],
      'fb.up': 'Пайдалы', 'fb.down': 'Көмектеспеді', 'fb.thanks': 'Пікірің үшін рақмет! 🙌',
      'profile.eyebrow': 'Жекелендіру', 'profile.title': 'Өзің туралы<br>айт', 'profile.lead': 'ЖИ тек сенің деңгейіңе шынымен сай келетінді ұсынады. Кез келген өрісті бос қалдыруға болады.',
      'profile.b1': '<b>IELTS</b> — қол жетпейтін тіл шегі бар бағдарламаларды алып тастайды', 'profile.b2': '<b>GPA</b> — үлгеріміңе қарай гранттарды таңдайды', 'profile.b3': '<b>Бағыт</b> — мамандығың бойынша бағдарламаларға басымдық',
      'profile.field': 'Бағыт', 'profile.field.ph': 'Мысалы, Computer Science', 'profile.ielts.ph': 'Мысалы, 6.5', 'profile.gpa.ph': 'Мысалы, 3.7',
      'save': 'Сақтау', 'clear': 'Тазалау', 'profile.saved': 'Профиль сақталды. ЖИ оны кеңестерде ескереді.', 'profile.cleared': 'Профиль тазаланды',
      'admin.eyebrow': 'Тек әкімшіге', 'admin.title': 'Басқару панелі', 'admin.lead': 'Сканер, дереккөздер мониторингі, модель және статистика.',
      'card.coverage': 'Жабуы', 'card.requirements': 'Талаптар', 'card.deadline': 'Дедлайн', 'card.source': 'Дереккөз', 'card.site': 'Ресми сайт',
      'tag.open': 'қабылдау ашық', 'tag.upcoming': 'жақында ашылады', 'tag.today': 'бүгін', 'tag.days': 'күн',
      'rem.text': '«{name}» өтінімін тапсыруға қалды:', 'rem.lessday': 'бір күннен аз', 'rem.opened': 'Өтінім қабылдау ашылды: «{name}»', 'card.ongoing': 'жыл бойы', 'tag.from': 'басталуы',
      'bell.title': 'Ашылғанда хабарлау', 'bell.added': 'Қабылдау ашылғанда хабарлаймыз', 'bell.removed': 'Хабарлама өшірілді', 'rem.open': 'Ашу →',
      'foot.words': 'Университеттер &nbsp;&nbsp; конкурстар &nbsp;&nbsp; дедлайндар',
      'auth.eyebrow': 'GrantHub аккаунты', 'auth.login': 'Кіру', 'auth.register': 'Тіркелу', 'auth.sub': 'Таңдаулылар мен профиль барлық құрылғыда сақталады.',
      'auth.google': 'Google арқылы жалғастыру', 'auth.github': 'GitHub арқылы жалғастыру', 'auth.or': 'немесе пошта арқылы',
      'auth.name': 'Аты', 'auth.name.ph': 'Саған қалай жүгінейік', 'auth.email': 'Пошта', 'auth.password': 'Құпиясөз', 'auth.password.ph': 'кемінде 6 таңба',
      'auth.create': 'Аккаунт жасау', 'auth.noacc': 'Аккаунт жоқ па? ', 'auth.hasacc': 'Аккаунт бар ма? ', 'auth.toreg': 'Тіркелу', 'auth.tologin': 'Кіру',
      'auth.welcome': 'Қош келдің, {name}!', 'auth.back': 'Қайта оралуыңмен, {name}!', 'auth.out': 'Аккаунттан шықтың',
    },
    en: {
      'nav.homeapp': 'Home', 'theme': 'Theme', 'palette': 'Search everything · Ctrl K', 'palette.ph': 'Find a grant or a command…', 'palette.nav': 'Sections', 'palette.grants': 'Grants', 'palette.none': 'Nothing found', 'palette.theme': 'Toggle theme', 'palette.lang': 'Change language',
      'home.hi': 'Hi', 'home.hiName': 'Hi, {name}', 'home.sub': 'Here is what AI picked for you today', 'home.subAnon': 'Fill in your profile or sign in to make this personal',
      'home.matches': 'Match you', 'home.active': 'Active grants', 'home.favs': 'In favorites', 'home.profile': 'Profile complete',
      'home.tip': 'Tip for today', 'home.tip.profile': 'Fill in IELTS, GPA and your field — then I can drop what doesn’t fit and show your real options.', 'home.tip.profile.btn': 'Fill in profile',
      'home.tip.favorites': 'Add a few grants to favorites — I’ll start reminding you 7, 3 and 1 day before deadlines.', 'home.tip.favorites.btn': 'Open catalog',
      'home.tip.deadline': 'One of your favorite grants closes in less than two weeks. Time to gather documents.', 'home.tip.deadline.btn': 'To favorites',
      'home.tip.chat': 'Ask the AI mentor how to strengthen your application: motivation letter, references, portfolio.', 'home.tip.chat.btn': 'Ask AI',
      'home.deadlines': 'Upcoming deadlines', 'home.deadlinesFav': 'Deadlines in favorites', 'home.forYou': 'Picked for you', 'home.forYouAnon': 'Fresh programs', 'home.all': 'Full catalog',
      'home.scan': 'Scanning now', 'home.scanIdle': 'Next scan on schedule', 'why.field': 'by field', 'why.ielts_ok': 'IELTS fits', 'why.gpa_ok': 'GPA fits', 'why.open': 'open now',
      'card.days': 'days', 'card.day1': 'day', 'card.days2': 'days', 'card.today': 'today', 'card.tbd': 'TBA', 'card.expired': 'passed', 'card.apply': 'Apply', 'card.compare': 'Compare', 'card.coverageLvl': 'coverage level',
      'cmp.title': 'Compare grants', 'cmp.bar': 'Compare', 'cmp.clear': 'Clear', 'cmp.max': 'You can compare up to 3 grants', 'cmp.country': 'Country', 'cmp.level': 'Level', 'cmp.status': 'Status',
      'live.title': 'Just found', 'live.scan': 'Scanning', 'live.of': 'of', 'live.sources': 'sources', 'live.extract': 'AI is parsing results', 'live.check': 'Checking links', 'live.last': 'Last check', 'live.new': 'new',
      'nav.home': 'Home', 'nav.catalog': 'Catalog', 'nav.search': 'Search', 'nav.favorites': 'Favorites', 'nav.chat': 'AI advisor', 'nav.profile': 'Profile', 'nav.admin': 'Admin',
      'pill.online': 'AI online 24/7', 'pill.ask': 'Ask AI', 'login': 'Sign in', 'logout': 'Sign out',
      'catalog.step1': 'Step 1 of 2: choose where to study', 'catalog.step2': 'Step 2 of 2: choose the level', 'catalog.results': 'Current programs for your choice',
      'catalog.title': 'Where do you<br>want to study?', 'catalog.title2': 'Which degree<br>level?', 'catalog.titleKz': 'Grants in Kazakhstan', 'catalog.titleAbroad': 'Grants worldwide',
      'catalog.lead': 'Kazakhstan or the whole world. AI checks the sources twice a day — only active programs here.',
      'choice.kz': 'Kazakhstan', 'choice.kz.desc': 'State grants by UNT, rector grants, university scholarships',
      'choice.abroad': 'Abroad', 'choice.abroad.desc': 'International competitions and scholarships of world universities',
      'choice.bachelor': "Bachelor's", 'choice.bachelor.desc': 'First degree after school or college',
      'choice.master': "Master's", 'choice.master.desc': 'Second cycle, usually 1–2 years',
      'choice.all': 'Show all', 'choice.all.desc': 'All levels and programs in the region',
      'back.regions': '← Back to regions', 'back.change': '← Change', 'loadmore': 'Show more', 'total': 'Total',
      'region.kz': 'Kazakhstan', 'region.abroad': 'Abroad', 'degree.bachelor': "Bachelor's", 'degree.master': "Master's", 'degree.all': 'All levels',
      'catalog.empty': 'Nothing here yet. AI will add grants after the next scan.',
      'scope.kz': 'Kazakhstan', 'scope.abroad': 'Abroad', 'scope.all': 'All', 'catalog.titleAll': 'All grants', 'degree.phd': 'PhD', 'degree.language': 'Language courses',
      'filter.degree': 'Level', 'filter.country': 'Country', 'filter.funding': 'Funding', 'filter.deadline': 'Applications', 'filter.req': 'Requirements', 'filter.reset': 'Reset',
      'funding.full': 'Full grant', 'funding.partial': 'Partial grant', 'deadline.open': 'Open now', 'deadline.upcoming': 'Opening soon', 'deadline.closed': 'Closed', 'req.ent': 'UNT', 'country.multi': 'Several countries', 'sort.new': 'Newest first', 'sort.deadline': 'By deadline', 'sort.funding': 'By coverage',
      'search.eyebrow': 'Search the database', 'search.title': 'Find a grant<br>with one word', 'search.lead': 'Name, country, coverage or requirements. For example: IT, Germany, master, IELTS 6.0.',
      'search.placeholder': 'Type a keyword…', 'search.hint': 'Start typing — results appear instantly.', 'search.found': 'Found', 'search.none': 'Nothing found for “{q}”.',
      'quick': ['Germany', 'IT', "Master's", 'Fully funded', 'Kazakhstan'],
      'fav.eyebrow': 'Your shortlist', 'fav.title': 'Favorites', 'fav.lead': 'Saved grants and deadline reminders 7, 3 and 1 day before.',
      'fav.empty': 'Empty so far. Star grants in the catalog and they will show up here.', 'fav.open': 'Open catalog',
      'fav.added': 'Added to favorites ⭐', 'fav.removed': 'Removed from favorites', 'fav.btn': 'Add to favorites',
      'chat.eyebrow': 'Local model · no limits', 'chat.title': 'Ask the AI mentor', 'chat.lead': 'Admissions, grants, UNT, IELTS, GPA, motivation letters. Answers consider your profile.',
      'chat.name': 'AI admissions mentor', 'chat.status': 'Answers with your profile in mind', 'chat.thinking': 'Thinking…', 'chat.typing': 'Typing…',
      'chat.hello': 'Hi! I help with admissions, grants, UNT, IELTS, GPA and motivation letters. Ask anything — e.g. “which grants fit an IT master’s in Europe?”',
      'chat.placeholder': 'Type your question…', 'chat.empty': '⚠️ Empty answer.',
      'suggestions': ['Which grants abroad are open now?', 'How to write a motivation letter?', 'What is needed for Bolashak?', 'Grants in Kazakhstan by UNT'],
      'fb.up': 'Helpful', 'fb.down': 'Not helpful', 'fb.thanks': 'Thanks for the feedback! 🙌',
      'profile.eyebrow': 'Personalization', 'profile.title': 'Tell us<br>about you', 'profile.lead': 'AI will only suggest what really fits your level. Any field can be left empty.',
      'profile.b1': '<b>IELTS</b> — filters out programs with an unreachable language bar', 'profile.b2': '<b>GPA</b> — matches grants to your academic record', 'profile.b3': '<b>Field</b> — prioritizes programs in your specialty',
      'profile.field': 'Field of study', 'profile.field.ph': 'e.g. Computer Science', 'profile.ielts.ph': 'e.g. 6.5', 'profile.gpa.ph': 'e.g. 3.7',
      'save': 'Save', 'clear': 'Clear', 'profile.saved': 'Profile saved. AI will use it in advice.', 'profile.cleared': 'Profile cleared',
      'admin.eyebrow': 'Administrator only', 'admin.title': 'Control panel', 'admin.lead': 'Scanner, source monitoring, model and statistics.',
      'card.coverage': 'Coverage', 'card.requirements': 'Requirements', 'card.deadline': 'Deadline', 'card.source': 'Source', 'card.site': 'Official website',
      'tag.open': 'applications open', 'tag.upcoming': 'opening soon', 'tag.today': 'today', 'tag.days': 'days',
      'rem.text': 'Time left to apply for “{name}”:', 'rem.lessday': 'less than a day', 'rem.opened': 'Applications are now open: “{name}”', 'card.ongoing': 'year-round', 'tag.from': 'from',
      'bell.title': 'Notify me when it opens', 'bell.added': 'We will let you know when applications open', 'bell.removed': 'Notification turned off', 'rem.open': 'Open →',
      'foot.words': 'Universities &nbsp;&nbsp; competitions &nbsp;&nbsp; deadlines',
      'auth.eyebrow': 'GrantHub account', 'auth.login': 'Sign in', 'auth.register': 'Sign up', 'auth.sub': 'Favorites and profile stay with you on every device.',
      'auth.google': 'Continue with Google', 'auth.github': 'Continue with GitHub', 'auth.or': 'or with email',
      'auth.name': 'Name', 'auth.name.ph': 'What should we call you', 'auth.email': 'Email', 'auth.password': 'Password', 'auth.password.ph': 'at least 6 characters',
      'auth.create': 'Create account', 'auth.noacc': 'No account? ', 'auth.hasacc': 'Already have an account? ', 'auth.toreg': 'Sign up', 'auth.tologin': 'Sign in',
      'auth.welcome': 'Welcome, {name}!', 'auth.back': 'Welcome back, {name}!', 'auth.out': 'You signed out',
    },
  };

  /* ---------------- Лендинг (/) ---------------- */
  const LANDING = {
    ru: {
      brandBottom: 'Kazakhstan',
      nav: [['Каталог', '/app#catalog'], ['ИИ-консультант', '/app#chat'], ['Избранное', '/app#favorites'], ['Профиль', '/app#profile'], ['Контакты', '#contact'], ['Войти', '/app#auth']],
      concierge: 'ИИ онлайн 24/7', navCta: 'Спросить ИИ', eyebrow: 'ИИ ищет гранты, пока ты спишь',
      titleLine1: 'Гранты на учёбу', titleLine2: 'по всему миру',
      cards: [['150+', 'университетов'], ['70', 'международных конкурсов'], ['24/7', 'ИИ-мониторинг']],
      note: 'Для тех, кто не просто поступает, а выбирает лучшее.', cta: 'Найти свой грант',
      footWords: ['Университеты', 'конкурсы', 'дедлайны'], footBrand: 'GrantHub Kazakhstan',
      contact: { title: 'Свяжись с нами', text: 'Вопросы по грантам, партнёрство, идеи для проекта — пиши, отвечаем в течение дня.', telegram: 'Telegram-бот GrantHub', copy: 'Скопировать почту', copied: 'Почта скопирована', close: 'Закрыть', badge: 'Отвечаем в течение дня', meta: ['Казахстан', 'GrantHub Kazakhstan'] },
      stats: ['Активных программ', 'Приём открыт сейчас', 'Университетов под наблюдением', 'Международных конкурсов'], lastCheck: 'Последняя проверка', never: 'ещё не было', plan: 'план',
      sec1: ['Что умеет GrantHub', 'Один агент вместо<br>десятков вкладок'],
      feats: [['Живой каталог', 'Казахстан и зарубежье, бакалавриат и магистратура. Каждый грант привязан к источнику и статусу приёма.'], ['Персональный совет', 'Заполни IELTS, GPA и направление — ИИ будет рекомендовать то, что реально подходит под твой уровень.'], ['Напоминания', 'Сохраняй гранты в избранное — за 7, 3 и 1 день до дедлайна ты увидишь напоминание.'], ['Локальный ИИ', 'Работает без облачных лимитов и квот. Твои вопросы не уходят третьим лицам.']],
      sec2: ['Как это работает', 'Три шага до заявки'],
      steps: [['ИИ сканирует', 'Дважды в день проходит по 150+ университетам и 70 конкурсам, отбрасывает закрытые наборы и статьи-подборки.'], ['Ты выбираешь', 'Регион, уровень, ключевое слово. Сохраняй в избранное и спрашивай ИИ-ментора о деталях.'], ['Мы напоминаем', 'За 7, 3 и 1 день до дедлайна приходит напоминание, чтобы ты успел подать документы.']],
      final: ['Начни сегодня', 'Твой грант уже<br>где-то ждёт'],
    },
    kz: {
      brandBottom: 'Kazakhstan',
      nav: [['Каталог', '/app#catalog'], ['ЖИ-кеңесші', '/app#chat'], ['Таңдаулылар', '/app#favorites'], ['Профиль', '/app#profile'], ['Байланыс', '#contact'], ['Кіру', '/app#auth']],
      concierge: 'ЖИ онлайн 24/7', navCta: 'ЖИ-ден сұрау', eyebrow: 'Сен ұйықтап жатқанда ЖИ грант іздейді',
      titleLine1: 'Бүкіл әлем бойынша', titleLine2: 'оқу гранттары',
      cards: [['150+', 'университет'], ['70', 'халықаралық конкурс'], ['24/7', 'ЖИ-мониторинг']],
      note: 'Жай ғана түспей, ең жақсысын таңдайтындар үшін.', cta: 'Өз грантыңды тап',
      footWords: ['Университеттер', 'конкурстар', 'дедлайндар'], footBrand: 'GrantHub Kazakhstan',
      contact: { title: 'Бізбен байланыс', text: 'Гранттар бойынша сұрақтар, серіктестік, жоба идеялары — жаз, бір күн ішінде жауап береміз.', telegram: 'GrantHub Telegram-боты', copy: 'Поштаны көшіру', copied: 'Пошта көшірілді', close: 'Жабу', badge: 'Бір күн ішінде жауап береміз', meta: ['Қазақстан', 'GrantHub Kazakhstan'] },
      stats: ['Белсенді бағдарламалар', 'Қазір қабылдау ашық', 'Бақылаудағы университеттер', 'Халықаралық конкурстар'], lastCheck: 'Соңғы тексеру', never: 'әлі болған жоқ', plan: 'жоспар',
      sec1: ['GrantHub не істей алады', 'Ондаған қойындының орнына<br>бір агент'],
      feats: [['Тірі каталог', 'Қазақстан мен шетел, бакалавриат пен магистратура. Әр грант дереккөзге және қабылдау мәртебесіне байланған.'], ['Жеке кеңес', 'IELTS, GPA және бағытты толтыр — ЖИ деңгейіңе шынымен сай келетінді ұсынады.'], ['Еске салулар', 'Гранттарды таңдаулыға сақта — дедлайнға 7, 3 және 1 күн қалғанда еске салу көресің.'], ['Жергілікті ЖИ', 'Бұлттық шектеусіз жұмыс істейді. Сұрақтарың үшінші тарапқа кетпейді.']],
      sec2: ['Бұл қалай жұмыс істейді', 'Өтінімге дейін үш қадам'],
      steps: [['ЖИ сканерлейді', 'Күніне екі рет 150+ университет пен 70 конкурсты қарап, жабық қабылдаулар мен жинақ мақалаларды алып тастайды.'], ['Сен таңдайсың', 'Аймақ, деңгей, кілт сөз. Таңдаулыға сақта және ЖИ-ментордан егжей-тегжейін сұра.'], ['Біз еске саламыз', 'Құжат тапсырып үлгеруің үшін дедлайнға 7, 3 және 1 күн қалғанда еске салу келеді.']],
      final: ['Бүгін баста', 'Сенің грантың бір жерде<br>күтіп тұр'],
    },
    en: {
      brandBottom: 'Kazakhstan',
      nav: [['Catalog', '/app#catalog'], ['AI advisor', '/app#chat'], ['Favorites', '/app#favorites'], ['Profile', '/app#profile'], ['Contact', '#contact'], ['Sign in', '/app#auth']],
      concierge: 'AI online 24/7', navCta: 'Ask AI', eyebrow: 'AI hunts for grants while you sleep',
      titleLine1: 'Study grants', titleLine2: 'around the world',
      cards: [['150+', 'universities'], ['70', 'international competitions'], ['24/7', 'AI monitoring']],
      note: 'For those who don’t just apply — they choose the best.', cta: 'Find your grant',
      footWords: ['Universities', 'competitions', 'deadlines'], footBrand: 'GrantHub Kazakhstan',
      contact: { title: 'Get in touch', text: 'Questions about grants, partnership, ideas for the project — write to us, we reply within a day.', telegram: 'GrantHub Telegram bot', copy: 'Copy email', copied: 'Email copied', close: 'Close', badge: 'We reply within a day', meta: ['Kazakhstan', 'GrantHub Kazakhstan'] },
      stats: ['Active programs', 'Open for applications now', 'Universities monitored', 'International competitions'], lastCheck: 'Last check', never: 'not yet', plan: 'schedule',
      sec1: ['What GrantHub does', 'One agent instead of<br>dozens of tabs'],
      feats: [['Live catalog', 'Kazakhstan and abroad, bachelor’s and master’s. Every grant is tied to its source and application status.'], ['Personal advice', 'Fill in IELTS, GPA and your field — AI recommends only what truly fits your level.'], ['Reminders', 'Save grants to favorites — you’ll see a reminder 7, 3 and 1 day before the deadline.'], ['Local AI', 'No cloud limits or quotas. Your questions never leave for third parties.']],
      sec2: ['How it works', 'Three steps to apply'],
      steps: [['AI scans', 'Twice a day it goes through 150+ universities and 70 competitions, dropping closed calls and listicles.'], ['You choose', 'Region, level, keyword. Save to favorites and ask the AI mentor for details.'], ['We remind', '7, 3 and 1 day before the deadline a reminder arrives so you can submit in time.']],
      final: ['Start today', 'Your grant is already<br>waiting somewhere'],
    },
  };

  const detect = () => {
    try { const s = localStorage.getItem('gh_lang'); if (LANGS.includes(s)) return s; } catch { }
    const n = (navigator.language || '').toLowerCase();
    return n.startsWith('kk') ? 'kz' : n.startsWith('en') ? 'en' : 'ru';
  };
  const lang = detect();
  document.documentElement.lang = lang === 'kz' ? 'kk' : lang;
  const t = (key, vars) => {
    let v = (APP[lang] && APP[lang][key]) ?? APP.ru[key] ?? key;
    if (typeof v === 'string' && vars) Object.entries(vars).forEach(([k, val]) => { v = v.replace('{' + k + '}', val); });
    return v;
  };
  const setLang = (l) => { if (!LANGS.includes(l)) return; try { localStorage.setItem('gh_lang', l); } catch { } location.reload(); };
  /* Переключатель RU/KZ/EN — вставляется в контейнер */
  const switcher = (container) => {
    if (!container) return;
    const box = document.createElement('div'); box.className = 'lang';
    LANGS.forEach(l => { const b = document.createElement('button'); b.type = 'button'; b.textContent = NAMES[l]; b.className = l === lang ? 'is-on' : ''; b.setAttribute('aria-label', NAMES[l]); b.addEventListener('click', () => setLang(l)); box.appendChild(b); });
    container.appendChild(box);
  };
  window.I18N = { lang, t, setLang, switcher, LANDING: LANDING[lang], APP: APP[lang], LANGS, NAMES };
})();
