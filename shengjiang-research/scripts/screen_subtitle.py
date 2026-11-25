"""抖音等视频画面字幕识别：画面上压了字幕的口播视频，每秒截 2 张图，用 macOS 自带 Vision 文字识别读出字幕那一行，去重拼成全文。
不听声音、不用本地大模型、不花钱。必剪接口被限制时的备用办法；识别稿有重复句和错字，标“画面识别稿，未校对”。
用法：python3 screen_subtitle.py 视频 [--out 输出.txt]   依赖：ffmpeg、swift（Xcode 命令行工具）、同目录 screen_text_ocr.swift"""
import argparse, collections, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
BAND = 0.04  # 字幕行纵向位置的容差（画面高度的比例）
ap = argparse.ArgumentParser(); ap.add_argument("src"); ap.add_argument("--out"); a = ap.parse_args()
tmp = tempfile.mkdtemp()
subprocess.run(["ffmpeg", "-v", "error", "-i", a.src, "-vf", "fps=2", "-q:v", "3", os.path.join(tmp, "f%05d.jpg")], check=True)
tsv = subprocess.run(["swift", os.path.join(HERE, "screen_text_ocr.swift"), tmp], capture_output=True, text=True, check=True).stdout
rows = []
for l in tsv.splitlines():
    _, _, t = l.partition("\t")
    rows.append([(float(x.split(":", 1)[0]), x.split(":", 1)[1]) for x in t.split("|") if ":" in x])
ys = collections.Counter(round(y, 2) for r in rows for y, t in r if 4 <= len(t) <= 30)
if not ys: sys.exit("画面上没识别到字幕，换必剪或火山转写")
band = ys.most_common(1)[0][0]
out = []
for r in rows:
    s = " ".join(t for y, t in r if abs(y - band) <= BAND).strip()
    if not s or (out and (s in out[-1])): continue
    if out and out[-1] in s: out[-1] = s; continue
    out.append(s)
dst = a.out or os.path.splitext(a.src)[0] + ".画面识别.txt"
open(dst, "w").write("# 画面识别稿，未校对\n" + "\n".join(out) + "\n")
subprocess.run(["rm", "-rf", tmp])
print(f"完成：{len(out)} 句 → {dst}")
