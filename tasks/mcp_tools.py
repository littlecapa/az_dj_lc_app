"""MCP-Tools für die zentrale Task-Registry — werden in die bestehenden MCP-Server eingehängt
(z. B. leisure.mcp_server), damit Cowork die Prompts über die schon konfigurierte URL bekommt."""

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Task, TaskRun


def _summary(task):
    return {"name": task.name, "executor": task.executor,
            "parent": task.parent.name if task.parent else None, "prompt": task.prompt}


def _tasks(args):
    tasks = [_summary(t) for t in Task.objects.filter(active=True).select_related("parent")]
    return 200, {"count": len(tasks), "tasks": tasks}


def _task(args):
    task = Task.objects.filter(active=True, name__iexact=args["name"].strip()).select_related("parent").first()
    if task is None:
        names = list(Task.objects.filter(active=True).values_list("name", flat=True))
        return 404, {"error": f"Unknown task: {args['name']}", "available": names}
    subtasks = [_summary(t) for t in task.subtasks.filter(active=True)]
    return 200, {**_summary(task), "parameters": task.parameters, "subtasks": subtasks}


TASK_TOOLS = {
    "get_tasks": {
        "title": "Tasks",
        "description": "All active predefined tasks (unique name, executor, parent task and the Claude prompt).",
        "inputSchema": {"type": "object", "properties": {}},
        "run": _tasks,
    },
    "get_task": {
        "title": "Task",
        "description": "One predefined task looked up by its name (case-insensitive): Claude prompt, parameters "
                       "and sub-tasks in execution order. Execute the returned prompt.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Task name, e.g. 'Alle Künstler auslesen'"}},
            "required": ["name"],
        },
        "run": _task,
    },
}


def _log_task_run(args):
    task = Task.objects.filter(active=True, name__iexact=args["task"].strip()).exclude(executor=Task.Executor.SERVER).first()
    if task is None:
        return 404, {"error": f"Unknown or server-side task: {args['task']}"}
    if args["status"] not in (TaskRun.Status.SUCCESS, TaskRun.Status.ERROR):
        return 400, {"error": "'status' must be 'success' or 'error'"}
    now = timezone.now()
    try:
        started_at = parse_datetime(args["started_at"]) if args.get("started_at") else None
    except ValueError:
        started_at = None
    if started_at is None or started_at > now:
        started_at = now
    run = TaskRun.objects.create(task=task, status=args["status"], started_at=started_at, finished_at=now,
                                 message=(args.get("message") or "")[:2000])
    return 200, {"task": task.name, "status": run.status, "logged_at": now.isoformat()}


TASK_WRITE_TOOLS = {
    "log_task_run": {
        "title": "Log task run",
        "description": "Report the result of a predefined Claude task (call once at the end of every run, also on "
                       "failure). Shown on the owner's task health page.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Task name as returned by get_task"},
                "status": {"type": "string", "enum": ["success", "error"]},
                "message": {"type": "string", "description": "Short result, e.g. '3 neue Vorschläge, 2 übersprungen'"},
                "started_at": {"type": "string", "format": "date-time", "description": "Optional ISO start time"},
            },
            "required": ["task", "status"],
        },
        "run": _log_task_run,
    },
}
