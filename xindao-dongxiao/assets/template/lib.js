// 新岛动效引擎：每条镜头的 index.html 先加载它，再写自己的 seek(t)。
// 一切都由时间 t（秒）算出来，不用 CSS 动画、不用计时器，所以逐帧截图每次都一样。

// ---------- 时间和缓动 ----------
const W = 1080, H = 1920, FPS = 30;
const $ = id => document.getElementById(id);
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, p) => a + (b - a) * p;
const prog = (t, a, b) => clamp((t - a) / (b - a));              // t 在 a→b 之间走到几成
const eOut = p => 1 - Math.pow(1 - p, 3);                          // 先快后慢（入场默认）
const eIn = p => p * p * p;                                        // 先慢后快（被吸走、掉下去）
const eIO = p => p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;   // 两头慢（挪位置）
const eBack = p => { const c = 1.7; return 1 + (c + 1) * Math.pow(p - 1, 3) + c * Math.pow(p - 1, 2); };  // 弹一下
// 闪一下再回落：a 时刻起 rise 秒升到 1，再 decay 秒落到 base
const flash = (t, a, rise, decay, base = 0) => t < a ? 0 : t < a + rise ? (t - a) / rise : lerp(1, base, eOut(prog(t, a + rise, a + rise + decay)));
const pulse = (t, a, dur) => Math.sin(Math.PI * prog(t, a, a + dur)); // 0→1→0
// 以中心点摆放 DOM 元素
const place = (el, x, y, s = 1, extra = '') => { el.style.transform = `translate(${x}px,${y}px) translate(-50%,-50%) scale(${s}) ${extra}`; };
function rng(seed) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
// 颜色小工具：两个 #rrggbb 按比例混合
const hex2rgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
const mixHex = (a, b, p) => '#' + hex2rgb(a).map((v, i) => Math.round(lerp(v, hex2rgb(b)[i], p)).toString(16).padStart(2, '0')).join('');

// ---------- 风格 ----------
// 颜色的意思固定（每套都一样）：accent 强调色 = 解决、结论、新的；warn = 问题、风险、旧的、被否掉的；data = 次要信息、数据来源
// 想换成自己的颜色：useStyle('paper', { accent: '#你的颜色' })，其余颜色会跟着算好
const STYLES = {
  paper: {   // 米白手账：米白纸、点阵、墨线、荧光笔
    label: '米白手账', light: true, bgKind: 'paper',
    bg: ['#f4efe6', '#efe8db'], dot: '#d6ccba',
    accent: '#1f7a5c', warn: '#e2483d', data: '#5a6b8c', text: '#1f1d1a', dim: '#8c8476', mark: '#ffe46b',
    lineW: 4.5, glow: 0, flash: null,
    css: `
      .w{color:var(--text);}
      .a{color:var(--accent);background:linear-gradient(transparent 60%,var(--mark) 60%,var(--mark) 90%,transparent 90%);-webkit-background-clip:border-box;background-clip:border-box;padding:0 6px;}
      .card{background:#fffdf8;border:3px solid var(--text);border-radius:14px;box-shadow:8px 8px 0 var(--text);}
      .card.hot{border-color:var(--accent);box-shadow:8px 8px 0 var(--accent);}
      .chip{background:#fffdf8;border:2.5px solid var(--text);color:var(--text);}
      .label{font-family:WK,Body,sans-serif;color:var(--dim);}
      #vignette{display:none;}`,
  },
  swiss: {   // 白底网格：白纸、细网格、黑字、一种纯色强调（克莱因蓝）
    label: '白底网格', light: true, bgKind: 'swiss',
    bg: ['#f7f7f5', '#f7f7f5'], dot: '#e2e2de',
    accent: '#1d3bff', warn: '#ff3b1f', data: '#7a7a7a', text: '#111111', dim: '#9a9a96', mark: '#1d3bff',
    lineW: 5, glow: 0, flash: null, onHot: '#ffffff',
    css: `
      .w{color:var(--text);}
      .a{color:var(--accent);}
      .card{background:#ffffff;border:2.5px solid var(--text);border-radius:0;box-shadow:none;}
      .card.hot{background:var(--accent);color:#fff;border-color:var(--accent);}
      .card.hot div{color:#fff;} .card.hot .mid,.card.hot .no{color:rgba(255,255,255,.75);}
      .chip{background:#fff;border:2px solid var(--text);border-radius:0;color:var(--text);}
      .label{font-family:Body,sans-serif;letter-spacing:6px;color:var(--text);}
      #vignette{display:none;}`,
  },
  aurora: {  // 紫夜霓虹：深紫底、流动的极光色块、扫描线、粉色发光
    label: '紫夜霓虹', light: false, bgKind: 'aurora',
    bg: ['#140a2e', '#07030f'], dot: '#2a1a55',
    accent: '#ff5ccf', warn: '#ff9f1c', data: '#7fd6ff', text: '#f3eeff', dim: '#8f84b3', mark: '#ff5ccf',
    lineW: 4, glow: 7, flash: '#ffd6f5',
    css: `
      .w{color:#fff;text-shadow:0 0 30px rgba(255,255,255,.25);}
      .a{background:linear-gradient(180deg,#ffe0f7 0%,var(--accent) 55%,#b83cff 100%);-webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 0 18px color-mix(in srgb,var(--accent) 60%,transparent));}
      .card{background:rgba(255,255,255,.06);border:1.5px solid color-mix(in srgb,var(--accent) 55%,transparent);border-radius:26px;box-shadow:0 0 30px color-mix(in srgb,var(--accent) 22%,transparent);}
      .card.hot{background:color-mix(in srgb,var(--accent) 18%,rgba(20,10,46,.6));border-color:var(--accent);}
      .chip{background:rgba(20,10,46,.7);border:1.5px solid color-mix(in srgb,var(--accent) 60%,transparent);color:var(--text);}
      .label{font-family:Body,sans-serif;letter-spacing:4px;color:var(--dim);}`,
  },
  pastel: {  // 奶油渐变：桃色到淡紫的渐变、柔和色团、白色圆角卡、软阴影
    label: '奶油渐变', light: true, bgKind: 'pastel',
    bg: ['#fff1e6', '#ebe7ff'], dot: '#ffffff',
    accent: '#ff6a3d', warn: '#e5484d', data: '#6c7cf0', text: '#2b2440', dim: '#9a90b0', mark: '#ff6a3d',
    lineW: 5, glow: 0, flash: null,
    css: `
      .w{color:var(--text);}
      .a{background:linear-gradient(90deg,var(--accent) 0%,#ff4f8b 100%);-webkit-background-clip:text;background-clip:text;color:transparent;}
      .card{background:rgba(255,255,255,.88);border:1.5px solid rgba(255,255,255,.95);border-radius:30px;box-shadow:0 22px 50px rgba(80,60,140,.16);}
      .card.hot{box-shadow:0 22px 50px color-mix(in srgb,var(--accent) 35%,transparent);border-color:color-mix(in srgb,var(--accent) 50%,#fff);}
      .chip{background:rgba(255,255,255,.9);border:none;box-shadow:0 8px 24px rgba(80,60,140,.14);color:var(--text);}
      .label{font-family:Body,sans-serif;color:var(--dim);}
      #vignette{display:none;}`,
  },
  chalk: {   // 黑板粉笔：墨绿黑板、粉笔灰、手写字、毛边线
    label: '黑板粉笔', light: false, bgKind: 'chalk',
    bg: ['#24322c', '#17211d'], dot: '#3a4a43',
    accent: '#ffe680', warn: '#ff8f8f', data: '#9fd0ff', text: '#f2f0e6', dim: '#93a39a', mark: '#ffe680',
    lineW: 5, glow: 0, flash: '#fff6cc', rough: true,
    css: `
      #stage{font-family:WK,Body,sans-serif;}
      .heavy{font-family:WK,SHS,sans-serif;}
      .w{color:var(--text);}
      .a{color:var(--accent);}
      .card{background:rgba(255,255,255,.035);border:3px solid rgba(242,240,230,.75);border-radius:12px;box-shadow:none;}
      .card.hot{border-color:var(--accent);}
      .chip{background:transparent;border:2.5px solid rgba(242,240,230,.7);color:var(--text);}
      .label{font-family:WK,Body,sans-serif;color:var(--dim);}`,
  },
};
let S = STYLES.paper;
// 风格名可以写在网址里：index.html?style=chalk，方便同一条镜头换风格出预览
function useStyle(name, opt = {}) {
  const fromUrl = new URLSearchParams(location.search).get('style');
  S = Object.assign({}, STYLES[fromUrl || name] || STYLES.paper, opt);
  const urlAccent = new URLSearchParams(location.search).get('accent');
  if (urlAccent) S.accent = '#' + urlAccent.replace('#', '');
  S.accentLight = mixHex(S.accent, '#ffffff', .65);
  S.accentDeep = mixHex(S.accent, '#000000', .25);
  S.onHot = S.onHot || S.accent;   // 画在点亮的卡片上的线（对勾）用什么颜色
  // 换的强调色和这套风格的红色（warn）太像时，红色让位成灰，免得一屏两种红分不清
  const dist = Math.hypot(...hex2rgb(S.accent).map((v, i) => v - hex2rgb(S.warn)[i]));
  if (dist < 110) S.warn = S.light ? '#6b665e' : '#a9a29a';
  const r = document.documentElement.style;
  for (const [k, v] of Object.entries({ accent: S.accent, 'accent-light': S.accentLight, warn: S.warn, data: S.data, text: S.text, dim: S.dim, mark: S.mark, bg0: S.bg[0] })) r.setProperty('--' + k, v);
  let tag = document.getElementById('style-css');
  if (!tag) { tag = document.createElement('style'); tag.id = 'style-css'; document.head.appendChild(tag); }
  tag.textContent = S.css;
  const g = $('grain'); if (g) { g.style.mixBlendMode = S.light ? 'multiply' : 'screen'; g.style.opacity = S.light ? .35 : .5; }
  const f = $('fade'); if (f) f.style.background = S.bg[0];
  return S;
}

// ---------- 背景：每套风格自己的底，都在轻微地动 ----------
function makeBackground(seed = 7) {
  const r = rng(seed);
  // 颗粒：8 张轮流用，画面停住时也不是死图
  const grains = []; const rg = rng(seed + 1);
  for (let k = 0; k < 8; k++) { const g = document.createElement('canvas'); g.width = 540; g.height = 960; const cc = g.getContext('2d'), im = cc.createImageData(540, 960);
    for (let i = 0; i < im.data.length; i += 4) {
      const n = rg();
      if (S.light) { const v = 255 - (n > .996 ? 90 * rg() : n * 18); im.data[i] = v; im.data[i + 1] = v * .99; im.data[i + 2] = v * .97; }
      else { const v = n > .997 ? 160 * rg() : n * 22; im.data[i] = v; im.data[i + 1] = v; im.data[i + 2] = v; }
      im.data[i + 3] = 255; }
    cc.putImageData(im, 0, 0); grains.push(g); }
  // 色团（aurora、pastel、chalk 用）
  const blobs = [];
  for (let i = 0; i < 5; i++) blobs.push({ x: r() * W, y: 200 + r() * 1300, rad: 380 + r() * 360, sx: .15 + r() * .25, sy: .1 + r() * .2, ph: r() * 6.28 });
  const blobColors = { aurora: ['#7b3cff', '#ff3fb4', '#2fb8ff', '#5a2bd6', '#ff6ad5'], pastel: ['#ffc4a3', '#c9c2ff', '#ffd9ec', '#bfe3ff', '#ffe0b8'], chalk: ['#ffffff', '#ffffff', '#ffffff', '#ffffff', '#ffffff'] };
  return {
    draw(t) {
      const ctx = $('bg').getContext('2d');
      ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
      const lg = ctx.createLinearGradient(0, 0, 0, H); lg.addColorStop(0, S.bg[0]); lg.addColorStop(1, S.bg[1]);
      ctx.fillStyle = lg; ctx.fillRect(0, 0, W, H);
      const k = S.bgKind;
      if (k === 'paper') {          // 点阵慢慢往上漂
        const off = (t * 6) % 40; ctx.fillStyle = S.dot;
        for (let y = -40; y < H + 40; y += 40) for (let x = 20; x < W; x += 40) { ctx.beginPath(); ctx.arc(x, y - off, 2.2, 0, 6.283); ctx.fill(); }
      } else if (k === 'swiss') {   // 细网格 + 左上一根粗黑条
        ctx.strokeStyle = S.dot; ctx.lineWidth = 1.5; const off = (t * 5) % 90;
        for (let x = 60; x < W; x += 120) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
        for (let y = -90; y < H + 90; y += 90) { ctx.beginPath(); ctx.moveTo(0, y - off); ctx.lineTo(W, y - off); ctx.stroke(); }
        ctx.fillStyle = S.text; ctx.fillRect(60, 96, 120, 10);
      } else if (k === 'aurora' || k === 'pastel' || k === 'chalk') {
        const cols = blobColors[k];
        ctx.globalCompositeOperation = k === 'aurora' ? 'screen' : 'source-over';
        blobs.forEach((b, i) => {
          const x = b.x + Math.sin(t * b.sx + b.ph) * 120, y = b.y + Math.cos(t * b.sy + b.ph) * 90;
          const rad = k === 'chalk' ? b.rad * .7 : b.rad;
          const g = ctx.createRadialGradient(x, y, 0, x, y, rad);
          const a = k === 'aurora' ? .42 : k === 'pastel' ? .55 : .045;
          const c = hex2rgb(cols[i % cols.length]);
          g.addColorStop(0, `rgba(${c},${a})`); g.addColorStop(1, `rgba(${c},0)`);
          ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
        });
        ctx.globalCompositeOperation = 'source-over';
        if (k === 'aurora') { ctx.fillStyle = 'rgba(0,0,0,.18)'; const off = (t * 40) % 6; for (let y = -6; y < H; y += 6) ctx.fillRect(0, y + off, W, 2); }
        if (k === 'chalk') { ctx.strokeStyle = 'rgba(255,255,255,.022)'; ctx.lineWidth = 90; const rr = rng(seed + 9); for (let i = 0; i < 6; i++) { ctx.beginPath(); const y = 200 + rr() * 1400; ctx.moveTo(-50, y); ctx.bezierCurveTo(300, y - 80, 700, y + 80, 1130, y - 20); ctx.stroke(); } }
      }
      const gc = $('grain'); if (gc) { const c2 = gc.getContext('2d'); c2.clearRect(0, 0, 540, 960); c2.drawImage(grains[Math.floor(t * FPS) % 8], 0, 0); }
    }
  };
}

// ---------- SVG 小工具 ----------
const NS = 'http://www.w3.org/2000/svg';
function mk(tag, attrs = {}, parent) { parent = parent || $('fx'); const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); parent.appendChild(e); return e; }
function svgSetup() {
  for (const host of [$('fx'), $('fxTop')]) {
    if (!host) continue;
    const defs = mk('defs', {}, host);
    // 发光滤镜必须用 userSpaceOnUse：水平线、竖线的包围盒高度为 0，默认写法会让整条线消失
    const glow = mk('filter', { id: host.id + '-glow', filterUnits: 'userSpaceOnUse', x: 0, y: 0, width: W, height: H }, defs);
    mk('feGaussianBlur', { stdDeviation: String(S.glow || 0.01), result: 'b' }, glow);
    const m = mk('feMerge', {}, glow); mk('feMergeNode', { in: 'b' }, m); mk('feMergeNode', { in: 'SourceGraphic' }, m);
    // 粉笔毛边
    const ch = mk('filter', { id: host.id + '-chalk', filterUnits: 'userSpaceOnUse', x: 0, y: 0, width: W, height: H }, defs);
    mk('feTurbulence', { type: 'fractalNoise', baseFrequency: '0.9', numOctaves: '2', seed: '3', result: 'n' }, ch);
    mk('feDisplacementMap', { in: 'SourceGraphic', in2: 'n', scale: '5' }, ch);
  }
}
// 线条用哪种效果：霓虹发光、粉笔毛边，或者什么都不加
const lineFx = (parent, opt = {}) => { const id = (parent || $('fx')).id; if (opt.glow === false) return ''; if (S.rough) return `url(#${id}-chalk)`; return S.glow ? `url(#${id}-glow)` : ''; };
const show = (el, on) => { el.style.opacity = on ? 1 : 0; };

// 一段会「画出来」的直线，线头带一个点。p 是 0→1
function growLine(x1, y1, x2, y2, opt = {}) {
  const l = mk('line', { stroke: opt.color || S.accent, 'stroke-width': opt.width || S.lineW, 'stroke-linecap': 'round', filter: lineFx(opt.parent, opt) }, opt.parent);
  if (opt.dash) l.setAttribute('stroke-dasharray', opt.dash);
  const h = mk('circle', { r: opt.head || 7, fill: S.light ? (opt.color || S.accent) : '#ffffff', filter: lineFx(opt.parent, opt) }, opt.parent);
  return { l, h, set(p, headOn = true) { const x = lerp(x1, x2, p), y = lerp(y1, y2, p);
    l.setAttribute('x1', x1); l.setAttribute('y1', y1); l.setAttribute('x2', x); l.setAttribute('y2', y);
    show(l, p > 0); h.setAttribute('cx', x); h.setAttribute('cy', y); show(h, p > 0 && p < 1 && headOn); } };
}
// 一个会描出来的圆环
function growRing(opt = {}) {
  const c = mk('circle', { fill: 'none', stroke: opt.color || S.accent, 'stroke-width': opt.width || S.lineW, 'stroke-linecap': 'round', filter: lineFx(opt.parent, opt) }, opt.parent);
  return { c, set(cx, cy, r, p) { const C = 2 * Math.PI * r;
    c.setAttribute('cx', cx); c.setAttribute('cy', cy); c.setAttribute('r', r);
    c.setAttribute('stroke-dasharray', C); c.setAttribute('stroke-dashoffset', C * (1 - p)); c.setAttribute('transform', `rotate(-90 ${cx} ${cy})`); show(c, p > 0); } };
}
// 一个会描出来的路径（卡框、对勾、任意形状）
function growPath(d, opt = {}) {
  const pth = mk('path', { d, fill: 'none', stroke: opt.color || S.accent, 'stroke-width': opt.width || S.lineW, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', filter: lineFx(opt.parent, opt) }, opt.parent);
  const len = opt.len || pth.getTotalLength();
  return { el: pth, set(p) { pth.setAttribute('stroke-dasharray', len); pth.setAttribute('stroke-dashoffset', len * (1 - p)); show(pth, p > 0); } };
}
// 圆角矩形路径
const rrPath = (x, y, w, h, r) => `M${x + r} ${y}H${x + w - r}Q${x + w} ${y} ${x + w} ${y + r}V${y + h - r}Q${x + w} ${y + h} ${x + w - r} ${y + h}H${x + r}Q${x} ${y + h} ${x} ${y + h - r}V${y + r}Q${x} ${y} ${x + r} ${y}Z`;
// 对勾路径：以 (cx,cy) 为中心、大小 s
const checkPath = (cx, cy, s = 40) => `M${cx - s * .5} ${cy}L${cx - s * .12} ${cy + s * .38}L${cx + s * .55} ${cy - s * .4}`;
// 冲击波：一圈往外扩、变淡
function shockwave(opt = {}) {
  const c = mk('circle', { fill: 'none', stroke: opt.color || S.accent, 'stroke-width': 4 }, opt.parent);
  return { set(t, a, cx, cy, r0, grow = 360, dur = .6) { const p = prog(t, a, a + dur);
    c.setAttribute('cx', cx); c.setAttribute('cy', cy); c.setAttribute('r', r0 + eOut(p) * grow); c.setAttribute('stroke-width', 2 + 5 * (1 - p));
    c.style.opacity = (p > 0 && p < 1) ? (1 - p) * .85 : 0; } };
}
// 结论落定的一下：深色风格是一道光，浅色风格是一圈强调色的线往外散。一条镜头最多用两次
function hitFlash(parent) {
  const col = S.flash || S.accent;
  const line = mk('line', { x1: 0, x2: W, stroke: col, 'stroke-width': S.light ? 3 : 2.5, filter: lineFx(parent) }, parent);
  const blob = mk('ellipse', { fill: S.light ? 'none' : '#ffffff', stroke: S.light ? col : 'none', 'stroke-width': 3, filter: lineFx(parent) }, parent);
  const rays = mk('g', { stroke: col, 'stroke-width': S.light ? 4 : 2.5, 'stroke-linecap': 'round' }, parent);
  for (let i = 0; i < 12; i++) mk('line', {}, rays);
  return { set(t, a, cx, cy) { const f = flash(t, a, .08, .45);
    line.setAttribute('y1', cy); line.setAttribute('y2', cy); line.style.opacity = S.light ? 0 : f * .9;
    blob.setAttribute('cx', cx); blob.setAttribute('cy', cy);
    if (S.light) { blob.setAttribute('rx', 60 + 260 * (1 - f)); blob.setAttribute('ry', 60 + 260 * (1 - f)); blob.style.opacity = t > a ? f * .8 : 0; }
    else { blob.setAttribute('rx', 30 + 220 * f); blob.setAttribute('ry', 3 + 6 * f); blob.style.opacity = f; }
    [...rays.children].forEach((ln, i) => { const ang = i / 12 * Math.PI * 2 + .26, r1 = 40 + 70 * f, r2 = r1 + 30 + 70 * f;
      ln.setAttribute('x1', cx + r1 * Math.cos(ang)); ln.setAttribute('y1', cy + r1 * Math.sin(ang)); ln.setAttribute('x2', cx + r2 * Math.cos(ang)); ln.setAttribute('y2', cy + r2 * Math.sin(ang)); });
    rays.style.opacity = f * .85; } };
}
// 沿折线走的点：给 0→1 返回坐标
function along(pts, p) { let tot = 0; const ls = []; for (let i = 1; i < pts.length; i++) { const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); ls.push(d); tot += d; }
  let d = p * tot; for (let i = 0; i < ls.length; i++) { if (d <= ls[i]) { const q = d / ls[i]; return [lerp(pts[i][0], pts[i + 1][0], q), lerp(pts[i][1], pts[i + 1][1], q)]; } d -= ls[i]; } return pts[pts.length - 1]; }

// ---------- DOM 动作 ----------
// 大字砸下：从放大、模糊、透明落到原样
function slam(el, t, a, opt = {}) { const p = prog(t, a, a + (opt.dur || .26)), e = eOut(p);
  el.style.opacity = clamp(p * 2.2); el.style.transform = `${opt.base || ''} scale(${(opt.from || 1.35) - ((opt.from || 1.35) - 1) * e})`;
  el.style.filter = `blur(${(opt.blur ?? 18) * (1 - e)}px)`; return p; }
// 弹出：小东西（卡片、标签、图标）从小到原样，带一点回弹
function popIn(el, t, a, opt = {}) { const p = prog(t, a, a + (opt.dur || .3));
  el.style.opacity = clamp(p * 2); el.style.transform = `${opt.base || ''} translateY(${(opt.dy ?? 16) * (1 - eOut(p))}px) scale(${.6 + .4 * eBack(p)})`; return p; }
// 从左边擦出来（卡片、列表行）
function wipeIn(el, t, a, opt = {}) { const p = eOut(prog(t, a, a + (opt.dur || .3)));
  el.style.opacity = clamp(p * 1.5); el.style.clipPath = `inset(-20px ${100 * (1 - p)}% -20px -20px)`;
  el.style.transform = `${opt.base || ''} translateX(${-(opt.dx ?? 16) * (1 - p)}px)`; return p; }
// 模糊淡入（标题、说明字）
function blurIn(el, t, a, dur = .2) { const p = eOut(prog(t, a, a + dur)); el.style.opacity = p; el.style.filter = `blur(${8 * (1 - p)}px)`; return p; }
// 变暗退下：旧的东西被否掉以后用
function dimOut(el, t, a, to = .3, dur = .3) { const p = eOut(prog(t, a, a + dur)); el.style.opacity = lerp(1, to, p); el.style.filter = `grayscale(${p})`; return p; }
// 打字：每字 perChar 秒，打字中带光标
function typeText(el, text, t, a, perChar = .045, cursor = '|') { const n = Math.floor(clamp((t - a) / perChar, 0, text.length));
  el.textContent = text.slice(0, n) + (n > 0 && n < text.length && Math.floor(t * 12) % 2 ? cursor : ''); return n / text.length; }
// 数字滚动：先快后慢，只跳整数
function countTo(el, from, to, t, a, dur = 1, fmt = v => v.toLocaleString('en-US')) { const p = eOut(prog(t, a, a + dur)); el.textContent = fmt(Math.round(lerp(from, to, p))); return p; }
// 印章：直接盖下，略大一点再落定，带一点倾斜
function stampIn(el, t, a) { const p = prog(t, a, a + .18); el.style.opacity = p > 0 ? 1 : 0;
  el.style.transform = `rotate(-6deg) scale(${p >= 1 ? 1 : 1.5 - .5 * eOut(p)})`; return p; }
// 闪烁的小灯
const blink = (t, phase = 0) => .55 + .45 * Math.sin(t * 6 + phase);

// ---------- 页面公共部分：开场淡入、左上角小标签、字幕预览 ----------
function chrome(t) {
  $('fade').style.opacity = 1 - eOut(prog(t, 0, 0.22));
  const lb = $('topLabel'); if (lb) { const p = eOut(prog(t, 0.05, 0.35)); lb.style.opacity = p; lb.style.transform = `translate(${80 - 24 * (1 - p)}px,140px)`; }
  if (window.SUBMODE) { const s = (window.SUBS || []).find(s => t >= s[0] && t < s[1]); const el = $('sub'); el.style.display = 'block'; el.style.visibility = s ? 'visible' : 'hidden'; if (s) el.textContent = s[2]; }
}
window.SUBMODE = new URLSearchParams(location.search).get('sub') === '1';

// ---------- 就绪：三种字体都加载好再开始截图 ----------
function ready() {
  Promise.all(['40px SHS', '40px Body', '40px WK'].map(f => document.fonts.load(f, '中文字AaGg01')))
    .catch(() => {}).then(() => document.fonts.ready).then(() => { window.READY = true; seek(0); });
}
