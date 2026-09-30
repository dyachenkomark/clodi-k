"""Мастер первого запуска, вход в Google и модель для анализа — без сети."""

import json
from datetime import date, datetime
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication

from clodick import llm
from clodick.core.models import Category, CategoryStatus, DayStatus, Task
from clodick.core.tracker import Tracker
from clodick.desktop.controller import DesktopApp, SetupEnv
from clodick.desktop.onboarding import DONE, HELLO, MODEL, SHEET
from clodick.storage.state import StateStore
from clodick.sync import google

# --- модель ---


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def answer(text):
    return FakeResponse(payload={"choices": [{"message": {"content": text}}]})


def test_llm_client_calls_openai_compatible_api():
    calls = []

    def post(url, json, headers, timeout):
        calls.append((url, json, headers))
        return answer("<think>hmm</think> OK")

    settings = llm.LLMSettings.from_dict(
        {"base_url": "http://box:8000/v1/chat/completions/", "model": " gemma "}
    )
    client = llm.LLMClient(settings, "secret", post=post)
    assert client.check() == "OK"
    url, body, headers = calls[0]
    assert url == "http://box:8000/v1/chat/completions"
    assert body["model"] == "gemma"
    assert headers["Authorization"] == "Bearer secret"
    assert "Authorization" not in _headers_without_key()


def _headers_without_key():
    seen = {}

    def post(url, json, headers, timeout):
        seen.update(headers)
        return answer("OK")

    llm.LLMClient(llm.LLMSettings("http://x/v1", "m"), post=post).check()
    return seen


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (FakeResponse(401), "rejected"),
        (FakeResponse(404), "Not found"),
        (FakeResponse(500, text="boom"), "500"),
        (FakeResponse(200, payload={"oops": 1}), "OpenAI chat format"),
    ],
)
def test_llm_client_explains_errors(response, message):
    client = llm.LLMClient(llm.LLMSettings("http://x/v1", "m"), post=lambda *a, **k: response)
    with pytest.raises(llm.LLMError, match=message):
        client.check()


def test_llm_client_explains_network_errors():
    import requests

    def post(*args, **kwargs):
        raise requests.ConnectionError("refused")

    client = llm.LLMClient(llm.LLMSettings("http://x/v1", "m"), post=post)
    with pytest.raises(llm.LLMError, match="Cannot reach http://x/v1"):
        client.check()


def test_day_context_holds_the_facts_for_the_model():
    today = date(2026, 9, 30)
    late = Category("task:1", "fix login", project="Turkov", due=date(2026, 9, 28), custom=True)
    status = DayStatus(
        today,
        (
            CategoryStatus(Category("sport", "Sport"), True),
            CategoryStatus(late, False),
        ),
    )
    soon = Task("2", "report", project="Maga", due=date(2026, 10, 2), time="15:00")
    text = llm.day_context(status, [soon], "Wednesday 30 September 2026, 09:00")
    assert "- Sport (daily habit): done" in text
    assert "- fix login (Turkov, overdue by 2 days): not done" in text
    assert "- report (Maga, due Friday 02 October, in 2 days, at 15:00)" in text


# --- Google ---


def test_sheet_link_round_trip_and_validation():
    link = google.SheetLink("oauth", "abc", "C:/t.json", "https://x")
    assert google.SheetLink.from_dict(link.to_dict()) == link
    odd = {"mode": "ftp", "spreadsheet_id": "a", "key_file": "b"}
    assert google.SheetLink.from_dict(odd) is None
    assert google.SheetLink.from_dict(None) is None


def test_oauth_client_file_prefers_data_dir(tmp_path):
    assert google.oauth_client_file(tmp_path) in (None, *_packaged())
    own = tmp_path / google.OAUTH_CLIENT_NAME
    own.write_text("{}", encoding="utf-8")
    assert google.oauth_client_file(tmp_path) == own


def _packaged():
    packaged = Path(google.__file__).resolve().parents[1] / "assets" / google.OAUTH_CLIENT_NAME
    return (packaged,) if packaged.is_file() else ()


class FakeCreds:
    def to_json(self):
        return json.dumps({"token": "t", "refresh_token": "r"})


class FakeGspread:
    class exceptions:
        APIError = RuntimeError

    SpreadsheetNotFound = LookupError
    NoValidUrlKeyFound = ValueError

    def authorize(self, creds):
        return ("gc", creds)


def test_sign_in_saves_token_and_asks_only_for_own_files(tmp_path, monkeypatch):
    monkeypatch.setattr(google, "_gspread", FakeGspread)
    client_file = tmp_path / "client.json"
    client_file.write_text('{"installed": {"client_id": "id"}}', encoding="utf-8")
    seen = {}

    def flow(config, scopes):
        seen.update(config=config, scopes=scopes)
        return FakeCreds()

    token = tmp_path / "data" / "google-token.json"
    gc = google.sign_in(client_file, token, flow=flow)
    assert gc[0] == "gc"
    assert seen["scopes"] == ["https://www.googleapis.com/auth/drive.file"]
    assert seen["config"]["installed"]["client_id"] == "id"
    assert json.loads(token.read_text(encoding="utf-8"))["refresh_token"] == "r"


def test_find_or_create_sheet(monkeypatch):
    monkeypatch.setattr(google, "_gspread", FakeGspread)

    class Book:
        def __init__(self, sheet_id):
            self.id, self.url = sheet_id, f"https://docs.google.com/spreadsheets/d/{sheet_id}"

    class GC:
        def __init__(self):
            self.created = []

        def openall(self, title):
            return [Book("old")] if self.created else []

        def create(self, title):
            self.created.append(title)
            return Book("new")

    gc = GC()
    assert google.find_or_create_sheet(gc) == ("new", "https://docs.google.com/spreadsheets/d/new")
    assert google.find_or_create_sheet(gc)[0] == "old"  # второй раз находит свою
    assert gc.created == ["cloDICK"]


# --- мастер в приложении ---


class FakeSync:
    status = "Sheet synced 09:00"

    def __init__(self, link):
        self.link = link
        self.started = self.stopped = False
        self.requests = 0

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def request(self):
        self.requests += 1

    def pop_changed(self):
        return False


class FakeLLM:
    fail = False

    def __init__(self, settings, key=""):
        self.settings, self.key = settings, key

    def check(self):
        if FakeLLM.fail:
            raise llm.LLMError("Cannot reach the box")
        return "OK"

    def chat(self, system, user, max_tokens=300):
        if FakeLLM.fail:
            raise llm.LLMError("Cannot reach the box")
        return "Start with the overdue login fix, then the report."


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def setup_world(qapp, config, repo, tmp_path):
    FakeLLM.fail = False
    keys = {}
    signed = {}

    def sign_in(client_file, token):
        signed["token"] = token
        return "gc"

    env = SetupEnv(
        data_dir=tmp_path,
        oauth_client=tmp_path / "client.json",
        sign_in=sign_in,
        find_or_create=lambda gc: ("sheet123", "https://docs.google.com/spreadsheets/d/sheet123"),
        authorize=lambda link: ("svc", link.key_file),
        open_link=lambda gc, link: ("svc456", link),
        llm_client=FakeLLM,
        load_key=lambda: keys.get("llm", ""),
        save_key=lambda key: keys.__setitem__("llm", key),
    )
    syncs = []

    def factory(link):
        syncs.append(FakeSync(link))
        return syncs[-1]

    state = StateStore(repo.conn)
    clock = lambda: datetime(2026, 9, 30, 9, 0)  # noqa: E731
    desktop = DesktopApp(
        qapp, config, Tracker(config, repo, clock=clock), state, ram_reader=lambda: 42,
        clock=clock, sync_factory=factory, setup_env=env,
    )  # fmt: skip
    desktop.inline_jobs = True
    desktop.start()
    yield desktop, env, syncs, keys, signed
    for window in (desktop.pet, desktop.bubble, desktop.checklist, desktop.setup):
        if window is not None:
            window.close()
            window.deleteLater()
    qapp.processEvents()


def test_whole_first_run_with_google_sign_in_and_a_model(setup_world):
    desktop, env, syncs, keys, signed = setup_world
    assert not desktop._state.get("onboarding_done", False)
    desktop.open_setup()
    dialog = desktop.setup
    assert dialog.isVisible()
    assert dialog.pages.currentIndex() == HELLO
    assert {"raccoon", "mouse", "penguin"} <= set(dialog.pick_buttons)

    dialog.pick_buttons["penguin"].click()
    assert desktop.character.id == "penguin"

    dialog.hello_next.click()
    assert dialog.pages.currentIndex() == SHEET
    assert dialog.google_button.isVisible()
    dialog.google_button.click()
    assert signed["token"] == env.data_dir / "google-token.json"
    assert desktop._state.get("sheet_link")["spreadsheet_id"] == "sheet123"
    assert syncs[0].started and syncs[0].requests == 1
    assert desktop.sync is syncs[0]
    assert desktop._sync_action.isEnabled()
    assert "Connected" in dialog.sheet_status.text()
    assert dialog.sheet_next.isVisible()

    dialog.sheet_next.click()
    assert dialog.pages.currentIndex() == MODEL
    dialog.llm_url.setText("http://box:11434/v1/")
    dialog.llm_model.setText("gemma3:12b")
    dialog.llm_key.setText("secret")
    dialog.llm_check.click()
    assert "The model answered: OK" in dialog.llm_status.text()
    assert desktop._state.get("llm") is None  # проверка ещё не сохраняет

    dialog.llm_save.click()
    assert desktop._state.get("llm") == {"base_url": "http://box:11434/v1", "model": "gemma3:12b"}
    assert keys["llm"] == "secret"
    assert dialog.pages.currentIndex() == DONE

    dialog.finish_button.click()
    assert desktop._state.get("onboarding_done") is True
    assert not dialog.isVisible()
    assert desktop.bubble.isVisible()


def test_service_account_path_and_errors(setup_world):
    desktop, env, syncs, _, _ = setup_world
    desktop.open_setup()
    dialog = desktop.setup
    dialog.show_page(SHEET)
    dialog.service_toggle.click()
    dialog.service_button.click()
    assert "Choose the key file" in dialog.sheet_status.text()

    def broken(gc, link):
        raise google.SheetsError("No access. Share the sheet with the service account.")

    env.open_link = broken
    dialog.key_path.setText("C:/keys/bot.json")
    dialog.sheet_link.setText("https://docs.google.com/spreadsheets/d/svc456/edit")
    dialog.service_button.click()
    assert "No access" in dialog.sheet_status.text()
    assert dialog.service_button.isEnabled()
    assert syncs == []

    env.open_link = lambda gc, link: ("svc456", link)
    dialog.service_button.click()
    link = desktop._state.get("sheet_link")
    assert (link["mode"], link["spreadsheet_id"], link["key_file"]) == (
        "service", "svc456", "C:/keys/bot.json",
    )  # fmt: skip


def test_google_button_hidden_without_oauth_client(setup_world):
    desktop, env, _, _, _ = setup_world
    env.oauth_client = None
    desktop.open_setup()
    desktop.setup.show_page(SHEET)
    assert not desktop.setup.google_button.isVisibleTo(desktop.setup)
    assert desktop.setup.no_google.isVisibleTo(desktop.setup)


def test_model_errors_are_shown_and_nothing_is_saved(setup_world):
    desktop, _, _, keys, _ = setup_world
    FakeLLM.fail = True
    desktop.open_setup()
    dialog = desktop.setup
    dialog.show_page(MODEL)
    dialog.llm_save.click()
    assert "Fill in the address" in dialog.llm_status.text()
    dialog.llm_url.setText("http://box/v1")
    dialog.llm_model.setText("gemma")
    dialog.llm_save.click()
    assert "Cannot reach the box" in dialog.llm_status.text()
    assert desktop._state.get("llm") is None
    assert keys == {}


def test_plan_my_day_uses_the_model_and_falls_back(setup_world):
    desktop, _, _, _, _ = setup_world
    desktop.plan_my_day()
    assert "Connect an AI model" in desktop.bubble.text

    desktop._llm = FakeLLM(llm.LLMSettings("http://box/v1", "gemma"))
    desktop.plan_my_day()
    assert desktop.bubble.text == "Start with the overdue login fix, then the report."

    FakeLLM.fail = True
    desktop.bubble.hide()
    desktop._greet()  # утром без модели: обычное приветствие из кода
    assert desktop.bubble.text.startswith("Hi! Today:")


def test_saved_settings_come_back_after_restart(setup_world, qapp, config, repo):
    desktop, env, _, keys, _ = setup_world
    desktop._state.set("llm", {"base_url": "http://box/v1", "model": "gemma"})
    keys["llm"] = "secret"
    again = DesktopApp(
        qapp, config, Tracker(config, repo), desktop._state, ram_reader=lambda: 1, setup_env=env
    )
    assert again._llm.settings.model == "gemma"
    assert again._llm.key == "secret"
    again.open_setup()
    assert again.setup.llm_model.text() == "gemma"
    for window in (again.pet, again.bubble, again.checklist, again.setup):
        window.close()
