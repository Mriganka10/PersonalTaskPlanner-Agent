"""Transparent text extraction and deterministic, conflict-aware daily scheduling."""

import re
from datetime import date as Date
from datetime import datetime, time, timedelta
from typing import Literal
from uuid import uuid4

import dateparser
from pydantic import BaseModel, Field, field_validator, model_validator


def local_minute_time(value: time | None):
    if value is not None and (value.tzinfo is not None or value.second or value.microsecond):
        raise ValueError("Use a local time in HH:MM format, without seconds or timezone")
    return value


class Task(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex, min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=160)
    duration: int = Field(default=60, ge=5, le=720)
    priority: Literal["high", "medium", "low"] = "medium"
    deadline: Date | None = None
    fixed_time: time | None = None
    scheduled_date: Date | None = None
    completed: bool = False
    notes: str = Field(default="", max_length=1000)

    _validate_time = field_validator("fixed_time")(local_minute_time)

    @model_validator(mode="after")
    def clean_title(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("Task title cannot be blank")
        return self


class Settings(BaseModel):
    date: Date = Field(default_factory=Date.today)
    start: time = time(9)
    end: time = time(21)
    focus_minutes: int = Field(default=50, ge=15, le=120)
    break_minutes: int = Field(default=10, ge=5, le=30)

    _validate_times = field_validator("start", "end")(local_minute_time)

    @model_validator(mode="after")
    def valid_hours(self):
        if self.end <= self.start:
            raise ValueError("End time must be after start time; use one calendar day")
        return self


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    date: Date = Field(default_factory=Date.today)


class PlanRequest(BaseModel):
    tasks: list[Task] = Field(max_length=100)
    settings: Settings = Field(default_factory=Settings)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({t.id for t in self.tasks}) != len(self.tasks):
            raise ValueError("Task IDs must be unique")
        return self


DATE_PATTERN = re.compile(
    r"\b(?:day after tomorrow|tomorrow|today|next week|next (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{4}-\d{2}-\d{2})\b",
    re.IGNORECASE,
)
TIME_PATTERN = re.compile(r"\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)(?![\w:])", re.IGNORECASE)
DURATION_PATTERN = re.compile(r"\b(?:for\s+)?(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)\b", re.IGNORECASE)


def parse_tasks(request: ParseRequest):
    text = re.sub(
        r"\b(?:prepare|generate|create|make|plan)\s+(?:my\s+|a\s+|the\s+)?(?:today['’]s\s+|daily\s+)?plan\b.*",
        "",
        request.text,
        flags=re.IGNORECASE,
    )
    chunks = re.split(r"[,;\n]+|\.(?=\s|$)|\s+and\s+", text, flags=re.IGNORECASE)
    tasks, warnings = [], []
    base = datetime.combine(request.date, time(12))
    for raw in chunks:
        raw = raw.strip(" .!\t")
        raw = re.sub(r"^(?:i\s+(?:have|need to|want to|must)|please|also)\s+", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"^(?:an?|the)\s+", "", raw, flags=re.IGNORECASE)
        if not raw:
            continue
        notes = []
        deadline = None
        date_match = DATE_PATTERN.search(raw)
        if date_match:
            phrase = date_match.group().lower()
            offsets = {"today": 0, "tomorrow": 1, "day after tomorrow": 2, "next week": 7}
            if phrase in offsets:
                deadline = request.date + timedelta(days=offsets[phrase])
            else:
                weekday = phrase.removeprefix("next ")
                days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                if weekday in days:
                    deadline = request.date + timedelta(
                        days=(days.index(weekday) - request.date.weekday()) % 7 or 7
                    )
                else:
                    parsed = dateparser.parse(
                        phrase, settings={"RELATIVE_BASE": base, "PREFER_DATES_FROM": "future"}
                    )
                    deadline = parsed.date() if parsed else None
            if deadline is None:
                notes.append("Could not read the date. Set it manually before planning.")
                warnings.append(f"Review the unrecognized date in: {raw}")
            if phrase == "next week":
                notes.append("‘Next week’ interpreted as seven days from the planning date.")
        fixed_time = None
        tm = TIME_PATTERN.search(raw)
        if tm:
            clock_text = re.sub(r"\s+", "", tm.group(1)).upper()
            clock_format = "%I:%M%p" if ":" in clock_text else "%I%p"
            if not clock_text.endswith(("AM", "PM")):
                clock_format = "%H:%M" if ":" in clock_text else "%H"
            try:
                fixed_time = datetime.strptime(clock_text, clock_format).time()  # noqa: DTZ007 — local wall time
                if not re.search(r"am|pm|:", tm.group(1), re.IGNORECASE):
                    notes.append("Time without AM/PM interpreted using the 24-hour clock; review it.")
            except ValueError:
                notes.append("Could not read the fixed time. Set it manually before planning.")
                warnings.append(f"Review the unrecognized time in: {raw}")
        dm = DURATION_PATTERN.search(raw)
        if dm:
            minutes = round(float(dm.group(1)) * (60 if dm.group(2).lower().startswith(("h",)) else 1))
            duration = max(5, min(720, minutes))
            if duration != minutes:
                notes.append("Duration adjusted to supported range of 5–720 minutes.")
        else:
            duration = 120 if re.search(r"assignment|project|essay", raw, re.IGNORECASE) else 60
            notes.append(f"Estimated {duration} minutes; adjust if needed.")
        high = re.search(r"\b(?:urgent|important|high priority|asap)\b", raw, re.IGNORECASE)
        low = re.search(r"\b(?:low priority|optional)\b", raw, re.IGNORECASE)
        priority = (
            "high"
            if high or (deadline and deadline <= request.date + timedelta(days=1))
            else "low"
            if low
            else "medium"
        )
        title = DATE_PATTERN.sub("", raw) if deadline else raw
        if fixed_time is not None:
            title = TIME_PATTERN.sub("", title)
        title = DURATION_PATTERN.sub("", title)
        title = re.sub(
            r"\b(?:high priority|low priority|urgent|important|asap|optional)\b",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(r"\b(?:due|by|on|for|at)\s*$", "", title.strip(), flags=re.IGNORECASE)
        title = re.sub(r"\s+", " ", title).strip(" .-:")
        if not title:
            warnings.append(f"Could not identify a task in: {raw}")
            continue
        if (
            re.search(r"\binterview\b", title, re.IGNORECASE)
            and not re.search(r"prep|prepare|practice", title, re.IGNORECASE)
            and fixed_time is None
        ):
            title = f"Prepare for {title}"
            notes.append(
                "Interview interpreted as preparation work; add a fixed time to schedule the interview itself."
            )
        tasks.append(
            Task(
                title=title[:160],
                duration=duration,
                priority=priority,
                deadline=deadline,
                fixed_time=fixed_time,
                scheduled_date=(deadline or request.date) if fixed_time else None,
                notes=" ".join(notes),
            )
        )
    if not tasks:
        warnings.append(
            "No tasks found. Try ‘SQL assignment tomorrow, gym at 7 PM’. You can also add tasks manually."
        )
    return {
        "tasks": tasks[:100],
        "warnings": warnings + (["Only the first 100 tasks were imported."] if len(tasks) > 100 else []),
        "mode": "local",
        "message": "Local text extraction: review inferred dates, durations, and task boundaries before planning.",
    }


def minute(value: time):
    return value.hour * 60 + value.minute


def clock(value: int):
    return f"{value // 60:02d}:{value % 60:02d}"


def build_plan(request: PlanRequest):
    settings = request.settings
    start, end = minute(settings.start), minute(settings.end)
    blocks, warnings, unscheduled = [], [], []
    active = [t for t in request.tasks if not t.completed]
    fixed = sorted([t for t in active if t.fixed_time], key=lambda t: minute(t.fixed_time))
    accepted = []
    for task in fixed:
        a, b = minute(task.fixed_time), minute(task.fixed_time) + task.duration
        reason = None
        if task.scheduled_date and task.scheduled_date != settings.date:
            reason = f"Appointment is on {task.scheduled_date}, outside this planning date."
        elif a < start or b > end:
            reason = "Fixed appointment is outside your available hours."
        elif any(a < y and b > x for x, y, _ in accepted):
            reason = (
                "Fixed appointment overlaps another appointment. Change its time to resolve the conflict."
            )
        if reason:
            unscheduled.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "remaining_minutes": task.duration,
                    "reason": reason,
                }
            )
        else:
            accepted.append((a, b, task))
            blocks.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "start": clock(a),
                    "end": clock(b),
                    "minutes": task.duration,
                    "kind": "fixed",
                    "priority": task.priority,
                }
            )
    flexible = sorted(
        [t for t in active if not t.fixed_time],
        key=lambda t: (t.deadline or Date.max, {"high": 0, "medium": 1, "low": 2}[t.priority]),
    )
    remaining = {t.id: t.duration for t in flexible}
    gaps, cursor = [], start
    for a, b, _ in accepted:
        gaps.append((cursor, a))
        cursor = b
    gaps.append((cursor, end))
    # Each work block reserves recovery time before another work block/appointment.
    for gap_start, gap_end in gaps:
        cursor = gap_start
        while cursor < gap_end:
            task = next((t for t in flexible if remaining[t.id] > 0), None)
            if task is None:
                break
            available = gap_end - cursor
            reserve = settings.break_minutes if gap_end < end else 0
            work = min(remaining[task.id], settings.focus_minutes, available - reserve)
            if work < 5:
                break
            blocks.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "start": clock(cursor),
                    "end": clock(cursor + work),
                    "minutes": work,
                    "kind": "focus",
                    "priority": task.priority,
                }
            )
            remaining[task.id] -= work
            cursor += work
            if any(remaining.values()) or gap_end < end:
                pause = min(settings.break_minutes, gap_end - cursor)
                if pause:
                    blocks.append(
                        {
                            "task_id": None,
                            "title": "Take a breather",
                            "start": clock(cursor),
                            "end": clock(cursor + pause),
                            "minutes": pause,
                            "kind": "break",
                            "priority": None,
                        }
                    )
                    cursor += pause
    for task in flexible:
        if remaining[task.id]:
            unscheduled.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "remaining_minutes": remaining[task.id],
                    "reason": "Not enough time today. Extend your hours, shorten tasks, or move work to another day.",
                }
            )
        if task.deadline and task.deadline < settings.date:
            warnings.append(f"{task.title} is overdue (due {task.deadline}).")
    blocks.sort(key=lambda b: b["start"])
    work_minutes = sum(b["minutes"] for b in blocks if b["kind"] != "break")
    break_minutes = sum(b["minutes"] for b in blocks if b["kind"] == "break")
    return {
        "date": settings.date,
        "blocks": blocks,
        "unscheduled": unscheduled,
        "warnings": warnings,
        "summary": {
            "work_minutes": work_minutes,
            "break_minutes": break_minutes,
            "free_minutes": end - start - work_minutes - break_minutes,
            "completed_tasks": sum(t.completed for t in request.tasks),
            "total_tasks": len(request.tasks),
        },
    }
