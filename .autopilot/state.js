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
  "updatedAt": "2026-10-21T23:09:21+03:00",
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
      "note": "срез A: 0 из 4 тасков готовы, идёт 01",
      "startedAt": "2026-10-21T23:09:21+03:00"
    },
    {
      "id": "review",
      "status": "pending"
    },
    {
      "id": "final",
      "status": "pending"
    }
  ],
  "requirements": {
    "total": 192,
    "done": 0,
    "inTicket": 13,
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
      "status": "in-progress",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0,
      "startedAt": "2026-10-21T23:09:21+03:00"
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
        "src/web/routes_office_project.py",
        "web/src/components/office/passport/",
        "web/src/api/officeProject.ts"
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
        "web/src/components/office/brief/",
        "web/src/api/officeBrief.ts"
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
        "web/src/components/office/spec/",
        "web/src/api/officeSpec.ts"
      ],
      "status": "pending",
      "retries": 0,
      "repairs": 0,
      "handoffs": 0
    }
  ],
  "singlePass": null,
  "tests": null,
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
  "concerns": [],
  "reviewers": {
    "manifestSpec": null,
    "craft": null
  },
  "blind": null
}
