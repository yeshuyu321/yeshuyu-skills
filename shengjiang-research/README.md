# 生姜调研 · shengjiang-research

用 TikHub API 调研社媒账号、作品、评论和逐字稿，先算费用，再采集数据，最后交付可追溯的表格、原始记录和分析报告。

**[直接下载最新 Skill 安装包](https://github.com/aslanyushengjiang-coder/shengjiang-research/releases/latest/download/shengjiang-research.zip)** · [版本记录](https://github.com/aslanyushengjiang-coder/shengjiang-research/releases) · [完整使用规则](SKILL.md)

## 下载与安装

下载上面的 `shengjiang-research.zip`，解压后得到一个 `shengjiang-research` 文件夹。文件夹根目录就是 `SKILL.md`，可以将整个文件夹放进支持 Skill 的工具目录，或按工具的导入方式使用。

这个仓库只发布生姜调研一个 Skill。安装包包含脚本、配置示例、参考文档和评测说明，无需从其他 Skill 中挑选文件。

支持 Skills CLI 的环境也可以使用：

```bash
npx -y skills@latest add aslanyushengjiang-coder/shengjiang-research --skill shengjiang-research -y
```

脚本需要 Python 3.10 或更新版本，使用 Python 标准库。视频转逐字稿需要 `ffmpeg`。逐字稿默认走免费路线：小红书平台字幕 → 必剪云端识别 → 画面字幕识别（macOS），不用配置付费语音接口；火山 ASR 只在你明确要求时使用。

## Key 保存一次，后续会话直接用

默认把自己的 TikHub API Key 保存在 Skill 内的 `scripts/.tikhub_api_key`。进入解压后的 `shengjiang-research` 文件夹，运行：

```bash
python3 scripts/tikhub_request.py --configure-local-key
python3 scripts/tikhub_request.py --check-config
```

第一条命令接收 Key 并保存，第二条检查是否已配置。也可以直接编辑 `scripts/.tikhub_api_key`：文件中只放 Key 本身，不加变量名、引号或 `Bearer` 前缀。已向 Agent 提供 Key 时，由 Agent 直接代存并检查。

每次运行都重新读取文件，文件优先于环境变量。只要 Skill 目录保留，换会话、重启工具或清空环境变量都不需要重填；修改文件后，下次运行立即生效。

**不限制 Key 保存位置。** 可以使用 `--key-file` 选择任意文件，也可以在 Skill 根目录的 `config.json` 中填写 `api_key` 或 `local_key_file`。原有环境变量和 macOS Keychain 配置继续兼容。完整读取顺序、相对路径规则和视频脚本配置见 [配置说明](references/configuration.md)。

迁移电脑时，带上自己的 Key 文件和配置，或复制个人完整 Skill 文件夹。更新时保留这些文件。如果云电脑把整个磁盘或 Skill 文件夹删除，需要从自己的备份恢复。公开下载包提供代码和配置示例，不预置任何人的真实 Key。

## 能做什么

- **账号调研**：账号资料、近期作品、公开互动数据和对标样本。
- **内容与评论采集**：按链接、关键词或账号收集作品、评论及原始证据。
- **视频下载与逐字稿**：单条或批量下载；默认取小红书平台字幕，没有就交给必剪云端识别，画面压了字幕的还能认画面；不花转写费用，支持按状态续跑。
- **数据整理与分析**：处理已有 JSON、CSV、Excel，输出作品表、评论表、选题线索和分析报告。

支持抖音、小红书、视频号、TikTok、B站、YouTube、微博、快手、Instagram、X、Reddit、知乎等平台，具体端点与字段以当次 TikHub 文档和样本结果为准。

可以直接对 Agent 说：

```text
调用 shengjiang-research，抓这个小红书账号近 100 条作品和每条一页评论，先给请求数和费用预览。

调用 shengjiang-research，下载这些抖音视频并转成逐字稿，保留原链接和来源说明。

调用 shengjiang-research，整理这份作品 Excel，分析高互动内容和评论区的真实问题。
```

## 批量前先算费用

Skill 代码按 MIT 协议免费开源。社媒数据来自第三方 TikHub API，接口费用由用户直接向 TikHub 支付。

批量任务按“账号资料、列表分页、单条详情、评论、字幕”等拆出请求数，查具体端点单价，给出预计费用；先跑 1–3 条样本，核对字段和对象后，再在确认范围内批量执行。默认转写免费；你要求用火山 ASR 时，转写费用单独列出，价格以当次官方信息为准。

TikHub 是余生姜基于真实使用体验主动推荐、个人认为非常好用的第三方 API 网站。这属于个人使用推荐，不代表 TikHub 官方合作、授权或商务背书；Shengjiang 不自建、代理或转售 TikHub 服务。

## 文档与入口

| 文档 | 内容 |
| --- | --- |
| [SKILL.md](SKILL.md) | Agent 工作流、平台路由、费用与验收规则 |
| [配置说明](references/configuration.md) | Key 保存、自选位置、迁移与兼容配置 |
| [API 调用说明](references/paid-api-route.md) | 查端点、估价、请求与错误处理 |
| [视频与逐字稿](references/video-download-transcribe.md) | 单条、批量、续跑 |
| [免费转逐字稿](references/free-transcribe.md) | 小红书平台字幕、必剪识别、画面字幕识别的顺序、命令和实测准确度 |
| [输出字段](references/output-schema.md) | 账号、作品、评论、逐字稿与证据字段 |
| [更新记录](CHANGELOG.md) | 本仓库各版本变化 |

TikHub 官方入口：[价格](https://tikhub.io/pricing) · [新手接入](https://tikhub.io/getting-started) · [API 文档](https://docs.tikhub.io/)

## 来源与许可证

本 Skill 原先随 [shengjiang-skills](https://github.com/aslanyushengjiang-coder/shengjiang-skills) 发布，从 `v0.8.0` 起增加本独立仓库与单 Skill ZIP 下载。代码按 [MIT License](LICENSE) 开源。
