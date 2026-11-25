# 火山转写额度池

默认不用：公开视频转逐字稿先走 [free-transcribe.md](free-transcribe.md) 的免费路线（平台字幕 → 必剪识别 → 画面字幕识别）。本页只在用户当轮明确要求“用火山转”时适用。

此入口同时管理旧 AUC Cluster、大模型录音 V3 与两种流式资源。用户的实际额度、到期日、密钥与验证记录在本机 `.local/`，公开 Skill 不携带账户数据。

## 本机数据

- `.local/volc-asr-pool.json`：凭据与每个资源的开关、到期日、控制台快照和本地估算剩余量。权限 0600，目录 0700。后续会话直接复用，不重新索取。
- `.local/额度与接入记录.md`：可读余额快照、实例对应与实测范围，不包含密钥值。
- `.local/asr-ledger.json`：原任务 ID、预留时长、完成结果与错误状态；额度用完退出可用列表，但保留账本和凭据以便核对，不删除云端实例。
- 配置路径可以用 `VOLC_ASR_POOL_CONFIG` 覆盖。状态查询不会显示密钥：

```bash
python3 scripts/volc_pool.py --status
```

## 自动转写

平台链接走 `video_download_transcribe.py`，会测量实际提交 URL 的时长，并按平台和内容 ID 避免重复消费。

已有音频 URL：先用 ffprobe 获取时长，再调用：

```bash
python3 scripts/volc_pool.py --url 'https://example.com/audio.mp3' \
  --format mp3 --duration 60 --uid stable-job-id --out /path/to/transcript
```

`--duration` 必须是真实时长，示例 60 不能照抄。显式 `--profile` 只用指定入口，适合单资源验证。URL 变化会改变此命令的任务标识；平台流水线和本地文件入口有独立稳定标识。

本地视频或录音：

```bash
python3 scripts/volc_local.py --file /path/to/video.mp4 --out-dir /path/to/transcript
```

需要 ffmpeg、ffprobe 与 cloudflared；找不到 cloudflared 时设 `CLOUDFLARED=/path/to/cloudflared`。只向临时公网地址提供本次提取的单个音轨，关闭目录列表，结束后关闭隧道。输出 Markdown、TXT 与 JSON（包含分句时间戳）；这是第三方识别，未使用本地 ASR 模型。

## 扣量与恢复

1. 录音资源按配置顺序使用：按到期日先用旧录音、再用流式额度，再到大模型试用及已购套餐。流式使用独立 WebSocket 协议，45 秒分片转写，成功片缓存并合并分句时间戳；不把它伪装成录音 HTTP。
2. 每次串行持锁，录音预留 `ceil(实际秒数)+1` 秒；流式预留 `ceil(实际秒数)+2×分片数` 秒。剩余量不足整条音频时跳过；到期或余额归零自动停用。余额不足这一条不等于已经用完，不删剩余尾额。
3. 只有明确的 `audio_duration_lifetime/month/total` 拒绝且无服务端任务 ID，才把该资源标为耗尽并继续下一项。鉴权、QPS、网络、服务故障停止，不乱切。
4. 已接受的任务超时只查询原 ID；提交结果不确定时保持预留并停止自动重投，先核对账本与控制台。流式连接无法按 HTTP 任务 ID 恢复；已成功片保留，任何尝试发送音频后的错误都停止自动重投或切换，先核对账本，避免重复消费。片段边界需人工审听。
5. 同一任务成功后复用账本中的逐字稿。不要删除账本来解决超时，避免重复扣费。资源全不可用就停止，禁止自动转到配置外的后付费资源。
6. `remaining_hours` 是控制台快照减去本机保守预留，**不是实时账单查询**。若其他工具/应用也在消费，批量前从控制台更新快照；本地余额不能保证拦截账户其他入口的消费。正式实例可能自动后付费，套餐边缘必须复核余额，未授权额外余额支出。

## 公开发行

`.local/`、`.env*`、`scripts/.tikhub_api_key`、`config.json` 和缓存必须显式排除；不能直接压缩整个 Skill 目录。Git 忽略与打包排除是两回事。仅当用户要求分发才打包，不上传本机数据。

没有私有额度池时，保留原有 V3 API Key 和 Keychain AUC 兼容路径；这种独立安装不继承本机余额、轮换或额度保护，不能宣称共享本机套餐。

官方录音接口：<https://docs.volcengine.com/docs/DoubaoVoice/task-submission-http-1?lang=zh>。
流式单向接口（独立协议，已接入）：<https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-automatic-speech-recognition-websocket?lang=zh>。

## 流式运行依赖

流式客户端使用 aiohttp。系统 Python 无该依赖时自动调用 `.local/venv/bin/python`，密钥仅通过子进程 stdin 传入，不进入命令行或环境变量。新设备安装一次：

```bash
python3 -m venv .local/venv
.local/venv/bin/python -m pip install 'aiohttp>=3.9,<4'
```

旧流式资源 `volcengine_streaming_common` 使用 v2；新流式资源 `volc.seedasr.sauc.duration` 使用 v3。两者分别实测后才 enabled=true。流式按接近实时速度处理，长音频会比录音异步接口慢；45 秒分片的长音频合并有单独测试，不宣称没有分段识别误差。
