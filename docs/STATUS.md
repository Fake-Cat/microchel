# docs/STATUS.md — текущее состояние

**Дата последнего обновления:** 2026-10-10
**Текущий этап:** **PHASE 3 — Character Behavior — ЗАВЕРШЁН (коммит `069e46c`, шаг 11)**; PHASE 4 в процессе (Welcome/Greeting и нарезка шитов, Walk/Left добавлен, showcase играет по playback-спеке `clips.toml`, без коммита)

## Где мы находимся (для продолжения в новом сеансе)

1. PHASE 0 ✅, PHASE 1 ✅, PHASE 2 ✅, **PHASE 3 ✅ (коммит `069e46c`, шаги 1–11)** (план `docs/PHASE3_PLAN.md`): события/шина, states/config/fsm/controller, `config/behavior.toml`, генератор клипов, интеграция окно+main, флаги `--demo` / `--demo-events` / `--showcase`; тесты **167 passed, ruff чисто**.
2. **Сценарии P3-1…P3-7 — все подтверждены** (TESTING.md, 2026-10-08): автономность ≥10 мин, ходьба с разворотом у края (лог `разворот → -1`, позиция 5500→5563→5447), клик/драг глазами пользователя, 13+ событий `--demo-events` (интервалы 47–89 с), ночь (сон 14,4 мин из прогонного окна), RSS 104,5→105,5 МБ.
3. **Найден и исправлен баг:** `start_behavior` вызывал `load_behavior_config()` без пути → `path=None` → всегда дефолты, `config/behavior.toml` в приложении **не читался вообще** (тесты были зелёные, т.к. файл зеркалит дефолты). Фикс: `load_behavior_config(DEFAULT_CONFIG_PATH)` + регресс-тест `test_start_behavior_loads_config_file`.
4. **Ключевые решения PHASE 3:** FSM чистый (без Qt), случайность через seeded `random.Random`, ночь — через `hour`-колбэк; `night.sleep_weight = 300` (сон ~78% ночью, выбор пользователя); state-клипы `loop=True` + `restart=True` (правка плеера); реакция на клик REACTION с возвратом через `animation_finished`; разворот у края — `EdgeWalker` (чистый, юнит-тесты); `available` FSM = состояния с клипами (нет клипа → пропуск, FR-P3.1).
5. **UX-наблюдение:** системные события поверх сна (blink ~570 мс стоячей позой) выглядят как «резкое пробуждение на секунду» — сон FSM не прерывается. В TESTING.md «Известные ошибки» №3 → PHASE 4 (лежачий blink/пауза реакций в сне).
6. **Git:** коммиты `9302f3f`, `987c3a8`, `030d183`, `3051dac`, `bbe51e8`, **`069e46c` (PHASE 3, шаг 11, 2026-10-08)** — рабочее дерево чистое.
7. **Референс внешности/фонов** `docs/Микрочел_ питомец на Raspberry Pi.png` (собственный материал, подтверждено пользователем) — в репозитории с коммитом `069e46c`. Идея «фон-задник за персонажем для отдельных состояний/эмоций/задач» записана в ROADMAP (PHASE 4).
8. **PHASE 4 начат (2026-10-09, без коммита):** ассеты первой внешности — нарезка `docs/Милый спрайт-лист девочки-малинки.png` → `assets/characters/malinka/` (9 клипов, 45 кадров, скрипт `/tmp/slice_malinka.py`); smoke-плеер: все 6 состояний обеспечиваются клипами (Blink в шите отсутствует — предупреждение, не блокер). Замечания пользователя по `Happy/_003` (обрезанные искры) и `Thinking/_003` (участок чужого дыма) диагностированы и исправлены: граница 4/5-й колонки 759 → 720 (Happy) / 728 (Thinking) по реальным долинам alpha-профиля; попиксельная верификация пройдена, **ожидается визуальное подтверждение пользователем** (DEVELOPMENT_LOG 2026-10-09).
9. **Выбор персонажа кнопкой (2026-10-09):** подменю «Персонаж» в контекстном меню окна (пункты — каталоги `assets/characters/`, галочка у текущего); смена на лету без перезапуска — старый плеер останавливается, showcase перечитывает клипы на каждом тике; флаг `--showcase-interval SEC` (по умолчанию 10) задаёт частоту показа. Живой прогон `--showcase --showcase-interval 1.5`: test → malinka переключено кнопкой, показ 9 клипов малинки (лог `/tmp/showcase.log`); pytest 173 passed, ruff чист.
10. **Логические проблемы с анимациями разобраны (2026-10-10):** решение — встроить клип Welcome как idle-фоллбэк (п. 11): крутильное приветствие работает, поведение FSM не стартует без клипов состояний. Следующее — визуальная проверка и коммит по команде; далее PHASE 4: переработка шита/эмоции/костюмы, фон-задник, плавность движения, лежачий blink во сне (TESTING.md №1, №3).
11. **Внешность встроена (2026-10-10, без коммита, вариант 3 «Welcome = idle»):** клип `assets/characters/malinka/Welcome/` (25 кадров ×100 мс, единый bbox 100×192) подключён как idle-фоллбэк; дефолт окна — malinka, спрайт-фоллбэк — первый кадр Welcome. Удалены старые 8 клипов малинки, `assets/characters/test/`, `assets/frames/`, `scripts/make_test_{sprite,animations}.py`; генератор тестовых клипов → `tests/conftest.py` (временные каталоги). Без клипов состояний `start_behavior` → `None` (одна info-строка вместо 6 предупреждений) — **pytest 178 passed, ruff чисто, офсайнов-запуск подтверждён**. Приветствие станет разовым при появлении эмоций (решение пользователя).
12. **Отдельный generator PHASE 1 (2026-10-09, без коммита):** для канонического
    PNG подтверждены alpha/ореол, RGB flood-fill отклонён как финальная маска;
    создан валидируемый черновой `generator/assets/character/segmentation_manifest.json`
    на 8 крупных частей и валидатор SHA/координат. Из манифеста воспроизводимо
    построен и визуально проверен guide-overlay `1524 × 1536` с bbox, ID, z-index,
    pivot и отдельной легендой. Bbox восьми частей проверены на увеличенных
    вырезках: наушники расширены до `(347, 538)–(683, 742)`, локон сужен до
    `(355, 26)–(552, 229)`, его pivot перенесён в `(444, 208)`; скрытые суставные
    pivot остаются `draft`. Выбрана ручная master-маска с alpha/цветом как
    подсказкой и проверкой на трёх фонах. Принята строго бинарная master-маска;
    воспроизводимо экспортированы восемь visible-only RGBA-слоёв и контрольная
    композиция. Все `565077` foreground-пикселей покрыты ровно один раз, но
    внутреннее распределение по bbox остаётся предварительным и требует ручной
    визуальной проверки до восстановления скрытых областей и риггинга.
13. **Клипы нарезаны из готовых шитов (2026-10-10, PHASE 4):** 17 шитов из `/home/fake-cat/projects/animation/` → `assets/characters/malinka/` (якорь «низ + центр по X», единый холст 296×471, 1:1; границы ячеек — по alpha-«долинам»; скрипт `scripts/slice_sheets.py`). Верификация попиксельно: низ bbox = 470 у всех кадров — общий пол гарантирован. Манифест `assets/characters/malinka/clips.toml` (генерируется слайсером): loop-диапазоны 0-based включительно (ANGRY 4–10, COFFEE 1–9, SLEEP_WAKE 4–9 + suffix_on_exit, TYPING 1–10, WALK DIRECT 2–10 + mirror=left, WALK RIGHT 2–10, WALK BACK 6–10, SITTING HAPPILLY 3–11, DANCING 2–10, TALKING 0–11), once (ERROR_PANIC, HAPPY_SUCCESS, IDLE, THINKING, WELCOME, LIE DORMANT), repeat_fill_ms=4000 (ANGRY), motion walk/traverse, scale=1.0. **Рантайм спеку пока не использует** (плеер играет клипы один раз) — подключение loop-спеки и привязка к FSM следующий шаг. Дефекты шитов: Sit/Typing кадры 5/11 обрезаны краем шита; Walk/Back пустая ячейка (11 кадров, пропуск в нумерации).
14. **Welcome — приветственная анимация (2026-10-10, правка пользователя):** крутка Welcome/Normal (п. 11, 25 кадров из импорта frames) **удалена пользователем как ненужная** — **Welcome/Greeting (шит WELCOME, 12 кадров ×150 мс) является приветственным клипом**. Спрайт-фоллбэк `window.py` переключён на `Welcome/Greeting/1/_000_150.png`; idle-фоллбэк — `Idle/Normal`.
15. **Ходьба влево — Walk/Left (2026-10-10, правка пользователя):** клип создан как **зеркальное отражение Walk/Right** — в слайсере механизм `mirror_from` (план «(mirror WALK RIGHT)»; `QTransform().scale(-1, 1)` + FastTransformation — точное пиксельное отражение, deprecated `QImage.mirrored` не используется). Попиксельно подтверждено: каждый кадр Walk/Left = отражение кадра Walk/Right, пол bbox = 470 сохранён. Итого **18 клипов, 213 кадров**. Тесты приведены под новый состав ассетов (`test_setup_animation_default_is_malinka`; welcome-only сценарий — на временном каталоге `tmp_path`): **pytest 178 passed, ruff чисто**.
16. **Showcase играет по playback-спеке (2026-10-10, PHASE 4):** `--showcase` больше не крутит клипы «в лоб», а строит план показа из `clips.toml` — те же правила, что заложены для рантайма: once → один проход; loop-сегмент [a, b] крутится по кругу весь слот; `repeat_fill_ms` → случайное число повторов ~ цель (не дольше слота); `prefix_once`/`suffix_on_exit`; `mirror="left"` → кадры флипаются в плеере (`AnimationRequest.mirror`, `is_mirrored`, точный пиксель); `motion=walk` → шаги `EdgeWalker` во время клипа (разворот у края, направление по имени/зеркалу), `motion=traverse` → шаги без разворота (допущение до утверждения FSM-спеки). Код: новый `animation/spec.py` (`load_clip_specs`, `plan_frames`), окно (`clip_specs`, `clip_durations`, `play_clip(frame_indices, mirror)` — производный клип `Имя#plan`), `EdgeWalker(step_px, direction=1)`. **Визуально подтверждено пользователем:** нарезка глазами в порядке; размеры персонажа между клипами местами сильно различаются — второстепенно (рантайм-`scale` в спеке пока 1.0, подбор — отдельным шагом). **pytest 210 passed, ruff чисто**; live offscreen-прогон показал корректные планы у всех 18 клипов (mirror/motion в логе, без warning).
17. **Нарезка DANCING исправлена — нарезка по связным компонентам (2026-10-10, PHASE 4):** рядовая нарезка по сетке резала пересечения ног (до y≈477 при срезе строки на y=470) и оставляла шум от смещённых колонок. `scripts/slice_sheets.py` переписан: компоненты всего шита (BFS по alpha, `MIN_COMPONENT_PX = 10`) назначаются ячейкам по центру, кадр кропится по объединённому bbox (без масштабирования, якорь низ+центр, канва 296×471); фоллбэк на alpha-bbox ячейки + warning, если компонентов нет (Walk/Back ячейка 6 пуста — 11 кадров). Во всех 17 шитах ровно cols×rows компонент. Регенерация: **213 кадров, все 17 клипов OK**; попиксельная верификация DANCING — 12/12 кадров OK; визуально кадры чистые. Showcase запущен (`--pet-scale 0.65 --speed 1.0 --showcase-interval 1.0`, лог `/tmp/showcase_dance.log`) — все 17 анимаций играют без ошибок, **ожидается вердикт пользователя**. **pytest 226 passed, ruff чисто**.
18. **Персонаж «стал микро» — фикс нарезки + переходный клип MOVED CLIP (2026-10-10):** причина размера — union-bbox-логика в `slice_sheets.py` сжимала весь шит (1774×887) в холст 296×471 → `scale ≈ 0.17` во всех 17 клипах (спрайт 69 px), коэффициент уходил и в `clips.toml`. Исправлено: каждый кадр снова кроется 1:1 с якорем «низ + центр по X» (низ=470, спрайт h≈250–460), `scale` из манифеста исчез; узкий случай «кадр больше холста» — масштаб до влезания с warning. Добавлен клип **`Move/Transition`** (шит `MOVED CLIP`, 12 кадров, `once`) и `AnimationPlayer.set_transition()`: **каждая смена анимации начинается с перехода**, цель запоминается и стартует после него; первый старт и рестарт того же клипа — без перехода; переход **не эмитит `animation_finished`** (иначе controller принял бы его за конец реакции). Wiring: `window.setup_animation` → `player.set_transition(clips["Move/Transition"])`. Живая проверка offscreen: `Idle → Move/Transition → Happy/Success` ✓. **pytest 229 passed (+3 теста TestTransition), ruff чисто**; showcase 18 анимаций играет (лог `/tmp/showcase_fix.log`).

## Ключевые решения / где что лежит

- Состояния/маппинг: `character/states.py` (`STATE_CLIP_PREFIX`, `STATE_PRIORITY`, `TRANSIENT_STATES`).
- Конфиг: `config/behavior.toml` + `character/config.py::load_behavior_config` (битые значения → дефолт + лог); **путь передаёт `start_behavior`** (`DEFAULT_CONFIG_PATH`) — вызов без пути возвращает только дефолты (баг, исправлен 2026-10-08).
- FSM: `character/fsm.py` (`BehaviorFSM`, `is_night`); выбор — `rng.choices` по весам, ночью вес SLEEP ×(ночной бонус).
- Контроллер: `character/controller.py` (`CharacterController`, `EdgeWalker`); 2 QTimer (состояние + шаг ходьбы).
- Шина/события: `common/event_bus.py`, `common/events.py`; клик/драг порог 5 px — `desktop/window.py` (`DRAG_THRESHOLD_PX`).
- Сборка: `desktop/main.py::start_behavior/start_demo_events/states_with_clips`.
- Плеер (правки PHASE 3): `restart=True` — немедленная замена клипа; `_start_next` не перетирает клип, запущенный слушателем `animation_finished`.
- Тестовые клипы: генератор в `tests/conftest.py` (фикстуры `characters_root`/`clips_root`, временные каталоги); удалены `scripts/make_test_animations.py`, `scripts/make_test_sprite.py`, `assets/characters/test/` (2026-10-10).

## Последняя завершённая задача

Шаг 11 PHASE 3 — **коммит `069e46c`** (2026-10-08): 67 файлов, код шагов 1–10 + фикс загрузки `config/behavior.toml` + тесты **167 passed / ruff чисто** + документация + референс внешности. **PHASE 3 закрыт.**

## Что реализовано (PHASE 3, доп. к PHASE 0–2)

- `src/microchel/common/events.py`, `src/microchel/common/event_bus.py` — типы событий и синхронная шина.
- `src/microchel/character/` — `states.py`, `config.py`, `fsm.py`, `controller.py`; `config/behavior.toml`.
- `desktop/window.py` — клик/драг → `UserEvent` в шину (порог 5 px), `move_by(dx)` для ходьбы.
- `desktop/main.py` — сборка controller, флаги `--demo` (взаимоисключен с FSM) и `--demo-events` (45–90 с).
- Тесты: `tests/unit/test_{events,states,behavior_config,fsm,controller}.py`, `tests/integration/test_{character_controller,start_behavior,demo_events}.py` + расширены `test_player/test_window/test_main`.

## Что работает / что проверено

| Проверка | Результат |
|---|---|
| `pytest` | **226 passed** (2026-10-10; было 178 до showcase-спеки) |
| `ruff check .` | **All checks passed** |
| Генерация ассетов | тестовые клипы — `tests/conftest.py` (временные каталоги); malinka — **18 клипов, 213 кадров** (17 нарезанных шитов + Walk/Left — зеркало Walk/Right; крутильное Welcome/Normal удалено пользователем — приветственный клип Welcome/Greeting; idle-фоллбэк Idle/Normal; playback-спека `clips.toml` подключена к showcase — к FSM следующий шаг) |
| `--showcase` по спеке, offscreen (2026-10-10) | планы всех 18 клипов корректны (once/loop/segment/mirror/motion в логе), warning и error нет; визуально глазами — по команде пользователя |
| Smoke offscreen 6 с (2026-10-10) | старт без ошибок, 1 клип Welcome как idle, одна info-строка о клипах состояний, поведение не стартует |
| Smoke offscreen 90 с | переходы `idle → walk → idle` в логе, клипы Idle→Walk→Idle, 0 ошибок |
| Ручные сценарии P3-1…P3-7 | **все OK 2026-10-08** (TESTING.md: ≥10 мин, разворот у края, RSS, ночь, события) |
| Загрузка `behavior.toml` | фикс 2026-10-08: `start_behavior` → `load_behavior_config(DEFAULT_CONFIG_PATH)`; до фикса файл не читался в приложении |
| `--demo-events` живой | 13+ событий, интервалы 47–89 с (в границах 45–90) |

## Что сломано / что не проверено

- **Визуальная верификация скриншотами невозможна** на dev-стенде: grim/scrot отсутствуют, ffmpeg x11grab под Wayland даёт чёрный кадр — проверка глазами пользователя (зафиксировано в TESTING.md).
- Замечание о плавности движения → PHASE 4; «blink поверх сна» (стоячая поза выглядит как резкое пробуждение) → PHASE 4 (TESTING.md, Известные ошибки №3).
- Ubuntu X11 и RPi — не проверялись (нет сред).

## Известные ограничения и риски

1–4 — как в PHASE 2 (Wayland/xcb, RPi, MIT, лицензии VPet) + замечание о плавности движения → PHASE 4.
5. **Приоритет REACTION vs событие во время клика:** `SystemEvent` во время играющей реакции уходит в no-op (blink уже играет) — визуально корректно, задокументировано в `controller._on_system_event`.

## Следующее конкретное действие

**Ближайшее (2026-10-10):** вердикт пользователя по showcase после фикса нарезки DANCING (п. 17; показ запущен: `--pet-scale 0.65 --speed 1.0 --showcase-interval 1.0` — все 17 анимаций по очереди, следить за DANCE: пересечения ног целы, без шума между ног, общий пол). Если ОК — коммит ассетов, кода и документов по команде пользователя. Затем по команде: привязка playback-спеки `assets/characters/malinka/clips.toml` к FSM (состояния, движение walk/traverse по-настоящему, рантайм-`scale` — подбор размеров персонажа визуально). Далее **PHASE 4 — Character Customization**: переработка шита/повышение качества кадров, эмоции/костюмы (с возвратом разового приветствия и реакций), фон-задник (ROADMAP PHASE 4), плавность движения и лежачий blink во сне (TESTING.md №1, №3).

## Команды для запуска и тестирования

```bash
cd /home/fake-cat/projects/microchel
source .venv/bin/activate
pytest                                  # 178 passed
ruff check .                            # чисто
python -m microchel.desktop.main        # автономное поведение (под Wayland сам выберет xcb)
python -m microchel.desktop.main --demo # PHASE 2 демо (FSM отключён)
python -m microchel.desktop.main --demo-events  # + синтетические события 45–90 с
python -m microchel.desktop.main --showcase     # все клипы по 10 с подряд (ручной показ)
```

## Блокирующие проблемы

Нет.
