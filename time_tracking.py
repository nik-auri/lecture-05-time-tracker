"""Лекция 5. Независимый модуль учёта времени (Python 3.9+, без библиотек).

Использование:
    tracker = TimeTracker()
    tracker.start_timer(task_id=1)
    tracker.stop_timer(task_id=1)
    print(tracker.generate_report())

Повторный start после stop продолжает накопление времени. Одновременно
работает один таймер: один человек не выполняет две задачи одновременно.
Отчёт включает текущий незавершённый сеанс, но не останавливает его.
Дополнительно: ручные записи, оценка времени, CSV, история сеансов.
Данные хранятся в памяти до завершения программы.
"""

import csv
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional


def _positive(value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Время должно быть конечным положительным числом")
    return value


def _task_id(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("ID задачи должен быть положительным целым числом")


@dataclass(frozen=True)
class TimeEntry:
    task_id: int
    seconds: float
    recorded_at: str
    note: str = ""
    source: str = "timer"


class TimeTracker:
    """Не зависит от TaskManager. Все значения времени выражены в секундах.

    Для длительностей используется monotonic: перевод системных часов
    не влияет на таймер. clock и now можно подменить в тестах без sleep.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime] = datetime.now):
        self._clock = clock
        self._now = now
        self._entries: List[TimeEntry] = []
        self._estimates: Dict[int, float] = {}
        self._active_task: Optional[int] = None
        self._started_at = 0.0

    @property
    def active_task_id(self) -> Optional[int]:
        return self._active_task

    @property
    def entries(self) -> tuple:
        """Неизменяемая копия истории: внешний код не испортит накопления."""
        return tuple(self._entries)

    def start_timer(self, task_id: int) -> None:
        _task_id(task_id)
        if self._active_task is not None:
            raise ValueError(f"Сначала остановите таймер задачи {self._active_task}")
        self._started_at = self._clock()
        self._active_task = task_id

    def stop_timer(self, task_id: int, note: str = "") -> TimeEntry:
        _task_id(task_id)
        if self._active_task != task_id:
            raise ValueError("Для этой задачи таймер не запущен")
        seconds = max(0.0, self._clock() - self._started_at)
        entry = TimeEntry(task_id, seconds, self._now().isoformat(), note)
        self._entries.append(entry)
        self._active_task = None
        return entry

    def add_manual_time(self, task_id: int, seconds: float,
                        note: str = "") -> TimeEntry:
        """Дополнительная функция: внести работу, выполненную без таймера."""
        _task_id(task_id)
        entry = TimeEntry(task_id, _positive(seconds), self._now().isoformat(),
                          note, "manual")
        self._entries.append(entry)
        return entry

    def set_estimate(self, task_id: int, seconds: float) -> None:
        _task_id(task_id)
        self._estimates[task_id] = _positive(seconds)

    def get_total_time(self, task_id: Optional[int] = None) -> float:
        """Сумма завершённых сеансов и текущего сеанса, если он есть."""
        if task_id is not None:
            _task_id(task_id)
        total = sum(e.seconds for e in self._entries
                    if task_id is None or e.task_id == task_id)
        if self._active_task is not None and task_id in (None, self._active_task):
            total += max(0.0, self._clock() - self._started_at)
        return total

    def generate_report(self, task_ids=None) -> dict:
        """Отчёт по задачам; task_ids позволяет включить задачи без записей."""
        ids = set(task_ids or ()) | set(self._estimates)
        ids.update(e.task_id for e in self._entries)
        if self._active_task is not None:
            ids.add(self._active_task)
        # Одно показание часов для согласованного снимка всех строк.
        current = self._clock()
        rows = []
        for task_id in sorted(ids):
            _task_id(task_id)
            entries = [e for e in self._entries if e.task_id == task_id]
            active = task_id == self._active_task
            seconds = sum(e.seconds for e in entries)
            if active:
                seconds += max(0.0, current - self._started_at)
            estimate = self._estimates.get(task_id)
            rows.append({
                "task_id": task_id, "total_seconds": seconds,
                "total_hours": seconds / 3600,
                "sessions": len(entries), "timer_running": active,
                "estimate_seconds": estimate,
                "over_budget": estimate is not None and seconds > estimate,
            })
        return {"generated_at": self._now().isoformat(), "tasks": rows,
                "total_seconds": sum(row["total_seconds"] for row in rows)}

    def export_csv(self, path, task_ids=None) -> Path:
        """UTF-8 с BOM и ';' для открытия русских отчётов в Excel."""
        report = self.generate_report(task_ids)
        path = Path(path)
        fields = ["task_id", "total_seconds", "total_hours", "sessions",
                  "timer_running", "estimate_seconds", "over_budget"]
        with path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";")
            writer.writeheader()
            writer.writerows(report["tasks"])
        return path

    def get_history(self, task_id: int) -> list:
        _task_id(task_id)
        return [asdict(e) for e in self._entries if e.task_id == task_id]


if __name__ == "__main__":
    tracker = TimeTracker()
    tracker.add_manual_time(1, 90, "Пример ручной записи")
    tracker.start_timer(1)
    tracker.stop_timer(1, "Пример сеанса")
    print(tracker.generate_report())
