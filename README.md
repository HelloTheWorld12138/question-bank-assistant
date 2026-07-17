# 高中物理题库助手 MVP

本项目是本地网页工具，支持“手动粘贴题目与答案解析 -> 审核入库 -> 搜索组卷 -> 生成 exam.md -> 有 Pandoc 时导出 exam.docx”。

## 安装依赖

```powershell
python -m pip install -r requirements.txt
```

## 启动

Windows 可直接双击：

```text
start.bat
```

或在 PowerShell 中运行：

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动后打开：

```text
http://127.0.0.1:8000
```

## 导入一道示例题

1. 在“导入题目”中选择：
   - 板块：力学
   - 主类型：创新题
   - 难度：3
   - 年份：2026
   - 来源：教师自编
2. 在“题目正文”粘贴：

```text
质量为 2 kg 的物体在水平恒力作用下做匀加速直线运动，若合外力为 6 N，求物体加速度。
```

3. 在“答案”粘贴：

```text
3 m/s^2
```

4. 在“解析”粘贴：

```text
由牛顿第二定律 F=ma，可得 a=F/m=6/2=3 m/s^2。
```

5. 点击“生成题目草稿”。
6. 在“审核入库”中填写知识点，例如：

```text
牛顿第二定律
匀加速直线运动
```

7. 点击“确认入库”。
8. 到“搜索组卷”点击“搜索题库”，勾选题目。
9. 在“导出 Word”选择导出范围，点击“生成试卷”。

## Word 转 Markdown 草稿

页面中的“Word 转 Markdown 草稿”可以上传 `.docx`，并把转换后的 Markdown 填入：

- 题目正文
- 答案
- 解析

这个功能使用项目内置 Pandoc。系统会尽量提取 Word 中的图片，先作为草稿图片预览；确认入库时会重命名为 `题号_01.png`、`题号_02.png`。

如果 Word 内图片格式较特殊导致无法提取，可以在“上传题目、答案、解析附件或图片”里手动补充上传。

如果本机没有安装 Pandoc，系统会生成 `exports/exam.md` 并提示无法生成 Word。安装 Pandoc 后再次导出即可生成 `exports/exam.docx`。

本项目也支持项目内置 Pandoc：

```text
tools/pandoc/pandoc.exe
```

如果系统 PATH 中没有 Pandoc，网页工具会自动使用这个本地版本。

## 项目目录

```text
app/
  main.py              FastAPI 后端、编号、Markdown 存储、搜索、导出
static/
  index.html           本地网页
  app.js               前端交互
  style.css            页面样式
vault/
  index.json           每个“板块代码+类型代码”的当前最大序号
  题目/                每道题一个 Markdown 文件
  assets/              图片与上传附件
exports/
  exam.md              导出的 Markdown 试卷
  exam.docx            Pandoc 可用时生成的 Word
requirements.txt       Python 依赖
```

## 编号与图片规则

- 题号由程序在确认入库时自动生成。
- `vault/index.json` 记录每个前缀的最大序号，例如 `LXCX: 12` 下一题为 `LXCX0013`。
- 图片保存为 `题号_01.png`、`题号_02.jpg` 等，图片文件名和题号绑定。
- Word/PDF 等非图片附件会保存为 `题号_附件1.docx`、`题号_附件2.pdf`，不写入 Markdown 的图片列表。
