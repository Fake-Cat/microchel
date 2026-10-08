# Microchel / Микрочел

Анимированный Desktop Pet для Linux с автономным ИИ-агентом. Вдохновлён [VPet-Simulator](https://github.com/LorisYounger/VPet), но реализован самостоятельно на Python + PySide6.

Микрочел — маленькая chibi-аниме девочка-сисадмин, которая живёт на рабочем столе: ходит, спит, пьёт кофе, реагирует на пользователя, выполняет поручения на естественном языке и мониторит систему.

## Статус

**PHASE 1 — Minimal Desktop Pet (выполняется).** Есть работающее прозрачное окно с перетаскиванием: `python -m microchel.desktop.main`. Актуальное состояние: [docs/STATUS.md](docs/STATUS.md).

## Платформы

| | Разработка / тесты | Целевая |
|---|---|---|
| Устройство | ThinkPad x86-64 | Raspberry Pi 4 Model B |
| ОС | Ubuntu 26.04 LTS | Raspberry Pi OS 64-bit |
| Ресурсы | 16 CPU / 61 GB RAM | 4 CPU / 4 GB RAM |
| Дисплей | Wayland (XWayland доступен) | X11 |

## Структура

```
src/microchel/   — исходный код (desktop, animation, character, agent, tools, voice, monitoring, memory, common)
assets/          — графика и звуки персонажа
config/          — конфигурация приложения
docs/            — обязательная документация (см. docs/STATUS.md как точку входа)
tests/           — unit/ и integration/ тесты
scripts/, packaging/ — вспомогательные скрипты и упаковка
```

## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest                                  # тесты
python -m microchel.desktop.main        # запустить питомца
```

Под Wayland-сессией приложение само выбирает XWayland (`QT_QPA_PLATFORM=xcb`) — иначе перетаскивание невозможно (ADR-002). Для xcb нужен системный пакет `libxcb-cursor0`: `sudo apt-get install libxcb-cursor0`.

## Документация

Точка входа — [docs/STATUS.md](docs/STATUS.md). Далее: [docs/ROADMAP.md](docs/ROADMAP.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [AGENTS.md](AGENTS.md).

## Лицензии

Код собственного проекта — **MIT** (см. [LICENSE](LICENSE), выбрано 2026-10-08). Код VPet — Apache-2.0; анимации VPet — отдельные условия (см. [docs/RESEARCH_VPET.md](docs/RESEARCH_VPET.md)).
