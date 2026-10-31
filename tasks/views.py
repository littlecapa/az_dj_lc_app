from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, render

from .health import LABELS, task_health
from .models import Task

WEEKDAYS = 'Mo Di Mi Do Fr Sa So'.split()


def _row(task):
    status, last, last_success = task_health(task)
    return {'task': task, 'status': status, 'label': LABELS[status], 'last': last, 'last_success': last_success,
            'days': ' '.join(WEEKDAYS[int(d)] for d in task.run_days if d.isdigit() and int(d) < 7)}


@staff_member_required
def task_list(request):
    tasks = Task.objects.filter(active=True).select_related('parent')
    rows = [_row(t) for t in tasks]
    rows.sort(key=lambda r: (r['task'].parent.name if r['task'].parent else r['task'].name, r['task'].parent is not None,
                             r['task'].position))
    return render(request, 'tasks/task_list.html', {'rows': rows})


@staff_member_required
def task_detail(request, pk):
    task = get_object_or_404(Task, pk=pk)
    return render(request, 'tasks/task_detail.html', {'row': _row(task), 'runs': task.runs.all()[:50]})
