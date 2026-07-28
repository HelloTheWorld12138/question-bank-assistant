# 题搭子

题搭子是一款面向高中物理教师的本地题库与组卷工具。题目、图片和导出文件默认保存在本机，不需要将题库上传到云端。

![题搭子 Logo](./static/brand/tidazi-logo.png)

当前稳定版本：**1.0.0**

## 能做什么

- 导入 Word、PDF、图片中的题目，批量整理后审核入库
- 手动录入题目，并即时预览文字、图片和公式
- 按知识板块或题型浏览题库，并按难度、年份和来源筛选
- 选择题目并生成题目卷、答案卷和解析卷
- 导出 A4 单栏、A4 双栏或正式考试卷 Word 文档
- 可选使用本地或云端模型辅助分类、找题与组卷

## 下载与使用

### macOS

从 [Releases](../../releases/latest) 下载名称包含 `macOS` 的 `.dmg` 文件，拖入“应用程序”后打开。

当前安装包适用于 Apple 芯片 Mac。应用尚未经过 Apple 公证；如果 macOS 首次打开时提示无法验证开发者，请在“系统设置 → 隐私与安全性”中确认打开。

### Windows

从 [Releases](../../releases/latest) 下载 `题搭子-Windows.zip`，解压后运行 `题搭子.exe`。

Windows 构建产物为便携版，无需安装 Python。

发布页同时提供 `SHA256SUMS.txt`，可用于校验下载文件的完整性。

## 本地开发

```bash
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 <http://127.0.0.1:8000>。

运行测试：

```bash
python -m pytest
```

## 打包

macOS：

```bash
bash scripts/build_macos_dmg.sh
```

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

Windows 需要 Python 3.10；仓库中的 GitHub Actions 也可直接生成 Windows 包。

## 版本记录

完整变更记录见 [CHANGELOG.md](./CHANGELOG.md)。

## 项目结构

```text
app/        后端与题库服务
static/     网页界面与本地公式渲染资源
templates/  Word 试卷模板
assets/     应用 Logo 与平台图标
scripts/    macOS / Windows 打包脚本
tests/      自动化测试
```

## 数据与隐私

运行后的题库数据不纳入仓库：题目、图片、导出文件、日志和本地设置均被忽略。使用云端模型前，请自行确认发送范围与服务商隐私政策。
