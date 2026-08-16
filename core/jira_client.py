"""
App-unabhängiger Client für die Jira Cloud REST API (v3).

Konfiguration kommt aus den Settings: JIRA_BASE_URL, JIRA_EMAIL,
JIRA_API_TOKEN, JIRA_PROJECT_KEY (Default-Projekt für create_issue).
Liegt bewusst in `core`, nicht in `fintech`, damit jede App im Projekt
(Reisen, Telegram, ...) Jira-Tickets anlegen/ergänzen kann.

Nutzung:
    from core.jira_client import JiraClient, JiraApiError

    client = JiraClient()
    issue = client.create_issue(summary="...", description="...", issue_type="Bug")
    client.add_comment(issue["key"], "Zusätzliche Info ...")
"""
import logging
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15  # Sekunden


class JiraApiError(Exception):
    """Einheitlicher Fehlertyp für Netzwerk-, Auth- und Validierungsfehler."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail=None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


def _text_to_adf(text: str) -> dict:
    """Wandelt einfachen Text (Absätze durch Leerzeile getrennt) ins Atlassian Document Format um."""
    paragraphs = text.split("\n\n") if text else [""]
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": p}] if p else [],
            }
            for p in paragraphs
        ],
    }


class JiraClient:
    """Dünner Wrapper um die Jira Cloud REST API v3 (Basic Auth mit E-Mail + API-Token)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
        project_key: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.JIRA_BASE_URL or "").rstrip("/")
        self.project_key = project_key or getattr(settings, "JIRA_PROJECT_KEY", None)
        self._auth = (email or settings.JIRA_EMAIL, api_token or settings.JIRA_API_TOKEN)

        if not self.base_url or not self._auth[0] or not self._auth[1]:
            raise JiraApiError(
                "Jira ist nicht konfiguriert (JIRA_BASE_URL/JIRA_EMAIL/JIRA_API_TOKEN fehlen)."
            )

    # ------------------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(
                method,
                url,
                auth=self._auth,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=DEFAULT_TIMEOUT,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise JiraApiError(f"Jira nicht erreichbar: {exc}") from exc

        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text
            logger.warning(f"Jira-API-Fehler {resp.status_code} bei {method} {path}: {detail}")
            raise JiraApiError(f"Jira-API-Fehler ({resp.status_code})", status_code=resp.status_code, detail=detail)

        return resp.json() if resp.content else {}

    # ------------------------------------------------------------------
    def create_issue(
        self,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
        project_key: Optional[str] = None,
        **extra_fields,
    ) -> dict:
        """
        Legt ein neues Ticket an.
        Gibt {'key': 'FIN-123', 'id': ..., 'url': 'https://.../browse/FIN-123'} zurück.
        """
        project_key = project_key or self.project_key
        if not project_key:
            raise JiraApiError("Kein Projekt angegeben (project_key fehlt und JIRA_PROJECT_KEY ist nicht gesetzt).")
        if not summary:
            raise JiraApiError("'summary' ist erforderlich.")

        fields = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
            **extra_fields,
        }
        if description:
            fields["description"] = _text_to_adf(description)

        data = self._request("POST", "/rest/api/3/issue", json={"fields": fields})
        data["url"] = f"{self.base_url}/browse/{data['key']}"
        logger.info(f"Jira-Ticket angelegt: {data['key']}")
        return data

    # ------------------------------------------------------------------
    def add_comment(self, issue_key: str, comment: str) -> dict:
        """Ergänzt ein bestehendes Ticket um einen Kommentar."""
        if not issue_key:
            raise JiraApiError("'issue_key' ist erforderlich.")
        if not comment:
            raise JiraApiError("'comment' ist erforderlich.")

        data = self._request(
            "POST",
            f"/rest/api/3/issue/{issue_key}/comment",
            json={"body": _text_to_adf(comment)},
        )
        logger.info(f"Kommentar zu Jira-Ticket {issue_key} hinzugefügt")
        return data

    # ------------------------------------------------------------------
    def get_issue(self, issue_key: str) -> dict:
        """Liest Kerninfos eines bestehenden Tickets (z. B. zur Anzeige/Validierung)."""
        return self._request(
            "GET",
            f"/rest/api/3/issue/{issue_key}",
            params={"fields": "summary,status,issuetype"},
        )

    # ------------------------------------------------------------------
    def get_transitions(self, issue_key: str) -> list:
        """Liste der aktuell verfügbaren Workflow-Übergänge für dieses Ticket."""
        data = self._request("GET", f"/rest/api/3/issue/{issue_key}/transitions")
        return data.get("transitions", [])

    def transition_issue_to_done(self, issue_key: str) -> None:
        """Setzt ein bestehendes Ticket auf den Status 'Done'. No-op falls es das bereits ist."""
        issue = self.get_issue(issue_key)
        current_status = issue.get("fields", {}).get("status", {}).get("name", "")
        if current_status.strip().lower() == "done":
            logger.info(f"Jira-Ticket {issue_key} ist bereits 'Done'")
            return

        transitions = self.get_transitions(issue_key)
        done = next(
            (
                t for t in transitions
                if t.get("name", "").strip().lower() == "done"
                or t.get("to", {}).get("name", "").strip().lower() == "done"
            ),
            None,
        )
        if not done:
            available = ", ".join(t.get("name", "?") for t in transitions) or "keine"
            raise JiraApiError(
                f"Keine 'Done'-Transition für {issue_key} verfügbar (aktueller Status "
                f"'{current_status}', verfügbare Übergänge: {available})."
            )

        self._request(
            "POST",
            f"/rest/api/3/issue/{issue_key}/transitions",
            json={"transition": {"id": done["id"]}},
        )
        logger.info(f"Jira-Ticket {issue_key} auf 'Done' gesetzt (Transition {done['id']})")

    def delete_issue(self, issue_key: str) -> None:
        """Löscht ein Ticket endgültig. Nicht rückgängig zu machen."""
        self._request("DELETE", f"/rest/api/3/issue/{issue_key}")
        logger.info(f"Jira-Ticket {issue_key} gelöscht")
