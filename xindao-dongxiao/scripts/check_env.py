"""检查这台电脑能不能出动效片：Python 版本、playwright、浏览器、ffmpeg。缺什么就告诉你装什么。
用法：python3 check_env.py（Windows 上用 python check_env.py）
加 --install 会自动用 pip 装缺的两个包（playwright、imageio-ffmpeg），再装 playwright 自带的浏览器。
"""
import sys, shutil, subprocess, platform
try:
    sys.stdout.reconfigure(errors="replace"); sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

win = platform.system() == "Windows"
py = "python" if win else "python3"
ok = True
install = "--install" in sys.argv


def pip(*pk):
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", *pk], check=False)


print(f"电脑：{platform.system()} {platform.machine()}，Python {platform.python_version()}")
if sys.version_info < (3, 9):
    ok = False
    print("[缺] Python 版本太旧，要 3.9 以上。到 https://www.python.org/downloads/ 装新版（Windows 安装时勾上 Add python.exe to PATH）")

try:
    import playwright  # noqa
    print("[有] playwright 已装")
except ImportError:
    if install:
        pip("playwright")
    else:
        ok = False
        print(f"[缺] 没装 playwright：运行 {py} -m pip install playwright")

if shutil.which("ffmpeg"):
    print("[有] ffmpeg：用电脑上装好的", shutil.which("ffmpeg"))
else:
    try:
        import imageio_ffmpeg
        print("[有] ffmpeg：用 imageio-ffmpeg 自带的", imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        if install:
            pip("imageio-ffmpeg")
        else:
            ok = False
            print(f"[缺] 没有 ffmpeg：运行 {py} -m pip install imageio-ffmpeg")

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        got = None
        for kw, name in [({}, "playwright 自带的 Chromium"), ({"channel": "chrome"}, "电脑上的 Chrome"), ({"channel": "msedge"}, "电脑上的 Edge")]:
            try:
                b = p.chromium.launch(**kw)
                b.close()
                got = name
                break
            except Exception:
                continue
        if got:
            print("[有] 浏览器：", got)
        elif install:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
        else:
            ok = False
            print(f"[缺] 找不到能用的浏览器：运行 {py} -m playwright install chromium")
except ImportError:
    pass

if install:
    print("\n装完了，再跑一次不带 --install 的检查确认。")
elif ok:
    print("\n都齐了，可以出片。")
else:
    print(f"\n照上面标 [缺] 的装好，或者直接运行 {py} check_env.py --install 让它自己装。")
