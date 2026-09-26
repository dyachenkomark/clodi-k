# cloDICK

Лёгкий десктоп-компаньон для Windows с управлением через Telegram.
Пиксельный енот с домиком каждый день напоминает про спорт, учёбу и язык.

Статус: этап 0 готов, дальше окно с енотом. Статистика по дням уходит в Google Таблицу (этап 3). Роадмап и стек — в [docs/ROADMAP.md](docs/ROADMAP.md).

## Разработка

Нужен [uv](https://docs.astral.sh/uv/).

```
uv sync                 # поставить зависимости
uv run clodick          # статус дня
uv run clodick done sport
uv run clodick undo sport
uv run pytest           # тесты
uv run ruff check       # линтер
uv run ruff format      # форматирование
```

Данные лежат в `%LOCALAPPDATA%\cloDICK` на Windows и в `~/.local/share/clodick` на других ОС.
Там же `config.toml` с направлениями, временем напоминаний и началом дня.
Чтобы не трогать настоящие данные при разработке, задайте другой путь:

```
set CLODICK_HOME=.clodick-dev        # Windows cmd
export CLODICK_HOME=.clodick-dev     # bash
```
