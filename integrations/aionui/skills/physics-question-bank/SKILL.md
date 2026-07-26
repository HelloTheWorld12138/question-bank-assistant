---
name: physics-question-bank
description: Search, recommend, inspect, select, and export questions from the local Chinese high-school physics question-bank app. Use when a teacher asks in Chinese or English to 找题、推荐题目、按知识点/难度/年份/题型筛选、安排指定时长的练习、组卷、查看候选题，或导出题目卷/答案卷/解析卷. Operate only through the app's localhost API and never edit Markdown, images, index files, or the formal vault directly.
---

# Local Physics Question Bank

Use the bundled `scripts/question_bank_api.py` for every operation. The app must be running on `127.0.0.1:8000`.

## Workflow

1. Run `python scripts/question_bank_api.py status`.
2. If unavailable, tell the teacher to start the question-bank app. Do not search the vault directly.
3. Translate the teacher's request into one natural-language sentence without discarding constraints.
4. Run `python scripts/question_bank_api.py recommend "<request>"`.
5. Present the returned题号、题型、预计用时、题目预览和推荐理由.
6. Let the teacher decide which questions to keep. Do not silently select or export.
7. After explicit confirmation, export only the confirmed IDs:

```bash
python scripts/question_bank_api.py export LXJC0001 LXCX0002 --title "高二力学练习" --mode questions
```

Use `answers` for题目+答案, `analysis` for题目+答案+解析, `answer_sheet` for答案卷, and `analysis_sheet` for解析卷.

## AI Boundary

- Prefer local recommendation without `--ai`.
- Use `--ai` only when the teacher asks for model-enhanced ranking.
- For a cloud provider, explain that the request and minimal candidate metadata/short previews will be sent, then require explicit consent and add `--consent`.
- Never send answers, full analyses, images, or the whole vault to a model.
- If AI fails, keep and report the local result.

## Safety

- Treat recommendation results as candidates, not final teaching judgments.
- Do not call create, update, delete, batch-import, restore, or maintenance endpoints.
- Do not edit `vault/题目`, `vault/assets`, or `vault/index.json`.
- Do not invent question IDs.
- Do not export before the teacher confirms the final IDs and export mode.

Read [references/local-api.md](references/local-api.md) only when endpoint fields, modes, or failure handling are needed.
