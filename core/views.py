import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache

from .jira_client import JiraClient, JiraApiError

logger = logging.getLogger(__name__)

JIRA_ISSUE_TYPES = ["Task", "Bug", "Story", "Feature", "Epic"]


@never_cache
@login_required
def jira_page(request):
    """Seite zum Anlegen neuer Jira-Tickets und Ergänzen bestehender per Kommentar."""
    if request.method == "POST":
        form_type = request.POST.get("form_type")

        try:
            client = JiraClient()
        except JiraApiError as exc:
            request.session["jira_result"] = {"ok": False, "message": str(exc)}
            return redirect("core:jira")

        if form_type == "create":
            summary = request.POST.get("summary", "").strip()
            description = request.POST.get("description", "").strip()
            issue_type = request.POST.get("issue_type", "Task").strip()
            project_key = request.POST.get("project_key", "").strip() or None

            if not summary:
                request.session["jira_result"] = {
                    "ok": False, "message": "Zusammenfassung darf nicht leer sein.",
                }
                return redirect("core:jira")

            try:
                issue = client.create_issue(
                    summary=summary,
                    description=description,
                    issue_type=issue_type,
                    project_key=project_key,
                )
                request.session["jira_result"] = {
                    "ok": True,
                    "message": f"Ticket {issue['key']} angelegt.",
                    "key": issue["key"],
                    "url": issue["url"],
                }
            except JiraApiError as exc:
                logger.warning(f"Jira create_issue fehlgeschlagen: {exc}")
                request.session["jira_result"] = {
                    "ok": False, "message": str(exc), "detail": str(exc.detail) if exc.detail else None,
                }

        elif form_type == "comment":
            issue_key = request.POST.get("issue_key", "").strip().upper()
            comment = request.POST.get("comment", "").strip()

            if not issue_key or not comment:
                request.session["jira_result"] = {
                    "ok": False, "message": "Ticket-Key und Kommentar sind erforderlich.",
                }
                return redirect("core:jira")

            try:
                client.add_comment(issue_key, comment)
                request.session["jira_result"] = {
                    "ok": True,
                    "message": f"Kommentar zu {issue_key} hinzugefügt.",
                    "key": issue_key,
                    "url": f"{client.base_url}/browse/{issue_key}",
                }
            except JiraApiError as exc:
                logger.warning(f"Jira add_comment fehlgeschlagen: {exc}")
                request.session["jira_result"] = {
                    "ok": False, "message": str(exc), "detail": str(exc.detail) if exc.detail else None,
                }

        return redirect("core:jira")

    result = request.session.pop("jira_result", None)
    return render(request, "core/jira.html", {
        "result": result,
        "issue_types": JIRA_ISSUE_TYPES,
        "default_project_key": getattr(settings, "JIRA_PROJECT_KEY", ""),
    })
