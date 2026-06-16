# providers/github.py
# ─────────────────────────────────────────────
# Parses GitHub webhook payloads
# ─────────────────────────────────────────────

from .base import BaseProvider


class GitHubProvider(BaseProvider):

    def parse(self, payload: dict) -> dict:
        # GitHub puts event type in header
        # We detect from payload content instead

        event_type = self._detect_event(payload)
        repo = payload.get("repository", {})\
                      .get("full_name", "unknown")
        sender = payload.get("sender", {})\
                        .get("login", "unknown")

        return {
            "event_type": event_type,
            "readable": self._get_readable(
                event_type, payload, repo, sender
            ),
            "metadata": {
                "repository": repo,
                "sender": sender,
                "ref": payload.get("ref"),
                "commits": len(payload.get("commits", [])),
                "action": payload.get("action"),
            }
        }

    def _detect_event(self, payload: dict) -> str:
        """Detect event type from payload structure"""
        if "commits" in payload:
            return "push"
        if "pull_request" in payload:
            action = payload.get("action", "")
            return f"pull_request.{action}"
        if "issue" in payload:
            action = payload.get("action", "")
            return f"issues.{action}"
        if "release" in payload:
            return "release"
        if "workflow_run" in payload:
            return "workflow_run"
        return "unknown"

    def _get_readable(
        self,
        event: str,
        payload: dict,
        repo: str,
        sender: str
    ) -> str:
        commits = len(payload.get("commits", []))
        branch = payload.get("ref", "").replace(
            "refs/heads/", ""
        )
        action = payload.get("action", "")
        pr = payload.get("pull_request", {})

        messages = {
            "push":
                f" {sender} pushed {commits} commit(s) to {branch} in {repo}",

            "pull_request.opened":
                f" {sender} opened PR: {pr.get('title', '')} in {repo}",

            "pull_request.closed":
                f" PR merged/closed in {repo} by {sender}",

            "pull_request.merged":
                f" PR merged into {repo}",

            "issues.opened":
                f" New issue opened in {repo} by {sender}",

            "issues.closed":
                f" Issue closed in {repo}",

            "release":
                f" New release published in {repo}",
        }

        return messages.get(
            event, f" GitHub event: {event} in {repo}"
        )


class GenericProvider(BaseProvider):
    """For unknown providers — basic parsing"""

    def parse(self, payload: dict) -> dict:
        return {
            "event_type": payload.get(
                "event",
                payload.get("type", "webhook")
            ),
            "readable": " Webhook received",
            "metadata": {}
        }