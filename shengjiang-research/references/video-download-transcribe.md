# 视频下载与逐字稿快捷模式

当用户给出一条或一批公开视频链接，并要求下载、转写、提取逐字稿或准备对标素材时，优先使用本模式。它把平台识别、TikHub 详情请求、视频下载、免费转写、断点续跑和状态记录收成一条确定性流水线，避免 Agent 逐步重复编排。

默认 `--transcribe free`（`auto` 同义）：平台明确字幕 → 小红书平台字幕 → 必剪云端识别，不占火山额度。`--transcribe volc` 只在用户当轮明确要求火山时用；`--transcribe off` 只下载。三条免费路线的细节和画面字幕识别见 [free-transcribe.md](free-transcribe.md)。

## 支持范围

| 平台 | 下载 | 转写 |
| --- | --- | --- |
| 抖音 | TikHub Web 单条详情中的 MP4 地址 | 详情没有字幕地址；下载后交给必剪识别，画面压了字幕的可再用画面识别 |
| 小红书视频笔记 | TikHub App V2 视频详情中的 H.264 MP4 | 详情 `video_info_v2.media.video.subtitles` 的中文 SRT 优先（签名几小时后失效）；没有就交给必剪识别 |
| 微信视频号 | TikHub V2 详情 + 可选 WASM 解密下载器 | 平台明确字幕优先；否则解密后的本地 MP4 交给必剪识别 |

脚本不会把作品标题、简介或 `caption` 字段误当成逐字稿。只有明确的字幕 / transcript 字段才算平台字幕。

## 配置检查

```bash
python3 scripts/video_download_transcribe.py --check-config
```

TikHub Key 与 `tikhub_request.py` 共用读取方式：默认实时读取 Skill 内 `scripts/.tikhub_api_key`，文件优先于环境变量，已保存就跨会话复用；也兼容旧 `.local/tikhub-api-key`。未指定配置时自动读取 Skill 根目录 `config.json`，支持其中的 `api_key` 或 `local_key_file`。

自选配置或 Key 文件也可直接用于视频脚本：

```bash
python3 scripts/video_download_transcribe.py --config /path/to/config.json --check-config
python3 scripts/video_download_transcribe.py --key-file /path/to/my-tikhub-key --check-config
```

配置中的相对路径按配置文件所在目录解析。一次保存和迁移说明见 `configuration.md`，视频任务不需要重新配置同一份 TikHub Key。

以下火山说明只在用户明确要求 `--transcribe volc` 时适用。火山语音优先读取 Skill 私有额度池 `.local/volc-asr-pool.json`，运行说明见 [volc-quota-pool.md](volc-quota-pool.md)。存在额度池时，按已启用资源的到期日顺序消费（流式走独立分片适配），明确额度耗尽才自动切下一个；不会退回未登记的旧密钥或额外后付费。

- 用户授权后把凭据保存在 Skill `.local/` 内，目录 0700、文件 0600；密钥、账户额度和运行账本均不进入 Git 或公开发行包。
- 公共链接流水线用 ffprobe 测量实际提交的音频时长，再预留额度。保留标点、分句时间戳和语气词，不把逐字稿改成摘要。
- 已完成任务复用结果；提交后超时只查原任务。限流、鉴权、网络错误不冒充额度耗尽。
- 本地文件使用 `scripts/volc_local.py`：仅公开临时音轨，任务结束关闭隧道。原目录和凭据目录不会通过隧道提供访问。
- 未配置额度池的其他安装，仍兼容 `~/.config/shengjiang/volc-asr.json` 的 V3 API Key，以及环境变量/Keychain 的旧 AUC 凭据。该兼容模式不拥有本机的额度池保护；详情见额度池文档。

视频号解密器使用：

```bash
export SHENGJIANG_WECHAT_DOWNLOADER="/path/to/download_wechat_videos.cjs"
```

该路径属于用户自己的本机配置，不写入 Skill 或 Git。

## 先预览

任何批量任务先运行：

```bash
python3 scripts/video_download_transcribe.py \
  --links-file links.txt \
  --dry-run
```

输出会列出平台、端点和 TikHub 预计请求数。TikHub 费用按端点另行查询；默认免费转写不产生转写费用；用户要求火山时，火山费用单列，不混在 TikHub 费用里。

## 单条执行

```bash
python3 scripts/video_download_transcribe.py \
  --url "https://v.douyin.com/example/" \
  --out "/absolute/path/to/project/social-research"
```

未传 `--out` 时，只写系统临时目录。长期证据必须显式写入项目唯一真源。

## 批量与断点续跑

```bash
python3 scripts/video_download_transcribe.py \
  --links-file links.txt \
  --out "/absolute/path/to/project/social-research"
```

重新运行同一输出目录时，脚本先读取 `manifest.json`。状态为 `done` 的链接会在 TikHub 请求前跳过，避免重复扣费。使用 `--replace` 才重新抓取和覆盖。

## 输出

```text
social-research/
├── manifest.json
├── 001-douyin-作品ID/
│   ├── video.mp4
│   ├── transcript.txt
│   ├── transcript.md
│   ├── transcript.raw.json
│   ├── metadata.json
│   ├── metadata.raw.sanitized.json
│   └── status.json
└── 002-xiaohongshu-作品ID/
    └── ...
```

`metadata.raw.sanitized.json` 会去掉 Key、临时下载签名、`decode_key`、`cache_url` 等可复用字段。脚本只在内存或系统临时目录使用真实媒体地址。

## 状态解释

- `done`：视频和逐字稿都已完成，或用户用 `--transcribe off` 明确关闭转写；
- `partial`：视频已下载，但免费路线没拿到逐字稿（状态里的 blocker 写了原因），先试 `scripts/screen_subtitle.py`，仍不行标“待转写”；
- `failed`：详情请求、解析或视频下载失败。

免费路线都失败时保留视频和元数据，写清 blocker；不自动切到火山，禁止改用本地 Whisper。

## 离线解析测试

开发和字段映射测试可使用保存的 TikHub 响应，不产生付费请求：

```bash
python3 scripts/video_download_transcribe.py \
  --url "https://www.douyin.com/video/example" \
  --metadata-json sample.json \
  --transcribe off \
  --out "/tmp/shengjiang-video-test"
```
