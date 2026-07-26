# 高中物理题库助手

面向高中物理教师的本地题库与组卷工具。当前仓库处于从网页 MVP 向独立 Windows APP 演进的阶段。

## 项目入口

- [项目实施规划](./项目实施规划.md)：产品原则、总体架构、阶段任务和验收标准；
- [数据格式规范](./docs/数据格式规范.md)：Markdown、题号、图片和兼容规则；
- [开发说明](./docs/开发说明.md)：开发环境、模块结构和测试命令；
- [国内模型配置](./docs/国内模型配置.md)：阿里云、DeepSeek、Ollama、密钥与隐私边界；
- [导入与 OCR 说明](./docs/导入与OCR说明.md)：DOCX/PDF/照片批量切题、答案匹配和离线降级；
- [AionUI 接入说明](./docs/AionUI接入说明.md)：可选聊天入口、Skill、国内网络与本地 API 边界；
- [教师使用教程](./使用教程.md)：当前 MVP 的实际操作方式；
- [MVP 验收清单](./MVP最终验收清单.md)：现有功能检查项。

## 当前能力

```text
手动粘贴 / DOCX / 数字 PDF / 扫描件 / 照片
        ↓
批量切题、答案匹配与草稿审核
        ↓
Markdown + 图片入库
        ↓
编辑 / 搜索 / 勾选组卷
        ↓
Markdown / Word 导出
```

题目数据保存在 `vault/题目/`，图片保存在 `vault/assets/`。Markdown 是正式题库的唯一真源。

当前版本已经支持题目复制、批量标签修改、全文搜索与排序、回收站恢复、图片完整性检查、编号索引修复、自动/手动备份，以及每次使用独立文件名导出试卷。组卷时可以调整题目顺序和展示题号、按题型分组，并分别生成题目卷、答案卷和解析卷。Word 导出可选择 A4 单栏、A4 双栏和正式考试卷模板；OfficeCLI 可在导出后执行结构校验与 HTML 预览。OpenCode、公式 OCR 和 OfficeCLI 均有明确的离线降级路径。

可选 AI 层支持阿里云百炼、DeepSeek、自定义 OpenAI 兼容接口、Ollama 和
LM Studio。API Key 不写入题库；云端调用前需要明确确认，且只发送当前题目正文。
AI 分类结果必须先进入审核草稿，不能直接修改正式题库。

批量导入中心支持数字 PDF 文字提取、Word 多题切分、照片预处理、相邻题合并/拆分、
答案卷匹配和置信度提示。PaddleOCR 是可选的完整离线能力；未安装时，扫描件与照片
会保留原图进入人工审核，数字 PDF、DOCX 和其余核心功能不受影响。

“搜索组卷”支持直接输入自然语言，例如“找 5 道近三年力学创新题，中等难度，
覆盖牛顿第二定律，约 45 分钟，带解析”。系统先在本机解析条件并筛选候选题，
给出预计用时和推荐理由，老师确认后才能加入组卷。模型增强排序和 AionUI Skill
都是可选层，不影响独立 APP 离线使用。

## 当前 MVP 启动

macOS 直接双击：

```text
打开高中物理题库.command
```

不再使用时可双击 `关闭高中物理题库.command`。不要直接打开 `static/index.html`，
否则浏览器只会读取页面骨架，无法连接本地题库服务。

Windows 可以双击：

```text
start.bat
```

开发环境启动：

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

需要在开发环境启用完整离线 OCR 时：

```bash
python -m pip install -r requirements-ocr.txt
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
- OpenCode 和公式 OCR 已不再是基础导入的硬依赖；Pandoc 负责 Markdown/DOCX 转换，OfficeCLI 负责结构读取、模板能力、导出复核和预览；
- OfficeCLI 固定为 `1.0.142`，发行包构建时下载并校验哈希，教师电脑不需要连接 GitHub；
- 最终版本要求无需 Python、Node、OpenCode、Obsidian 或命令行；
- 第七阶段才制作标准版和完整离线 OCR 版安装包；当前先完成功能与验收；
- 后续开发严格按《项目实施规划》逐阶段完成。
