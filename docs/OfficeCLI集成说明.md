# OfficeCLI 集成说明

## 固定版本与用途

项目固定使用 OfficeCLI `1.0.142`。上游仓库：

https://github.com/iOfficeAI/OfficeCLI

当前接入能力：

- 读取 DOCX 根结构；
- 合并 `{{key}}` 模板变量；
- 校验 OOXML 文档结构；
- 检查文档 issues；
- 生成 HTML 排版预览。

OfficeCLI 命令由 `app/services/office.py` 统一封装并串行执行。

## Windows 分发

构建机执行 `scripts/download_officecli.ps1`，下载
`officecli-win-x64.exe` 并核对固定 SHA-256。二进制进入安装包，但不提交到
Git 仓库。

教师运行软件时：

- 不访问 GitHub；
- 不自动更新 OfficeCLI；
- 不要求安装 Microsoft Office；
- 不要求配置命令行。

应用运行时设置 `OFFICECLI_SKIP_UPDATE=1`。国内网络是否能访问 GitHub不会影响
已打包版本的基础功能。

## 许可证

OfficeCLI 使用 Apache License 2.0。安装包必须一并包含：

- `third_party/OfficeCLI/LICENSE`
- `third_party/OfficeCLI/NOTICE`

不得在发行包中删除上游归属信息。

## 降级行为

Pandoc 负责从 Markdown 生成 DOCX。OfficeCLI 用于复核和预览；如果 OfficeCLI
不可用或复核失败：

1. 已生成的 DOCX 不删除；
2. 界面显示明确提示；
3. 教师仍可下载 Word；
4. 日志保留失败原因。
