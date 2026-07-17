# MVP 最终验收清单

## 必须通过

- [ ] 启动 `start.bat` 后能打开网页。
- [ ] 新增一道题时能自动生成题号。
- [ ] 题号写入 `vault/index.json`。
- [ ] 每道题生成一个 Markdown 文件。
- [ ] Markdown 文件位于 `vault/题目/`。
- [ ] 图片位于 `vault/assets/`。
- [ ] 图片命名为 `题号_01.png`、`题号_02.png`。
- [ ] 搜索能按板块、类型、难度、年份、来源、知识点过滤。
- [ ] 搜索结果能勾选加入试卷。
- [ ] 能生成 `exports/exam.md`。
- [ ] 能生成 `exports/exam.docx`。
- [ ] 导出支持“仅题目 / 题目+答案 / 题目+答案+解析”。

## 当前已实现

- 本地 FastAPI 网页工具
- Markdown + 图片文件存储
- 自动编号
- Word 转 Markdown
- Word 图片抽取并按题号入库
- 搜索题库
- 勾选组卷
- 项目内置 Pandoc 导出 Word
- Obsidian 库与常用插件

## 暂不承诺

- 自动高质量 OCR
- 自动拆分所有组卷网 Word 多题格式
- AI 自动解题
- 云同步
- 多用户协作
