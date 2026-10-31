from django import forms
from django.contrib import admin
from django.db import models

from .models import Task, TaskRun


class SubTaskInline(admin.TabularInline):
    model = Task
    fk_name = 'parent'
    fields = ('position', 'name', 'executor', 'active')
    show_change_link = True
    extra = 0


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('name', 'executor', 'parent', 'position', 'interval_hours', 'active')
    list_editable = ('position', 'active')
    list_filter = ('executor', 'active')
    search_fields = ('name', 'prompt')
    inlines = [SubTaskInline]
    formfield_overrides = {models.TextField: {'widget': forms.Textarea(attrs={'rows': 30, 'cols': 120})}}


@admin.register(TaskRun)
class TaskRunAdmin(admin.ModelAdmin):
    list_display = ('task', 'status', 'started_at', 'finished_at')
    list_filter = ('status', 'task')
    date_hierarchy = 'started_at'
