<p align="center">
  <img src="./static/brand/tidazi-logo.png" width="96" alt="题搭子 Logo">
</p>

<h1 align="center">题搭子</h1>

<p align="center"><strong>面向高中物理教师的本地题库整理、检索与 Word 组卷工具</strong></p>

<p align="center">
  把 Word 题目整理为可检索的本地题库，经人工审核后入库，再按教学需要选题并导出试卷。
</p>

<p align="center">
  <a href="https://github.com/HelloTheWorld12138/question-bank-assistant/releases/latest">下载最新版</a> ·
  <a href="./CHANGELOG.md">更新记录</a> ·
  <a href="https://github.com/HelloTheWorld12138/question-bank-assistant/issues">反馈问题</a>
</p>

<p align="center">
  <img src="https://img.shields.io/github/v/release/HelloTheWorld12138/question-bank-assistant?label=稳定版" alt="GitHub Release">
  <img src="https://github.com/HelloTheWorld12138/question-bank-assistant/actions/workflows/tests.yml/badge.svg" alt="Tests">
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows-44566c" alt="macOS and Windows">
</p>

![题搭子题库工作台](./docs/assets/app-overview.jpg)

## 题搭子是什么

题搭子用于处理高中物理教师日常积累和使用题目的完整流程：从资料中导入题目，检查题干、答案、解析、公式与图片，补充分类信息，写入本地题库，再完成检索、选题和 Word 组卷。

它遵循三个原则：

- **本地优先**：题库、图片、设置、备份和导出文件默认保存在自己的电脑中；核心功能不依赖云端服务。
- **人工确认后入库**：批量导入首先生成草稿，教师可以逐题修改、拆分和确认，程序不会把未经检查的内容直接写入正式题库。
- **文件可长期维护**：每道题以独立 Markdown 文件保存，图片单独存放；搜索索引损坏后可以从原始题目重新生成。

## 下载与安装

请从 [GitHub Releases](https://github.com/HelloTheWorld12138/question-bank-assistant/releases/latest) 下载与电脑匹配的安装包。

| 系统 | 安装包 | 适用设备 |
|---|---|---|
| macOS | `Tidazi-*-macOS-arm64.dmg` | Apple 芯片 Mac（M1、M2、M3、M4 等） |
| macOS | `Tidazi-*-macOS-x64.dmg` | Intel 芯片 Mac |
| Windows | `Tidazi-*-Windows-x64-Setup.exe` | 64 位 Windows 10 / 11 |

每个 Release 同时提供 `SHA256SUMS.txt`，可用于核对安装包是否下载完整。

### macOS

1. 打开 DMG，将“题搭子”拖入“应用程序”。
2. 首次启动时，如果系统提示无法验证开发者，请打开“系统设置 → 隐私与安全性”，在安全提示下选择“仍要打开”。
3. 当前安装包使用临时签名，尚未经过 Apple 公证；后续正常启动不需要重复确认。

### Windows

1. 运行 `Tidazi-*-Windows-x64-Setup.exe`，按安装器提示完成安装。
2. 安装器会检查 Microsoft Edge WebView2 Runtime；缺少时将从 Microsoft 下载并安装。
3. Word、MathType 和组卷所需的运行组件已包含在安装包中，不需要单独安装 Pandoc、Ruby 或 MathType。

升级时先关闭题搭子，再覆盖安装新版本即可。题库位于应用程序之外，正常升级或卸载不会删除题目数据。

## 典型工作流

1. **导入或录入**：选择题目 Word 和可选的答案解析 Word，或者自动整理、手动录入单题。
2. **检查草稿**：核对自动拆分结果，修改题干、答案、解析、公式、图片和分类信息。
3. **确认入库**：只把选中且已经确认的草稿写入正式题库。
4. **检索与选题**：按题号、关键词、板块、题型、知识点、难度、年份和来源筛选题目。
5. **组卷与导出**：调整题目顺序和试卷设置，生成题目卷、答案卷或解析卷 Word 文档。

```text
Word 批量导入 / Word 单题整理 / 手动录入
                       ↓
                   导入草稿
                       ↓
               人工审核与分类确认
                       ↓
                    本地题库
                       ↓
                 检索、选题、组卷
                       ↓
                   可编辑 Word
```

## 功能范围

| 环节 | 支持内容 |
|---|---|
| 批量导入 | 仅支持 DOCX；可同时上传题目 Word 和可选的答案解析 Word，不支持 PDF |
| 单题录入 | Word 自动整理题目、答案和解析；也可手动填写并添加题目图片 |
| 草稿审核 | 逐题修改、批量选择、保存进度、拆分题目、确认后入库 |
| 公式与图片 | Word 可编辑公式、旧版 MathType/OLE 公式、题图提取、WMF/EMF 本地转换、图片裁剪与透视校正 |
| 题库管理 | Markdown 独立题目、分类与知识点、条件筛选、全文检索、编辑、复制、批量修改、回收站 |
| 选题组卷 | 条件找题、自然语言找题、本地排序、可选 AI 调整、上移或下移题目顺序 |
| Word 导出 | A4 单栏、A4 双栏、正式考试卷；可导出题目、答案、解析或分别生成三个文档 |
| 数据维护 | 自动备份、手动备份、恢复前安全备份、图片完整性检查、索引重建、模板恢复 |

题库覆盖力学、电磁学、热学、光学、近代物理、物理实验，以及物理学史、物理方法、单位制与常识等板块。

## Word 与公式兼容性

桌面安装包已经内置固定版本的 Word 读写组件和 MathType 转换资源，安装后即可导入、整理和导出 `.docx` 文件。

- Word 原生可编辑公式会转换为题库中的 LaTeX 公式，并在导出时恢复为可编辑的 Word 公式。
- 旧版 MathType/OLE 公式会优先读取内部结构，转换后仍保留在原来的正文位置。
- 单个公式无法转换时，只回退该公式的原始预览图并在审核页提示，不会阻断同一文档中的其他题目和公式。
- Word 中的 WMF/EMF 题图会在本机转换为常见图片格式，不依赖外部图片服务。
- 打包审计会实际转换随包附带的 MathType 公式样本，而不是只检查组件文件是否存在。

导入后仍建议在草稿页对照原文件检查公式、上下标、单位、题图位置和题目分段。当前只支持 `.docx`，旧版 `.doc` 文件请先使用 Word 或其他兼容软件另存为 `.docx`。

## 题目图片

- 题目图片只用于单题录入中的题图附件，不作为批量导入来源。
- “题目图片”入口只接受图片文件；Word 应使用“从 Word 自动整理题目”。
- 图片编辑器支持裁剪和透视校正，适合处理拍照题图和倾斜题图。
- 疑似公式图片需要在审核页明确选择“转为公式”或“保留原图”，确认前不能直接入库。

## AI 辅助是可选功能

不配置模型也可以完成导入、录题、检索、组卷、导出和备份。启用后，AI 只用于辅助填写分类或调整找题顺序，不会绕过人工审核直接修改正式题库。

目前支持：

- 阿里云百炼 / 通义千问；
- DeepSeek；
- 其他 OpenAI 兼容服务，包括 LM Studio；
- 本机 Ollama 模型。

使用云端模型前，界面会说明将要发送的内容并要求确认。访问密钥保存到操作系统凭据存储，不写入题库 Markdown、设置文件或 Git 仓库。选择 Ollama 时可以只使用本机模型。

## 数据位置与隐私

桌面版默认将数据保存在：

```text
用户文档目录/高中物理题库/
├─ 题目/           # 每道题一个 Markdown 文件
├─ assets/         # 题图和公式回退图片
├─ backups/        # 自动与手动备份
├─ templates/      # 可替换的 Word 模板
├─ exports/        # 导出的试卷
├─ logs/           # 本地运行日志
└─ settings.json   # 不含 API Key 的应用设置
```

- 不需要注册账号，核心题库工作不要求联网。
- 删除题目时先进入本地回收站，可以在维护区恢复。
- 应用默认每 24 小时创建一次自动备份，并保留最近 10 份。
- 恢复历史备份前会先备份当前题库，降低误操作风险。
- 云端 AI 关闭时，题目内容不会因为分类或组卷操作发送给模型服务。

## 已知边界

- macOS 安装包尚未经过 Apple Developer ID 公证，首次运行需要手动确认。
- 批量导入只接受 `.docx` Word 文件；PDF 和图片需先在外部工具中整理为 Word。
- 不同年代和来源的 MathType 文件结构可能不同，批量导入后必须保留人工核对步骤。
- AI 给出的分类和选题建议可能出错，应由教师确认后使用。
- 本项目面向单机题库工作流，不提供账号体系、多人实时协作或云端同步。

## 本地开发

需要 Python 3.10 或更高版本。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Windows PowerShell 使用 `.\.venv\Scripts\Activate.ps1` 激活环境。启动后访问 <http://127.0.0.1:8000>。

运行测试：

```bash
python -m pytest
```

构建桌面安装包：

```bash
# macOS
bash scripts/build_macos_dmg.sh

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

发布构建会在生成安装包前实际启动 Pandoc、OfficeCLI 和 MathType 运行时。缺少必要文件或运行时加载失败时，构建会直接停止，不会发布不完整的安装包。

更多信息：

- [开发与构建说明](./docs/开发说明.md)
- [题库数据格式规范](./docs/数据格式规范.md)
- [版本更新记录](./CHANGELOG.md)

## 反馈与许可

遇到 Word 导入、公式、图片、题目拆分或安装问题时，请在 [GitHub Issues](https://github.com/HelloTheWorld12138/question-bank-assistant/issues) 中附上操作系统、应用版本、错误提示和可复现的脱敏文件信息。

本仓库目前未附加开源许可证。除 GitHub 正常浏览、下载发行包和提交反馈外，源码与发行包的复制、修改及再分发需获得项目作者许可。
