window.STATE =
{
  "slug": "ai-project-office",
  "dir": "2026-10-18-ai-project-office--wip",
  "title": "AI-first проектный офис",
  "mode": "interview",
  "depth": "deep",
  "polish": null,
  "tier": "T2",
  "briefFile": "2026-10-18-brief.md",
  "memoryFile": "CLAUDE.md",
  "skillDir": "/Users/ifinance/.claude/skills/autopilot",
  "startedAt": "2026-10-18T23:28:00+03:00",
  "updatedAt": "2026-10-21T23:49:49+03:00",
  "finishedAt": null,
  "stages": [
    {
      "id": "preflight",
      "status": "done",
      "startedAt": "2026-10-18T23:28:00+03:00",
      "finishedAt": "2026-10-18T23:28:40+03:00"
    },
    {
      "id": "manifest",
      "status": "done",
      "startedAt": "2026-10-18T23:30:00+03:00",
      "finishedAt": "2026-10-18T23:37:08+03:00"
    },
    {
      "id": "briefing",
      "status": "done",
      "startedAt": "2026-10-18T23:37:08+03:00",
      "finishedAt": "2026-10-19T00:16:00+03:00"
    },
    {
      "id": "spec",
      "status": "done",
      "startedAt": "2026-10-19T00:16:00+03:00",
      "finishedAt": "2026-10-19T00:27:41+03:00"
    },
    {
      "id": "plan",
      "status": "done",
      "startedAt": "2026-10-19T00:27:41+03:00",
      "finishedAt": "2026-10-21T23:06:05+03:00",
      "note": "срезы A–H; срез A: 4 таска, ярус T2, 3 волны"
    },
    {
      "id": "build",
      "status": "active",
      "note": "срез A: 1 из 4 тасков готов",
      "startedAt": "2026-10-21T23:09:21+03:00"
    },
    {
      "id": "review",
      "status": "active",
      "startedAt": "2026-10-21T23:27:39+03:00",
      "note": "проверено 1 из 4"
    },
    {
      "id": "final",
      "status": "pending"
    }
  ],
  "requirements": {
    "total": 192,
    "done": 2,
    "inTicket": 11,
    "inSpec": 179,
    "placeholder": 0,
    "deferred": 0,
    "dropped": 0
  },
  "tickets": [
    {
      "id": "01",
      "title": "Каркас проектного офиса",
      "requirements": [
        "R07",
        "G05"
      ],
      "blockedBy": [],
      "wave": 1,
      "zone": [
        "src/office/",
        "src/web/routes_office*.py",
        "src/web/server.py",
        "web/src/routes/OfficePage.tsx",
        "web/src/components/office/",
        "web/src/App.tsx",
        "web/src/components/Sidebar.tsx",
        "tests/office/"
      ],
      "status": "done",
      "retries": 0,
      "repairs": 1,
      "handoffs": 0,
      "startedAt": "2026-10-21T23:09:21+03:00",
      "repairFindings": [
        "мок OfficePage.test теряет officeRequest; нет теста 404 по несуществующему id; нечисловой id даёт NaN и сырой 422"
      ],
      "finishedAt": "2026-10-21T23:49:49+03:00",
      "tests": {
        "passed": 17,
        "failed": 0
      },
      "files": [
        "src/office/",
        "src/web/routes_office*.py",
        "src/web/server.py",
        "web/src/routes/OfficePage.tsx",
        "web/src/components/office/",
        "web/src/App.tsx",
        "web/src/components/Sidebar.tsx",
        "tests/office/",
        "web/src/__tests__/Office*.test.tsx"
      ],
      "concerns": [
        "клиент API оболочки в components/office/officeApi.ts, не в web/src/api/",
        "кнопка «Новый проект» заглушка до таска 02"
      ]
    },
    {
      "id": "02",
      "title": "Паспорт проекта и выбор типа",
      "requirements": [
        "R02",
        "R03",
        "R04",
        "R10",
        "R17",
        "R18",
        "G20",
        "G21"
      ],
      "blockedBy": [
        "01"
      ],
      "wave": 2,
      "zone": [
        "src/office/project/",
        "src/office/storage.py",
        "src/web/routes_office_project.py",
        "web/src/components/office/passport/"
      ],
      "status": "pending",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0
    },
    {
      "id": "03",
      "title": "Бриф проекта",
      "requirements": [
        "R11",
        "R19"
      ],
      "blockedBy": [
        "01"
      ],
      "wave": 2,
      "zone": [
        "src/office/knowledge/",
        "src/web/routes_office_brief.py",
        "web/src/components/office/brief/"
      ],
      "status": "pending",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0
    },
    {
      "id": "04",
      "title": "Черновик задания из брифа",
      "requirements": [
        "R20"
      ],
      "blockedBy": [
        "02",
        "03"
      ],
      "wave": 3,
      "zone": [
        "src/office/cycle/",
        "src/office/agents/",
        "src/web/routes_office_spec.py",
        "web/src/components/office/spec/"
      ],
      "status": "pending",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0
    }
  ],
  "singlePass": null,
  "tests": {
    "passed": 1000,
    "failed": 39
  },
  "debt": {
    "placeholders": [],
    "assumptions": [],
    "emptyEnv": []
  },
  "additions": [],
  "coverage": {
    "missing": 18,
    "half": 8,
    "extraAttached": true,
    "action": "spec amended before leaving the phase"
  },
  "concerns": [
    "База до среза A красная, не трогалась: бэкенд 865 passed / 29 failed / 4 errors (2 файла не импортируются: tests/test_config_env_placeholders.py, tests/test_model_catalog.py; падения в тестах бота и веб-роутов), фронт 118 passed / 10 failed в 4 файлах (LoginPageTelegramOptional, newSession, UsageEventNumbers, ChatEmptyState). Зелёный таск = ни одного нового падения",
    "Корень репозитория: посторонний package-lock.json с @xterm (не в git, не из этого прогона)",
    "tenancy: два источника администратора, флаг users.is_admin и роль участника system_admin, которую open_project не учитывает (src/office/tenancy/_roles.py:22); в срезе A источник один, флаг",
    "src/office/storage.py:17: константа OFFICE_TABLES не используется",
    "tests/office/test_access.py:23,42: фикстура строит SessionManager вручную и чистит через приватный _engine вместо make_mgr из conftest; :95 async-тест без await",
    "web/src/components/office/officeApi.ts:19: officeRequest повторяет форму api/client.ts (fetch, событие 401, ApiError), общего request там нет",
    "src/web/routes_office.py:29: require_actor повторяет перепроверку роли по БД из require_admin (dependencies.py вне зоны)",
    "OfficeProjectList.tsx:29, OfficeProjectView.tsx:45, OfficePage.tsx:21: шапка с кнопкой назад и баннер ошибки повторены дословно трижды, нужна одна общая шапка",
    "web/src/App.tsx:54: защита /office под Protected не покрыта тестом на редирект неавторизованного",
    "фронт: SshSettingsPanel.test.tsx флакает под нагрузкой параллельных прогонов, в одиночном зелёный"
  ],
  "reviewers": {
    "manifestSpec": "ad33f64a7ea3fdd11",
    "craft": "a6c9dd36834ace861"
  },
  "blind": null
}
