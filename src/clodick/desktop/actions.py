"""Чем персонаж занимается сам: позы, забавные выходки и что он при этом говорит. Без Qt.

Действие с kind="anim" показывает одноимённую анимацию из пакета персонажа: если её
нет, персонаж просто не выбирает это действие. Остальные виды — поведение: spin кружится
на месте кадрами ходьбы, zoomies носится зигзагом, climb лазает по правому краю экрана
(нужна анимация climb).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    # Как часто выбирается, относительно других.
    weight: float
    # Сколько секунд длится: (минимум, максимум).
    seconds: tuple[float, float]
    # Сколько секунд на кадр анимации.
    frame: float = 0.3
    # Годится для фокуса Pomodoro и ночи: тихое, без беготни.
    calm: bool = False
    # Особенно уместно в перерыв Pomodoro: вес втрое больше.
    lively: bool = False
    # Что он иногда говорит, начиная действие.
    lines: tuple[str, ...] = ()
    kind: str = "anim"


ACTIONS: dict[str, Action] = {
    "wash": Action(3, (2.5, 4.0), 0.22, calm=True, lines=("Clean paws, clean code.",)),
    "stretch": Action(2, (2.5, 4.0), 0.8, calm=True, lines=("*yaaawn*", "Stretch with me?")),
    "scratch": Action(2, (2.0, 3.0), 0.12, lines=("Itchy ear...",)),
    "roll": Action(1, (3.0, 5.0), 0.4, lively=True, lines=("Belly rubs? No? Okay.",)),
    "dance": Action(1, (3.0, 5.0), 0.25, lively=True, lines=("La-la-la!", "Dance break!")),
    "peek": Action(1, (2.5, 3.5), 0.6, lines=("Peek-a-boo!",)),
    "sneeze": Action(0.6, (1.6, 1.6), 0.4, lines=("Achoo!",)),
    "dig": Action(1.5, (3.0, 4.5), 0.18, lines=("Burying a snack for later.",)),
    "sniff": Action(2, (2.5, 4.0), 0.3, calm=True, lines=("Smells like deadlines.",)),
    "play": Action(1.5, (3.5, 5.0), 0.22, lively=True, lines=("Boing! Boing!",)),
    "read": Action(2, (5.0, 9.0), 0.9, calm=True, lines=("Reading about raccoons.",)),
    "sip": Action(2, (4.0, 7.0), 0.7, calm=True, lines=("Mmm, cocoa.",)),
    "clap": Action(0.5, (2.0, 3.0), 0.18, lines=("Yay!",)),
    "doze": Action(1.5, (5.0, 9.0), 0.9, calm=True, lines=("Just resting my eyes...",)),
    "sing": Action(1, (3.0, 5.0), 0.45, lively=True, lines=("Hmm-hmm-hmm~",)),
    "flex": Action(0.8, (2.5, 3.5), 0.35, lines=("Look at these muscles!",)),
    "tailwag": Action(2, (2.5, 4.0), 0.3, calm=True),
    "trash": Action(1, (4.0, 5.0), 0.7, lines=("Found your old to-do list!", "Treasure!")),
    "hiccup": Action(0.5, (2.4, 3.2), 0.4, lines=("Hic!",)),
    # Только в награду за дело, сам не выбирает.
    "eat": Action(0, (3.0, 3.0), 0.35),
    "spin": Action(0.8, (1.6, 2.4), lively=True, lines=("Almost got my tail!",), kind="spin"),
    "zoomies": Action(0.5, (0.0, 0.0), lively=True, lines=("Zoom zoom!",), kind="zoomies"),
    # Лазает по правому краю экрана, как по дереву. Нужны кадры climb.
    "climb": Action(
        3,
        (0.0, 0.0),
        lively=True,
        lines=("Tree time!", "I can see my house from here."),
        kind="climb",
    ),
}

# Реакция на отмеченное дело: направление из настроек → действие. Остальное — случайно.
TASK_REACTIONS = {"sport": "flex", "study": "read", "language": "sing"}
TASK_REACTION_POOL = ("clap", "dance", "eat")
TASK_LINES = {
    "flex": ("Strong like a raccoon!", "Sport done. Flex!"),
    "read": ("Big brain time.", "Knowledge +1."),
    "sing": ("Bonjour! Hola! Privet!", "New words, new me."),
    "clap": ("Nice one!", "Done and done."),
    "dance": ("Victory dance!",),
    "eat": ("A cookie for you... and me.",),
}
