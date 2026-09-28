"""Что персонаж говорит просто так: факты, шутки, фразы по времени суток и прогрессу дня.

Без Qt, чтобы переиспользовать в боте.
"""

from __future__ import annotations

import random
from datetime import datetime

from clodick.core.models import DayStatus

FACTS = (
    "Raccoons wash their food. I wash my paws before touching your code.",
    "A raccoon remembers a solution for three years. Do you remember yours?",
    "A group of raccoons is called a gaze. Gaze upon my greatness.",
    "Raccoon paws have more nerve endings than your fingers. Just saying.",
    "Raccoons can open jars. I can open your to-do list.",
)
JOKES = (
    "I'm not a trash panda. I'm a desktop panda.",
    "Commit early, snack often.",
    "Your screen is my favourite floor.",
    "If you need me, I'll be right here. Always. Watching.",
    "I would help, but I have tiny paws.",
)
CHEERS = (
    "Fifteen minutes is enough to start.",
    "Small steps still count.",
    "You're doing better than you think.",
    "Water break? I'll guard the screen.",
)


def idle_line(now: datetime, status: DayStatus, focus_today: int, rng: random.Random) -> str:
    """Случайная реплика. Фразы про время и прогресс выпадают чаще общих."""
    general = [*FACTS, *JOKES, *CHEERS]
    special: list[str] = []
    hour = now.hour
    if 6 <= hour < 11:
        special.append("Good morning! Cocoa first, tasks second.")
    elif 12 <= hour < 14:
        special.append("Lunch time? I'd eat a cookie.")
    elif hour >= 22 or hour < 5:
        special.append("It's late. Sleep is a productivity hack too.")
    pending = [item.category.title for item in status.items if not item.done]
    if status.total and status.all_done:
        special.append("Everything is done. Nap time?")
    elif status.done_count:
        special.append(f"{status.done_count} of {status.total} done. Keep going!")
    elif pending:
        special.append(f"How about fifteen minutes of {pending[0]}?")
    if focus_today:
        special.append(f"{focus_today} focus session{'s' if focus_today > 1 else ''} today. Nice.")
    pool = general + special * 3
    return rng.choice(pool)
