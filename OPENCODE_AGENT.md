# 本地 opencode agent 和公式 OCR 配置

OpenCode 和公式 OCR 都是可选增强，不是题库基础功能的运行前提。

普通老师直接使用一键启动：

```bat
start.bat
```

`start.bat` 会调用 `scripts\start_all.ps1` 完成：

- 创建项目内 `.venv`
- 安装 Python 依赖
- 检测已有的 `opencode-ai` CLI
- 检测已有的 `latexocr` / `pix2tex`
- 启动本地网页服务

启动脚本不会为了可选能力自动安装 Node.js、pnpm、OpenCode 或 pix2tex。缺少它们时，普通录题、离线规则整理、搜索和组卷仍可使用。

程序会在 Word 转 Markdown 之后调用本地 agent 来拆分：

- 题目
- 答案
- 解析

如果你已经有自己的 agent 命令，也可以手动覆盖。默认检测方式：

```bat
opencode run --print "<prompt>"
```

如果你的 opencode 命令不是这个形式，可以在启动前设置：

```bat
set QUESTION_AGENT_COMMAND=你的命令
```

可用模板变量：

- `{prompt_file}`：程序生成的提示词文件路径
- `{output_file}`：希望 agent 写入 JSON 的结果文件路径

示例：

```bat
set QUESTION_AGENT_COMMAND=opencode run --print < "{prompt_file}"
```

或让 agent 写入指定文件：

```bat
set QUESTION_AGENT_COMMAND=opencode run < "{prompt_file}" > "{output_file}"
```

agent 必须返回 JSON：

```json
{
  "question": "题干 Markdown",
  "answer": "答案",
  "analysis": "解析",
  "confidence": 0.8,
  "notes": "可选说明"
}
```

如果没有检测到 OpenCode，或者 agent 返回失败，Word 单题导入会回退到离线规则解析和教师人工编辑。

## 本地公式 OCR

旧版 MathType 经常会在 `.docx` 中变成图片。程序会检测疑似公式图片，并优先调用本地公式 OCR。

默认自动检测：

```bat
latexocr
pix2tex
```

也可以手动指定：

```bat
set FORMULA_OCR_COMMAND=你的命令
```

可用模板变量：

- `{image_file}`：待识别公式图片路径
- `{output_file}`：希望 OCR 写入 LaTeX 的结果文件路径

示例：

```bat
set FORMULA_OCR_COMMAND=latexocr "{image_file}"
```

或：

```bat
set FORMULA_OCR_COMMAND=pix2tex "{image_file}" > "{output_file}"
```

OCR 结果不会直接入库。页面会显示原公式图片和 LaTeX 文本框，老师确认后才会替换为可编辑公式。

如果没有检测到公式 OCR，普通 Word 不受影响；疑似公式图片会保留原图，并要求老师手动填写和确认 LaTeX 后再入库。

## 高级找题与组卷接入

OpenCode 不需要直接遍历或修改 `vault`。独立 APP 已提供稳定的本地接口和 CLI：

```bash
python -m app.cli recommend "找5道近三年力学创新题，中等难度，约45分钟"
```

也可以复用 AionUI Skill 内只依赖 Python 标准库的本地客户端：

```bash
python integrations/aionui/skills/physics-question-bank/scripts/question_bank_api.py recommend "找5道力学创新题"
```

推荐结果只是候选题。教师确认题号后，才调用 `export`；不要让 OpenCode 直接修改
Markdown、图片、`index.json`，也不要让它自动调用删除或恢复接口。
