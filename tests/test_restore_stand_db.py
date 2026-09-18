"""restore_stand_db.sh: дамп обязателен, на сервер скрипт не ходит."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
RESTORE = REPO_ROOT / "scripts" / "restore_stand_db.sh"


def _run(env: dict[str, str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    merged = {**os.environ, **env, "STAND_SKIP_STOP": "1"}
    return subprocess.run(
        ["bash", str(RESTORE)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd or REPO_ROOT,
        env=merged,
    )


class RestoreStandDbTests(unittest.TestCase):
    def test_missing_dump_exits_without_touching_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "dumps").mkdir(parents=True)
            proc = _run({"STAND_ROOT": str(root), "STAND_DUMP_DIR": str(root / "data" / "dumps")})
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("Нет дампа БД", proc.stderr)
        self.assertIn("fetch_stand_dump.sh", proc.stderr)
        self.assertNotIn("scp", proc.stderr)
        self.assertNotIn("ssh ", proc.stderr)

    def test_restore_copies_dump_to_working_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dumps = root / "data" / "dumps"
            dumps.mkdir(parents=True)
            src = dumps / "sessions.latest.db"
            with sqlite3.connect(src) as conn:
                conn.execute("CREATE TABLE ping (id INTEGER PRIMARY KEY)")
                conn.execute("INSERT INTO ping (id) VALUES (7)")
                conn.commit()
            target = root / "data" / "sessions.db"
            proc = _run(
                {
                    "STAND_ROOT": str(root),
                    "STAND_DUMP_DIR": str(dumps),
                    "STAND_DB_PATH": str(target),
                }
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertTrue(target.exists())
            with sqlite3.connect(target) as conn:
                row = conn.execute("SELECT id FROM ping").fetchone()
            self.assertEqual(row[0], 7)

    def test_restore_remaps_prod_paths_and_mkdirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dumps = root / "data" / "dumps"
            dumps.mkdir(parents=True)
            src = dumps / "sessions.latest.db"
            prod_a = "/var/lib/ai-workspace/projects/AI_Sales_Assistant"
            prod_b = "/var/lib/ai-workspace/projects/Общий"
            with sqlite3.connect(src) as conn:
                conn.execute(
                    """
                    CREATE TABLE projects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        abspath TEXT NOT NULL UNIQUE
                    )
                    """
                )
                conn.execute(
                    "CREATE TABLE user_project_access ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER, project_id INTEGER, "
                    "project_path TEXT NOT NULL, access_level TEXT)"
                )
                conn.execute(
                    "INSERT INTO projects (id, name, abspath) VALUES (7, ?, ?)",
                    ("AI_Sales_Assistant", prod_a),
                )
                conn.execute(
                    "INSERT INTO projects (id, name, abspath) VALUES (9, ?, ?)",
                    ("Общий", prod_b),
                )
                conn.execute(
                    "INSERT INTO user_project_access "
                    "(user_id, project_id, project_path, access_level) "
                    "VALUES (1, 7, ?, 'full')",
                    (prod_a,),
                )
                conn.commit()
            local_root = root / "local-projects"
            target = root / "data" / "sessions.db"
            env = {
                "STAND_ROOT": str(root),
                "STAND_DUMP_DIR": str(dumps),
                "STAND_DB_PATH": str(target),
                "STAND_PROJECTS_DIR": str(local_root),
            }
            proc = _run(env)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertIn("Remap: 2 project path(s)", proc.stdout)
            with sqlite3.connect(src) as conn:
                dumped = {
                    r[0] for r in conn.execute("SELECT abspath FROM projects")
                }
            self.assertEqual(dumped, {prod_a, prod_b})
            with sqlite3.connect(target) as conn:
                rows = list(conn.execute("SELECT id, name, abspath FROM projects ORDER BY id"))
                grant = conn.execute(
                    "SELECT project_path FROM user_project_access"
                ).fetchone()[0]
            self.assertEqual(rows[0][2], str(local_root / "AI_Sales_Assistant"))
            self.assertEqual(rows[1][2], str(local_root / "Общий"))
            self.assertEqual(grant, str(local_root / "AI_Sales_Assistant"))
            self.assertTrue((local_root / "AI_Sales_Assistant").is_dir())
            self.assertTrue((local_root / "Общий").is_dir())
            proc2 = _run(env)
            self.assertEqual(proc2.returncode, 0, proc2.stderr + proc2.stdout)
            with sqlite3.connect(target) as conn:
                again = conn.execute(
                    "SELECT abspath FROM projects WHERE id = 7"
                ).fetchone()[0]
            self.assertEqual(again, str(local_root / "AI_Sales_Assistant"))

    def test_fetch_refuses_without_explicit_flag(self) -> None:
        fetch = REPO_ROOT / "scripts" / "fetch_stand_dump.sh"
        proc = subprocess.run(
            ["bash", str(fetch)],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            cwd=REPO_ROOT,
            env={**os.environ, "STAND_DUMP_SSH": "nobody@example.invalid"},
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("только по явной просьбе", proc.stderr)


if __name__ == "__main__":
    unittest.main()
