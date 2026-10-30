"""HTTP к Redmine. Ключ читается из ``REDMINE_API_KEY`` и в ответы не попадает."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from src.office.redmine_mirror._mirror import MirrorError, RedmineUnavailableError

_KEY = "REDMINE_API_KEY"


class HttpRedmine:
    def __init__(self, base_url: str, api_key: str):
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise MirrorError("unavailable", "Адрес Redmine не задан")
        self._base = base_url.rstrip("/")
        self._key = api_key

    def __repr__(self) -> str:
        return f"HttpRedmine(base_url={self._base!r})"

    def _call(self, method: str, path: str, query: dict | None = None, payload: dict | None = None):
        url = self._base + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"X-Redmine-API-Key": self._key, "Accept": "application/json"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RedmineUnavailableError("Redmine не ответил") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RedmineUnavailableError("Redmine не ответил") from exc

    def list_issues(self, project: str) -> list[dict]:
        offset = 0
        limit = 100
        found: list[dict] = []
        while True:
            page = self._call(
                "GET",
                "/issues.json",
                {
                    "project_id": project,
                    "status_id": "*",
                    "limit": limit,
                    "offset": offset,
                    "include": "journals",
                },
            )
            batch = page.get("issues") or []
            found.extend(batch)
            total = int(page.get("total_count") or len(found))
            offset += limit
            if offset >= total or not batch:
                break
        return found

    def get_issue(self, issue_id: int) -> dict:
        page = self._call("GET", f"/issues/{int(issue_id)}.json", {"include": "journals"})
        issue = page.get("issue")
        if not isinstance(issue, dict):
            raise RedmineUnavailableError("Redmine не ответил")
        return issue

    def create_issue(self, project: str, fields: dict) -> dict:
        body = {"issue": {"project_id": project, **fields}}
        return self._call("POST", "/issues.json", payload=body)

    def update_issue(self, issue_id: int, fields: dict) -> None:
        self._call("PUT", f"/issues/{int(issue_id)}.json", payload={"issue": fields})

    def get_user(self, user_id: int) -> dict:
        try:
            page = self._call("GET", f"/users/{int(user_id)}.json")
        except RedmineUnavailableError:
            return {}
        user = page.get("user") or {}
        name = user.get("name") or " ".join(
            part for part in (user.get("firstname"), user.get("lastname")) if part
        )
        return {"id": user.get("id", user_id), "login": user.get("login") or "", "name": name}


def open_client(base_url: str) -> HttpRedmine:
    key = os.environ.get(_KEY, "")
    if not key:
        raise MirrorError("no_key", "Ключ Redmine не задан")
    return HttpRedmine(base_url, key)
