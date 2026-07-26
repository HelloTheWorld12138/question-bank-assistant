# Local API Reference

Base URL: `http://127.0.0.1:8000`

The bundled script rejects non-loopback URLs.

## Read operations

### Status

`GET /api/health`

### Natural-language recommendation

`POST /api/assistant/recommend`

```json
{
  "query": "找5道近三年力学创新题，中等难度，约45分钟，带解析",
  "use_ai": false,
  "consent": false
}
```

The response includes parsed constraints, candidate count, recommended items, estimated minutes, warnings, and whether AI was used.

### Question detail

`GET /api/questions/{question_id}`

Use only after the ID came from the local API.

## Export operation

`POST /api/export`

Call only after the teacher confirms IDs, title, template, and mode.

Modes:

- `questions`: 题目
- `answers`: 题目 + 答案
- `analysis`: 题目 + 答案 + 解析
- `answer_sheet`: 独立答案卷
- `analysis_sheet`: 独立解析卷

Templates:

- `a4_single`
- `a4_double`
- `formal_exam`

Export writes a new file under the app's export directory and does not modify formal question data.

## Failure handling

- Connection refused: ask the teacher to start the app.
- `consent_required`: explain the minimal cloud payload and request explicit consent, or retry without AI.
- Zero candidates: report the parsed strict constraints and ask which constraint may be relaxed.
- Missing Pandoc: the API still creates Markdown; do not claim Word was created.
