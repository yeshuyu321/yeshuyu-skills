"""小红书平台字幕：从 TikHub 小红书视频详情里取平台自带的中文字幕，存成 SRT 和纯文字。
不花转写额度，也不上传音频。

先用 tikhub_request.py 拉详情（每次约 0.01 美元，以当次价格为准）：
  python3 scripts/tikhub_request.py --path /api/v1/xiaohongshu/app_v2/get_video_note_detail \
    --params '{"share_text":"笔记链接"}' --out detail.json
再取字幕：
  python3 scripts/xhs_subtitle.py detail.json [--note-id 笔记ID] [--out 输出路径前缀]

字幕地址带签名、几小时后失效（旧地址返回 403），所以拿到详情后马上取；失效了就重拉一次详情。
详情里常带好几条相关笔记，默认取第一条；指定 --note-id 时只取这一条。
输出：<前缀>.srt、<前缀>.txt。没有中文字幕时退出码 2，交给 bcut_asr.py。
"""
import argparse, json, os, re, sys, urllib.request, urllib.error

LANG_ORDER = ("zh-CN", "source")  # zh-CN 是平台整理过的中文字幕；source 是原声识别稿，备用


def notes(payload):
    data = payload.get("data", payload)
    while isinstance(data, dict) and "data" in data:
        data = data["data"]
    return data if isinstance(data, list) else [data]


def pick_url(note):
    subs = (((note.get("video_info_v2") or {}).get("media") or {}).get("video") or {}).get("subtitles") or {}
    for lang in LANG_ORDER:
        for item in subs.get(lang) or []:
            if item.get("url"):
                return lang, item["url"]
    return None, None


def srt_to_text(srt):
    lines = []
    for block in re.split(r"\n\s*\n", srt.strip()):
        rows = [r for r in block.splitlines() if r.strip() and not r.strip().isdigit() and "-->" not in r]
        if rows:
            lines.append("".join(r.strip() for r in rows))
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="取小红书视频平台字幕")
    ap.add_argument("detail"); ap.add_argument("--note-id"); ap.add_argument("--out")
    a = ap.parse_args()
    items = [n for n in notes(json.load(open(a.detail))) if isinstance(n, dict)]
    if a.note_id:
        items = [n for n in items if a.note_id in (n.get("id"), n.get("note_id"))]
    if not items:
        sys.exit("详情里没找到这条笔记，检查 --note-id 或重拉详情")
    note = items[0]
    lang, url = pick_url(note)
    if not url:
        print("这条笔记没有平台字幕，改用 bcut_asr.py", file=sys.stderr)
        sys.exit(2)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        srt = urllib.request.urlopen(req, timeout=60).read().decode("utf-8-sig")
    except urllib.error.HTTPError as e:
        sys.exit(f"字幕地址返回 HTTP {e.code}：签名多半过期了，重拉一次详情再取")
    prefix = a.out or os.path.splitext(a.detail)[0]
    open(prefix + ".srt", "w").write(srt)
    text = srt_to_text(srt)
    open(prefix + ".txt", "w").write(text)
    print(f"完成：{note.get('id')}《{note.get('title', '')}》{lang} 字幕 {len(text.strip())} 字 → {prefix}.srt / .txt")


if __name__ == "__main__":
    main()
