"""
Reusable progress-bar helper for Pyrogram uploads/downloads.
"""
import time
from typing import Callable, Awaitable

PROGRESS_INTERVAL = 3  # seconds between edits


def _bar(current: int, total: int, width: int = 20) -> str:
    if total <= 0:
        return "░" * width
    filled = int(width * current / total)
    return "█" * filled + "░" * (width - filled)


def _human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _eta(current: int, total: int, elapsed: float) -> str:
    if current <= 0 or elapsed <= 0:
        return "--:--"
    speed = current / elapsed
    remaining = (total - current) / speed
    m, s = divmod(int(remaining), 60)
    return f"{m:02d}:{s:02d}"


class ProgressReporter:
    """
    Pass `callback` to Pyrogram's progress parameter.

    Usage:
        pr = ProgressReporter(msg, "Uploading")
        await client.send_video(..., progress=pr.callback)
    """

    def __init__(self, message, label: str = "Processing"):
        self._msg = message
        self._label = label
        self._last_edit = 0.0
        self._start = time.time()

    async def callback(self, current: int, total: int) -> None:
        now = time.time()
        if now - self._last_edit < PROGRESS_INTERVAL and current < total:
            return
        self._last_edit = now

        elapsed = now - self._start
        bar = _bar(current, total)
        pct = (current / total * 100) if total else 0
        eta = _eta(current, total, elapsed)
        speed_bytes = current / elapsed if elapsed > 0 else 0

        text = (
            f"**{self._label}**\n\n"
            f"`{bar}` {pct:.1f}%\n"
            f"📦 {_human(current)} / {_human(total)}\n"
            f"⚡ {_human(int(speed_bytes))}/s  •  ⏱ ETA {eta}"
        )
        try:
            await self._msg.edit_text(text)
        except Exception:
            pass
