# 更新记录

## v0.9.0 — 2026-11-22

- 视频转逐字稿默认改走免费路线，不再默认消耗火山额度：小红书平台字幕 → 必剪云端识别 → 画面字幕识别。`video_download_transcribe.py` 的 `--transcribe` 默认值改为 `free`（`auto` 同义），火山只在明确传 `--transcribe volc` 时使用。
- 新增 `scripts/xhs_subtitle.py`：从小红书视频详情取平台中文字幕，存成 SRT 和纯文字。实测和火山转写稿相似度 0.96。
- 新增 `scripts/bcut_asr.py`：必剪云端识别，免费、不用密钥，调用步骤参照开源项目 VideoCaptioner。实测和火山转写稿相似度 0.98。非官方接口，只用于公开视频。
- 新增 `scripts/screen_subtitle.py`：用 macOS 自带文字识别读画面字幕，作为必剪不可用时的备用，输出标“未校对”。
- 新增 `references/free-transcribe.md`，写清三条路线的顺序、命令、适用范围和失败处理；三条都失败标“待转写”，不自动切到火山，也不用本地语音模型。
- 火山额度池（录音与流式资源轮换、账本、本地文件转写）纳入公开包，改为用户明确要求时才使用；账户数据仍只留在本机 `.local/`，不随包分发。
- 增加免费转写默认值和小红书字幕优先的回归测试。

## v0.8.0 — 2026-09-06

- 增加独立仓库 `aslanyushengjiang-coder/shengjiang-research`，仓库根目录直接提供 `SKILL.md`。
- 增加单 Skill 安装包 `shengjiang-research.zip`，解压后得到一个可导入的 `shengjiang-research` 文件夹，并提供固定的最新版本下载入口。
- 默认将 TikHub Key 一次保存到 Skill 内的 `scripts/.tikhub_api_key`，每次运行实时读取并跨会话复用，文件优先于环境变量。
- 支持任意位置的 Key 文件、`--key-file`、配置中的 `api_key` 与 `local_key_file`；默认自动读取 Skill 根目录 `config.json`，相对文件路径按配置文件目录解析。
- 保留旧 `.local/tikhub-api-key`、环境变量与 macOS Keychain 的兼容读取，不因文件权限模式拒绝读取，也不强制修改已有目录权限。
- 通用请求和视频下载脚本共用配置入口；已配置时直接复用，更新和迁移时保留个人 Key 与配置。
- 将视频下载、平台字幕与第三方 ASR 工作流纳入独立包，支持按状态续跑和已知火山极速资源额度错误的一次标准资源重试。
- 同步配置说明、使用入口和相关验证，保留批量请求数与费用预览、1–3 条样本验证以及原始证据回溯流程。

## 独立发布前

本 Skill 原先位于 [shengjiang-skills](https://github.com/aslanyushengjiang-coder/shengjiang-skills/tree/main/skills/shengjiang-research)。最近的调研 Skill 历史版本为 [v0.7.1](https://github.com/aslanyushengjiang-coder/shengjiang-skills/releases/tag/v0.7.1)，于 2026-07-29 发布。

旧仓库保留其历史版本。本仓库从 `v0.8.0` 起单独维护发布记录与下载包。
