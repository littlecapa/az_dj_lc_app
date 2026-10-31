"""MCP-Tools für die zentrale Task-Registry — werden in die bestehenden MCP-Server eingehängt
(z. B. events.mcp_server), damit Cowork die Prompts über die schon konfigurierte URL bekommt."""

from .models import Task


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
