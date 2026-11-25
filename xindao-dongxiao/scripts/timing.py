"""把口播里的关键词换成镜头里的秒数，填进 index.html 的 T 和 SUBS。
有配音（先用剪映等工具导出 srt 字幕文件）：
  python3 timing.py --srt 字幕.srt --from 12.3 --to 20.1 --words 以前,三天,现在,一个下午
  --from/--to 是这条镜头在整条配音里的起止秒，输出的秒数都已减去 --from。
没有配音（按正常语速估，每秒 4.5 个字，交付时要说明是估的）：
  python3 timing.py --text "以前剪一条视频要三天，现在用AI，一个下午就搞定。" --words 以前,三天,现在,一个下午
  对方给了总时长（比如「视频时长 8 秒」）：加 --fit 7.5，按说完用 7.5 秒、最后留 0.5 秒停顿来排
（Windows 上把 python3 换成 python）
"""
import sys, re
try:
    sys.stdout.reconfigure(errors="replace"); sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

a = sys.argv[1:]
get = lambda k, d=None: a[a.index(k) + 1] if k in a else d
words = [w for w in (get("--words", "") or "").split(",") if w]
cps = float(get("--cps", 4.5))
PUNC = "，。！？、；：,.!?;: 　\"“”'‘’（）()…—-"


def ts(s):
    h, m, rest = s.split(":")
    sec, ms = rest.replace(".", ",").split(",")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000


segs = []
if get("--srt"):
    raw = open(get("--srt"), encoding="utf-8").read().strip()
    for block in re.split(r"\n\s*\n", raw):
        lines = block.strip().splitlines()
        tl = next((l for l in lines if "-->" in l), None)
        if not tl:
            continue
        s, e = [ts(x.strip()) for x in tl.split("-->")]
        text = "".join(lines[lines.index(tl) + 1:])
        segs.append((s, e, text))
    t0, t1 = float(get("--from", 0)), float(get("--to", 1e9))
    segs = [(s - t0, e - t0, x) for s, e, x in segs if e > t0 and s < t1]
elif get("--text"):
    t = 0.15
    for part in re.split(r"(?<=[，。！？；,.!?;])", get("--text")):
        n = len([c for c in part if c not in PUNC])
        if not n:
            continue
        segs.append((t, t + n / cps, part))
        t += n / cps + (0.18 if part[-1:] in "，,;；" else 0.3)
else:
    sys.exit(__doc__)
if get("--fit") and segs:
    k = (float(get("--fit")) - segs[0][0]) / (segs[-1][1] - segs[0][0])
    segs = [(segs[0][0] + (s - segs[0][0]) * k, segs[0][0] + (e - segs[0][0]) * k, x) for s, e, x in segs]

print("字幕（填进 SUBS）：")
print("window.SUBS = [" + ",".join(f"[{s:.2f},{e:.2f},'{x.strip(PUNC)}']" for s, e, x in segs) + "];")
print("\n关键词（这个词开口的那一刻，填进 T）：")
for w in words:
    hit = False
    for s, e, x in segs:
        i = x.find(w)
        if i < 0:
            continue
        chars = [c for c in x if c not in PUNC]
        before = len([c for c in x[:i] if c not in PUNC])
        print(f"  {w}: {s + (e - s) * before / max(1, len(chars)):.2f}  （在「{x.strip()}」里）")
        hit = True
        break
    if not hit:
        print(f"  {w}: 找不到，检查是不是转写写成了别的字")
end = segs[-1][1] if segs else 0
print(f"\n这一段口播到 {end:.2f} 秒说完，镜头总长 T.end 建议 {end + 0.5:.1f}（说完再停 0.5 秒）")
