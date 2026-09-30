"""MCP-сервер: Claude видит задачи, заводит их, пишет результаты; закрывает по просьбе."""

import asyncio
from datetime import datetime

import pytest

from clodick.core.tracker import Tracker
from clodick.mcp_server import Desk, build_server
from clodick.storage.state import EXTERNAL_CHANGE, StateStore

NOW = datetime(2026, 9, 30, 12, 0)  # среда


@pytest.fixture
def desk(config, repo):
    tracker = Tracker(config, repo, clock=lambda: NOW)
    tracker.add_topic("Maga")
    tracker.add_topic("Turkov")
    return Desk(tracker, StateStore(repo.conn)), tracker


def test_today_lists_keys_topics_and_deadlines(desk):
    d, tracker = desk
    tracker.add_from_text("maga: report by 28.09")
    tracker.add_from_text("turkov: deploy by fri 15:00")
    text = d.today()
    assert text.startswith("Today Wed 30 Sep 2026: 0/4 done.")
    assert "[ ] sport «Sport»" in text
    assert "«report» — Maga, OVERDUE 2d" in text
    assert "Soon:" in text and "«deploy» — Turkov, due Fri 02 Oct, at 15:00" in text
    d.add_note("deploy", "staging is green")
    assert "note: staging is green" in d.today()  # заметки видны и у задач из Soon


def test_add_task_uses_quick_syntax_and_topic(desk):
    d, _ = desk
    assert "«fix login» — Turkov, due today" in d.add_task("fix login today", topic="Turkov")
    assert "Maga" in d.add_task("maga: slides")
    assert "No topic «Nope»" in d.add_task("x", topic="Nope")
    assert d.list_tasks("maga").count("\n") == 0 and "slides" in d.list_tasks("maga")
    assert "No topic «Sport»" in d.list_tasks("Sport")


def test_items_are_found_by_key_or_part_of_title(desk):
    d, tracker = desk
    report = tracker.add_from_text("maga: monthly report")
    tracker.add_from_text("maga: report slides")
    assert "Several items match «report»" in d.add_note("report", "x")
    assert "Nothing matches" in d.add_note("banana", "x")
    assert "«monthly report»" in d.add_note("monthly", "sent draft to Anna")
    assert "«monthly report»" in d.add_note(report.key, "fixed totals")
    notes = [n.text for n in tracker.status().items[-2].notes]
    assert notes == ["sent draft to Anna", "fixed totals"]
    assert "«report slides»" in d.add_note("Report Slides", "exact title wins")


def test_complete_and_reopen_leave_a_trace_for_the_pet(desk, repo):
    d, tracker = desk
    task = tracker.add_from_text("turkov: fix login")
    state = StateStore(repo.conn)
    assert state.get(EXTERNAL_CHANGE) is None

    assert d.complete("fix login", note="deployed, 2 bugs left") == (
        f"Marked done: «fix login» ({task.key})."
    )
    assert state.get(EXTERNAL_CHANGE)["text"] == "«fix login» is done"
    assert tracker._repo.get_task(task.id).done
    assert "already done" in d.complete(task.key)
    # Закрытая задача в сегодняшнем списке: и найти, и открыть снова можно.
    assert "Reopened" in d.reopen("fix login")
    assert not tracker._repo.get_task(task.id).done
    assert "was not marked" in d.reopen("fix login")


def test_move_task_and_topics(desk):
    d, tracker = desk
    tracker.add_from_text("report", topic="Maga")
    assert d.move_task("report", "turkov") == "Moved «report» to Turkov."
    assert "is a habit" in d.move_task("sport", "Maga")
    assert d.add_topic("Daily") == "Topic ready: Daily (every day)."
    assert "- Daily (every day), short names: daily" in d.list_topics()


def test_server_exposes_the_tools(desk):
    d, _ = desk
    server = build_server(d)
    tools = {t.name for t in asyncio.run(server.list_tools())}
    assert tools == {
        "today", "list_tasks", "list_topics", "add_task", "add_note",
        "complete", "reopen", "move_task", "add_topic",
    }  # fmt: skip
    result = asyncio.run(server.call_tool("add_task", {"text": "maga: slides by fri"}))
    assert "«slides» — Maga, due Fri 02 Oct" in result.content[0].text
    assert "ONLY after the user" in next(
        t.description for t in asyncio.run(server.list_tools()) if t.name == "complete"
    )
