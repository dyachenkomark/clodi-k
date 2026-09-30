"""Логика дня: какой сейчас день, что отмечено, отметить, снять, задачи со сроками."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta

from clodick.config import Config
from clodick.core import quickadd
from clodick.core.models import (
    Category,
    CategoryStatus,
    DayStatus,
    Note,
    Task,
    Topic,
    task_id,
)
from clodick.storage.repository import CompletionRepository, new_uid

Clock = Callable[[], datetime]

# На сколько дней вперёд показывать задачи в разделе «Скоро».
SOON_DAYS = 7
# Цвета новых тем по кругу: различимы и на тёмном, и на светлом чек-листе.
TOPIC_COLORS = ("#e8792b", "#4a90d9", "#9b6bd6", "#2fa37a", "#d9557a", "#c9a227", "#3fb0c4")
# Тема с таким именем сразу ежедневная.
DAILY_NAMES = {"daily", "дэйли", "дейли", "ежедневно", "ежедневное", "каждый день", "привычки"}


def logical_day(moment: datetime, day_start_hour: int) -> date:
    """День, к которому относится момент. До day_start_hour считается вчерашний день."""
    return (moment - timedelta(hours=day_start_hour)).date()


def _category(task: Task) -> Category:
    return Category(
        key=task.key,
        title=task.title,
        daily=task.daily,
        custom=True,
        project=task.project,
        due=task.due,
        time=task.time,
    )


class Tracker:
    def __init__(
        self, config: Config, repo: CompletionRepository, clock: Clock = datetime.now
    ) -> None:
        self._config = config
        self._repo = repo
        self._clock = clock
        repo.fill_titles({cat.key: cat.title for cat in config.categories})
        self._seed_topics()

    def today(self) -> date:
        return logical_day(self._clock(), self._config.day_start_hour)

    def status(self, day: date | None = None) -> DayStatus:
        day = day or self.today()
        done = self._repo.completions_for(day)
        notes: dict[str, list[Note]] = {}
        for note in self._repo.notes_between(day, day):
            notes.setdefault(note.key, []).append(note)
        today, soon, tasks = self._split(day)

        def item(cat: Category) -> CategoryStatus:
            task = tasks.get(cat.key)
            if task is not None and not task.daily:
                # Разовая задача закрывается один раз: правда лежит в ней самой.
                is_done, at = task.done, task.done_at
            else:
                is_done, at = cat.key in done, done.get(cat.key)
            return CategoryStatus(cat, is_done, at, tuple(notes.get(cat.key, ())))

        return DayStatus(
            day=day, items=tuple(item(c) for c in today), upcoming=tuple(item(c) for c in soon)
        )

    def mark_done(self, key: str, source: str = "cli") -> bool:
        """Отмечает пункт выполненным. Возвращает False, если уже было отмечено."""
        cat, task = self._find(key)
        now = self._clock()
        if task is not None and not task.daily:
            if task.done:
                return False
            self._repo.save_task(replace(task, done=True, done_at=now))
            self._repo.add(key, self.today(), now, source, cat.title)
            return True
        return self._repo.add(key, self.today(), now, source, cat.title)

    def unmark(self, key: str) -> bool:
        """Снимает отметку. Возвращает False, если отметки не было."""
        _, task = self._find(key)
        if task is not None and not task.daily:
            if not task.done:
                return False
            self._repo.save_task(replace(task, done=False, done_at=None))
            self._repo.remove(key, self._day_of(task.done_at) if task.done_at else self.today())
            return True
        return self._repo.remove(key, self.today())

    # --- задачи ---

    def add_task(
        self,
        title: str,
        daily: bool = False,
        *,
        project: str = "",
        due: date | None = None,
        time: str = "",
    ) -> Task:
        """Своя задача. Разовая видна, пока не закрыта, и ещё до конца дня закрытия."""
        title = " ".join(title.split())
        if not title:
            raise ValueError("Task title is empty")
        task = Task(
            id=new_uid(),
            title=title,
            daily=daily,
            project=project,
            due=due,
            time=time,
            created_at=self._clock().replace(microsecond=0),
        )
        return self._repo.save_task(task)

    def add_from_text(self, text: str, daily: bool = False, topic: str = "") -> Task:
        """Задача из короткой записи: «мага: отчёт до пт в 15:00».

        topic — открытая вкладка чек-листа: тема по умолчанию, если в записи её нет.
        """
        parsed = quickadd.parse(text, self.today(), self.projects())
        project = parsed.project or topic
        found = self.topic(project)
        return self.add_task(
            parsed.title,
            daily or parsed.daily or (found is not None and found.daily),
            project=found.name if found else project,
            due=parsed.due,
            time=parsed.time,
        )

    def move_task(self, key: str, topic: str) -> Task:
        """Перенести задачу в другую тему. Пустая тема — без темы."""
        _, task = self._find(key)
        if task is None:
            raise KeyError(f"«{key}» is not a task")
        return self._repo.save_task(replace(task, project=topic))

    # --- темы ---

    def topics(self) -> list[Topic]:
        """Темы по порядку. Проект задачи без своей темы тоже показывается темой."""
        seen: set[str] = set()
        out: list[Topic] = []
        for topic in self._repo.topics():
            if topic.name.casefold() not in seen:
                seen.add(topic.name.casefold())
                out.append(topic)
        for task in self._repo.tasks():
            name = task.project.strip()
            if name and name.casefold() not in seen:
                seen.add(name.casefold())
                out.append(Topic("", name, color=self._color(len(out))))
        return out

    def topic(self, name: str) -> Topic | None:
        wanted = name.strip().casefold()
        if not wanted:
            return None
        return next((t for t in self.topics() if t.name.casefold() == wanted), None)

    def projects(self) -> dict[str, tuple[str, ...]]:
        """Темы и их короткие имена для быстрой записи: из приложения и из config.toml."""
        found = {name: tuple(aliases) for name, aliases in self._config.projects.items()}
        for topic in self.topics():
            key = next((n for n in found if n.casefold() == topic.name.casefold()), topic.name)
            found[key] = tuple(dict.fromkeys((*found.get(key, ()), *topic.aliases)))
        return found

    def add_topic(self, name: str, daily: bool | None = None) -> Topic:
        name = " ".join(name.split())
        if not name:
            raise ValueError("Topic name is empty")
        existing = self.topic(name)
        if existing is not None and existing.id:
            return existing
        count = len(self._repo.topics())
        if daily is None:
            daily = name.casefold() in DAILY_NAMES
        topic = Topic(new_uid(), name, (name.casefold(),), self._color(count), daily, count)
        return self._repo.save_topic(topic)

    def update_topic(self, current: str, /, **changes) -> Topic:
        """Поменять тему current: name (с переносом задач), color, daily."""
        topic = self.topic(current)
        if topic is None:
            raise KeyError(f"Unknown topic «{current}»")
        if not topic.id:  # тема из задач, ещё не сохранённая
            topic = self.add_topic(topic.name)
        new_name = " ".join(changes.pop("name", topic.name).split()) or topic.name
        if new_name != topic.name:
            self._repo.move_tasks(topic.name, new_name)
            aliases = tuple(dict.fromkeys((*topic.aliases, new_name.casefold())))
            changes["aliases"] = aliases
        return self._repo.save_topic(replace(topic, name=new_name, **changes))

    def remove_topic(self, name: str) -> None:
        """Удалить тему. Её задачи остаются, но уже без темы."""
        topic = self.topic(name)
        if topic is None:
            return
        self._repo.move_tasks(topic.name, "")
        for stored in self._repo.topics():
            if stored.name.casefold() == topic.name.casefold():
                self._repo.remove_topic(stored.id)

    def _seed_topics(self) -> None:
        """Первый запуск с темами: завести их из [projects] в config.toml."""
        if self._repo.flag("topics_seeded"):
            return
        if not self._repo.topics():
            for position, (name, aliases) in enumerate(self._config.projects.items()):
                self._repo.save_topic(
                    Topic(new_uid(), name, tuple(aliases), self._color(position), False, position)
                )
        self._repo.set_flag("topics_seeded")

    @staticmethod
    def _color(index: int) -> str:
        return TOPIC_COLORS[index % len(TOPIC_COLORS)]

    def remove_task(self, key: str) -> bool:
        tid = task_id(key)
        return tid is not None and self._repo.remove_task(tid)

    def open_tasks(self) -> list[Task]:
        """Незакрытые разовые задачи: сначала со сроком по порядку, потом без срока."""
        tasks = [t for t in self._repo.tasks() if not t.daily and not t.done]
        return sorted(tasks, key=lambda t: (t.due is None, t.due or date.max, t.created_at))

    def due_now(self, skip: set[str] | frozenset[str] = frozenset()) -> list[Category]:
        """Пункты на сегодня со временем, которое уже наступило, ещё не сделанные."""
        clock = self._clock().strftime("%H:%M")
        status = self.status()
        return [
            item.category
            for item in status.items
            if not item.done
            and item.category.time
            and item.category.time <= clock
            and item.category.key not in skip
            # Просроченным по дате о времени не напоминаем: оно было в другой день.
            and (item.category.due is None or item.category.due == status.day)
        ]

    # --- заметки и фокусы ---

    def add_note(self, key: str, text: str, source: str = "cli") -> Note:
        """Заметка к пункту сегодняшнего чек-листа: результат, комментарий."""
        cat, _ = self._find(key)
        text = text.strip()
        if not text:
            raise ValueError("Note is empty")
        return self._repo.add_note(self.today(), key, cat.title, text, self._clock(), source)

    def delete_note(self, note_id: int) -> bool:
        return self._repo.delete_note(note_id)

    def add_focus(self, key: str | None, started_at: datetime, minutes: int) -> None:
        """Записать законченный фокус Pomodoro. День считается по моменту начала."""
        self._repo.add_focus(self._day_of(started_at), key, started_at, minutes)

    def focus_count(self) -> int:
        return self._repo.focus_count(self.today())

    def title_of(self, key: str) -> str | None:
        try:
            return self._find(key)[0].title
        except KeyError:
            return None

    # --- внутреннее ---

    def _day_of(self, moment: datetime) -> date:
        return logical_day(moment, self._config.day_start_hour)

    def _split(self, day: date) -> tuple[list[Category], list[Category], dict[str, Task]]:
        """Пункты на день, пункты «скоро» и задачи по ключам.

        На день: направления, ежедневные задачи, затем разовые — просроченные и на сегодня
        по сроку, за ними без срока. Закрытая разовая видна до конца дня закрытия.
        """
        tasks = self._repo.tasks()

        def closed(task: Task) -> bool:
            return task.done and (task.done_at is None or self._day_of(task.done_at) < day)

        once = [t for t in tasks if not t.daily and not closed(t)]
        dated = sorted((t for t in once if t.due and t.due <= day), key=lambda t: t.due)
        undated = [t for t in once if t.due is None]
        soon = sorted(
            (t for t in once if t.due and day < t.due <= day + timedelta(days=SOON_DAYS)),
            key=lambda t: t.due,
        )
        today = [*self._config.categories, *(_category(t) for t in tasks if t.daily)]
        today += [_category(t) for t in [*dated, *undated]]
        return today, [_category(t) for t in soon], {t.key: t for t in tasks}

    def _find(self, key: str) -> tuple[Category, Task | None]:
        today, soon, tasks = self._split(self.today())
        for cat in [*today, *soon]:
            if cat.key == key:
                return cat, tasks.get(key)
        if key in tasks:
            # Задача со сроком дальше «скоро» или уже закрытая: в чек-листе её нет, но она есть.
            return _category(tasks[key]), tasks[key]
        keys = ", ".join(c.key for c in today)
        raise KeyError(f"Unknown item «{key}». Available: {keys}")
