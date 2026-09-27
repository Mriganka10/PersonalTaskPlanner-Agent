"use strict";
const $ = (id) => document.getElementById(id);
const STORAGE = "daylight-planner-v1";
const localDate = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
let tasks = [],
  plan = null,
  editingId = null,
  busy = false,
  noticeTimer;
$("plan-date").value = localDate();
const escapeHtml = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const duration = (m) =>
  m >= 60 ? `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ""}` : `${m}m`;
function notify(message) {
  $("notice").textContent = message;
  $("notice").hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => ($("notice").hidden = true), 6500);
}
function settings() {
  return {
    date: $("plan-date").value,
    start: $("start-time").value,
    end: $("end-time").value,
    focus_minutes: Number($("focus").value),
    break_minutes: Number($("break").value),
  };
}
function save() {
  try {
    localStorage.setItem(
      STORAGE,
      JSON.stringify({ tasks, settings: settings(), plan }),
    );
  } catch {
    notify(
      "Browser storage is unavailable or full. Download your plan to keep a copy.",
    );
  }
}
function updateDate() {
  const value = $("plan-date").value;
  $("date-label").textContent = value
    ? new Date(`${value}T12:00:00`).toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "Choose a date";
}
function invalidate() {
  plan = null;
  $("plan-status").textContent = "Ready to rebuild";
  renderPlan();
  save();
}
function renderTasks() {
  $("task-count").textContent = tasks.length;
  $("task-list").innerHTML = tasks.length
    ? tasks
        .map(
          (t) =>
            `<div class="task-row ${t.completed ? "completed" : ""}" data-id="${escapeHtml(t.id)}"><input type="checkbox" ${t.completed ? "checked" : ""} aria-label="Mark ${escapeHtml(t.title)} complete" data-action="complete"><div class="task-info"><div class="task-title">${escapeHtml(t.title)}</div><div class="task-meta"><span class="${escapeHtml(t.priority)}">${escapeHtml(t.priority)} priority</span><span>${duration(t.duration)}</span>${t.deadline ? `<span>Due ${escapeHtml(t.deadline)}</span>` : ""}${t.fixed_time ? `<span>◷ ${escapeHtml(t.fixed_time.slice(0, 5))}${t.scheduled_date ? ` · ${escapeHtml(t.scheduled_date)}` : ""}</span>` : ""}</div>${t.notes ? `<p class="task-notes">${escapeHtml(t.notes)}</p>` : ""}</div><div class="task-controls"><button class="icon-button" data-action="edit" aria-label="Edit ${escapeHtml(t.title)}">✎</button><button class="icon-button" data-action="delete" aria-label="Delete ${escapeHtml(t.title)}">×</button></div></div>`,
        )
        .join("")
    : '<div class="empty-tasks">Your mind has a lot going on.<br>Capture a few tasks above, or add one here.</div>';
}
const emptyPlan = $("plan-content").innerHTML;
function renderPlan() {
  $("plan-actions").hidden = !plan;
  if (!plan) {
    $("plan-content").innerHTML = emptyPlan;
    $("plan-subtitle").textContent = "A clear path from to-do to done.";
    return;
  }
  $("plan-status").textContent = plan.unscheduled.length
    ? "Needs your attention"
    : "Your day, mapped out";
  $("plan-subtitle").textContent =
    `${plan.date} · ${plan.summary.total_tasks} tasks · ${plan.summary.completed_tasks} completed`;
  const s = plan.summary;
  $("plan-content").innerHTML =
    `<div class="stats"><div><strong>${duration(s.work_minutes)}</strong><small>PLANNED WORK</small></div><div><strong>${duration(s.break_minutes)}</strong><small>RECHARGE</small></div><div><strong>${duration(s.free_minutes)}</strong><small>OPEN SPACE</small></div></div>${plan.warnings.map((w) => `<div class="warning">${escapeHtml(w)}</div>`).join("")}<div class="timeline">${plan.blocks.map((b) => `<div class="time-block"><div class="time-label">${escapeHtml(b.start)}</div><div class="block ${escapeHtml(b.kind)}"><span class="block-type">${b.kind === "fixed" ? "Fixed" : b.kind === "break" ? "Recharge" : "Focus"}</span><h3>${escapeHtml(b.title)}</h3><p>${escapeHtml(b.start)} – ${escapeHtml(b.end)} · ${duration(b.minutes)}</p></div></div>`).join("") || '<div class="empty-tasks">No work scheduled. Enjoy the breathing room,<br>or add a task to get started.</div>'}</div>${plan.unscheduled.map((t) => `<div class="warning"><strong>${escapeHtml(t.title)} · ${duration(t.remaining_minutes)} unplanned</strong>${escapeHtml(t.reason)}</div>`).join("")}`;
}
async function api(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(
      "The server returned an unexpected response. Please try again.",
    );
  }
  if (!response.ok)
    throw new Error(
      Array.isArray(data.detail)
        ? data.detail
            .map((e) => `${e.loc.slice(1).join(" ")}: ${e.msg}`)
            .join("; ")
        : data.detail || "Unable to complete this request.",
    );
  return data;
}
async function run(button, label, action) {
  if (busy) return;
  busy = true;
  const original = button.innerHTML;
  // Prevent edits during requests so responses cannot overwrite newer task changes.
  document
    .querySelectorAll("button,input,select,textarea")
    .forEach((e) => (e.disabled = true));
  button.textContent = label;
  try {
    await action();
  } catch (error) {
    notify(
      error.message === "Failed to fetch"
        ? "Cannot reach the planner. Check that your local server is running."
        : error.message,
    );
  } finally {
    busy = false;
    document
      .querySelectorAll("button,input,select,textarea")
      .forEach((e) => (e.disabled = false));
    button.innerHTML = original;
  }
}
$("example").onclick = () => {
  $("brain-dump").value =
    "I have a SQL assignment tomorrow, gym at 7 PM, and an interview next week. Prepare today’s plan.";
  $("brain-dump").focus();
};
$("extract").onclick = () =>
  run($("extract"), "Finding tasks…", async () => {
    if (!$("brain-dump").value.trim())
      throw new Error("Describe a task first, or try the example.");
    if (!$("plan-date").value) throw new Error("Choose a planning date first.");
    const data = await api("/api/tasks/parse", {
      text: $("brain-dump").value,
      date: $("plan-date").value,
    });
    if (tasks.length + data.tasks.length > 100)
      throw new Error(
        "Your workspace supports up to 100 tasks. Remove some tasks before importing more.",
      );
    tasks.push(...data.tasks);
    renderTasks();
    invalidate();
    $("brain-dump").value = "";
    notify(
      data.warnings.join(" ") ||
        `${data.tasks.length} tasks captured. Review estimated details, then build your day.`,
    );
  });
$("generate").onclick = () =>
  run($("generate"), "Planning…", async () => {
    if (!tasks.length)
      throw new Error("Add at least one task to build your day.");
    plan = await api("/api/plan", { tasks, settings: settings() });
    renderPlan();
    save();
    notify(
      plan.unscheduled.length
        ? "Plan created. Review tasks that need more time or have a conflict."
        : "Your daily plan is ready.",
    );
  });
function openEditor(task) {
  editingId = task?.id || null;
  $("dialog-title").textContent = task ? "Edit task" : "Add a task";
  $("edit-title").value = task?.title || "";
  $("edit-duration").value = task?.duration || 60;
  $("edit-priority").value = task?.priority || "medium";
  $("edit-deadline").value = task?.deadline || "";
  $("edit-time").value = task?.fixed_time?.slice(0, 5) || "";
  $("edit-date").value = task?.scheduled_date || $("plan-date").value;
  $("edit-notes").value = task?.notes || "";
  $("task-dialog").showModal();
  $("edit-title").focus();
}
$("add-task").onclick = () => openEditor();
$("close-dialog").onclick = () => $("task-dialog").close();
$("task-form").onsubmit = (e) => {
  e.preventDefault();
  const title = $("edit-title").value.trim();
  if (!title) {
    $("edit-title").setCustomValidity("Enter a task name.");
    $("edit-title").reportValidity();
    return;
  }
  if (!editingId && tasks.length >= 100) {
    notify("Maximum 100 tasks per workspace.");
    return;
  }
  const previous = tasks.find((t) => t.id === editingId);
  const task = {
    id: editingId || crypto.randomUUID(),
    title,
    duration: Number($("edit-duration").value),
    priority: $("edit-priority").value,
    deadline: $("edit-deadline").value || null,
    fixed_time: $("edit-time").value || null,
    scheduled_date: $("edit-time").value
      ? $("edit-date").value || $("plan-date").value
      : null,
    notes: $("edit-notes").value,
    completed: previous?.completed || false,
  };
  if (previous && previous.duration !== task.duration) {
    task.notes = task.notes
      .replace(/Estimated \d+ minutes; adjust if needed\.\s*/g, "")
      .trim();
  }
  if (editingId) tasks = tasks.map((t) => (t.id === editingId ? task : t));
  else tasks.push(task);
  $("task-dialog").close();
  renderTasks();
  invalidate();
};
$("edit-title").oninput = () => $("edit-title").setCustomValidity("");
$("task-list").onclick = (e) => {
  const control = e.target.closest("[data-action]");
  if (!control || busy) return;
  const id = control.closest("[data-id]").dataset.id;
  const task = tasks.find((t) => t.id === id);
  if (!task) return;
  if (control.dataset.action === "edit") openEditor(task);
  if (control.dataset.action === "delete") {
    tasks = tasks.filter((t) => t.id !== id);
    renderTasks();
    invalidate();
  }
  if (control.dataset.action === "complete") {
    task.completed = control.checked;
    renderTasks();
    invalidate();
  }
};
["plan-date", "start-time", "end-time", "focus", "break"].forEach(
  (id) =>
    ($(id).onchange = () => {
      updateDate();
      invalidate();
    }),
);
function planText() {
  return [
    `DAYLIGHT — DAILY PLAN · ${plan.date}`,
    "",
    ...plan.blocks.map(
      (b) => `${b.start}–${b.end}  ${b.title} (${b.minutes} min, ${b.kind})`,
    ),
    "",
    ...plan.unscheduled.map(
      (t) => `UNPLANNED: ${t.title} — ${t.remaining_minutes} min. ${t.reason}`,
    ),
    ...plan.warnings,
    "",
    `Planned: ${duration(plan.summary.work_minutes)} · Breaks: ${duration(plan.summary.break_minutes)} · Free: ${duration(plan.summary.free_minutes)}`,
  ].join("\n");
}
$("download").onclick = () => {
  if (!plan) return;
  const url = URL.createObjectURL(
    new Blob([planText()], { type: "text/plain;charset=utf-8" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = `daylight-${plan.date}.txt`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
$("print").onclick = () => window.print();
$("reset").onclick = () => {
  if (!confirm("Remove all tasks and the saved plan from this browser?"))
    return;
  tasks = [];
  plan = null;
  renderTasks();
  invalidate();
  notify("Workspace cleared.");
};
try {
  const data = JSON.parse(localStorage.getItem(STORAGE) || "null");
  if (
    data &&
    Array.isArray(data.tasks) &&
    data.tasks.every(
      (t) =>
        typeof t.id === "string" &&
        typeof t.title === "string" &&
        Number.isInteger(t.duration) &&
        t.duration >= 5 &&
        t.duration <= 720 &&
        ["high", "medium", "low"].includes(t.priority),
    )
  ) {
    tasks = data.tasks.slice(0, 100);
    if (data.settings) {
      const mapping = {
        "plan-date": "date",
        "start-time": "start",
        "end-time": "end",
        focus: "focus_minutes",
        break: "break_minutes",
      };
      for (const [id, key] of Object.entries(mapping))
        if (data.settings[key] !== undefined)
          $(id).value = String(data.settings[key]).slice(
            0,
            id.includes("time") ? 5 : undefined,
          );
    }
    if (
      data.plan?.summary &&
      Array.isArray(data.plan.blocks) &&
      Array.isArray(data.plan.unscheduled) &&
      Array.isArray(data.plan.warnings)
    )
      plan = data.plan;
  }
} catch {
  notify(
    "Could not restore your previous workspace. You can start a new plan.",
  );
}
updateDate();
renderTasks();
renderPlan();
