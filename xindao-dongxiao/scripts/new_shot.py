"""新建一条动效镜头：把空白模板（或者一个例子）连同引擎、字体复制到一个新文件夹。

用法（Windows 上把 python3 换成 python）：
  python3 new_shot.py <镜头文件夹> --style paper                    从空白模板开始
  python3 new_shot.py <镜头文件夹> --from 对比_划掉换新 --style chalk  从例子开始改（例子名见 assets/examples/）
  再加 --accent e8590c 换成自己的强调色

风格：paper 米白手账 / swiss 白底网格 / aurora 紫夜霓虹 / pastel 奶油渐变 / chalk 黑板粉笔
"""
import shutil, sys, pathlib, re
try:
    sys.stdout.reconfigure(errors="replace"); sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

ROOT = pathlib.Path(__file__).resolve().parent.parent / "assets"
TPL = ROOT / "template"
args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
opt = lambda k: args[args.index(k) + 1] if k in args else None
dst = pathlib.Path(args[0]).expanduser().resolve()
style, accent, src_name = opt("--style"), opt("--accent"), opt("--from")
styles = ["paper", "swiss", "aurora", "pastel", "chalk"]
if style and style not in styles:
    sys.exit(f"没有这套风格：{style}。可选：{'、'.join(styles)}")
if src_name and not (ROOT / "examples" / src_name / "index.html").exists():
    have = "、".join(sorted(p.name for p in (ROOT / "examples").iterdir() if p.is_dir()))
    sys.exit(f"没有这个例子：{src_name}。现有：{have}")
if dst.exists() and any(dst.iterdir()):
    sys.exit(f"{dst} 已经有东西了，换个文件夹名，或者直接改里面的 index.html")
dst.mkdir(parents=True, exist_ok=True)
shutil.copy(TPL / "lib.js", dst / "lib.js")
shutil.copytree(TPL / "fonts", dst / "fonts")
if src_name:
    src = ROOT / "examples" / src_name
    if not (src / "index.html").exists():
        have = "、".join(sorted(p.name for p in (ROOT / "examples").iterdir() if p.is_dir()))
        sys.exit(f"没有这个例子：{src_name}。现有：{have}")
    html = (src / "index.html").read_text(encoding="utf-8")
    html = html.replace("../../template/fonts/", "fonts/").replace("../../template/lib.js", "lib.js")
    for f in src.iterdir():   # 例子里用到的图片一起带上
        if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".webp"}:
            shutil.copy(f, dst / f.name)
else:
    html = (TPL / "index.html").read_text(encoding="utf-8")
if style or accent:
    m = re.search(r"useStyle\('(\w+)'(?:,\s*\{[^}]*\})?\)", html)
    if m:
        st = style or m.group(1)
        call = f"useStyle('{st}'" + (f", {{ accent: '#{accent.lstrip('#')}' }})" if accent else ")")
        html = html[:m.start()] + call + html[m.end():]
(dst / "index.html").write_text(html, encoding="utf-8")
print("镜头文件夹：", dst)
print("下一步：改 index.html 里的 T、SUBS 和 seek(t)，然后：python3 render.py", f'"{dst}"', "--frames 15,45,90")
