"""把一条镜头的 index.html 逐帧渲染成 1080x1920 / 30fps 视频，或者截检查帧、出审片拼图。苹果电脑和 Windows 都能用。

用法（Windows 上把 python3 换成 python）：
  python3 render.py <镜头文件夹>                    干净版：<文件夹名>.mp4（不带字幕，给剪辑用）
  python3 render.py <镜头文件夹> --sub              带字幕预览版：<文件夹名>_字幕预览.mp4
  python3 render.py <镜头文件夹> --frames 0,45,90   只截这几帧（第几帧，30 帧 = 1 秒）到 检查帧/，默认带字幕黄条（方便看有没有压到图形），加 --nosub 不带
  python3 render.py <镜头文件夹> --review           从字幕预览版每 0.1 秒抽一帧，拼成 审片/审片_N.jpg
  python3 render.py <镜头文件夹> --style chalk      临时换一套风格渲染（文件名后面加风格名），不改 index.html
  python3 render.py <镜头文件夹> --accent e8590c    临时换强调色渲染
  python3 render.py <镜头文件夹> --gif              另外出一张预览动图（宽 360）
横屏：index.html 开头写 <meta name="stage-size" content="1920x1080"> 就按 1920x1080 渲染。

要用到：Python 3.9 以上；pip 装 playwright 和 imageio-ffmpeg；浏览器用 playwright 自带的 Chromium，
没装就用电脑上的 Chrome 或 Edge（Windows 自带 Edge）。缺什么先跑 scripts/check_env.py，它会告诉你装什么。
"""
import subprocess, sys, pathlib, os, shutil, re, base64, urllib.parse
try:
    sys.stdout.reconfigure(errors="replace"); sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

FPS = 30
args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
shot = pathlib.Path(args[0]).expanduser().resolve()
page = shot / "index.html"
if not page.exists():
    sys.exit(f"找不到 {page}")
opt = lambda k: args[args.index(k) + 1] if k in args else None
style, accent = opt("--style"), opt("--accent")
suffix = "".join(f"_{x}" for x in [style, accent] if x)
name = shot.name + suffix
_m = re.search(r'<meta name="stage-size" content="(\d+)x(\d+)"', page.read_text(encoding="utf-8", errors="ignore")[:3000])
STAGE_W, STAGE_H = (int(_m.group(1)), int(_m.group(2))) if _m else (1080, 1920)
sub = "--sub" in args


def ffmpeg_exe():
    """优先用电脑上装好的 ffmpeg；没有就用 pip 装的 imageio-ffmpeg 自带的那一个"""
    if shutil.which("ffmpeg"):
        return shutil.which("ffmpeg")
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        sys.exit("找不到 ffmpeg。请先运行：python3 -m pip install imageio-ffmpeg（Windows 上用 python），再重试")


FF = ffmpeg_exe()


def review():
    src = shot / f"{name}_字幕预览.mp4"
    if not src.exists():
        sys.exit("先跑一遍 --sub 出字幕预览版，再审片")
    out = shot / "审片"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    subprocess.run([FF, "-v", "error", "-y", "-i", str(src), "-vf", "fps=10,scale=360:-1,tile=6x3",
                    str(out / "审片_%d.jpg")], check=True)
    print("审片拼图 ->", out, sorted(p.name for p in out.iterdir()))
    print("每张 18 格，一格 0.1 秒，从左到右、从上到下。")


if "--review" in args:
    review()
    sys.exit()

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("还没装 playwright。请先运行：python3 -m pip install playwright（Windows 上用 python），再重试")

frames_only = [int(x) for x in opt("--frames").split(",")] if "--frames" in args else None
q = {}
if sub or (frames_only is not None and "--nosub" not in args):
    q["sub"] = "1"
if style:
    q["style"] = style
if accent:
    q["accent"] = accent.lstrip("#")
url = page.as_uri() + ("?" + urllib.parse.urlencode(q) if q else "")


def launch(p):
    """依次试：playwright 自带的 Chromium、电脑上的 Chrome、Edge"""
    tried = []
    for kw in [{}, {"channel": "chrome"}, {"channel": "msedge"}]:
        try:
            return p.chromium.launch(args=["--allow-file-access-from-files"], **kw)
        except Exception as e:
            tried.append(str(e).splitlines()[0][:120])
    sys.exit("找不到能用的浏览器。请运行：python3 -m playwright install chromium（Windows 上用 python），或者装一个 Chrome。\n" + "\n".join(tried))


with sync_playwright() as p:
    b = launch(p)
    pg = b.new_page(viewport={"width": STAGE_W, "height": STAGE_H})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    missing = []
    pg.on("requestfailed", lambda r: missing.append(r.url) if r.url.startswith("file://") else None)
    pg.goto(url)
    try:
        pg.wait_for_function("window.READY === true", timeout=30000)
    except Exception:
        sys.exit("页面没有就绪，脚本报错：" + "; ".join(errors))
    pg.wait_for_timeout(300)
    end = pg.evaluate("T.end")
    stage = pg.locator("#stage")
    box = stage.bounding_box()
    clip = {"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"], "scale": 1}
    cdp = pg.context.new_cdp_session(pg)

    def shot_png():
        try:
            return base64.b64decode(cdp.send("Page.captureScreenshot", {"format": "png", "clip": clip, "optimizeForSpeed": True, "captureBeyondViewport": True})["data"])
        except Exception:
            return stage.screenshot(type="png")

    if frames_only is not None:
        out = shot / "检查帧"
        out.mkdir(exist_ok=True)
        for f in frames_only:
            pg.evaluate(f"seek({f / FPS})")
            stage.screenshot(path=str(out / f"{shot.name}{suffix}_f{f:03d}.png"))
        print("检查帧 ->", out)
    else:
        mp4 = shot / (f"{name}_字幕预览.mp4" if sub else f"{name}.mp4")
        n = round(end * FPS)
        ff = subprocess.Popen([FF, "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
                               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "medium",
                               "-movflags", "+faststart", str(mp4)], stdin=subprocess.PIPE)
        for f in range(n):
            pg.evaluate(f"seek({f / FPS})")
            ff.stdin.write(shot_png())
        ff.stdin.close()
        ff.wait()
        print("视频 ->", mp4, n, "帧")
        if "--gif" in args:
            gif = mp4.with_suffix(".gif")
            subprocess.run([FF, "-v", "error", "-y", "-i", str(mp4), "-vf",
                            "fps=15,scale=360:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer",
                            str(gif)], check=True)
            print("预览动图 ->", gif)
    if errors:
        print("页面报错：", errors)
    if missing:
        print(f"页面报错：读不到文件 {len(set(missing))} 个，比如 {urllib.parse.unquote(sorted(set(missing))[0])[-120:]}")
    b.close()
