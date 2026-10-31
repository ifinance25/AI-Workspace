"""Импорт пакета прогона: zip с ``manifest.json``, ``findings.json``, снимками и PDF.

Имена в архиве сверяются с белым списком, распаковки всего архива нет. Адаптер
приводит находки к одной форме; ``qa_results_v1`` для ``results.jsonl`` появится
вместе с ``qa-platform``.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.office.delivery._scan import scan
from src.office.delivery._validation_files import sync_files
from src.office.delivery._validation_schema import (
    ValidationError,
    data_root,
    ensure,
    run_dir,
)

MAX_ARCHIVE_BYTES = 120 * 1024 * 1024
MAX_UNPACKED_BYTES = 150 * 1024 * 1024
MAX_FILES = 1000
MAX_JSON_BYTES = 8 * 1024 * 1024

_ROOT_NAMES = frozenset({"manifest.json", "findings.json"})
_ASSET_NAME = re.compile(
    r"^(img/[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.png|docs/[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.pdf)$"
)
_MAGIC = {"png": b"\x89PNG\r\n\x1a\n", "pdf": b"%PDF-"}
_MIME = {"png": "image/png", "pdf": "application/pdf"}
_KIND = {"png": "image", "pdf": "pdf"}
_RUN_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SEVERITY = {"высокая": "blocking", "средняя": "significant", "низкая": "hint"}
_REQUIRED = ("gid", "doc", "category", "severity", "summary", "evidence", "edits")
_SCAN_FIELDS = ("summary", "why", "verdict_reason")


def _reject(message: str, code: str = "bad_package") -> ValidationError:
    return ValidationError(code, message)


def _members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    infos = [i for i in archive.infolist() if not i.is_dir()]
    if len(infos) > MAX_FILES:
        raise _reject("В архиве слишком много файлов", "too_large")
    if sum(i.file_size for i in infos) > MAX_UNPACKED_BYTES:
        raise _reject("Распакованный архив слишком велик", "too_large")
    seen: set[str] = set()
    for info in infos:
        name = info.filename
        if name in seen:
            raise _reject("В архиве повторяются имена файлов")
        seen.add(name)
        if name not in _ROOT_NAMES and not _ASSET_NAME.match(name):
            raise _reject("В архиве есть файл вне разрешённого списка")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise _reject("Символические ссылки в архиве запрещены")
        if name in _ROOT_NAMES and info.file_size > MAX_JSON_BYTES:
            raise _reject("Файл JSON слишком велик", "too_large")
    if not _ROOT_NAMES <= seen:
        raise _reject("В архиве нет manifest.json или findings.json")
    return infos


def _read_capped(archive: zipfile.ZipFile, info: zipfile.ZipInfo, cap: int) -> bytes:
    """Читает не больше заявленного: заголовок архива мог солгать о размере."""
    with archive.open(info) as stream:
        data = stream.read(cap + 1)
    if len(data) > cap:
        raise _reject("Файл в архиве больше заявленного", "too_large")
    return data


def _load_json(archive: zipfile.ZipFile, name: str) -> Any:
    raw = _read_capped(archive, archive.getinfo(name), MAX_JSON_BYTES)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _reject(f"{name} не разобран") from exc


def _reason_key(item: dict) -> str:
    blocks = sorted(str(e.get("block") or "") for e in item["evidence"])
    edits = sorted(f"{e.get('block')}|{e.get('col')}" for e in item["edits"])
    raw = json.dumps([item["doc"], item["category"], blocks, edits], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _doc_review_v1(items: Any) -> list[dict]:
    """Сверка документов: у находки нет сценария, класс ``document_defect``."""
    if not isinstance(items, list) or not items:
        raise _reject("Список находок пуст")
    out = []
    for item in items:
        if not isinstance(item, dict) or any(k not in item for k in _REQUIRED):
            raise _reject("У находки нет обязательных полей")
        if item["severity"] not in _SEVERITY:
            raise _reject("Неизвестная важность находки")
        if not isinstance(item["edits"], list) or not isinstance(item["evidence"], list):
            raise _reject("Правки и цитаты должны быть списками")
        out.append({**item, "defect_class": "document_defect", "reason_key": _reason_key(item)})
    return out


ADAPTERS: dict[str, Callable[[Any], list[dict]]] = {"doc_review_v1": _doc_review_v1}


def _check_scan(findings: list[dict]) -> None:
    for item in findings:
        texts = [str(item.get(k) or "") for k in _SCAN_FIELDS]
        for edit in item["edits"]:
            texts += [str(edit.get(k) or "") for k in ("old", "new", "comment")]
        texts += [str(e.get("quote") or "") for e in item["evidence"]]
        hits = sorted({h for t in texts for h in scan(t)})
        if hits:
            message = f"Сканер отклонил находку {item['gid']}: {', '.join(hits)}"
            raise _reject(message, "scan_failed")


def _check_refs(findings: list[dict], names: set[str]) -> None:
    for item in findings:
        for entry in [*item["evidence"], *(item.get("marked") or [])]:
            image = entry.get("img")
            if image and f"img/{image}" not in names:
                raise _reject(f"У находки {item['gid']} нет снимка в архиве")


def _unpack(archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo], target: Path) -> list[dict]:
    assets = []
    for info in infos:
        if info.filename in _ROOT_NAMES:
            continue
        ext = info.filename.rsplit(".", 1)[1]
        data = _read_capped(archive, info, info.file_size)
        if not data.startswith(_MAGIC[ext]):
            raise _reject("Содержимое файла не совпадает с расширением")
        path = target / info.filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        assets.append({
            "kind": _KIND[ext],
            "name": Path(info.filename).name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
            "mime": _MIME[ext],
        })
    return assets


def _insert_run(
    conn: Any, project_id: int, manifest: dict, sha: str, actor_id: int, at: str
) -> int:
    return conn.execute(
        "INSERT INTO office_validation_runs (project_id, run_key, source_kind, title, "
        "schema_version, package_sha, stand_version, imported_by, imported_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (project_id, manifest["run_key"], manifest["source_kind"], str(manifest.get("title") or ""),
         manifest["schema_version"], sha, manifest.get("stand_version"), actor_id, at),
    ).lastrowid


def _insert_finding(conn: Any, project_id: int, run_id: int, item: dict) -> None:
    finding_id = conn.execute(
        "INSERT INTO office_validation_findings (run_id, project_id, gid, source_id, "
        "defect_class, doc, category, severity_raw, severity, reason_key, llm_verdict, "
        "llm_verdict_reason, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, project_id, item["gid"], str(item.get("source_id") or ""), item["defect_class"],
         item["doc"], item["category"], item["severity"], _SEVERITY[item["severity"]],
         item["reason_key"], str(item.get("verdict") or ""), str(item.get("verdict_reason") or ""),
         json.dumps({k: v for k, v in item.items() if k != "edits"}, ensure_ascii=False)),
    ).lastrowid
    for ordinal, edit in enumerate(item["edits"], 1):
        conn.execute(
            "INSERT INTO office_validation_edits (finding_id, ordinal, edit_key, doc, block, "
            "col, place, old_text, new_text, comment) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (finding_id, ordinal, f"EDIT-{item['gid']}-{ordinal:02d}", str(edit.get("doc") or ""),
             str(edit.get("block") or ""), str(edit.get("col") or ""),
             str(edit.get("place") or ""), str(edit.get("old") or ""),
             str(edit.get("new") or ""), str(edit.get("comment") or "")),
        )


def _manifest(archive: zipfile.ZipFile) -> dict:
    manifest = _load_json(archive, "manifest.json")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise _reject("Неизвестная версия пакета")
    if manifest.get("adapter") not in ADAPTERS:
        raise _reject("Неизвестный адаптер пакета")
    if manifest.get("source_kind") not in ("doc_review", "stand_run"):
        raise _reject("Неизвестный вид источника")
    if not _RUN_KEY.match(str(manifest.get("run_key") or "")):
        raise _reject("Недопустимый ключ прогона")
    return manifest


def _existing(store: Any, project_id: int, run_key: str, sha: str) -> dict | None:
    with store._lock:
        row = store._connection().execute(
            "SELECT id, package_sha FROM office_validation_runs "
            "WHERE project_id = ? AND run_key = ?",
            (project_id, run_key),
        ).fetchone()
    if row is None:
        return None
    if row["package_sha"] != sha:
        raise _reject("Прогон с таким ключом уже загружен с другим содержимым", "run_conflict")
    return {"run_id": row["id"], "run_key": run_key, "duplicate": True}


def import_package(store: Any, project_id: int, path: Path, *, actor_id: int) -> dict:
    """Загрузить пакет. Повтор того же пакета ничего не меняет."""
    ensure(store)
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise _reject("Архив слишком велик", "too_large")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise _reject("Файл не является архивом zip") from exc
    with archive:
        infos = _members(archive)
        manifest = _manifest(archive)
        found = _existing(store, project_id, manifest["run_key"], sha)
        if found is not None:
            return found
        findings = ADAPTERS[manifest["adapter"]](_load_json(archive, "findings.json"))
        _check_refs(findings, {i.filename for i in infos})
        _check_scan(findings)
        tmp = data_root(store) / f"p{int(project_id)}" / f".tmp-{uuid.uuid4().hex}"
        tmp.mkdir(parents=True)
        try:
            assets = _unpack(archive, infos, tmp)
            run_id = _commit(store, project_id, manifest, sha, findings, assets, tmp, actor_id)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    sync_files(store, project_id, run_id)
    return {"run_id": run_id, "run_key": manifest["run_key"], "duplicate": False,
            "findings": len(findings), "assets": len(assets)}


def _commit(
    store: Any, project_id: int, manifest: dict, sha: str, findings: list[dict],
    assets: list[dict], tmp: Path, actor_id: int,
) -> int:
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with store._lock:
        conn = store._connection()
        conn.execute("BEGIN IMMEDIATE")
        target = None
        try:
            run_id = _insert_run(conn, project_id, manifest, sha, actor_id, at)
            for item in findings:
                _insert_finding(conn, project_id, run_id, item)
            for asset in assets:
                conn.execute(
                    "INSERT INTO office_validation_assets (run_id, kind, name, sha256, size, mime) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (run_id, asset["kind"], asset["name"], asset["sha256"], asset["size"],
                     asset["mime"]),
                )
            target = run_dir(store, project_id, run_id)
            tmp.rename(target)
            conn.commit()
        except Exception:
            conn.rollback()
            if target is not None:
                shutil.rmtree(target, ignore_errors=True)
            raise
    return run_id
