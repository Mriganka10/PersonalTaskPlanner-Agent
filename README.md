# Daylight — Personal Task Planner Agent

A local-first daily planner with a responsive web UI, built with Python and FastAPI. Describe your day, review the extracted tasks, and create an achievable schedule with focus sessions and breaks.

## Run in PyCharm (macOS / Linux)

Use **Python 3.10 or newer**. Open the repository folder in PyCharm and run these commands from its terminal:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000**. API documentation is at **http://127.0.0.1:8000/docs**. Stop the server with Ctrl+C. Set PyCharm's project interpreter to `.venv/bin/python` if running from the IDE.

On Windows, create the environment with `py -m venv .venv` and activate it with `.venv\Scripts\Activate.ps1` in PowerShell. The remaining commands are the same.

If virtual-environment creation fails with a `pyexpat` / `libexpat` error, the Python installation itself is broken. This occurred with the local Homebrew interpreters during development; validation succeeded on managed Python 3.12. If you have `uv` installed, this alternative creates a healthy environment:

```bash
uv python install 3.12
uv venv --python 3.12 --managed-python --seed .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload
```

No Node.js build step, paid service, API key, or external database is required. Internet access is needed for the initial Python dependency installation; the running app uses local assets only.

## Use it

1. Select a planning date and your available hours. The initial window is 09:00–21:00; set the start to your current time if planning the remainder of today.
2. Enter, for example: **“I have a SQL assignment tomorrow, gym at 7 PM, and an interview next week. Prepare today’s plan.”**
3. Select **Extract tasks**. This adds tasks to your existing list. Review the inferred durations, deadlines, priorities, and fixed times.
4. Add tasks manually, edit any extracted task, or remove tasks using its × button. Set an appointment date for fixed events.
5. Choose your focus and break lengths, then select **Build my day**.
6. Check tasks off as you finish. Changes invalidate the previous schedule; select **Build my day** again to refresh it.
7. Download the plan as text, or use **Print** to print/save a PDF through your browser.

Tasks, settings, and the latest generated plan persist in this browser's local storage. Reset workspace clears tasks and the plan after confirmation. There is no account, cloud sync, or server-side task storage. Use the same browser and localhost URL to see saved work.

## How planning works

- **Text extraction is a transparent local rules engine, not an LLM.** It recognizes comma/newline/semicolon-separated tasks, common relative dates (`today`, `tomorrow`, `next week`, weekdays), ISO dates, fixed times (`at 7 PM`, `at 19:00`), explicit durations (`for 90 minutes`, `for 1.5 hours`), and priority words (`urgent`, `optional`). Date parsing uses `dateparser`.
- Missing durations default to 120 minutes for assignments/projects/essays and 60 minutes otherwise. “Next week” means seven days after the selected planning date. Bare weekdays mean the next occurrence. Assumptions appear on each task.
- An interview without a fixed time becomes interview **preparation**. Add the actual interview separately with its date/time.
- Fixed appointments are reserved first. Conflicting or out-of-hours appointments are reported for review; they are never silently shifted. Future appointments stay outside today's plan.
- Flexible tasks are ordered by earliest deadline, then high/medium/low priority. Work is split into focus sessions and breaks around fixed appointments. Completed tasks are excluded.
- Unfinished minutes, overdue deadlines, and appointment conflicts appear in the plan. The planner does not claim that an overfull day is achievable.

### MVP boundaries

Complex prose, arbitrary date phrases, task dependencies, recurring events, and phrases containing “and” inside a task title may need manual correction. Due dates are calendar dates, not exact deadline times. Tasks use one local calendar day (no overnight schedules or timezone conversion). Breaks are inserted after flexible work, not inside fixed appointments. Flexible work can be split into segments as short as five minutes. There are no calendar integrations, push reminders, LLM calls, or background autonomous actions in this version.

Run on localhost for personal use. The app has no authentication and is not intended to be exposed publicly as-is.

## Development

```bash
python -m pytest
python -m ruff check app tests
```

- `app/main.py`: FastAPI routes and static UI serving.
- `app/planner.py`: validated models, extraction, and scheduling.
- `app/static/`: responsive UI, task editor, browser persistence, export, and print styles.
- `tests/test_planner.py`: API validation and scheduling invariants, including the example, overlaps, overflow, priorities, and breaks.

### API

`POST /api/tasks/parse` accepts `{"text":"gym at 7 PM", "date":"2026-09-27"}` and returns editable tasks plus assumptions/warnings.

`POST /api/plan` accepts `{"tasks":[{"title":"Study SQL","duration":90}],"settings":{"date":"2026-09-27","start":"09:00","end":"21:00","focus_minutes":50,"break_minutes":10}}` and returns scheduled blocks, unfinished work, warnings, and totals.

`GET /api/health` returns service status. Inputs are validated; limits are 100 tasks, 5–720 minutes per task, and 5,000 characters per capture request.
