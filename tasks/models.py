from django.db import models
from django.utils import timezone


class Task(models.Model):
    """Zentrale Registry aller wiederkehrenden Aufgaben (Server-Jobs und Claude-Prompts), Cowork holt
    die Prompts per MCP (get_tasks/get_task). Sub-Tasks über parent + position."""

    class Executor(models.TextChoices):
        SERVER = 'server', 'Server (Management-Command)'
        COWORK = 'cowork', 'Claude Cowork'
        CLOUD = 'cloud', 'Claude Cloud-Routine'

    name = models.CharField(max_length=200, unique=True)
    prompt = models.TextField('Claude-Prompt / Beschreibung', blank=True)
    executor = models.CharField(max_length=10, choices=Executor.choices, default=Executor.COWORK)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='subtasks',
                               help_text='Leer = Haupt-Task')
    position = models.PositiveIntegerField(default=0, help_text='Reihenfolge (innerhalb des Parents)')
    interval_hours = models.PositiveIntegerField('Intervall (Stunden)', null=True, blank=True,
                                                 help_text='Erwarteter Abstand zwischen Läufen, leer = kein Health-Check')
    parameters = models.JSONField('Parameter', default=dict, blank=True,
                                  help_text='Ausführungsparameter als JSON, z. B. {"parallel": 4}')
    active = models.BooleanField('Aktiv', default=True)

    class Meta:
        ordering = ['position', 'id']

    def __str__(self):
        return self.name


class TaskRun(models.Model):
    """Ein Lauf eines Tasks (Log und Grundlage für den Health-Check)."""

    class Status(models.TextChoices):
        RUNNING = 'running', 'Läuft'
        SUCCESS = 'success', 'Erfolgreich'
        ERROR = 'error', 'Fehler'
        TIMEOUT = 'timeout', 'Timeout'

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='runs')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField('Start', default=timezone.now)
    finished_at = models.DateTimeField('Ende', null=True, blank=True)
    message = models.TextField('Meldung', blank=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Task-Lauf'
        verbose_name_plural = 'Task-Läufe'
        indexes = [models.Index(fields=['task', '-started_at'], name='tasks_run_task_started')]

    def __str__(self):
        return f'{self.task} {self.started_at:%d.%m.%Y %H:%M} ({self.get_status_display()})'
