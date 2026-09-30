"""MCP-сервер клодика: Claude Code видит задачи и темы, заводит новые, записывает результаты.

Запуск (stdio): `python -m clodick.mcp_server`. Регистрация в Claude Code — docs/MCP.md.

Сервер работает с тем же кэшем, что и енот. Каждое изменение он отмечает в kv
(`external_change`): енот замечает это, обновляет чек-лист и отправляет правку в таблицу.
Задачу закрывает только по подтверждению человека: коммиты и файлы — не доказательство.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from clodick import paths
from clodick.config import load_config
from clodick.core.models import Category, Task
from clodick.core.tracker import Tracker
from clodick.logging_setup import setup_logging
from clodick.storage.db import connect
from clodick.storage.repository import CompletionRepository
from clodick.storage.state import EXTERNAL_CHANGE, StateStore

log = logging.getLogger(__name__)

SOURCE = "claude"

INSTRUCTIONS = """\
cloDICK is the user's personal task list: a desktop pet with a checklist, topics
(projects like Turkov, Maga, Personal, Daily), deadlines and notes. It is synced to
the user's Google Sheet.

Use it to know what the user is working on and to keep the list honest:
- Look at today() or list_tasks(topic) when the user talks about their plans or a project.
- Add tasks the user asks for with add_task. Quick syntax works: "maga: report by fri 15:00".
- When your work touches an open task, tell the user and offer to record a note (a result,
  what changed, what is left) with add_note.
- Mark a task done with complete ONLY after the user has confirmed it is done.
  Commits, files or your own judgement are not proof. Ask first.
Refer to items by their key (task:ab12cd34, sport) or by a unique part of the title.
"""


class Desk:
    """Действия над задачами для MCP. Ответы — короткий текст для модели."""

    def __init__(self, tracker: Tracker, state: StateStore) -> None:
        self._tracker = tracker
        self._state = state

    # --- чтение ---

    def today(self) -> str:
        status = self._tracker.status()
        lines = [f"Today {status.day:%a %d %b %Y}: {status.done_count}/{status.total} done."]
        lines += [self._line(i.category, status.day, i.done, i.notes) for i in status.items]
        if status.upcoming:
            lines.append("Soon:")
            lines += [self._line(i.category, status.day, i.done, i.notes) for i in status.upcoming]
        return "\n".join(lines)

    def list_tasks(self, topic: str = "") -> str:
        found = self._tracker.topic(topic) if topic else None
        if topic and found is None:
            return f"No topic «{topic}». Topics: {self._topic_names()}."
        today = self._tracker.today()
        tasks = [t for t in self._tracker._repo.tasks() if not t.done]
        if found is not None:
            tasks = [t for t in tasks if t.project.casefold() == found.name.casefold()]
        tasks.sort(key=lambda t: (t.daily, t.due is None, t.due or date.max))
        if not tasks:
            return f"No open tasks{f' in {found.name}' if found else ''}."
        return "\n".join(self._task_line(t, today) for t in tasks)

    def list_topics(self) -> str:
        topics = self._tracker.topics()
        if not topics:
            return "No topics yet."
        lines = []
        for topic in topics:
            line = f"- {topic.name}" + (" (every day)" if topic.daily else "")
            if topic.aliases:
                line += ", short names: " + ", ".join(topic.aliases)
            lines.append(line)
        return "\n".join(lines)

    # --- изменения ---

    def add_task(self, text: str, topic: str = "", daily: bool = False) -> str:
        if topic and self._tracker.topic(topic) is None:
            return f"No topic «{topic}». Topics: {self._topic_names()}. Use add_topic first."
        try:
            task = self._tracker.add_from_text(text, daily, topic)
        except ValueError as exc:
            return f"Not added: {exc}."
        self._changed(f"Claude added «{task.title}»")
        return f"Added: {self._task_line(task, self._tracker.today())}"

    def add_note(self, item: str, text: str) -> str:
        key, error = self._resolve(item)
        if error:
            return error
        try:
            self._tracker.add_note(key, text, source=SOURCE)
        except ValueError as exc:
            return f"Not saved: {exc}."
        title = self._tracker.title_of(key)
        self._changed(f"Claude noted a result for «{title}»")
        return f"Note saved for «{title}» ({key})."

    def complete(self, item: str, note: str = "") -> str:
        key, error = self._resolve(item)
        if error:
            return error
        title = self._tracker.title_of(key)
        if not self._tracker.mark_done(key, source=SOURCE):
            return f"«{title}» is already done."
        if note.strip():
            self._tracker.add_note(key, note, source=SOURCE)
        self._changed(f"«{title}» is done")
        return f"Marked done: «{title}» ({key})."

    def reopen(self, item: str) -> str:
        key, error = self._resolve(item, include_done=True)
        if error:
            return error
        title = self._tracker.title_of(key)
        if not self._tracker.unmark(key):
            return f"«{title}» was not marked done."
        self._changed(f"«{title}» is open again")
        return f"Reopened: «{title}» ({key})."

    def move_task(self, item: str, topic: str) -> str:
        key, error = self._resolve(item)
        if error:
            return error
        found = self._tracker.topic(topic) if topic else None
        if topic and found is None:
            return f"No topic «{topic}». Topics: {self._topic_names()}."
        try:
            task = self._tracker.move_task(key, found.name if found else "")
        except KeyError:
            return f"«{item}» is a habit from the settings, it has no topic to change."
        self._changed(f"«{task.title}» moved to {task.project or 'no topic'}")
        return f"Moved «{task.title}» to {task.project or 'no topic'}."

    def add_topic(self, name: str, daily: bool = False) -> str:
        try:
            topic = self._tracker.add_topic(name, daily or None)
        except ValueError as exc:
            return f"Not added: {exc}."
        self._changed(f"New topic {topic.name}")
        return f"Topic ready: {topic.name}{' (every day)' if topic.daily else ''}."

    # --- внутреннее ---

    def _resolve(self, ref: str, include_done: bool = False) -> tuple[str, str]:
        """Ключ пункта по ключу или по части названия. Второе — текст ошибки."""
        ref = ref.strip()
        status = self._tracker.status()
        items = [i.category for i in (*status.items, *status.upcoming)]
        tasks = self._tracker._repo.tasks()
        candidates: dict[str, str] = {c.key: c.title for c in items}
        for task in tasks:
            if include_done or not task.done:
                candidates.setdefault(task.key, task.title)
        if ref in candidates:
            return ref, ""
        wanted = ref.casefold()
        exact = [k for k, title in candidates.items() if title.casefold() == wanted]
        found = exact or [k for k, title in candidates.items() if wanted in title.casefold()]
        if len(found) == 1:
            return found[0], ""
        if not found:
            return "", f"Nothing matches «{ref}». Call today() or list_tasks() to see the keys."
        options = "; ".join(f"{k} «{candidates[k]}»" for k in found[:8])
        return "", f"Several items match «{ref}»: {options}. Use the key."

    def _changed(self, text: str) -> None:
        log.info("MCP: %s", text)
        stamp = datetime.now().isoformat(timespec="seconds")
        self._state.set(EXTERNAL_CHANGE, {"at": stamp, "text": text})

    def _topic_names(self) -> str:
        return ", ".join(t.name for t in self._tracker.topics()) or "none yet"

    @staticmethod
    def _describe(item: Category | Task, today: date) -> str:
        parts = [item.project] if item.project else []
        if item.due is not None:
            delta = (item.due - today).days
            if delta < 0:
                parts.append(f"OVERDUE {-delta}d (was due {item.due:%a %d %b})")
            elif delta == 0:
                parts.append("due today")
            else:
                parts.append(f"due {item.due:%a %d %b}")
        if item.time:
            parts.append(f"at {item.time}")
        if item.daily:
            parts.append("every day")
        return ", ".join(parts)

    def _line(self, category: Category, today: date, done: bool, notes=()) -> str:
        info = self._describe(category, today)
        line = f"[{'x' if done else ' '}] {category.key} «{category.title}»"
        line += f" — {info}" if info else ""
        for note in notes:
            line += f"\n      note: {note.text}"
        return line

    def _task_line(self, task: Task, today: date) -> str:
        info = self._describe(task, today)
        return f"{task.key} «{task.title}»" + (f" — {info}" if info else "")


def build_server(desk: Desk):
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("cloDICK", instructions=INSTRUCTIONS)

    @server.tool()
    def today() -> str:
        """Today's checklist: habits, daily tasks, overdue and today's tasks, and the next
        7 days. Each line has the item key, title, topic, deadline, done mark and notes."""
        return desk.today()

    @server.tool()
    def list_tasks(topic: str = "") -> str:
        """All open tasks, any deadline, sorted by deadline. topic filters by a topic
        name like Maga; empty means every topic."""
        return desk.list_tasks(topic)

    @server.tool()
    def list_topics() -> str:
        """Topics (projects) the user groups tasks by, with their short names."""
        return desk.list_topics()

    @server.tool()
    def add_task(text: str, topic: str = "", daily: bool = False) -> str:
        """Add a task. text may carry a topic, deadline and time:
        "maga: report by fri 15:00", "call bank tomorrow", "deploy in 3 days".
        topic is used when the text names none. daily=True repeats it every day."""
        return desk.add_task(text, topic, daily)

    @server.tool()
    def add_note(item: str, text: str) -> str:
        """Record a result or comment on an item: what was done, numbers, what is left.
        item is a key (task:ab12cd34) or a unique part of the title."""
        return desk.add_note(item, text)

    @server.tool()
    def complete(item: str, note: str = "") -> str:
        """Mark an item done, optionally with a result note. Call it ONLY after the user
        has confirmed the task is done; never on your own judgement."""
        return desk.complete(item, note)

    @server.tool()
    def reopen(item: str) -> str:
        """Undo a done mark: the item is open again."""
        return desk.reopen(item)

    @server.tool()
    def move_task(item: str, topic: str) -> str:
        """Move a task to another topic. Empty topic removes it from its topic."""
        return desk.move_task(item, topic)

    @server.tool()
    def add_topic(name: str, daily: bool = False) -> str:
        """Create a topic (project). daily=True: tasks in it repeat every day."""
        return desk.add_topic(name, daily)

    return server


def main() -> None:
    # Свой файл лога: енот пишет в clodick.log, два процесса не делят один файл.
    setup_logging(paths.log_dir(), filename="mcp.log")
    config = load_config(paths.config_path())
    conn = connect(paths.db_path())
    try:
        desk = Desk(Tracker(config, CompletionRepository(conn)), StateStore(conn))
        log.info("MCP-сервер запущен")
        build_server(desk).run("stdio")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
