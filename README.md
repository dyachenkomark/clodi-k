# cloDICK

Лёгкий десктоп-компаньон для Windows с управлением через Telegram.
Пиксельный персонаж живёт над панелью задач и каждый день напоминает про спорт, учёбу и язык. Первый персонаж — енот, своих можно добавлять: [docs/CHARACTERS.md](docs/CHARACTERS.md).

![Енот на рабочем столе](docs/screenshot.png)

Статус: этап 1 — енот на рабочем столе. Роадмап и стек — в [docs/ROADMAP.md](docs/ROADMAP.md).

## Что умеет сейчас

- Персонаж сидит над панелью задач, моргает, иногда засыпает или уходит погулять вдоль края экрана. Сменить его можно в меню «Персонаж». Енота можно перетащить мышью, место запоминается.
- Клик по еноту открывает чек-лист дня. Галочка — задача сделана.
- Напоминания по расписанию: енот машет лапой и говорит, что осталось.
- Загрузка оперативной памяти видна в чек-листе и в подсказке значка в трее.
- Меню по правому клику и в трее: чек-лист, показать или спрятать енота, прогулки, напоминания, выход.

## Запуск

Нужны [uv](https://docs.astral.sh/uv/) и Git.

```
git clone https://github.com/dyachenkomark/clodi-k.git
cd clodi-k
git checkout claude/jolly-bell-t6afa7
uv sync
uv run clodick-gui        # енот без консольного окна
```

Консольные команды:

```
uv run clodick status
uv run clodick done sport
uv run clodick undo sport
```

## Оформление

Четыре темы, выбираются в `config.toml`: `[desktop] theme = "..."`. По умолчанию `claude` — «Терракота».

![Темы оформления](docs/themes.png)

| Тема | Как выглядит |
|---|---|
| `classic` | Серый енот, тёмный чек-лист. |
| `claude` | Кремовая бумага, терракотовые акценты, заголовки с засечками. |
| `claude_orange` | Рыжий енот в терракоте, строгий чек-лист. |
| `claude_night` | Тёмная тема с терракотовыми акцентами. |

Пересобрать картинку с темами: `uv run python tools/theme_gallery.py docs/themes.png`.

## Настройки

Данные лежат в `%LOCALAPPDATA%\cloDICK` на Windows и в `~/.local/share/clodick` на других ОС.
Там же `config.toml`: направления, время напоминаний, начало дня, размер енота, прогулки, тема.
Изменения применяются после перезапуска.

## Разработка

```
uv run pytest           # тесты, окно проверяется без экрана
uv run ruff check       # линтер
uv run ruff format      # форматирование
uv run python tools/screenshot.py scene.png   # скриншот сцены без рабочего стола
```

Домик — текстовая карта пикселей в `src/clodick/desktop/art.py`. Персонажи — пакеты в `src/clodick/assets/characters`, формат описан в `docs/CHARACTERS.md`.
Чтобы не трогать настоящие данные при разработке, задайте другой путь:

```
set CLODICK_HOME=.clodick-dev        # Windows cmd
export CLODICK_HOME=.clodick-dev     # bash
```
