# AionUI 可选接入

AionUI 只是独立题库 APP 的可选聊天入口。题目数据、自然语言解析、候选筛选、组卷和导出仍由本地 APP 负责；不安装 AionUI 不影响任何核心功能。

格式依据：[AionUI 官方 Assistant Configuration Guide](https://github.com/iOfficeAI/AionUi/wiki/Assistant-Configuration-Guide)。

## 已提供文件

- Skill 目录：`integrations/aionui/skills/physics-question-bank`
- Assistant Rules：`integrations/aionui/高中物理题库智能体规则.md`
- 本地 API 客户端：Skill 内的 `scripts/question_bank_api.py`

## 在 AionUI 中配置

1. 先启动高中物理题库助手，确认浏览器能打开 `http://127.0.0.1:8000`。
2. 在 AionUI 打开“设置 → Assistants → Create”。
3. 名称填写“高中物理题库智能体”，后端优先选择内置 Aion CLI；也可以选择已安装的 OpenCode。
4. 把 `高中物理题库智能体规则.md` 的内容粘贴到 Rules。
5. 在 Skills 中点击 Add Skills，选择或粘贴本仓库的绝对目录（把前半部分替换成电脑上的实际路径）：

```text
D:\高中物理题库助手\integrations\aionui\skills
```

6. 勾选 `physics-question-bank`，保存 Assistant。

AionUI 当前官方说明确认：自定义 Skill 是包含 `SKILL.md` 的目录，可通过绝对路径扫描；内置 Aion CLI 始终可用，不要求教师另装 OpenCode。

## 典型对话

```text
找 5 道近三年力学创新题，中等难度，覆盖牛顿第二定律，约 45 分钟，带解析。
```

智能体会先调用本地推荐 API，展示候选题号、预览、推荐理由和预计用时。老师确认最终题号后，再说：

```text
保留第 1、3、4 道，生成 A4 单栏题目卷。
```

## 国内网络与离线边界

- Skill 到题库 APP 的通信只走 `127.0.0.1`，不经过公网。
- 不启用 AI 增强时，自然语言解析、筛选和推荐完全离线。
- AionUI [官方项目说明](https://github.com/iOfficeAI/AionUi)列出 DeepSeek、MiniMax、SiliconFlow、火山引擎及 Ollama/LM Studio 等后端；具体可用性仍取决于学校网络和服务商账户。
- 阿里云百炼、DeepSeek、Ollama 等题库内置可选模型与 AionUI 后端相互独立。
- AionUI 的下载安装本身可能受网络环境影响，因此它不能成为教师使用题库的前置条件。
- 最终教师版独立安装包和离线 OCR 模型将在第七阶段处理，本阶段不打包。

## 安全约束

- Skill 不调用题目录入、更新、删除、恢复或维护接口。
- Skill 不直接访问 `vault`。
- 云模型增强只发送找题要求、候选题元数据和短预览，不发送答案、完整解析、图片或整个题库。
- 导出前必须由教师确认题号和导出模式。
