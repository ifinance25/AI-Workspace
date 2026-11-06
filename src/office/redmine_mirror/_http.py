"""HTTP к Redmine. Ключ читается из ``REDMINE_API_KEY`` и в ответы не попадает.

Редиректы не выполняются: стандартный обработчик ``urllib`` переносит заголовок
``X-Redmine-API-Key`` на новый адрес, в том числе чужой хост (У43-05). Адрес
только https, http допустим лишь на петлевой адрес.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from src.office.redmine_mirror._account import url_allowed
from src.office.redmine_mirror._mirror import MirrorError, RedmineUnavailableError

_KEY = "REDMINE_API_KEY"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Любой 3xx это ошибка, а не переход: ключ на другой адрес не отправляется."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


class HttpRedmine:
    def __init__(self, base_url: str, api_key: str):
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise MirrorError("unavailable", "Адрес Redmine не задан")
        if not url_allowed(base_url):
            raise MirrorError(
                "bad_url", "Адрес Redmine должен начинаться с https:// (http только для 127.0.0.1)"
            )
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._project_ids: dict[str, str] = {}

    def _resolve_project_id(self, project: str) -> str:
        """Redmine принимает id или identifier; имя проекта из UI сопоставляем через /projects.json."""
        key = str(project or "").strip()
        if not key:
            return key
        cached = self._project_ids.get(key)
        if cached:
            return cached
        if key.isdigit():
            self._project_ids[key] = key
            return key
        offset = 0
        limit = 100
        while True:
            page = self._call("GET", "/projects.json", {"limit": limit, "offset": offset})
            batch = page.get("projects") or []
            for row in batch:
                ident = str(row.get("identifier") or "")
                name = str(row.get("name") or "")
                pid = str(row.get("id") or "")
                resolved = ident or pid
                for label in (ident, name, pid):
                    if label:
                        self._project_ids.setdefault(label, resolved)
                if key in (ident, name, pid):
                    self._project_ids[key] = resolved
                    return resolved
            total = int(page.get("total_count") or len(batch))
            offset += limit
            if offset >= total or not batch:
                break
        self._project_ids[key] = key
        return key

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
            with _OPENER.open(request, timeout=20) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            if 300 <= exc.code < 400:
                raise RedmineUnavailableError(
                    "Redmine перенаправляет запрос на другой адрес: ключ туда не отправлен"
                ) from exc
            raise RedmineUnavailableError("Redmine не ответил") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RedmineUnavailableError("Redmine не ответил") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RedmineUnavailableError("Redmine не ответил") from exc

    def list_issues(
        self,
        project: str,
        *,
        updated_since: datetime | None = None,
    ) -> list[dict]:
        project_id = self._resolve_project_id(project)
        offset = 0
        limit = 100
        found: list[dict] = []
        while True:
            query: dict[str, str | int] = {
                "project_id": project_id,
                "status_id": "*",
                "limit": limit,
                "offset": offset,
                "include": "journals",
            }
            if updated_since is not None:
                ts = updated_since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                query["updated_on"] = f">={ts}"
            page = self._call("GET", "/issues.json", query)
            batch = page.get("issues") or []
            found.extend(batch)
            total = int(page.get("total_count") or len(found))
            offset += limit
            if offset >= total or not batch:
                break
        return found

    def list_issue_ids(self, project: str) -> set[int]:
        """Номера всех задач проекта без journals (для сверки удалённых в Redmine)."""
        project_id = self._resolve_project_id(project)
        offset = 0
        limit = 100
        ids: set[int] = set()
        while True:
            page = self._call(
                "GET",
                "/issues.json",
                {
                    "project_id": project_id,
                    "status_id": "*",
                    "limit": limit,
                    "offset": offset,
                },
            )
            batch = page.get("issues") or []
            for row in batch:
                try:
                    ids.add(int(row["id"]))
                except (KeyError, TypeError, ValueError):
                    continue
            total = int(page.get("total_count") or len(batch))
            offset += limit
            if offset >= total or not batch:
                break
        return ids

    def get_issue(self, issue_id: int) -> dict:
        page = self._call("GET", f"/issues/{int(issue_id)}.json", {"include": "journals"})
        issue = page.get("issue")
        if not isinstance(issue, dict):
            raise RedmineUnavailableError("Redmine не ответил")
        return issue

    def create_issue(self, project: str, fields: dict) -> dict:
        project_id = self._resolve_project_id(project)
        body = {"issue": {"project_id": project_id, **fields}}
        return self._call("POST", "/issues.json", payload=body)

    def upload_attachment(self, path: Path, filename: str | None = None) -> str:
        file_path = Path(path)
        name = filename or file_path.name
        url = self._base + "/uploads.json?" + urllib.parse.urlencode({"filename": name})
        headers = {
            "X-Redmine-API-Key": self._key,
            "Accept": "application/json",
            "Content-Type": "application/octet-stream",
        }
        data = file_path.read_bytes()
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with _OPENER.open(request, timeout=120) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise RedmineUnavailableError("Redmine не принял вложение") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RedmineUnavailableError("Redmine не ответил") from exc
        try:
            page = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RedmineUnavailableError("Redmine не ответил") from exc
        token = (page.get("upload") or {}).get("token")
        if not token:
            raise RedmineUnavailableError("Redmine не вернул token вложения")
        return str(token)

    def create_relation(self, issue_id: int, issue_to_id: int, relation_type: str = "relates") -> None:
        if issue_to_id == issue_id:
            return
        self._call(
            "POST",
            f"/issues/{int(issue_id)}/relations.json",
            payload={"relation": {"issue_to_id": int(issue_to_id), "relation_type": relation_type}},
        )

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
