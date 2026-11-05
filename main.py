"""Система управления задачами с учётом времени."""

import argparse
import csv
import json
import logging
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from unittest.mock import Mock

from time_tracking import TimeTracker


# 1. Анализ требований
@dataclass
class TaskRequirement:
    description: str
    priority: str
    category: str

    def validate(self):
        if not self.description.strip():
            raise ValueError("Требование должно иметь описание")
        return True


requirements = [
    TaskRequirement(text, "High", "Functional") for text in (
        "Запуск и остановка таймера задачи",
        "Накопление общего времени по нескольким сеансам",
        "Формирование отчёта по времени",
        "Интеграция с системой управления задачами",
    )
]


# 2. Проектирование
class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class Status(Enum):
    TODO = "To Do"
    IN_PROGRESS = "In Progress"
    REVIEW = "Review"
    DONE = "Done"


@dataclass
class User:
    user_id: int
    name: str
    email: str


class Task:
    def __init__(self, task_id, title, description, priority, due_date):
        self.task_id = task_id
        self.title = title
        self.description = description
        self.priority = priority
        self.due_date = due_date
        self.status = Status.TODO
        self.assignee = None
        self.created_at = datetime.now()

    def assign_to(self, user):
        self.assignee = user
        if self.status == Status.TODO:
            self.status = Status.IN_PROGRESS

    def update_status(self, new_status):
        if not isinstance(new_status, Status):
            raise ValueError("Неизвестный статус")
        self.status = new_status

    def is_overdue(self):
        return self.status != Status.DONE and datetime.now() > self.due_date


# 3. Реализация и интеграция с отдельным модулем
class TaskManager:
    def __init__(self, tracker=None):
        self.tasks = {}
        self.users = {}
        self.next_task_id = 1
        self.next_user_id = 1
        self.time_tracker = tracker if tracker is not None else TimeTracker()

    def create_user(self, name, email):
        if not name.strip() or "@" not in email:
            raise ValueError("Укажите имя и email с символом @")
        user = User(self.next_user_id, name.strip(), email.strip())
        self.users[user.user_id] = user
        self.next_user_id += 1
        return user

    def create_task(self, title, description, priority, due_date):
        if not title.strip():
            raise ValueError("Название задачи не может быть пустым")
        if not isinstance(priority, Priority) or not isinstance(due_date, datetime):
            raise ValueError("Некорректный приоритет или срок")
        task = Task(self.next_task_id, title.strip(), description, priority, due_date)
        self.tasks[task.task_id] = task
        self.next_task_id += 1
        return task

    def _get_task(self, task_id):
        if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id not in self.tasks:
            raise ValueError(f"Задача {task_id} не найдена")
        return self.tasks[task_id]

    def assign_task(self, task_id, user_id):
        task, user = self.tasks.get(task_id), self.users.get(user_id)
        if task is None or user is None:
            return False
        task.assign_to(user)
        return True

    def update_task_status(self, task_id, status):
        task = self._get_task(task_id)
        if not isinstance(status, Status):
            raise ValueError("Неизвестный статус")
        if status == Status.DONE and self.time_tracker.active_task_id == task_id:
            self.stop_timer(task_id, "Автоматическая остановка при завершении")
        task.update_status(status)

    def start_timer(self, task_id):
        task = self._get_task(task_id)
        if task.status == Status.DONE:
            raise ValueError("Задача завершена; сначала верните её в работу")
        self.time_tracker.start_timer(task_id)
        if task.status == Status.TODO:
            task.update_status(Status.IN_PROGRESS)

    def stop_timer(self, task_id, note=""):
        self._get_task(task_id)
        return self.time_tracker.stop_timer(task_id, note)

    def add_manual_time(self, task_id, seconds, note=""):
        self._get_task(task_id)
        return self.time_tracker.add_manual_time(task_id, seconds, note)

    def set_estimate(self, task_id, seconds):
        self._get_task(task_id)
        self.time_tracker.set_estimate(task_id, seconds)

    def get_overdue_tasks(self):
        return [t for t in self.tasks.values() if t.is_overdue()]

    def get_user_tasks(self, user_id):
        return [t for t in self.tasks.values()
                if t.assignee and t.assignee.user_id == user_id]

    def generate_report(self):
        counts = {s.value: 0 for s in Status}
        for task in self.tasks.values():
            counts[task.status.value] += 1
        return {"total_tasks": len(self.tasks),
                "overdue_tasks": len(self.get_overdue_tasks()),
                "status_distribution": counts}

    def generate_time_report(self):
        report = self.time_tracker.generate_report(self.tasks)
        for row in report["tasks"]:
            task = self._get_task(row["task_id"])
            row.update(title=task.title, status=task.status.value,
                       assignee=task.assignee.name if task.assignee else "Не назначен")
        return report


# 4. Сопровождение: логирование и измерение производительности
class MonitoringSystem:
    def __init__(self):
        self.durations = []
        self.error_count = 0
        self.tasks_created = 0
        self.logger = logging.getLogger("TaskManager")

    def log_operation(self, operation, duration=None, success=True):
        if duration is not None:
            self.durations.append(duration)
        if not success:
            self.error_count += 1
        if operation == "create_task" and success:
            self.tasks_created += 1
        self.logger.log(logging.INFO if success else logging.WARNING,
                        "%s: success=%s, seconds=%s", operation, success, duration)

    def measure(self, name, function, *args):
        start = time.perf_counter()
        try:
            result = function(*args)
        except Exception:
            self.log_operation(name, time.perf_counter() - start, False)
            raise
        self.log_operation(name, time.perf_counter() - start, result is not False)
        return result

    def generate_maintenance_report(self):
        return {"operations": len(self.durations), "errors": self.error_count,
                "tasks_created": self.tasks_created,
                "average_seconds": sum(self.durations) / max(len(self.durations), 1)}


class MonitoredTaskManager(TaskManager):
    def __init__(self, tracker=None):
        super().__init__(tracker)
        self.monitor = MonitoringSystem()

    def create_task(self, title, description, priority, due_date):
        return self.monitor.measure("create_task", super().create_task,
                                    title, description, priority, due_date)

    def assign_task(self, task_id, user_id):
        return self.monitor.measure("assign_task", super().assign_task, task_id, user_id)

    def start_timer(self, task_id):
        return self.monitor.measure("start_timer", super().start_timer, task_id)

    def stop_timer(self, task_id, note=""):
        return self.monitor.measure("stop_timer", super().stop_timer, task_id, note)


# 5. Agile: колонки вычисляются из статусов, поэтому доска не рассинхронизируется.
class KanbanBoard:
    columns = {"todo": Status.TODO, "in_progress": Status.IN_PROGRESS,
               "review": Status.REVIEW, "done": Status.DONE}

    def __init__(self, manager):
        self.manager = manager

    def get_column(self, name):
        if name not in self.columns:
            raise ValueError("Неизвестная колонка")
        return [t for t in self.manager.tasks.values() if t.status == self.columns[name]]

    def move_task(self, task, from_column, to_column):
        if from_column not in self.columns or to_column not in self.columns:
            raise ValueError("Неизвестная колонка")
        if self.manager._get_task(task.task_id) is not task:
            raise ValueError("Задача принадлежит другой системе")
        if task.status != self.columns[from_column]:
            raise ValueError("Задача находится в другой колонке")
        self.manager.update_task_status(task.task_id, self.columns[to_column])

    def get_board_stats(self):
        counts = {name: len(self.get_column(name)) for name in self.columns}
        return dict(counts, completion_rate=counts["done"] / max(len(self.manager.tasks), 1))


# 6. Внедрение: проверка, тестирование, копирование двух файлов и повторный тест.
class DeploymentManager:
    def __init__(self, project_path, deploy_path):
        self.project_path = Path(project_path).resolve()
        self.deploy_path = Path(deploy_path).resolve()

    def deploy(self):
        if sys.version_info < (3, 9):
            raise RuntimeError("Требуется Python 3.9+")
        if self.deploy_path == self.project_path:
            raise ValueError("Выберите другую папку для развёртывания")
        files = ["main.py", "time_tracking.py"]
        for name in files:
            if not (self.project_path / name).is_file():
                raise FileNotFoundError(name)
            if (self.deploy_path / name).exists():
                raise FileExistsError("Не перезаписываем существующий файл: " + name)
        subprocess.run([sys.executable, "main.py", "--test"],
                       cwd=self.project_path, check=True)
        self.deploy_path.mkdir(parents=True, exist_ok=True)
        for name in files:
            shutil.copy2(self.project_path / name, self.deploy_path / name)
        subprocess.run([sys.executable, "main.py", "--test"],
                       cwd=self.deploy_path, check=True)
        print("Развёртывание завершено:", self.deploy_path)


def print_time_report(manager):
    report = manager.generate_time_report()
    print("\nОТЧЁТ ПО ВРЕМЕНИ")
    for row in report["tasks"]:
        plan = row["estimate_seconds"]
        plan_text = f"{plan / 60:.2f} мин" if plan is not None else "не задан"
        print(f"#{row['task_id']} {row['title']} | {row['assignee']} | {row['status']}")
        print(f"  Факт: {row['total_seconds'] / 60:.2f} мин; план: {plan_text}; "
              f"сеансов: {row['sessions']}; таймер: {row['timer_running']}; "
              f"перерасход: {row['over_budget']}")
    print(f"Всего: {report['total_seconds'] / 60:.2f} мин")


def demo():
    print("ЛЕКЦИЯ 5. СИСТЕМА ЗАДАЧ С МОДУЛЕМ УЧЁТА ВРЕМЕНИ")
    for req in requirements:
        req.validate()
        print("Требование:", req.description)
    manager = MonitoredTaskManager()
    user = manager.create_user("Иван Петров", "ivan@example.com")
    task = manager.create_task("Реализовать модуль учёта времени", "Практическое задание",
                               Priority.HIGH, datetime.now() + timedelta(days=7))
    manager.assign_task(task.task_id, user.user_id)
    manager.set_estimate(task.task_id, 60)
    manager.add_manual_time(task.task_id, 90, "Проектирование модуля (пример)")
    for note in ("Первый сеанс", "Повторный запуск: время суммируется"):
        manager.start_timer(task.task_id)
        time.sleep(0.1)  # Короткая имитация работы, чтобы увидеть ненулевой сеанс.
        entry = manager.stop_timer(task.task_id, note)
        print(f"{note}: {entry.seconds:.6f} с")
    manager.create_task("Подготовить защиту", "Показать репозиторий", Priority.MEDIUM,
                        datetime.now() + timedelta(days=1))
    board = KanbanBoard(manager)
    board.move_task(task, "in_progress", "done")
    print_time_report(manager)
    print("История:", json.dumps(manager.time_tracker.get_history(task.task_id), ensure_ascii=False))
    print("Канбан:", board.get_board_stats())
    print("Отчёт системы:", manager.generate_report())
    print("Мониторинг:", manager.monitor.generate_maintenance_report())
    print("\nРучная работа: python main.py --interactive; тесты: python main.py --test")
    return manager


def interactive():
    manager = MonitoredTaskManager()
    user = manager.create_user("Студент", "student@example.com")
    print("Время хранится только до выхода из программы.")
    while True:
        print("\n1 Создать задачу | 2 Список | 3 Старт | 4 Стоп | 5 Отчёт")
        print("6 Ручные минуты | 7 План в минутах | 8 Завершить | 9 CSV | 0 Выход")
        try:
            action = input("> ").strip()
            if action == "0":
                if manager.time_tracker.active_task_id is not None:
                    manager.stop_timer(manager.time_tracker.active_task_id)
                print_time_report(manager)
                return
            if action == "1":
                task = manager.create_task(input("Название: "), input("Описание: "),
                                           Priority.MEDIUM, datetime.now() + timedelta(days=7))
                manager.assign_task(task.task_id, user.user_id)
                print("Создана задача", task.task_id)
            elif action == "2":
                for t in manager.tasks.values():
                    print(f"#{t.task_id} {t.title} [{t.status.value}]")
            elif action == "5":
                print_time_report(manager)
            elif action == "9":
                print("Сохранено:", manager.time_tracker.export_csv(input("Путь CSV: "), manager.tasks))
            elif action in {"3", "4", "6", "7", "8"}:
                task_id = int(input("ID задачи: "))
                if action == "3":
                    manager.start_timer(task_id)
                elif action == "4":
                    print("Сеанс, секунд:", manager.stop_timer(task_id).seconds)
                elif action == "6":
                    minutes = float(input("Минуты: ").replace(",", "."))
                    manager.add_manual_time(task_id, minutes * 60, input("Комментарий: "))
                elif action == "7":
                    manager.set_estimate(task_id, float(input("Минуты: ").replace(",", ".")) * 60)
                else:
                    manager.update_task_status(task_id, Status.DONE)
            else:
                print("Выберите пункт от 0 до 9")
        except (ValueError, OSError) as error:
            print("Ошибка:", error)
        except (EOFError, KeyboardInterrupt):
            print("\nВыход. Данные в памяти будут потеряны.")
            return


# 7. Тестирование. Подменяем часы, чтобы тесты не зависели от скорости компьютера.
class TestTimeTracker(unittest.TestCase):
    def setUp(self):
        self.clock = Mock(return_value=100.0)
        self.tracker = TimeTracker(self.clock)

    def test_timer_accumulates_sessions(self):
        self.tracker.start_timer(1)
        self.clock.return_value = 110
        self.assertEqual(self.tracker.stop_timer(1).seconds, 10)
        self.tracker.start_timer(1)
        self.clock.return_value = 125
        self.tracker.stop_timer(1)
        self.assertEqual(self.tracker.get_total_time(1), 25)

    def test_running_timer_in_report_without_double_count(self):
        self.tracker.start_timer(1)
        self.clock.return_value = 105
        for _ in range(2):
            self.assertEqual(self.tracker.generate_report()["total_seconds"], 5)
        self.assertEqual(self.tracker.active_task_id, 1)
        self.tracker.stop_timer(1)
        self.assertEqual(self.tracker.get_total_time(), 5)

    def test_duplicate_and_parallel_timer_rejected(self):
        self.tracker.start_timer(1)
        for task_id in (1, 2):
            with self.assertRaises(ValueError):
                self.tracker.start_timer(task_id)
        self.clock.return_value = 108
        self.assertEqual(self.tracker.stop_timer(1).seconds, 8)

    def test_wrong_stop_preserves_active_timer(self):
        with self.assertRaises(ValueError):
            self.tracker.stop_timer(1)
        self.tracker.start_timer(1)
        with self.assertRaises(ValueError):
            self.tracker.stop_timer(2)
        self.assertEqual(self.tracker.active_task_id, 1)

    def test_manual_time_and_task_isolation(self):
        self.tracker.add_manual_time(1, 60, "Работа")
        self.tracker.add_manual_time(2, 120)
        self.assertEqual(self.tracker.get_total_time(1), 60)
        self.assertEqual(self.tracker.get_total_time(2), 120)
        self.assertEqual(self.tracker.get_total_time(), 180)
        self.assertEqual(self.tracker.get_history(1)[0]["note"], "Работа")
        self.assertEqual(self.tracker.get_history(1)[0]["source"], "manual")

    def test_invalid_durations(self):
        for value in (-1, 0, float("nan"), float("inf")):
            for method in (self.tracker.add_manual_time, self.tracker.set_estimate):
                with self.subTest(value=value, method=method.__name__):
                    with self.assertRaises(ValueError):
                        method(1, value)
        self.assertEqual(self.tracker.entries, ())

    def test_invalid_ids(self):
        for value in (0, -1, True, "1", 1.5):
            with self.assertRaises(ValueError):
                self.tracker.start_timer(value)

    def test_estimate_and_budget(self):
        self.tracker.set_estimate(1, 60)
        self.tracker.add_manual_time(1, 60)
        self.assertFalse(self.tracker.generate_report()["tasks"][0]["over_budget"])
        self.tracker.add_manual_time(1, 1)
        self.assertTrue(self.tracker.generate_report()["tasks"][0]["over_budget"])

    def test_empty_report_and_zero_task(self):
        self.assertEqual(self.tracker.generate_report()["total_seconds"], 0)
        self.assertEqual(self.tracker.generate_report([1])["tasks"][0]["total_seconds"], 0)

    def test_immediate_stop(self):
        self.tracker.start_timer(1)
        self.assertEqual(self.tracker.stop_timer(1).seconds, 0)

    def test_csv_export(self):
        self.tracker.add_manual_time(1, 3600)
        with tempfile.TemporaryDirectory() as directory:
            path = self.tracker.export_csv(Path(directory) / "report.csv", [1, 2])
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter=";"))
            self.assertEqual(len(rows), 2)
            self.assertEqual(float(rows[0]["total_hours"]), 1)
            self.assertEqual(float(rows[1]["total_seconds"]), 0)


class TestTaskSystem(unittest.TestCase):
    def setUp(self):
        self.clock = Mock(return_value=100.0)
        self.manager = TaskManager(TimeTracker(self.clock))
        self.user = self.manager.create_user("Иван", "ivan@example.com")
        self.task = self.manager.create_task("Задача", "Описание", Priority.HIGH,
                                             datetime.now() + timedelta(days=5))

    def test_creation_assignment_and_user_tasks(self):
        self.assertEqual(self.task.status, Status.TODO)
        self.assertIsNone(self.task.assignee)
        self.assertTrue(self.manager.assign_task(1, 1))
        self.assertEqual(self.task.status, Status.IN_PROGRESS)
        self.assertEqual(self.manager.get_user_tasks(1), [self.task])
        self.assertFalse(self.manager.assign_task(999, 1))

    def test_missing_task_cannot_track_time(self):
        for method in (self.manager.start_timer, self.manager.stop_timer):
            with self.assertRaises(ValueError):
                method(999)
        with self.assertRaises(ValueError):
            self.manager.add_manual_time(999, 60)
        with self.assertRaises(ValueError):
            self.manager.set_estimate(999, 60)
        self.assertIsNone(self.manager.time_tracker.active_task_id)

    def test_integration_report_includes_title_user_and_zero_time(self):
        self.manager.assign_task(1, 1)
        row = self.manager.generate_time_report()["tasks"][0]
        self.assertEqual((row["title"], row["assignee"], row["total_seconds"]),
                         ("Задача", "Иван", 0))
        self.manager.start_timer(1)
        self.clock.return_value = 130
        self.manager.stop_timer(1)
        self.assertEqual(self.manager.generate_time_report()["total_seconds"], 30)

    def test_completion_stops_timer_and_blocks_restart(self):
        self.manager.start_timer(1)
        self.clock.return_value = 115
        self.manager.update_task_status(1, Status.DONE)
        self.assertEqual(self.manager.time_tracker.get_total_time(1), 15)
        self.assertIsNone(self.manager.time_tracker.active_task_id)
        with self.assertRaises(ValueError):
            self.manager.start_timer(1)
        self.manager.update_task_status(1, Status.TODO)
        self.manager.start_timer(1)
        self.assertEqual(self.task.status, Status.IN_PROGRESS)

    def test_overdue_and_report(self):
        self.task.due_date = datetime.now() - timedelta(days=1)
        self.assertEqual(self.manager.get_overdue_tasks(), [self.task])
        self.manager.update_task_status(1, Status.DONE)
        self.assertEqual(self.manager.get_overdue_tasks(), [])
        self.assertEqual(self.manager.generate_report()["status_distribution"]["Done"], 1)

    def test_kanban_sync_and_invalid_move(self):
        board = KanbanBoard(self.manager)
        self.manager.start_timer(1)
        with self.assertRaises(ValueError):
            board.move_task(self.task, "todo", "done")
        with self.assertRaises(ValueError):
            board.move_task(self.task, "in_progress", "missing")
        board.move_task(self.task, "in_progress", "done")
        self.assertEqual(board.get_board_stats()["completion_rate"], 1)
        self.assertIsNone(self.manager.time_tracker.active_task_id)

    def test_monitoring_counts_false_and_exception(self):
        manager = MonitoredTaskManager()
        with self.assertLogs("TaskManager", level="WARNING"):
            self.assertFalse(manager.assign_task(999, 999))
            with self.assertRaises(ValueError):
                manager.start_timer(999)
        report = manager.monitor.generate_maintenance_report()
        self.assertEqual((report["operations"], report["errors"]), (2, 2))
        # duration=None тоже корректно логируется.
        manager.monitor.log_operation("check")

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.manager.create_task(" ", "", Priority.LOW, datetime.now())
        with self.assertRaises(ValueError):
            self.manager.update_task_status(1, "done")
        with self.assertRaises(ValueError):
            TaskRequirement("", "High", "Functional").validate()


def run_tests():
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                               for cls in (TestTimeTracker, TestTaskSystem))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--test", action="store_true", help="Запустить тесты")
    mode.add_argument("--interactive", action="store_true", help="Открыть меню")
    mode.add_argument("--deploy", metavar="DIR", help="Развернуть в другую папку")
    parser.add_argument("--csv", metavar="FILE", help="Экспорт отчёта демонстрации")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    if args.csv and (args.test or args.interactive or args.deploy):
        parser.error("--csv используется только с демонстрацией")
    if args.test:
        return run_tests()
    if args.interactive:
        interactive()
    elif args.deploy:
        DeploymentManager(Path(__file__).parent, args.deploy).deploy()
    else:
        manager = demo()
        if args.csv:
            print("CSV:", manager.time_tracker.export_csv(args.csv, manager.tasks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
