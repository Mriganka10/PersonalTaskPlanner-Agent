from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.planner import ParseRequest, PlanRequest, build_plan, parse_tasks

app = FastAPI(title="Daylight · Personal Task Planner", version="0.1.0")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "local"}


@app.post("/api/tasks/parse")
def extract_tasks(request: ParseRequest):
    return parse_tasks(request)


@app.post("/api/plan")
def generate_plan(request: PlanRequest):
    return build_plan(request)
