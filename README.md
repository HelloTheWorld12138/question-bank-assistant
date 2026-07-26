# 高中物理题库助手

面向高中物理教师的本地题库与组卷工具。当前仓库处于从网页 MVP 向独立 Windows APP 演进的阶段。

## 项目入口

- [项目实施规划](./项目实施规划.md)：产品原则、总体架构、阶段任务和验收标准；
- [数据格式规范](./docs/数据格式规范.md)：Markdown、题号、图片和兼容规则；
- [开发说明](./docs/开发说明.md)：开发环境、模块结构和测试命令；
- [教师使用教程](./使用教程.md)：当前 MVP 的实际操作方式；
- [MVP 验收清单](./MVP最终验收清单.md)：现有功能检查项。

## 当前能力

```text
手动粘贴 / DOCX
        ↓
草稿审核与自动编号
        ↓
Markdown + 图片入库
        ↓
条件搜索与勾选组卷
        ↓
Markdown / Word 导出
```

题目数据保存在 `vault/题目/`，图片保存在 `vault/assets/`。Markdown 是正式题库的唯一真源。

## 当前 MVP 启动

Windows 可以双击：

```text
start.bat
```

开发环境启动：

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000`。

## 测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

真实 Word、PDF 和照片样本放入 `tests/real_samples/`，该目录中的材料默认不会提交到 Git。

## 重要说明

- 当前仍是开发版，不是可直接分发给教师的正式安装包；
- OpenCode、公式 OCR 和 Pandoc 的耦合将在阶段 1、阶段 2 中继续处理；
- 最终版本要求无需 Python、Node、OpenCode、Obsidian 或命令行；
- 后续开发严格按《项目实施规划》逐阶段完成。
