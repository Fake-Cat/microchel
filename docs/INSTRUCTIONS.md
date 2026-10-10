# docs/INSTRUCTIONS.md — рабочая инструкция

Запуск приложения, нарезка картинок (шитов), проверки. Все команды — из корня
проекта `/home/fake-cat/projects/microchel`.

## 1. Одноразовая подготовка окружения

```bash
cd /home/fake-cat/projects/microchel
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 2. Запуск приложения

```bash
# обычный режим (автономный пет, FSM + агент, Wayland определяется сам)
python -m microchel.desktop.main

# демо: случайное переключение анимаций каждые 4 с
python -m microchel.desktop.main --demo

# демо + синтетические системные события каждые 45–90 с
python -m microchel.desktop.main --demo-events

# ручной показ всех анимаций по очереди (полный цикл каждой, idle пропускается)
python -m microchel.desktop.main --showcase

# только клипы, имя которых содержит подстроку
python -m microchel.desktop.main --showcase dance
python -m microchel.desktop.main --showcase walk
python -m microchel.desktop.main --showcase typing

# полезные опции
python -m microchel.desktop.main --showcase-interval 2.0   # пауза между анимациями, с
python -m microchel.desktop.main --speed 0.5               # медленнее в 2 раза
python -m microchel.desktop.main --pet-scale 1.0           # натуральный размер (по умолчанию 0.65)
python -m microchel.desktop.main --log-level DEBUG         # подробный лог
```

## 3. Генерация картинок (нарезка шитов → кадры)

**Источник** — шиты с прозрачным фоном: `/home/fake-cat/projects/animation/<ИМЯ_ШИТА>/sheet.png`
(сетка кадров 6×2 или 5×2, контент может расходиться с равномерной сеткой).

```bash
# нарезать все клипы (каталог шитов по умолчанию: /home/fake-cat/projects/animation)
python scripts/slice_sheets.py

# указать свой каталог с шитами
python scripts/slice_sheets.py /путь/к/каталогу/шитов
```

**Результат:**

- кадры: `assets/characters/malinka/<Анимация>/<Состояние>/1/_NNN_DDD.png`
  (сплошная нумерация, длительность кадра в имени);
- манифест: `assets/characters/malinka/clips.toml` (`frames`, `loop`, `once`,
  `motion`, авто-`scale` и т.д.) — **генерируется целиком, вручную не править**.

Скрипт идемпотентен (старые кадры каталога стираются), предупреждения печатаются
в консоль (например, «кадр пропущен — остатки»), при отсутствии ошибок exit-код 0.

**Нарезка — строго по контуру:** bbox кадра = полный объединённый bbox его
компонентов (кламп по ячейке отсутствует), 1:1 без масштабирования; канва клипа
динамическая (max размеры кадров клипа, якорь «низ + центр»). Габариты картинок
могут быть любыми — ничего не режется и не сжимается.

**Как добавить новый клип:**

1. Положить шит: `/home/fake-cat/projects/animation/МОЙ_ШИТ/sheet.png`.
2. Добавить `ClipPlan` в список `PLANS` в `scripts/slice_sheets.py`:

   ```python
   ClipPlan("МОЙ_ШИТ", "Anim", "State", 150, loop=(2, 10)),
   #             имя шита   анимация  состояние  мс/кадр  повторяемый сегмент (опц.)
   ```

   Для зеркального клипа без своего шита: `mirror_from="Anim/State"` (наследует
   `scale` источника). Параметры спеки: `once`, `loop`, `prefix_once`,
   `suffix_on_exit`, `repeat_fill_ms`, `mirror`, `motion`, `scale`, `notes`.
3. Перегенерить: `python scripts/slice_sheets.py`.
4. Посмотреть результат: `python -m microchel.desktop.main --showcase anim`.

## 4. Проверки

```bash
pytest -q        # 244 passed
ruff check .     # чисто
```

GUI-сценарии — вручную по `docs/TESTING.md`.

## 5. Верификация нарезки «без обрезки» (попиксельно)

Независимый скрипт: каждый пиксель компонента из шита обязан присутствовать в
PNG со сдвигом якоря без изменений (нет обрезки, нет масштаба) —
**212 кадров, 0 нарушений**.

```bash
python /tmp/verify_no_cut.py
```

> Скрипт живёт в `/tmp` (не в репозитории). Если удалится — воссоздать по
> описанию выше или взять из истории сессии 2026-10-10.

## 6. Где что лежит

| Что | Где |
| --- | --- |
| Код приложения | `src/microchel/` |
| Слайсер шитов | `scripts/slice_sheets.py` |
| Нарезанные кадры | `assets/characters/<персонаж>/<Анимация>/<Состояние>/1/` |
| Playback-спека клипов | `assets/characters/malinka/clips.toml` (генерируется) |
| Исходные шиты | `/home/fake-cat/projects/animation/` |
| Статус/журнал | `docs/STATUS.md`, `docs/DEVELOPMENT_LOG.md` |
| Ручное тестирование | `docs/TESTING.md` |
