import itertools
from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.planner import ParseRequest, PlanRequest, Settings, Task, build_plan, parse_tasks

client = TestClient(app)
DAY = date(2026, 9, 27)


def test_user_example():
    result = parse_tasks(
        ParseRequest(
            text="I have a SQL assignment tomorrow, gym at 7 PM, and an interview next week. Prepare today’s plan.",
            date=DAY,
        )
    )
    tasks = result["tasks"]
    assert len(tasks) == 3
    assert tasks[0].title == "SQL assignment"
    assert tasks[0].deadline == date(2026, 9, 28)
    assert tasks[0].priority == "high"
    assert tasks[1].fixed_time == time(19)
    assert tasks[2].title == "Prepare for interview"
    plan = build_plan(PlanRequest(tasks=tasks, settings=Settings(date=DAY)))
    assert not plan["unscheduled"]
    assert any(b["start"] == "19:00" and b["kind"] == "fixed" for b in plan["blocks"])
    assert plan["summary"]["work_minutes"] == 240
    assert any(b["kind"] == "break" for b in plan["blocks"])


def test_explicit_dates_duration_and_priority():
    tasks = parse_tasks(
        ParseRequest(
            text="Write report due 2026-09-30 for 90 minutes urgent; Read for 0.5 hours low priority",
            date=DAY,
        )
    )["tasks"]
    assert tasks[0].duration == 90
    assert tasks[0].deadline == date(2026, 9, 30)
    assert tasks[0].priority == "high"
    assert tasks[1].duration == 30
    assert tasks[1].priority == "low"


def test_fixed_conflict_outside_hours_and_future():
    tasks = [
        Task(title="First", fixed_time=time(10)),
        Task(title="Overlap", fixed_time=time(10, 30)),
        Task(title="Early", fixed_time=time(8)),
        Task(title="Tomorrow", fixed_time=time(12), scheduled_date=date(2026, 9, 28)),
    ]
    plan = build_plan(PlanRequest(tasks=tasks, settings=Settings(date=DAY)))
    assert len(plan["blocks"]) == 1
    assert len(plan["unscheduled"]) == 3


def test_deadlines_then_priority_and_completed_excluded():
    tasks = [
        Task(title="Later urgent", deadline=date(2026, 10, 1), priority="high"),
        Task(title="Tomorrow", deadline=date(2026, 9, 28), priority="low"),
        Task(title="Done", completed=True),
    ]
    plan = build_plan(PlanRequest(tasks=tasks, settings=Settings(date=DAY)))
    assert plan["blocks"][0]["title"] == "Tomorrow"
    assert plan["summary"]["work_minutes"] == 120
    assert plan["summary"]["completed_tasks"] == 1


def test_overflow_is_reported_and_no_overlap():
    task = Task(title="Long", duration=240)
    plan = build_plan(PlanRequest(tasks=[task], settings=Settings(date=DAY, start=time(9), end=time(10))))
    assert plan["unscheduled"][0]["remaining_minutes"] == 190
    assert plan["summary"]["work_minutes"] == 50
    assert plan["summary"]["break_minutes"] == 10


@pytest.mark.parametrize("fixed_hour", [9, 10, 12, 18, 20])
@pytest.mark.parametrize("focus", [25, 50, 90])
def test_schedule_invariants(fixed_hour, focus):
    tasks = [
        Task(title="Focus", duration=720),
        Task(title="Appointment", fixed_time=time(fixed_hour), duration=45),
    ]
    plan = build_plan(PlanRequest(tasks=tasks, settings=Settings(date=DAY, focus_minutes=focus)))
    blocks = plan["blocks"]
    assert all("09:00" <= b["start"] < b["end"] <= "21:00" for b in blocks)
    assert all(left["end"] <= right["start"] for left, right in itertools.pairwise(blocks))
    scheduled = sum(b["minutes"] for b in blocks if b["task_id"] == tasks[0].id)
    assert scheduled + plan["unscheduled"][0]["remaining_minutes"] == 720
    assert sum(plan["summary"][k] for k in ("work_minutes", "break_minutes", "free_minutes")) == 720


def test_overdue_and_empty():
    plan = build_plan(
        PlanRequest(tasks=[Task(title="Late", deadline=date(2026, 9, 26))], settings=Settings(date=DAY))
    )
    assert "overdue" in plan["warnings"][0]
    assert build_plan(PlanRequest(tasks=[]))["blocks"] == []
    assert parse_tasks(ParseRequest(text="   "))["tasks"] == []


def test_api_validation_and_ui():
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.post("/api/tasks/parse", json={"text": "gym at 7 PM"}).status_code == 200
    assert (
        client.post(
            "/api/plan", json={"tasks": [], "settings": {"start": "21:00", "end": "09:00"}}
        ).status_code
        == 422
    )
    assert client.post("/api/plan", json={"tasks": [{"title": " ", "duration": -5}]}).status_code == 422
    assert (
        client.post(
            "/api/plan", json={"tasks": [{"id": "same", "title": "A"}, {"id": "same", "title": "B"}]}
        ).status_code
        == 422
    )
    assert client.post("/api/tasks/parse", json={"text": "x" * 5001}).status_code == 422


@pytest.mark.parametrize(
    "value, expected", [("7", time(7)), ("7 PM", time(19)), ("12 AM", time(0)), ("19:30", time(19, 30))]
)
def test_fixed_clock_is_not_parsed_as_day_of_month(value, expected):
    task = parse_tasks(ParseRequest(text=f"gym at {value}", date=DAY))["tasks"][0]
    assert task.fixed_time == expected


def test_invalid_dates_and_times_are_flagged():
    result = parse_tasks(ParseRequest(text="gym at 25:00; report due 2026-02-30", date=DAY))
    assert len(result["warnings"]) == 2
    assert result["tasks"][0].fixed_time is None
    assert "25:00" in result["tasks"][0].title
    assert result["tasks"][1].deadline is None


def test_reject_seconds_and_timezone_in_api():
    assert client.post("/api/plan", json={"tasks": [], "settings": {"start": "09:00:30"}}).status_code == 422
    assert (
        client.post("/api/plan", json={"tasks": [{"title": "Gym", "fixed_time": "19:00:00Z"}]}).status_code
        == 422
    )
