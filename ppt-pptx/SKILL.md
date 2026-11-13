---
name: ppt-pptx
description: 生成可编辑的原生 PowerPoint（.pptx，16:9），不是图片、不是网页。用极简 Markdown 写内容，脚本一次出片，文字全是真文本框，客户能直接改。触发：做 pptx、要能改的 PPT、PowerPoint 格式、原生 PPT、给客户的 PPT、投标/汇报用的 PPT、把 HTML PPT 转成能改的版本。
---

# ppt-pptx · 原生 PPT 生成

## 这个 skill 解决什么

`guizang-ppt-skill` 出的是网页 PPT（HTML），好看、动效强，但客户打不开、改不了。
这个 skill 出的是 **.pptx**：PowerPoint 直接打开，每个字都是可编辑文本框，能加批注、能套客户模板、能打印。

一句话分工：

| 场景 | 用哪个 |
| --- | --- |
| 自己讲、线上演示、要视觉冲击 | `guizang-ppt-skill`（HTML） |
| 发给客户、要人改稿、投标/汇报 | **本 skill（pptx）** |

先问用户：**「你自己讲，还是发给别人看？」** 这一句决定用哪个。

## 工作流

1. **收内容**：问清页数、受众、有没有现成文案。没有就让用户口述，你整理成 Markdown。
2. **写 Markdown**：按下面的语法，存成 `deck.md`。
3. **生成**：跑脚本（见下）。
4. **自检**：`check_pptx.py`，看有没有空页/字多/标题过长。
5. **交付**：给 .pptx 路径；需要预览就导出 PNG 或转 PDF。

## Markdown 语法（只有 6 种写法）

```markdown
---
title:  deck 标题
author: 作者名
label:  页眉里显示的短名
theme:  ink        # ink（浅色）或 noir（深色）
date:   2026.11
---

::cover
主标题
副标题

::toc
第一条
第二条

# 页面标题
- 要点一
- 要点二
> 讲的时候补充的话（进演讲者备注，不显示在页面上）

::quote
一句引用，
可以跨两行。
—— 出处

::closing
最后一句
署名
```

- `# ` 开一页，内容全是 `- ` 要点
- `::` 开一页并指定版式：cover / toc / section / bullets / quote / closing
- 不写 `::` 也能自动判断（第一页 cover，含"目录"的页 toc，最后一页 closing）
- 标题写成 `02 我在做什么`，section 版式会自动把数字拆出来

## 命令

```bash
# 生成
python skills/ppt-pptx/scripts/build_pptx.py deck.md -o out/deck.pptx --theme ink

# 自检
python skills/ppt-pptx/scripts/check_pptx.py out/deck.pptx
```

Windows 上 python 用环境自带的解释器；本机：
`C:\Users\叶抒语\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`

## 版式长什么样

- 16:9，左右边距 0.95 英寸，页脚放作者名 + 页码
- 封面：小标签 + 大标题 + 一条强调色短线 + 副标题
- 目录：两列编号，带细分隔线
- 正文：左上页眉，下方标题 30pt，要点按字数自动调 19/17/15/13pt
- 引用：33pt 大字，左下强调线 + 出处
- 结尾：40pt 一句 + 署名

## 内容纪律（写进稿子之前先过一遍）

- 一页一个观点；要点超过 8 条就拆页
- 一页文字不超过 620 字（脚本会按字数自动缩字号，但缩到 13pt 就该拆页了）
- 标题不超过 30 字
- 不编数据、不写"提升 300%"这种没有来源的百分比
- 讲稿别塞进页面，塞进 `> ` 备注里

## 已知边界（v1）

- **不支持图片**：需要配图时，先占位文字，客户自己在 PowerPoint 里拖图，或等 v2
- **不做图表**：柱状图/折线图请用 PowerPoint 自带图表，别用文本画
- **不做动画**：pptx 动画交给用户在 PowerPoint 里加
- **字体**：默认 Microsoft YaHei + Inter；客户电脑没有 Inter 会回退成系统无衬线，中文不受影响

## 常见故障

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 打开后全是默认宋体 | 没走脚本，手写的 pptx | 用脚本生成 |
| 文字溢出页面 | 单页字数太多 | 拆页，或把长句改短 |
| 页眉显示 DECK / | front matter 没写 `label` | 补 `label: 项目名` |
| 中文变成方框 | 客户电脑缺字体 | 让对方装微软雅黑，或改用思源黑体嵌入 |
