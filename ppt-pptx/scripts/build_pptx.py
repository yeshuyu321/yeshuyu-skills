#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_pptx.py —— 把极简 Markdown 转成可编辑的原生 .pptx（16:9）

用法:
    python build_pptx.py outline.md -o deck.pptx --theme ink
    python build_pptx.py outline.md -o deck.pptx --theme noir --author 叶抒语

Markdown 约定:
    ---
    title: 叶抒语 · 个人介绍
    author: 叶抒语
    theme: ink
    ---

    ::cover
    叶抒语
    机械大一 / 我在做「企业 AI 知识库」

    ::toc
    我是谁
    我在做什么
    我能提供什么

    # 我是谁
    - 宁波工程学院机械设计制造及其自动化大一
    - 杭州湾校区
    > 讲的时候补一句：这个校区离市区远，反而更适合做事

    ::section
    02
    我在做什么

    ::quote
    把老师傅嘴里的经验，变成能查的东西。
    —— 自己的话

    ::closing
    先做一家，做透，再复制。

版式: cover / toc / section / bullets / quote / closing
不写 :: 时自动判断（第一页 cover，标题含"目录"toc，其余 bullets，最后一页 closing）
"""
import argparse
import re
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt, Emu
from lxml import etree

SLIDE_W, SLIDE_H = 13.333, 7.5
MARGIN = 0.95
CONTENT_W = SLIDE_W - MARGIN * 2

THEMES = {
    "ink": {
        "bg": "F7F5F0",
        "fg": "111111",
        "muted": "6B6B6B",
        "accent": "002FA7",
        "line": "D8D4CB",
    },
    "noir": {
        "bg": "0B0B0C",
        "fg": "F2F0EA",
        "muted": "9A9A96",
        "accent": "5B7BFF",
        "line": "2A2A2C",
    },
}

CJK_FONT = "Microsoft YaHei"
LATIN_FONT = "Inter"
MONO_FONT = "Consolas"


# ---------------- 低层工具 ----------------

def rgb(hexstr):
    return RGBColor.from_string(hexstr.upper())


def set_run(run, size=None, bold=None, color=None, font=None, italic=None, spacing=None):
    f = run.font
    if size is not None:
        f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    if italic is not None:
        f.italic = italic
    if color is not None:
        f.color.rgb = color
    if font:
        f.name = font
        set_ea_font(run, font)
    if spacing is not None:
        rPr = run._r.get_or_add_rPr()
        rPr.set("spc", str(int(spacing)))


def set_ea_font(run, font):
    rPr = run._r.get_or_add_rPr()
    latin = rPr.find(qn("a:latin"))
    if latin is None:
        latin = etree.SubElement(rPr, qn("a:latin"))
    latin.set("typeface", font)
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = etree.SubElement(rPr, qn("a:ea"))
        latin.addnext(ea)
    ea.set("typeface", font)
    cs = rPr.find(qn("a:cs"))
    if cs is None:
        cs = etree.SubElement(rPr, qn("a:cs"))
        ea.addnext(cs)
    cs.set("typeface", font)


def add_rect(slide, x, y, w, h, color, line=None):
    from pptx.enum.shapes import MSO_SHAPE
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(color)
    if line:
        shape.line.color.rgb = rgb(line)
        shape.line.width = Pt(0.75)
    else:
        shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def add_text(slide, x, y, w, h, anchor=MSO_ANCHOR.TOP, wrap=True):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    return box, tf


def para(tf, text, first=False, size=18, color=None, bold=False, font=CJK_FONT,
         align=PP_ALIGN.LEFT, space_after=8, line=1.3, spacing=None):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_after = Pt(space_after)
    p.line_spacing = line
    r = p.add_run()
    r.text = text
    set_run(r, size=size, bold=bold, color=color, font=font, spacing=spacing)
    return p


def bullet_para(tf, text, first=False, size=17, color=None, bullet_color=None, space_after=10, line=1.35):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.space_after = Pt(space_after)
    p.line_spacing = line
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(Emu(Inches(0.28))))
    pPr.set("indent", str(-Emu(Inches(0.28))))
    buClr = etree.SubElement(pPr, qn("a:buClr"))
    srgb = etree.SubElement(buClr, qn("a:srgbClr"))
    srgb.set("val", (bullet_color or "002FA7").upper())
    buFont = etree.SubElement(pPr, qn("a:buFont"))
    buFont.set("typeface", "Arial")
    buChar = etree.SubElement(pPr, qn("a:buChar"))
    buChar.set("char", "▪")
    r = p.add_run()
    r.text = text
    set_run(r, size=size, color=color, font=CJK_FONT)
    return p


def add_footer(slide, page, total, author, theme):
    _, tf = add_text(slide, MARGIN, SLIDE_H - 0.55, CONTENT_W * 0.6, 0.3)
    para(tf, f"{author}", first=True, size=9, color=rgb(theme["muted"]), font=MONO_FONT, spacing=120)
    _, tf2 = add_text(slide, SLIDE_W - MARGIN - 1.2, SLIDE_H - 0.55, 1.2, 0.3)
    para(tf2, f"{page:02d} / {total:02d}", first=True, size=9, color=rgb(theme["muted"]),
         font=MONO_FONT, align=PP_ALIGN.RIGHT, spacing=120)


def add_chrome(slide, label, theme):
    _, tf = add_text(slide, MARGIN, 0.42, CONTENT_W - 2.4, 0.3)
    para(tf, label.upper(), first=True, size=9.5, color=rgb(theme["muted"]), font=MONO_FONT, spacing=160)
    add_rect(slide, MARGIN, 0.78, 0.6, 0.02, theme["accent"])


# ---------------- 版式 ----------------

def slide_cover(prs, slide, data, theme, author):
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = rgb(theme["bg"])

    _, tf = add_text(slide, MARGIN, 1.6, CONTENT_W, 0.4)
    para(tf, "PERSONAL DECK", first=True, size=10, color=rgb(theme["muted"]), font=MONO_FONT, spacing=180)

    _, tf = add_text(slide, MARGIN, 2.15, CONTENT_W, 1.4)
    para(tf, data["title"], first=True, size=48, color=rgb(theme["fg"]), bold=False, line=1.08)

    add_rect(slide, MARGIN, 3.85, 2.2, 0.035, theme["accent"])

    if data.get("subtitle"):
        _, tf = add_text(slide, MARGIN, 4.15, CONTENT_W * 0.86, 1.1)
        para(tf, data["subtitle"], first=True, size=19, color=rgb(theme["muted"]), line=1.45)

    _, tf = add_text(slide, MARGIN, SLIDE_H - 1.15, CONTENT_W, 0.35)
    para(tf, f"{author} · {data.get('date', '')}".strip(" ·"), first=True, size=10,
         color=rgb(theme["muted"]), font=MONO_FONT, spacing=100)


def slide_section(prs, slide, data, theme, author):
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = rgb(theme["bg"])
    num = data.get("number", "")
    if num:
        _, tf = add_text(slide, MARGIN, 1.55, 3.2, 1.2)
        para(tf, num, first=True, size=64, color=rgb(theme["accent"]), font=MONO_FONT, bold=False)
    _, tf = add_text(slide, MARGIN, 3.05, CONTENT_W, 1.6)
    para(tf, data["title"], first=True, size=38, color=rgb(theme["fg"]), line=1.15)
    if data.get("subtitle"):
        _, tf = add_text(slide, MARGIN, 4.45, CONTENT_W * 0.8, 0.9)
        para(tf, data["subtitle"], first=True, size=15, color=rgb(theme["muted"]), line=1.4)


def slide_toc(prs, slide, data, theme, author):
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = rgb(theme["bg"])
    add_chrome(slide, "contents / 目录", theme)
    _, tf = add_text(slide, MARGIN, 1.45, CONTENT_W, 0.8)
    para(tf, "目录", first=True, size=30, color=rgb(theme["fg"]))

    items = data["bullets"][:8]
    n = len(items)
    col_count = 2 if n > 4 else 1
    per_col = (n + col_count - 1) // col_count
    col_w = CONTENT_W / col_count
    for i, item in enumerate(items):
        c = i // per_col
        r = i % per_col
        x = MARGIN + c * col_w
        y = 2.65 + r * 0.82
        _, tf = add_text(slide, x, y, 0.5, 0.4)
        para(tf, f"{i + 1:02d}", first=True, size=10, color=rgb(theme["accent"]), font=MONO_FONT)
        _, tf = add_text(slide, x + 0.55, y - 0.05, col_w - 0.9, 0.5)
        para(tf, item, first=True, size=18, color=rgb(theme["fg"]))
        add_rect(slide, x, y + 0.55, col_w - 1.0, 0.008, theme["line"])


def slide_bullets(prs, slide, data, theme, author):
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = rgb(theme["bg"])
    add_chrome(slide, f"PERSONAL DECK / {data.get('label', '')}".strip(" /"), theme)

    _, tf = add_text(slide, MARGIN, 1.35, CONTENT_W, 1.5)
    para(tf, data["title"], first=True, size=30, color=rgb(theme["fg"]), line=1.15)

    bullets = data["bullets"]
    total_chars = sum(len(b) for b in bullets)
    if total_chars <= 160:
        size, gap = 19, 16
    elif total_chars <= 300:
        size, gap = 17, 12
    elif total_chars <= 460:
        size, gap = 15, 9
    else:
        size, gap = 13, 7

    start_y = 2.85 if len(bullets) <= 4 else 3.05
    _, tf = add_text(slide, MARGIN, start_y, CONTENT_W, SLIDE_H - start_y - 0.9)
    for i, b in enumerate(bullets):
        bullet_para(tf, b, first=(i == 0), size=size, color=rgb(theme["fg"]),
                    bullet_color=theme["accent"], space_after=gap)


def slide_quote(prs, slide, data, theme, author):
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = rgb(theme["bg"])
    _, tf = add_text(slide, MARGIN, 1.85, CONTENT_W, 2.8, anchor=MSO_ANCHOR.TOP)
    para(tf, data["title"], first=True, size=33, color=rgb(theme["fg"]), line=1.32)
    if data.get("subtitle"):
        para(tf, data["subtitle"], size=33, color=rgb(theme["fg"]), line=1.32, space_after=0)
    if data.get("bullets"):
        add_rect(slide, MARGIN, 4.95, 0.9, 0.03, theme["accent"])
        _, tf = add_text(slide, MARGIN + 1.15, 4.82, CONTENT_W - 1.15, 0.6)
        para(tf, data["bullets"][0], first=True, size=13, color=rgb(theme["muted"]))


def slide_closing(prs, slide, data, theme, author):
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = rgb(theme["bg"])
    _, tf = add_text(slide, MARGIN, 2.55, CONTENT_W, 1.9, anchor=MSO_ANCHOR.TOP)
    para(tf, data["title"], first=True, size=40, color=rgb(theme["fg"]), line=1.25)
    add_rect(slide, MARGIN, 4.62, 2.0, 0.03, theme["accent"])
    _, tf = add_text(slide, MARGIN, 4.95, CONTENT_W, 0.5)
    para(tf, data.get("subtitle") or "——", first=True, size=12, color=rgb(theme["muted"]), font=MONO_FONT, spacing=100)


RENDERERS = {
    "cover": slide_cover,
    "toc": slide_toc,
    "section": slide_section,
    "bullets": slide_bullets,
    "quote": slide_quote,
    "closing": slide_closing,
}


# ---------------- 解析 ----------------

def parse(text):
    meta = {}
    body = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = text[m.end():]

    slides = []
    cur = None
    def new_slide(layout=None):
        nonlocal cur
        cur = {"layout": layout, "title": "", "subtitle": "", "bullets": [], "notes": [], "number": ""}
        slides.append(cur)

    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("::"):
            new_slide(line[2:].strip().lower())
            continue
        if line.startswith("# "):
            new_slide()
            cur["title"] = line[2:].strip()
            continue
        if line.startswith("> "):
            if cur:
                cur["notes"].append(line[2:].strip())
            continue
        if line.startswith("- "):
            if cur is None:
                new_slide("bullets")
            cur["bullets"].append(line[2:].strip())
            continue
        # 普通文本：第一行当标题，第二行当副标题
        if cur is None:
            new_slide()
        if cur["layout"] == "toc":
            cur["bullets"].append(line.strip())
            continue
        if not cur["title"]:
            cur["title"] = line.strip()
        elif not cur["subtitle"]:
            cur["subtitle"] = line.strip()
        else:
            cur["bullets"].append(line.strip())

    # 自动判断版式
    n = len(slides)
    for i, s in enumerate(slides):
        if s["layout"]:
            continue
        t = s["title"]
        if i == 0:
            s["layout"] = "cover"
        elif "目录" in t or t.upper() in ("CONTENTS", "TOC"):
            s["layout"] = "toc"
        elif i == n - 1 and len(s["bullets"]) <= 1 and len(t) <= 30:
            s["layout"] = "closing"
        elif not s["bullets"] and len(t) <= 12:
            s["layout"] = "section"
        else:
            s["layout"] = "bullets"

    # section 页把前两位数字拆出来
    for s in slides:
        if s["layout"] == "toc" and not s["title"]:
            s["title"] = "目录"
        if s["layout"] == "section":
            mm = re.match(r"^(\d{1,2})[\s.、]+(.+)$", s["title"])
            if mm:
                s["number"], s["title"] = mm.group(1), mm.group(2)
    return meta, slides


def build(md_path, out_path, theme_name, author_override=None):
    text = Path(md_path).read_text(encoding="utf-8")
    meta, slides = parse(text)
    theme_name = theme_name or meta.get("theme", "ink")
    theme = THEMES.get(theme_name, THEMES["ink"])
    author = author_override or meta.get("author", "")

    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W)
    prs.slide_height = Inches(SLIDE_H)
    blank = prs.slide_layouts[6]

    deck_label = meta.get("label") or (meta.get("title", "").split("·")[0].strip()) or "DECK"
    total = len(slides)
    for i, data in enumerate(slides, start=1):
        data["label"] = deck_label
        slide = prs.slides.add_slide(blank)
        renderer = RENDERERS.get(data["layout"], slide_bullets)
        renderer(prs, slide, data, theme, author)
        if data["layout"] not in ("cover", "closing"):
            add_footer(slide, i, total, author, theme)
        if data["notes"]:
            slide.notes_slide.notes_text_frame.text = "\n".join(data["notes"])

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    prs.save(out_path)
    return slides, theme_name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--theme", default=None, choices=list(THEMES.keys()))
    ap.add_argument("--author", default=None)
    args = ap.parse_args()

    slides, theme = build(args.input, args.output, args.theme, args.author)
    print(f"[ok] {len(slides)} slides -> {args.output}  (theme={theme})")
    for i, s in enumerate(slides, 1):
        print(f"  {i:02d} {s['layout']:<8} {s['title'][:40]}")


if __name__ == "__main__":
    sys.exit(main())
