#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_pptx.py —— 交付前自检：页数、空页、文字量、备注、溢出风险

用法:
    python check_pptx.py deck.pptx
    python check_pptx.py deck.pptx --strict
"""
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu

LIMITS = {
    "title_chars": 40,
    "bullets": 8,
    "chars_per_slide": 620,
}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    strict = "--strict" in sys.argv
    if not args:
        print("usage: python check_pptx.py deck.pptx [--strict]")
        return 2
    path = args[0]
    prs = Presentation(path)
    total = len(prs.slides)
    problems = []

    print(f"文件: {path}")
    print(f"页数: {total}   尺寸: {prs.slide_width / 914400:.2f} x {prs.slide_height / 914400:.2f} 英寸")
    print("-" * 64)

    for i, slide in enumerate(prs.slides, 1):
        texts = [sh.text_frame.text.strip() for sh in slide.shapes
                 if sh.has_text_frame and sh.text_frame.text.strip()]
        all_text = "\n".join(texts)
        chars = sum(len(t) for t in texts)
        has_notes = slide.has_notes_slide and bool(slide.notes_slide.notes_text_frame.text.strip())
        first = texts[0] if texts else ""
        is_chrome = (" / " in first) and len(first) < 40
        title = texts[1] if (is_chrome and len(texts) > 1) else first

        flag = ""
        if not texts:
            problems.append(f"第 {i} 页没有任何文字")
            flag += " [空页]"
        if chars > LIMITS["chars_per_slide"]:
            problems.append(f"第 {i} 页 {chars} 字，超过 {LIMITS['chars_per_slide']}，大概率挤")
            flag += " [字多]"
        if len(title) > LIMITS["title_chars"]:
            problems.append(f"第 {i} 页标题 {len(title)} 字，超过 {LIMITS['title_chars']}")
            flag += " [标题长]"

        print(f"{i:02d}  文字 {chars:>3} 字  块 {len(texts):>2}  备注 {'有' if has_notes else '无'}{flag}  | {title[:34]}")

    print("-" * 64)
    if problems:
        print("问题:")
        for p in problems:
            print("  - " + p)
        return 1 if strict else 0
    print("通过：没有空页、没有超量文字。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
