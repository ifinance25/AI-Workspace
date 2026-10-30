"""Страж: секреты панели не попадают в подпроцессы.

Утечка KB_MCP_KEY случилась потому, что окружение строилось по маске секретов, а
маска не знала нового имени, и потому, что запуск без env= молча наследует всё.
Здесь закреплены оба правила: разбор кода и настоящие запуски с новым именем.

Исключение из правила добавляется только сюда, в EXCEPTIONS, с причиной.
"""
from __future__ import annotations

import ast
import dataclasses
import json
import os
from pathlib import Path

import pytest

from src.child_env import (
    ALLOWED_NAMES,
    CLAUDE_AUTH_NAMES,
    CLAUDE_SETTING_NAMES,
    child_env,
    claude_env,
    connection_env,
)
from src.claude import commands
from src.claude.bridge import ClaudeBridge
from src.web import doc_preview
from tests.spawn_audit import spawn_audit, violations_during  # noqa: F401
from tests.test_bridge_env_scrub import _stub_cli

REPO = Path(__file__).resolve().parents[1]
SCANNED = (REPO / "src", REPO / "scripts")

# Запуски, которым разрешено идти без общей функции окружения: (файл, функция): причина.
EXCEPTIONS: dict[tuple[str, str], str] = {}

ENV_FUNCTIONS = {"child_env", "claude_env", "_spawn_env", "connection_env"}
CLAUDE_ENV_FUNCTIONS = {"claude_env", "_spawn_env"}
OPTIONS_CALLS = {"options_cls", "ClaudeAgentOptions"}
# Параметры запуска stdio-сервера MCP: процесс запускает библиотека mcp, env берётся отсюда.
MCP_STDIO_CALLS = {"StdioServerParameters"}
# Запуск SDK без options берёт окружение по умолчанию, то есть весь os.environ.
SDK_ENTRY_CALLS = {"query", "query_fn", "ClaudeSDKClient"}
# Методы цикла событий и модули, которыми процесс запускается мимо subprocess.
LOOP_SPAWN_METHODS = {"subprocess_exec", "subprocess_shell"}
FORBIDDEN_MODULES = {"multiprocessing", "concurrent.futures.process"}
SPAWN_MODULES = {"subprocess", "asyncio.subprocess", "pty", "multiprocessing"}

# Модуль → имена функций запуска. Функции, куда нельзя передать env, тоже в списке:
# страж для них всегда срабатывает, остаётся только исключение с причиной.
SPAWNERS = {
    "subprocess": {
        "run",
        "Popen",
        "check_output",
        "check_call",
        "call",
        "getoutput",
        "getstatusoutput",
    },
    "asyncio": {"create_subprocess_exec", "create_subprocess_shell"},
    "asyncio.subprocess": {"create_subprocess_exec", "create_subprocess_shell"},
    "os": {
        "system",
        "popen",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "posix_spawn",
        "posix_spawnp",
        "startfile",
        "fork",
        "forkpty",
    },
    "pty": {"spawn", "fork"},
    "anyio": {"run_process", "open_process"},
}
HELPERS_TAKING_FUNCTION = {"to_thread", "run_in_executor", "partial"}


@dataclasses.dataclass(frozen=True)
class Finding:
    function: str
    line: int
    spawner: str
    problem: str


class _Scanner(ast.NodeVisitor):
    def __init__(self) -> None:
        self.modules: dict[str, str] = {}
        self.functions: dict[str, tuple[str, str]] = {}
        self.sdk_names: set[str] = {"query_fn"}
        self.stdio_names: set[str] = set(MCP_STDIO_CALLS)
        self.dicts: dict[str, ast.Dict] = {}
        self.stack: list[str] = []
        self.findings: list[Finding] = []
        self.spawns = 0
        self.seen_as_call: set[int] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name in FORBIDDEN_MODULES:
                self._report(node, alias.name, "модуль запуска процессов мимо общей функции")
            if alias.name in SPAWNERS:
                self.modules[alias.asname or alias.name.split(".")[0]] = alias.name
            if alias.name == "claude_agent_sdk":
                self.modules[alias.asname or alias.name] = "claude_agent_sdk"

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module in FORBIDDEN_MODULES or (node.module or "").startswith("multiprocessing"):
            self._report(node, node.module or "", "модуль запуска процессов мимо общей функции")
        for alias in node.names:
            if alias.name in MCP_STDIO_CALLS:
                self.stdio_names.add(alias.asname or alias.name)
        if node.module == "claude_agent_sdk":
            for alias in node.names:
                if alias.name in SDK_ENTRY_CALLS:
                    self.sdk_names.add(alias.asname or alias.name)
        if node.module == "asyncio" or node.module in SPAWNERS:
            for alias in node.names:
                if alias.name == "subprocess" and node.module == "asyncio":
                    self.modules[alias.asname or alias.name] = "asyncio.subprocess"
                elif alias.name in SPAWNERS.get(node.module, ()):
                    self.functions[alias.asname or alias.name] = (node.module, alias.name)

    def _enter(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        self.stack.append(node.name)
        saved, self.dicts = self.dicts, dict(self.dicts)
        self.generic_visit(node)
        self.dicts = saved
        self.stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Dict):
                self.dicts[target.id] = node.value
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and isinstance(node.value, ast.Dict):
            self.dicts[node.target.id] = node.value
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._enter(node)

    def _spawner(self, func: ast.expr) -> str | None:
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            module = self.modules.get(func.value.id)
            if module and func.attr in SPAWNERS.get(module, ()):
                return f"{module}.{func.attr}"
        if isinstance(func, ast.Name) and func.id in self.functions:
            return ".".join(self.functions[func.id])
        return None

    def _report(self, node: ast.AST, spawner: str, problem: str) -> None:
        self.findings.append(
            Finding(".".join(self.stack) or "<module>", node.lineno, spawner, problem)
        )

    @staticmethod
    def _env_function(env: ast.expr | None) -> str | None:
        if not isinstance(env, ast.Call):
            return None
        func = env.func
        return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)

    def _options_env(self, node: ast.Call) -> ast.expr | None:
        """env= опций SDK: явный ключевой аргумент или ключ "env" словаря **kwargs."""
        for keyword in node.keywords:
            if keyword.arg == "env":
                return keyword.value
            if keyword.arg is None and isinstance(keyword.value, ast.Name):
                literal = self.dicts.get(keyword.value.id)
                for key, value in zip(literal.keys, literal.values) if literal else ():
                    if isinstance(key, ast.Constant) and key.value == "env":
                        return value
        return None

    def _check_spawn(self, node: ast.Call, spawner: str) -> None:
        self.spawns += 1
        env = next((kw.value for kw in node.keywords if kw.arg == "env"), None)
        if env is None:
            self._report(node, spawner, "нет env=")
            return
        name = self._env_function(env)
        if name not in ENV_FUNCTIONS:
            self._report(node, spawner, "env= не из общей функции окружения")
            return
        first = node.args[0] if node.args else None
        if (
            isinstance(first, ast.Constant)
            and first.value == "claude"
            and name not in CLAUDE_ENV_FUNCTIONS
        ):
            self._report(node, spawner, "claude без общей функции окружения Claude")

    def visit_Call(self, node: ast.Call) -> None:
        spawner = self._spawner(node.func)
        if spawner:
            self.seen_as_call.add(id(node.func))
            self._check_spawn(node, spawner)
        func = node.func
        func_name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if func_name in self.stdio_names:
            self.spawns += 1
            env = next((kw.value for kw in node.keywords if kw.arg == "env"), None)
            if self._env_function(env) not in ENV_FUNCTIONS:
                self._report(node, func_name, "stdio MCP без env= из общей функции окружения")
        if func_name in OPTIONS_CALLS:
            self.spawns += 1
            if self._env_function(self._options_env(node)) not in CLAUDE_ENV_FUNCTIONS:
                self._report(node, func_name, "опции SDK без env= из общей функции окружения")
        is_sdk_entry = func_name in self.sdk_names or (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and self.modules.get(func.value.id) == "claude_agent_sdk"
            and func_name in SDK_ENTRY_CALLS
        )
        if is_sdk_entry and not any(kw.arg in ("options", None) for kw in node.keywords):
            if len(node.args) < (2 if func_name != "ClaudeSDKClient" else 1):
                self._report(node, func_name, "запуск SDK без options: наследует os.environ")
        if func_name in LOOP_SPAWN_METHODS and isinstance(func, ast.Attribute):
            self._check_spawn(node, func_name)
        if func_name == "getattr" and len(node.args) >= 2:
            attr = node.args[1]
            spawn_names = set().union(*SPAWNERS.values()) | LOOP_SPAWN_METHODS
            ambiguous = {"run", "call", "spawn"}
            if isinstance(attr, ast.Constant) and attr.value in spawn_names - ambiguous:
                self._report(node, "getattr", "функция запуска получена через getattr")
            if not isinstance(attr, ast.Constant):
                base = node.args[0]
                if isinstance(base, ast.Name) and base.id in self.modules:
                    self._report(node, "getattr", "динамический getattr на модуле запуска")
        if func_name in ("import_module", "__import__") and node.args:
            module = node.args[0]
            if not isinstance(module, ast.Constant) or str(module.value).split(".")[0] in {
                name.split(".")[0] for name in SPAWN_MODULES
            }:
                self._report(node, func_name, "динамический импорт модуля запуска")
        if func_name in HELPERS_TAKING_FUNCTION:
            for arg in node.args:
                inner = self._spawner(arg)
                if inner:
                    self.seen_as_call.add(id(arg))
                    self._check_spawn(node, inner)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """subprocess.Popen[bytes] в аннотации это тип, а не запуск."""
        self.seen_as_call.add(id(node.value))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        spawner = self._spawner(node)
        if spawner and id(node) not in self.seen_as_call:
            self._report(node, spawner, "функция запуска передана как значение")
        self.generic_visit(node)


def scan(source: str) -> _Scanner:
    scanner = _Scanner()
    scanner.visit(ast.parse(source))
    return scanner


def _violations() -> tuple[list[str], int]:
    problems: list[str] = []
    spawns = 0
    for path in sorted(p for folder in SCANNED for p in folder.rglob("*.py")):
        relative = path.relative_to(REPO).as_posix()
        scanner = scan(path.read_text(encoding="utf-8"))
        spawns += scanner.spawns
        for finding in scanner.findings:
            if (relative, finding.function) in EXCEPTIONS:
                continue
            where = f"{relative}:{finding.line} {finding.function}"
            problems.append(f"{where}: {finding.spawner}: {finding.problem}")
    return problems, spawns


def test_every_spawn_in_src_uses_shared_env():
    problems, spawns = _violations()
    assert spawns >= 10  # разбор действительно нашёл запуски
    assert not problems, "\n".join(problems)


def test_exceptions_are_real_and_explained():
    for (relative, _function), reason in EXCEPTIONS.items():
        assert (REPO / relative).is_file()
        assert reason.strip()


@pytest.mark.parametrize(
    "source",
    [
        "import subprocess\nsubprocess.run(['x'])",
        "import subprocess as sp\nsp.Popen(['x'])",
        "from subprocess import run\nrun(['x'])",
        "from subprocess import check_output as co\nco(['x'])",
        "import subprocess\nsubprocess.check_call(['x'])",
        "import asyncio\nasyncio.create_subprocess_exec('x')",
        "import asyncio\nasyncio.create_subprocess_shell('x')",
        "from asyncio import subprocess as s\ns.create_subprocess_exec('x')",
        "from asyncio import create_subprocess_exec as c\nc('x')",
        "import os\nos.system('x')",
        "import os\nos.popen('x')",
        "import os\nos.execvp('x', [])",
        "import subprocess, asyncio\nasyncio.to_thread(subprocess.run, ['x'])",
        "import subprocess\nf = subprocess.run\nf(['x'])",
        "import subprocess, os\nsubprocess.run(['x'], env=os.environ)",
        "import subprocess, os\nsubprocess.run(['x'], env=os.environ.copy())",
        "import subprocess, os\nsubprocess.run(['x'], env={**os.environ})",
        "import subprocess\nsubprocess.run(['x'], env=None)",
        "import asyncio\nasyncio.create_subprocess_exec('claude', '-p', env=child_env())",
        "options_cls(cwd='/tmp')",
        # Обходы из повторного ревью.
        "import subprocess, os\nsubprocess.run(['x'], env=dict(os.environ))",
        "import subprocess, os\nsubprocess.run(['x'], env=os.environ | {})",
        "options_cls(**kwargs)",
        "kwargs = {'cwd': '/tmp'}\noptions_cls(**kwargs)",
        "kwargs = {'env': dict(os.environ)}\noptions_cls(**kwargs)",
        "ClaudeAgentOptions(env=child_env())",
        "from claude_agent_sdk import query\nquery(prompt='hi')",
        "from claude_agent_sdk import query as q\nq(prompt='hi')",
        "import claude_agent_sdk as sdk\nsdk.query(prompt='hi')",
        "import claude_agent_sdk\nclaude_agent_sdk.ClaudeSDKClient()",
        "query_fn(prompt='hi')",
        "loop.subprocess_exec(proto, 'claude')",
        "asyncio.get_running_loop().subprocess_shell(proto, 'ls')",
        "import subprocess\ngetattr(subprocess, 'Popen')(['x'])",
        "import subprocess\ngetattr(subprocess, name)(['x'])",
        "getattr(mod, 'create_subprocess_exec')('x')",
        "import importlib\nimportlib.import_module('subprocess').run(['x'])",
        "__import__('subprocess').run(['x'])",
        "import importlib\nimportlib.import_module(name)",
        "import multiprocessing\nmultiprocessing.Process(target=f).start()",
        "from multiprocessing import Process",
        "import pty\npty.fork()",
        "import os\nos.fork()",
        "import os\nos.forkpty()",
        "from os import system\nsystem('ls')",
        "import os as o\no.posix_spawn('/bin/ls', ['ls'], {})",
        # Личные подключения: stdio-сервер MCP запускает библиотека mcp.
        "StdioServerParameters(command='npx', args=[])",
        "StdioServerParameters(command='npx', env={'NOTION_TOKEN': token})",
        "import os\nStdioServerParameters(command='npx', env=dict(os.environ))",
        "from mcp.client.stdio import StdioServerParameters as P\nP(command='npx')",
    ],
)
def test_scanner_catches_violation(source):
    assert scan(source).findings


@pytest.mark.parametrize(
    "source",
    [
        "import subprocess\nsubprocess.run(['x'], env=child_env())",
        "import subprocess\nsubprocess.run(['x'], env=self._spawn_env(confined=True))",
        "import asyncio\nasyncio.create_subprocess_exec('claude', '-p', env=claude_env())",
        "import asyncio\nasyncio.run(main())",
        "kwargs = {'env': self._spawn_env(confined=True)}\noptions_cls(**kwargs)",
        "options_cls(env=self._spawn_env())",
        "ClaudeAgentOptions(env=claude_env())",
        "from claude_agent_sdk import query\nquery(prompt='hi', options=opts)",
        "query_fn(prompt=prompt, options=options)",
        "loop.subprocess_exec(proto, 'x', env=child_env())",
        "import importlib\nimportlib.import_module('json')",
        "StdioServerParameters(command='npx', env=connection_env(own))",
    ],
)
def test_scanner_accepts_shared_env(source):
    assert not scan(source).findings


# --- Второй рубеж: аудит-хук -----------------------------------------------------


def test_audit_hook_catches_inherited_env():
    import subprocess
    import sys

    found = violations_during(lambda: subprocess.run([sys.executable, "-c", "pass"]))
    assert found and "env не передан" in found[0]


def test_audit_hook_catches_extra_name(monkeypatch):
    import subprocess
    import sys

    monkeypatch.setenv(NEW_NAME, NEW_VALUE)
    env = {**child_env(), NEW_NAME: NEW_VALUE}
    found = violations_during(lambda: subprocess.run([sys.executable, "-c", "pass"], env=env))
    assert found and NEW_NAME in found[0]


def test_audit_hook_catches_os_system():
    import os

    assert violations_during(lambda: os.system("true"))


def test_audit_hook_accepts_shared_env(monkeypatch):
    import subprocess
    import sys

    monkeypatch.setenv(NEW_NAME, NEW_VALUE)
    assert not violations_during(
        lambda: subprocess.run([sys.executable, "-c", "pass"], env=claude_env())
    )


# --- Белый список --------------------------------------------------------------

NEW_NAME = "MY_NEW_SERVICE_SECRET"
NEW_VALUE = "fake-new-service-value-0123"


@pytest.mark.parametrize(
    "name",
    [NEW_NAME, "KB_MCP_KEY", "DATABASE_URL", "BACKEND_ADDRESS", "S3_ACCESS", "X", "lowercase_name"],
)
def test_unknown_name_never_passes(monkeypatch, name):
    monkeypatch.setenv(name, NEW_VALUE)
    assert name not in child_env()
    assert name not in child_env(claude=True, owner_auth=True)
    assert claude_env()[name] == ""


def test_connection_env_is_allowlist_plus_own_names(monkeypatch):
    """Процесс подключения (Notion): белый список и только его собственная переменная."""
    monkeypatch.setenv(NEW_NAME, NEW_VALUE)
    monkeypatch.setenv("KB_MCP_KEY", NEW_VALUE)
    env = connection_env({"NOTION_TOKEN": "ntn_FAKE_TEST_TOKEN_456"})
    assert env["NOTION_TOKEN"] == "ntn_FAKE_TEST_TOKEN_456"
    assert NEW_NAME not in env and "KB_MCP_KEY" not in env
    assert set(env) - {"NOTION_TOKEN"} == set(child_env())


def test_child_env_keeps_what_programs_need(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/home/x")
    monkeypatch.setenv("LC_CTYPE", "ru_RU.UTF-8")
    env = child_env()
    assert (env["PATH"], env["HOME"], env["LC_CTYPE"]) == ("/usr/bin", "/home/x", "ru_RU.UTF-8")


def test_owner_auth_goes_only_to_claude(monkeypatch):
    for name in CLAUDE_AUTH_NAMES:
        monkeypatch.setenv(name, "fake-auth")
    assert not set(child_env()) & CLAUDE_AUTH_NAMES
    assert not set(child_env(claude=True)) & CLAUDE_AUTH_NAMES
    env = claude_env()
    assert all(env[name] == "fake-auth" for name in CLAUDE_AUTH_NAMES)
    env = claude_env(owner_auth=False)
    assert all(env[name] == "" for name in CLAUDE_AUTH_NAMES)


def test_allowlist_holds_no_secret_looking_names():
    """Вход Claude вынесен отдельно, в общем списке секретов быть не должно."""
    words = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
    for name in ALLOWED_NAMES | CLAUDE_SETTING_NAMES:
        assert not any(word in name for word in words), name


# --- Настоящие запуски с новым именем ------------------------------------------


@pytest.fixture
def new_secret(monkeypatch, spawn_audit):  # noqa: F811
    monkeypatch.setenv(NEW_NAME, NEW_VALUE)
    monkeypatch.setenv("CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK", "1")
    monkeypatch.setattr(ClaudeBridge, "_jail_available", staticmethod(lambda: False))


@pytest.fixture
def stub_in_path(monkeypatch, tmp_path):
    def _install(name: str = "claude") -> Path:
        stub, dump = _stub_cli(tmp_path / f"bin-{name}", name=name)
        monkeypatch.setenv("PATH", str(stub.parent), prepend=":")
        return dump

    return _install


def _assert_clean(dump: Path) -> dict[str, str]:
    seen = json.loads(dump.read_text(encoding="utf-8"))
    assert NEW_VALUE not in json.dumps(seen)
    return seen["env"]


@pytest.mark.parametrize(
    "option_kwargs", [{}, {"confine_root": "/tmp/project"}], ids=["regular", "confined"]
)
async def test_sdk_path_stops_new_name(new_secret, tmp_path, option_kwargs):
    from claude_agent_sdk import ClaudeAgentOptions
    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

    stub, dump = _stub_cli(tmp_path / "stub")
    options = ClaudeBridge()._build_sdk_options(
        options_cls=ClaudeAgentOptions,
        project_path=str(tmp_path),
        session_id=None,
        **option_kwargs,
    )
    transport = SubprocessCLITransport(
        prompt="hi", options=dataclasses.replace(options, cli_path=str(stub))
    )
    await transport.connect()
    await transport._process.wait()
    await transport.close()
    assert _assert_clean(dump)[NEW_NAME] == ""


async def test_sdk_version_probe_stays_off(monkeypatch):
    """Иначе SDK запустил бы claude -v с полным os.environ, мимо общей функции."""
    from src.claude.bridge import _load_sdk

    monkeypatch.setenv("CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK", "0")
    _load_sdk()
    assert os.environ["CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK"] == "1"


async def test_cli_path_stops_new_name(new_secret, stub_in_path, tmp_path):
    dump = stub_in_path()
    async for _ in ClaudeBridge()._send_message_via_cli(
        message="hi", topic_id=1, project_path=str(tmp_path), session_id=None
    ):
        pass
    _assert_clean(dump)


async def test_auth_probe_stops_new_name(new_secret, stub_in_path):
    dump = stub_in_path()
    await ClaudeBridge()._check_auth_via_cli()
    _assert_clean(dump)


async def test_slash_command_fetch_stops_new_name(new_secret, stub_in_path):
    dump = stub_in_path()
    await commands._fetch_cli_slash_commands(timeout=10)
    _assert_clean(dump)


async def test_project_command_fetch_stops_new_name(new_secret, stub_in_path, tmp_path):
    dump = stub_in_path()
    commands._cli_cmd_cache.clear()
    await commands.fetch_cli_commands_for_project(str(tmp_path))
    _assert_clean(dump)


async def test_tmux_stops_new_name(new_secret, stub_in_path):
    dump = stub_in_path("tmux")
    await ClaudeBridge(transport="tmux")._run_tmux("ls", check=False)
    _assert_clean(dump)


def test_document_converter_stops_new_name(new_secret, stub_in_path, tmp_path):
    dump = stub_in_path("soffice")
    source = tmp_path / "doc.docx"
    source.write_text("x", encoding="utf-8")
    doc_preview._try_soffice(source)
    _assert_clean(dump)
