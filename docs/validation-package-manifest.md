# Манифест пакета прогона (`manifest.json`)

Пакет валидации: zip с `manifest.json`, `findings.json`, снимками `img/*.png` и PDF `docs/*.pdf`. Импорт: `POST /api/office/projects/{id}/validation/runs/import`.

## Обязательные поля

| Поле | Тип | Описание |
|---|---|---|
| `schema_version` | `1` | Версия схемы пакета |
| `adapter` | строка | `doc_review_v1` или `stand_run_v1` |
| `source_kind` | строка | `doc_review` или `stand_run` |
| `run_key` | строка | Короткий идентификатор прогона (`A-Za-z0-9_-`, до 64 символов) |

## Реестр прогонов (метаданные)

| Поле | Тип | Описание |
|---|---|---|
| `comparison_kind` | enum | Что с чем сравнивают (см. ниже). Если нет: для `stand_run` → `ftt_vs_stand`, для `doc_review` → `spmi_vs_ftt` |
| `documents` | массив | Участвующие документы. Элемент: строка (имя) или объект `{ "role": "ftt", "name": "ФТТ1.pdf" }`. Если нет: список PDF из `docs/` в архиве |
| `series_key` | строка | Логическая серия прогонов (версии одного сценария). По умолчанию = `run_key` |
| `import_version` | int | Явный номер версии в серии. Если нет: при повторной загрузке другого содержимого номер +1 |
| `started_at` | ISO8601 | Дата/время прогона на стороне QA (в UI приоритетнее `imported_at`) |
| `title` | строка | Заголовок в UI |
| `stand_version` | строка | Для `stand_run`: метка стенда |

### `comparison_kind`

| Значение | Смысл |
|---|---|
| `ftt_vs_stand` | Соответствие стенда ФТТ/ПМИ (`stand_run`) |
| `spmi_vs_ftt` | Сверка ПМИ с ФТТ (прогон № 4 и аналоги) |
| `admin_vs_pmi` | Руководство администратора ↔ ПМИ |
| `pmi_vs_ftt` | Явная пара ПМИ ↔ ФТТ (синоним сценария документов) |

## Версии одной серии

- Повтор **того же** архива (тот же `package_sha`): идемпотентно, строка не дублируется.
- Новое содержимое с тем же `series_key`: новая строка реестра, `import_version` увеличивается, `parent_run_id` указывает на предыдущую версию.
- Другая серия: другой `series_key` или другой `run_key` при первой загрузке.

## Пример

```json
{
  "schema_version": 1,
  "adapter": "doc_review_v1",
  "source_kind": "doc_review",
  "run_key": "RUN4",
  "series_key": "RUN4",
  "comparison_kind": "spmi_vs_ftt",
  "title": "Прогон № 4: ПМИ ↔ ФТТ",
  "started_at": "2026-10-28T14:00:00+00:00",
  "documents": [
    { "role": "ftt", "name": "ФТТ1.pdf" },
    { "role": "pmi", "name": "ПМИ1.pdf" }
  ]
}
```
