# 免费转逐字稿：平台字幕、必剪识别、画面识别

公开视频转逐字稿默认走这三条路，按顺序试，前一条拿不到再用下一条。它们都不占火山等付费转写额度。火山额度只在用户当轮明确说“用火山转”时才用。

| 顺序 | 方法 | 适用 | 命令 | 准确度（2026-11-22 实测） |
| --- | --- | --- | --- | --- |
| 1 | 小红书平台字幕 | 小红书视频笔记，详情里带 `subtitles` | `scripts/xhs_subtitle.py` | 和火山稿相似度 0.96，平台已断好句 |
| 2 | 必剪云端识别 | 抖音、小红书、视频号等任何已下载的公开视频 | `scripts/bcut_asr.py` | 和火山稿相似度 0.98 |
| 3 | 画面字幕识别 | 画面压了字幕、但必剪接口不可用时 | `scripts/screen_subtitle.py` | 只认得出画面上的字，漏掉没上字幕的口播，标“未校对” |

三条都失败：保留视频和元数据，状态写“待转写”，在汇报里列出哪几条、为什么失败，不自动切到火山，也不用本地 Whisper 等模型兜底。

## 1. 小红书平台字幕

小红书视频详情（`/api/v1/xiaohongshu/app_v2/get_video_note_detail`）里 `video_info_v2.media.video.subtitles` 带 `zh-CN`、`source`、`en-US` 三种 SRT 地址。抖音详情只有 `is_subtitled` 标记，没有字幕地址，抖音直接走第 2 步。

```bash
python3 scripts/tikhub_request.py --path /api/v1/xiaohongshu/app_v2/get_video_note_detail \
  --params '{"share_text":"笔记链接"}' --out raw/detail.json
python3 scripts/xhs_subtitle.py raw/detail.json --note-id <笔记ID> --out transcripts/<笔记ID>
```

字幕地址带签名，几小时后返回 403。拿到详情马上取；过期了重拉详情（约 0.01 美元）。退出码 2 表示这条没有平台字幕，转第 2 步。

## 2. 必剪云端识别

```bash
python3 scripts/bcut_asr.py 视频或音频文件 --out transcripts/<作品ID>
```

- 先用 ffmpeg 抽成 16k 单声道 MP3，再上传 B 站必剪识别接口，轮询拿带时间的结果；输出 `.srt`、`.txt`、`.bcut.json`。
- 免费、不用账号和密钥，只依赖 ffmpeg 和 Python 标准库。调用步骤照开源项目 VideoCaptioner（GPL-3.0）的必剪实现。
- 这是非官方接口，可能限流或关掉。报 HTTP 错误或识别失败时，稍等后重试一次；还不行就转第 3 步。
- 音频会传到 B 站服务器，所以只用于公开视频。客户录音、会议录音、内部视频不走这里。
- 批量时最多 3 条并行，一报错就停下，不硬重试。

视频要先下载。抖音、小红书、视频号用 `video_download_transcribe.py --transcribe off` 只下载不转写，再对下载好的文件跑必剪：

```bash
python3 scripts/video_download_transcribe.py --links-file links.txt --out <目录> --transcribe off
```

## 3. 画面字幕识别

```bash
python3 scripts/screen_subtitle.py 视频文件 --out transcripts/<作品ID>.txt
```

- 每秒抽 2 帧，用 macOS 自带的文字识别（Vision）认中文和英文，挑出现最多的那一横条当字幕区，再去重。
- 只在 macOS 上能用，需要 ffmpeg 和 `swift`（装了 Xcode 命令行工具就有）。
- 输出第一行是“# 画面识别稿，未校对”。画面上没有字幕的口播会漏，花字、标题也可能混进来，交付时注明来源。

## 记录来源

每份逐字稿在结果表里写清来源：`小红书平台字幕`、`必剪识别`、`画面识别（未校对）`或`待转写`。不把画面识别稿当成完整口播稿。
