# docs/HARDWARE.md — оборудование и окружение

## Dev-стенд (актуален сейчас)

| Параметр | Значение |
|---|---|
| Устройство | ThinkPad (fake-cat-ThinkPad) |
| ОС | Ubuntu 26.04.1 LTS (Resolute Raccoon) |
| Ядро | 7.0.0-38-generic, x86_64 |
| CPU | 16 логических ядер |
| RAM | 61 GB (46 GB доступно на момент замера) |
| Диск | NVMe, 354 GB свободно |
| Сессия | **Wayland** (GNOME, XDG_CURRENT_DESKTOP=ubuntu:GNOME), XWayland `:0` доступен |
| Python | 3.14.4, pip 25.1.1 |
| Git | 2.53.0 |

Роль: разработка и ручное тестирование. **Ресурсы в разы больше целевых — не забывать про лимиты RPi.**

## Целевая платформа (малинка ещё не пришла)

| Параметр | Значение |
|---|---|
| Устройство | Raspberry Pi 4 Model B |
| RAM | 4 GB |
| Накопитель | microSD 64 GB |
| ОС | Raspberry Pi OS 64-bit Desktop |
| Архитектура | ARM64 / aarch64 |
| Дисплей | X11 / Xorg (+ touchscreen, audio — PHASE 10) |

Роль: финальные тесты производительности, ARM64-совместимости, autostart (PHASE 9–10).

## Правила совместимости

- Зависимости должны иметь wheels/пакеты и для x86-64, и для aarch64 (PySide6 pip-wheels; fallback — apt `python3-pyside6`).
- Замеры памяти/CPU в IDLE проводить с учётом 4 GB RAM: бюджет IDLE — цель < 150 MB RSS и низкая CPU (уточнить в PHASE 9).
- Не использовать x86-only бинарные зависимости.
- Проверять `XDG_SESSION_TYPE` — не предполагать X11.

## Замеры окружения (2026-10-08)

- `free -h`: всего 61G, доступно 46G.
- `nproc`: 16.
- Доступные утилиты: xrandr, wmctrl, xdpyinfo. Нет: Xvfb, xdotool, wmctrl-тесты не делались.
- Apt-кандидаты: `python3-pyside6` 6.10.2-6ubuntu1, `xvfb` 2:21.1.22 (установка — только с согласования).
