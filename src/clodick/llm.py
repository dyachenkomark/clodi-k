"""Модель для анализа через OpenAI-совместимый API: vLLM, Ollama, LM Studio и облака.

Адрес и имя модели лежат в состоянии интерфейса, ключ — в защищённом хранилище системы
(Диспетчер учётных данных Windows, Связка ключей macOS). Модели доверяем только текст:
сводки и советы по готовым данным. Даты и числа считает код.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from datetime import date

import requests

from clodick.core.models import DayStatus, Task

log = logging.getLogger(__name__)

KEYRING_SERVICE = "cloDICK"
KEYRING_USER = "llm-api-key"
TIMEOUT_SECONDS = 60


class LLMError(Exception):
    """Модель недоступна или ответила не так. Текст понятен человеку."""


class ModelGone(LLMError):
    """Сервер не знает такой модели: её сменили или выгрузили."""


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    # Пусто — «какая модель сейчас на сервере»: спросить у него и следовать за сменой.
    model: str = ""

    def to_dict(self) -> dict:
        return {"base_url": self.base_url, "model": self.model}

    @classmethod
    def from_dict(cls, data: dict | None) -> LLMSettings | None:
        if not data or not data.get("base_url"):
            return None
        return cls(normalize_url(data["base_url"]), (data.get("model") or "").strip())


def normalize_url(url: str) -> str:
    """Адрес API без хвоста /chat/completions и без слэша в конце."""
    url = url.strip().rstrip("/")
    for tail in ("/chat/completions", "/completions"):
        url = url.removesuffix(tail)
    return url


def load_key() -> str:
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, KEYRING_USER) or ""
    except Exception:  # нет хранилища ключей в системе
        log.warning("хранилище ключей недоступно, ключ модели не прочитан")
        return ""


def save_key(key: str) -> None:
    import keyring

    if key:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key)
    else:
        with contextlib.suppress(keyring.errors.PasswordDeleteError):
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)


class LLMClient:
    def __init__(
        self, settings: LLMSettings, api_key: str = "", post=requests.post, get=requests.get
    ) -> None:
        self.settings = settings
        self._key = api_key
        self._post = post
        self._get = get
        # Модель, которую сервер отдаёт сейчас, если в настройках она не закреплена.
        self._resolved: str | None = None

    @property
    def auto(self) -> bool:
        return not self.settings.model

    def model_name(self, refresh: bool = False) -> str:
        """Имя модели для запроса: закреплённое или то, что сейчас стоит на сервере."""
        if self.settings.model:
            return self.settings.model
        if refresh or self._resolved is None:
            models = self.list_models()
            if not models:
                raise LLMError("The server has no models loaded.")
            self._resolved = pick_model(models)
        return self._resolved

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        return headers

    def list_models(self) -> list[str]:
        """Какие модели есть на сервере: GET /models, так умеют vLLM, Ollama и LM Studio."""
        url = f"{self.settings.base_url}/models"
        try:
            response = self._get(url, headers=self._headers(), timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise LLMError(f"Cannot reach {self.settings.base_url}: {exc}") from exc
        if response.status_code in (401, 403):
            raise LLMError("The API key was rejected.")
        if response.status_code >= 400:
            raise LLMError(
                "The server did not list its models. Check the address "
                "(usually it ends with /v1) or type the model name yourself."
            )
        try:
            return [item["id"] for item in response.json()["data"] if item.get("id")]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError("The server answered, but not with a list of models.") from exc

    def chat(self, system: str, user: str, max_tokens: int = 300) -> str:
        try:
            return self._chat(self.model_name(), system, user, max_tokens)
        except ModelGone:
            if not self.auto:
                raise LLMError(
                    f"The server has no model {self.settings.model}. "
                    "Clear the model field in Setup, and I'll follow the server."
                ) from None
            # На сервере сменили модель: перечитать список и повторить один раз.
            return self._chat(self.model_name(refresh=True), system, user, max_tokens)

    def _chat(self, model: str, system: str, user: str, max_tokens: int) -> str:
        headers = self._headers()
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": 0.4,
        }
        url = f"{self.settings.base_url}/chat/completions"
        try:
            response = self._post(url, json=body, headers=headers, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise LLMError(f"Cannot reach {self.settings.base_url}: {exc}") from exc
        if response.status_code in (401, 403):
            raise LLMError("The API key was rejected.")
        if response.status_code in (400, 404) and "model" in response.text.casefold():
            raise ModelGone(model)  # vLLM: «The model `x` does not exist.»
        if response.status_code == 404:
            raise LLMError("Not found. Check the address: usually it ends with /v1.")
        if response.status_code >= 400:
            raise LLMError(f"The API answered {response.status_code}: {response.text[:200]}")
        try:
            text = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("The answer is not in the OpenAI chat format.") from exc
        return strip_thinking(text or "").strip()

    def check(self) -> str:
        """Проверка подключения: короткий ответ модели."""
        return self.chat("You are a connection test.", "Reply with the single word: OK", 10)


def pick_model(models: list[str]) -> str:
    """Какую модель взять, если человек не выбрал: первую, что годится для чата.

    Модели для эмбеддингов, переранжирования и распознавания речи отвечать текстом
    не умеют, их пропускаем.
    """
    skip = ("embed", "rerank", "whisper", "tts", "clip", "bge", "e5-")
    usable = [m for m in models if not any(word in m.casefold() for word in skip)]
    return (usable or models)[0]


def strip_thinking(text: str) -> str:
    """Некоторые модели сначала думают вслух в <think>…</think>: это не для пузыря."""
    while "<think>" in text and "</think>" in text:
        start, end = text.index("<think>"), text.index("</think>") + len("</think>")
        text = text[:start] + text[end:]
    return text


PLAN_SYSTEM = (
    "You are cloDICK, a small friendly desktop pet and personal assistant. "
    "Reply in the language the task titles are written in. "
    "Give a short plan for today: 2-4 sentences, no lists, no markdown. "
    "Mention overdue items first, then today's deadlines, then one thing from the next days "
    "if it needs a start. Be warm and concrete. Never invent tasks or dates."
)


def day_context(status: DayStatus, open_tasks: list[Task], now_text: str) -> str:
    """Факты для модели: всё посчитано кодом, модель только пересказывает."""
    lines = [f"Now: {now_text}.", "Today's checklist:"]
    for item in status.items:
        mark = "done" if item.done else "not done"
        lines.append(f"- {item.category.title} ({_describe(item.category, status.day)}): {mark}")
        for note in item.notes:
            lines.append(f"  note: {note.text}")
    later = [t for t in open_tasks if t.due and t.due > status.day]
    if later:
        lines.append("Coming up:")
        for task in later[:8]:
            lines.append(f"- {task.title} ({_describe(task, status.day)})")
    return "\n".join(lines)


def _describe(item, today: date) -> str:
    parts = [item.project] if getattr(item, "project", "") else []
    due = getattr(item, "due", None)
    if due is not None:
        delta = (due - today).days
        if delta < 0:
            parts.append(f"overdue by {-delta} days")
        elif delta == 0:
            parts.append("due today")
        else:
            parts.append(f"due {due:%A %d %B}, in {delta} days")
    if getattr(item, "time", ""):
        parts.append(f"at {item.time}")
    if getattr(item, "daily", False) and due is None:
        parts.append("daily habit")
    return ", ".join(parts) or "no deadline"


def plan_day(client: LLMClient, status: DayStatus, open_tasks: list[Task], now_text: str) -> str:
    return client.chat(PLAN_SYSTEM, day_context(status, open_tasks, now_text), 220)
