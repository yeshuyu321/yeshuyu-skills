"""必剪（B 站 Bcut）云端语音识别：把视频里的声音上传到 B 站必剪的识别接口，拿回带时间的逐字稿。
免费、不用账号和密钥、不占火山转写额度；在云端识别，不是本地模型。

调用步骤照开源项目 VideoCaptioner（GPL-3.0，NovaCaption 也基于它）的必剪实现：
申请上传 → 分片上传音频 → 提交上传 → 建识别任务 → 轮询结果。
这不是 B 站官方开放的接口，随时可能被限流或关掉；失败时稍后重试一次，还不行就用 screen_subtitle.py 认画面字幕，
仍不行标“待转写”，不自动改用火山额度。
音频会传到 B 站服务器，只用于公开视频，客户录音、会议录音不要用。

用法：
  python3 bcut_asr.py 视频或音频文件 [--out 输出路径前缀]
输出：<前缀>.srt（带时间字幕）、<前缀>.txt（纯文字）、<前缀>.bcut.json（接口原始结果）
依赖：ffmpeg（抽音频）；只用 Python 标准库。
其他脚本可 `import bcut_asr` 后调 `bcut_asr.transcribe(路径)`，拿回 SRT 文本，失败抛 BcutError。
"""
import argparse, json, os, subprocess, sys, tempfile, time, urllib.request, urllib.error

BASE = "https://member.bilibili.com/x/bcut/rubick-interface"
UA = "Bilibili/1.0.0 (https://www.bilibili.com)"
MODEL_ID = "8"          # 上游实现里上传、建任务用的模型编号
QUERY_MODEL_ID = 7      # 上游实现里查结果用的编号
POLL_SECONDS = 3
POLL_LIMIT = 400        # 3 秒一次，最多约 20 分钟


class BcutError(RuntimeError):
    pass


def req(method, url, body=None, params=None, raw=None, headers=None):
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    h = {"User-Agent": UA}
    data = None
    if raw is not None:
        data = raw
    elif body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        raise BcutError(f"必剪接口返回 HTTP {e.code}（{url.split('?')[0]}），可能被限流或改了接口，稍后重试或改用画面字幕识别")


def api(method, path, **kw):
    _, b = req(method, BASE + path, **kw)
    d = json.loads(b)
    if d.get("code") not in (0, None):
        raise BcutError(f"必剪接口报错 {path}：{d.get('code')} {d.get('message')}")
    return d["data"]


def to_mp3(src):
    out = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", out], check=True)
    return out


def ms(t):
    t = int(t); return f"{t//3600000:02d}:{t//60000%60:02d}:{t//1000%60:02d},{t%1000:03d}"


def recognize(src):
    """上传并识别，返回接口原始结果（dict，含 utterances）。"""
    mp3 = src if src.lower().endswith(".mp3") else to_mp3(src)
    audio = open(mp3, "rb").read()
    if mp3 != src: os.unlink(mp3)
    up = api("POST", "/resource/create", body={"type": 2, "name": "audio.mp3", "size": len(audio), "ResourceFileType": "mp3", "model_id": MODEL_ID})
    per = up["per_size"]; etags = []
    for i, u in enumerate(up["upload_urls"]):
        h, _ = req("PUT", u, raw=audio[i * per:(i + 1) * per])
        etags.append(h.get("Etag") or h.get("ETag") or "")
    done = api("POST", "/resource/create/complete", body={"InBossKey": up["in_boss_key"], "ResourceId": up["resource_id"],
                "Etags": ",".join(etags), "UploadId": up["upload_id"], "model_id": MODEL_ID})
    task = api("POST", "/task", body={"resource": done["download_url"], "model_id": MODEL_ID})["task_id"]
    for _ in range(POLL_LIMIT):
        r = api("GET", "/task/result", params={"model_id": QUERY_MODEL_ID, "task_id": task})
        if r.get("state") == 4: break
        if r.get("state") == 3: raise BcutError(f"必剪识别失败：{r.get('remark') or r}")
        time.sleep(POLL_SECONDS)
    else:
        raise BcutError("必剪识别超时（约 20 分钟没出结果）")
    return json.loads(r["result"])


def utterances(res):
    return [u for u in res.get("utterances", []) if u.get("transcript", "").strip()]


def to_srt(utt):
    return "\n".join(f"{i}\n{ms(u['start_time'])} --> {ms(u['end_time'])}\n{u['transcript'].strip()}\n" for i, u in enumerate(utt, 1))


def transcribe(src):
    """给其他脚本用：识别并返回 SRT 文本。"""
    return to_srt(utterances(recognize(src)))


def run(src, prefix):
    res = recognize(src)
    utt = utterances(res)
    open(prefix + ".bcut.json", "w").write(json.dumps(res, ensure_ascii=False))
    open(prefix + ".srt", "w").write(to_srt(utt))
    open(prefix + ".txt", "w").write("\n".join(u["transcript"].strip() for u in utt) + "\n")
    print(f"完成：{len(utt)} 句，{sum(len(u['transcript']) for u in utt)} 字 → {prefix}.srt / .txt")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="必剪云端语音识别（免费，非官方接口）")
    ap.add_argument("src"); ap.add_argument("--out")
    a = ap.parse_args()
    try:
        run(a.src, a.out or os.path.splitext(a.src)[0])
    except BcutError as e:
        sys.exit(str(e))
