# GitHub 上传说明

这个项目不要上传到：

```text
https://github.com/HelloTheWorld12138/computational-physics
```

那个仓库是课程仓库，题库助手应该使用一个单独的新仓库。

## 推荐仓库名

建议新建一个私有仓库，例如：

```text
HelloTheWorld12138/physics-question-bank-assistant
```

或：

```text
HelloTheWorld12138/whitecaps-question-bank
```

## 本机上传步骤

1. 在 GitHub 上新建一个 Private 仓库，不要勾选初始化 README。
2. 安装 Git for Windows：

```text
https://git-scm.com/download/win
```

3. 在项目目录打开 PowerShell：

```text
F:\文档\WhiteCaps
```

4. 运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\上传到新GitHub仓库.ps1 -RepositoryUrl "https://github.com/HelloTheWorld12138/physics-question-bank-assistant.git"
```

脚本会拒绝上传到 `computational-physics`，避免和课程仓库混在一起。

## 不会上传的内容

`.gitignore` 已排除：

- `.venv/`
- `exports/` 运行导出文件
- 题库真实题目数据
- 题库真实图片数据
- `tools/pandoc/`
- `tools/opencode/node_modules/`
- 本地临时文件

第一次 clone 后运行：

```text
start.bat
```

启动脚本会安装 Python 依赖，并下载 Pandoc。
