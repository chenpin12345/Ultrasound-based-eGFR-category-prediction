// Generates index.html + compositions/*.html from the real-app screenshots
// (assets/shots + manifest.json), the report PDF pages, and the HeyGen narration
// word timings. Re-run after changing the shot plan:  node scripts/build.mjs
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const manifest = JSON.parse(readFileSync(join(ROOT, 'assets/shots/manifest.json'), 'utf8'));
const shotInfo = Object.fromEntries(manifest.map(s => [s.name, s]));

// ---------- layout ----------
const CARD = { x: 204, y: 96, w: 1512, h: 850 };
const IMG = { w: 1920, h: 1080 };
const K = CARD.w / IMG.w;
const LEAD = 0.35, TAIL = 0.45, OUTRO = 2.2;

// ---------- narration (durations.json = ffprobe of assets/vo/*.mp3) ----------
const VO = JSON.parse(readFileSync(join(ROOT, 'assets/vo/durations.json'), 'utf8'));
const scenes = Object.keys(VO).map(id => ({ id, text: readFileSync(join(ROOT, `assets/vo/${id}.txt`), 'utf8').trim(),
  words: JSON.parse(readFileSync(join(ROOT, `assets/vo/${id}.words.json`), 'utf8')) }));
let cursor = 0;
for (const s of scenes) { s.start = cursor; s.audio = cursor + LEAD; s.dur = LEAD + VO[s.id] + TAIL; cursor += s.dur; }
const TOTAL = +(cursor + OUTRO).toFixed(2);
const sc = Object.fromEntries(scenes.map(s => [s.id, s]));

// Time (from the scene's narration start) at which `anchor` is spoken, so the shot plan
// follows the voice instead of hard-coded seconds.
function A(sid, anchor, delta = 0) {
  const s = sc[sid], idx = s.text.indexOf(anchor);
  if (idx < 0) throw new Error(`${sid}: anchor "${anchor}" not in narration`);
  const tokenIndex = [...s.text.slice(0, idx)].filter(c => c !== ' ').length;
  return +(s.words[tokenIndex].start + delta).toFixed(3);
}

// ---------- shot plan (times are seconds from that scene's narration start) ----------
// marks: box = element box captured from the live DOM; cam = move camera to it; click = cursor click
const CHIPS = {
  s2: ['1', 'B 電腦', '開始接收'], s3: ['2', 'A 電腦', '配對'], s4: ['3', 'A 電腦', '選圖與案例資料'],
  s5: ['4', 'A → B', '傳送與自動分析'], s6: ['5', 'B 電腦', 'AI 分析結果'], s7: ['6', 'B 電腦', '報告中心'], s8: ['7', '輸出', 'PDF 報告'],
};
const PLAN = {
  s2: [
    { img: 'b01_demo', t: -0.35, marks: [{ box: 'title', t: A('s2', '開啟', -0.25), cam: 1.25 }] },
    { img: 'b02_address_plan', t: A('s2', '系統', -0.45), marks: [{ box: 'address', t: A('s2', '系統'), cam: true }, { box: 'plan', t: A('s2', '並套用', -0.05), cam: true }, { box: 'start', t: A('s2', '按下'), click: true, cam: 1.3 }] },
    { img: 'b03_pairing', t: A('s2', '產生配對', -0.55), marks: [{ box: 'pair', t: A('s2', '產生配對', -0.5), cam: true, nobox: true }, { box: 'fingerprint', t: A('s2', '指紋', -0.3) }] },
  ],
  s3: [
    { img: 'a01_sender', t: -0.35, marks: [{ box: 'title', t: A('s3', '圖片發送', -0.7), cam: 1.15, nobox: true }] },
    { img: 'a02_pair_filled', t: A('s3', '匯入', -0.08), marks: [{ box: 'pairsec', t: A('s3', '匯入', -0.03), cam: true, nobox: true }, { box: 'fingerprint', t: A('s3', '核對', -0.1) }, { box: 'connect', t: A('s3', '完成配對', -0.06), click: true }] },
    { img: 'a03_paired', t: A('s3', '並顯示', -0.3), marks: [{ box: 'planinfo', t: A('s3', '並顯示'), cam: 1.35 }] },
  ],
  s4: [
    { img: 'a04_gallery', t: -0.35, marks: [{ box: 'folder', t: -0.15, click: true, cam: true }, { box: 'gallery', t: A('s4', '資料夾'), cam: true, nobox: true }] },
    { img: 'a05_case_form', t: A('s4', '為每張', -0.07), marks: [{ box: 'form', t: A('s4', '為每張', 0.03), cam: true, nobox: true }, { box: 'code', t: A('s4', '填寫') }, { box: 'age', t: A('s4', '案例資料', 0.15) }, { box: 'diabetes', t: A('s4', '資料，', 0.2) }] },
    { img: 'a06_selected', t: A('s4', '勾選', -0.1), marks: [{ box: 'gallery', t: A('s4', '勾選', -0.05), cam: true, nobox: true }, { box: 'selection', t: A('s4', '勾選', 0.3) }] },
    { img: 'a07_send_ready', t: A('s4', '按下', -0.2), marks: [{ box: 'start', t: A('s4', '傳送已', -0.17), click: true, cam: 1.3 }] },
  ],
  s5: 'split',
  s6: [
    { img: 'b05_result_images', t: -0.35, marks: [{ box: 'item', t: A('s6', '點選', -0.5), click: true }, { box: 'original', t: A('s6', '原始', -0.04) }, { box: 'overlay', t: A('s6', '分割', -0.3) }] },
    { img: 'b06_result_probs', t: A('s6', '以及', -0.1), marks: [{ box: 'probs', t: A('s6', '以及', 0.25), cam: true }] },
    { img: 'b07_save', t: A('s6', '確認後', -0.22), marks: [{ box: 'save', t: A('s6', '確認後', 0.23), click: true, cam: 1.25 }] },
    { img: 'b08_saved', t: A('s6', '保存', 0.38), marks: [] },
  ],
  s7: [
    { img: 'r01_report_new', t: -0.35, marks: [{ box: 'nav', t: A('s7', '報告中心', -0.3) }, { box: 'editor', t: A('s7', '建立草稿', -0.07), cam: true, nobox: true }] },
    { img: 'r02_ai_attached', t: A('s7', '附上', -0.16), marks: [{ box: 'picker', t: A('s7', '附上', -0.06), cam: true, nobox: true }, { box: 'ai', t: A('s7', '輔助', -0.18) }] },
    { img: 'r03_fields', t: A('s7', '由醫師', -0.07), marks: [{ box: 'findings', t: A('s7', '醫師', -0.1), cam: true }, { box: 'diagnosis', t: A('s7', '判讀', -0.33) }] },
    { img: 'r04_saved', t: A('s7', '保存後', -0.1), marks: [{ box: 'pdf', t: A('s7', '產生', -0.32), click: true, cam: 1.3 }] },
    { img: 'r05_pdf_ready', t: A('s7', 'PDF', -0.19), marks: [{ box: 'panel', t: A('s7', 'PDF', -0.14), cam: true, nobox: true }, { box: 'status', t: A('s7', 'PDF', 0.1) }] },
  ],
  s8: 'pdf',
};

// ---------- helpers ----------
const r = n => +n.toFixed(3);
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const T = (sceneId, t) => r(sc[sceneId].audio + t);
function camFor(box, zoomCap = 1.7, vw = CARD.w, vh = CARD.h, iw = IMG.w, ih = IMG.h, k = K) {
  if (!box) return { x: 0, y: 0, s: k };
  const pad = 60;
  let z = Math.min(vw / (k * (box.w + 2 * pad)), vh / (k * (box.h + 2 * pad)));
  z = Math.max(1, Math.min(zoomCap, z));
  const s = k * z, cx = box.x + box.w / 2, cy = box.y + box.h / 2;
  const x = Math.min(0, Math.max(vw - iw * s, vw / 2 - cx * s));
  const y = Math.min(0, Math.max(vh - ih * s, vh / 2 - cy * s));
  return { x: r(x), y: r(y), s: r(s) };
}

// ---------- captions: phrase groups timed by the per-character timestamps ----------
const captions = [];
for (const s of scenes) {
  const chars = [...s.text];
  const times = []; let wi = 0;
  for (const ch of chars) {
    if (ch === ' ') { times.push(null); continue; }
    const w = s.words[wi];
    if (!w || w.text !== ch) throw new Error(`${s.id}: token mismatch at "${ch}" vs "${w && w.text}"`);
    times.push(w); wi++;
  }
  let phrases = [], cur = [];
  chars.forEach((ch, i) => { cur.push(i); if ('，。：'.includes(ch)) { phrases.push(cur); cur = []; } });
  if (cur.length) phrases.push(cur);
  const len = idx => idx.filter(i => !'，。： '.includes(chars[i])).length;
  const merged = [];
  for (const p of phrases) {
    const last = merged[merged.length - 1];
    // One caption per clause; only a tiny clause (≤3 chars) rides along with the previous one.
    if (last && len(p) <= 3) merged[merged.length - 1] = last.concat(p); else merged.push(p);
  }
  merged.forEach(idx => {
    const t0 = idx.map(i => times[i]).find(Boolean).start;
    const text = idx.map(i => chars[i]).join('').replace(/[，。：]+$/, '').trim();
    captions.push({ scene: s.id, text, start: r(s.audio + t0), lastEnd: r(s.audio + idx.map(i => times[i]).filter(Boolean).pop().end) });
  });
}
captions.forEach((c, i) => {
  const next = captions[i + 1];
  const sameScene = next && next.scene === c.scene;
  c.end = r(sameScene ? next.start - 0.04 : Math.min(c.lastEnd + 0.5, next ? next.start - 0.1 : TOTAL));
});

// ---------- card layer (all real screenshots) — JS positions authored in global time ----------
let cardHtml = '', cardJs = '';

function shotHtml(id, img, marks) {
  const boxes = shotInfo[img].boxes;
  let inner = `<img class="shot-img" src="assets/shots/${img}.png" alt="">`;
  marks.forEach((m, i) => {
    const b = boxes[m.box]; if (!b) throw new Error(`${img}: missing box ${m.box}`);
    if (!m.nobox) inner += `<div class="hl" id="${id}-hl${i}" style="left:${b.x - 8}px;top:${b.y - 8}px;width:${b.w + 16}px;height:${b.h + 16}px"></div>`;
    if (m.click) inner += `<div class="cursor" id="${id}-cur${i}" style="left:${b.x + b.w / 2}px;top:${b.y + b.h / 2}px"><div class="ripple" id="${id}-rip${i}"></div><svg viewBox="0 0 32 40" width="40" height="50"><path d="M3 2 L3 32 L11 25 L16 37 L22 34 L17 23 L28 23 Z" fill="#fff" stroke="#10231f" stroke-width="2.5" stroke-linejoin="round"/></svg></div>`;
  });
  return `<div class="shot" id="${id}"><div class="stage" id="${id}-stage" data-layout-allow-overflow>${inner}</div></div>`;
}

function planShots(sceneId, shots) {
  shots.forEach((sh, si) => {
    const id = `${sceneId}-${si}`;
    cardHtml += shotHtml(id, sh.img, sh.marks);
    const start = T(sceneId, sh.t);
    const end = si + 1 < shots.length ? T(sceneId, shots[si + 1].t) : null;
    const boxes = shotInfo[sh.img].boxes;
    const c0 = camFor(null);
    cardJs += `tl.set('#${id}-stage',{x:${c0.x},y:${c0.y},scale:${c0.s}},0);\n`;
    cardJs += `tl.fromTo('#${id}',{opacity:0},{opacity:1,duration:0.35,ease:'power1.out'},${r(start)});\n`;
    if (end !== null) cardJs += `tl.to('#${id}',{opacity:0,duration:0.3,ease:'power1.in'},${r(end + 0.05)});\n`;
    sh.marks.forEach((m, i) => {
      const t = T(sceneId, m.t);
      if (m.cam) {
        const c = camFor(boxes[m.box], m.cam === true ? 1.7 : m.cam);
        cardJs += `tl.to('#${id}-stage',{x:${c.x},y:${c.y},scale:${c.s},duration:0.8,ease:'power2.inOut'},${r(t)});\n`;
      }
      if (!m.nobox) {
        cardJs += `tl.fromTo('#${id}-hl${i}',{opacity:0,scale:1.06},{opacity:1,scale:1,duration:0.35,ease:'power2.out'},${r(t + (m.cam ? 0.45 : 0))});\n`;
        const off = m.until ? T(sceneId, m.until) : (sh.marks[i + 1] ? T(sceneId, sh.marks[i + 1].t) : null);
        if (off !== null) cardJs += `tl.to('#${id}-hl${i}',{opacity:0,duration:0.25},${r(off)});\n`;
      }
      if (m.click) {
        const tc = t + (m.cam ? 0.55 : 0.15);
        cardJs += `tl.fromTo('#${id}-cur${i}',{opacity:0,x:150,y:110},{opacity:1,x:0,y:0,duration:0.55,ease:'power2.out'},${r(tc)});\n`;
        cardJs += `tl.fromTo('#${id}-rip${i}',{opacity:0.9,scale:0.2},{opacity:0,scale:1.6,duration:0.5,ease:'power1.out'},${r(tc + 0.55)});\n`;
      }
    });
  });
}

// live transfer: A queue frames (top) and B counters (bottom), captured together from the running apps
function splitScene(sceneId) {
  const frames = manifest.filter(m => /^a08_queue_\d+$/.test(m.name)).map(m => ({ a: m.name, b: m.name.replace('a08_queue', 'b04_counts'), t: m.t }));
  frames.push({ a: 'a09_queue_done', b: 'b04_counts_done', t: shotInfo['b04_counts_done'].t });
  const t0 = frames[0].t, t1 = frames[frames.length - 1].t;
  const PW = 1476, PH = 360;
  const pane = (side, key, label, boxName) => {
    // Frame the union of the target box across all frames (the A table grows as rows update).
    const all = frames.map(f => shotInfo[f[key]].boxes[boxName]).filter(Boolean);
    const x0 = Math.min(...all.map(b => b.x)), y0 = Math.min(...all.map(b => b.y));
    const x1 = Math.max(...all.map(b => b.x + b.w)), y1 = Math.max(...all.map(b => b.y + b.h));
    const bx = { x: x0 - 24, y: y0 - 24, w: x1 - x0 + 48, h: y1 - y0 + 48 };
    const z = Math.min(PW / bx.w, PH / bx.h, 1.25);
    const x = r(PW / 2 - (bx.x + bx.w / 2) * z), y = r(PH / 2 - (bx.y + bx.h / 2) * z);
    const imgs = frames.map((f, i) => `<img class="flip" id="${sceneId}-${side}${i}" src="assets/shots/${f[key]}.png" alt="">`).join('');
    cardJs += `tl.set('#${sceneId}-${side}-stage',{x:${x},y:${y},scale:${r(z)}},0);\n`;
    return `<div class="pane"><div class="pane-label">${label}</div><div class="pane-view"><div class="stage" id="${sceneId}-${side}-stage" data-layout-allow-overflow>${imgs}</div></div></div>`;
  };
  cardHtml += `<div class="shot split" id="${sceneId}-split">` +
    pane('a', 'a', 'A 電腦｜超音波圖片發送工具・傳送清單', 'queue') +
    pane('b', 'b', 'B 電腦｜真實圖片雙機示範・接收統計', 'counts') + `</div>`;
  cardJs += `tl.fromTo('#${sceneId}-split',{opacity:0},{opacity:1,duration:0.35},${r(sc[sceneId].start)});\n`;
  cardJs += `tl.to('#${sceneId}-split',{opacity:0,duration:0.3},${r(sc[sceneId].start + sc[sceneId].dur - 0.05)});\n`;
  // Real capture spacing, stretched over the narration so "三張全部完成" lands on the last frame.
  const span0 = T(sceneId, 0.2), span1 = T(sceneId, A(sceneId, '三張', -0.1));
  frames.forEach((f, i) => {
    const at = i === 0 ? sc[sceneId].start : r(span0 + (f.t - t0) / (t1 - t0) * (span1 - span0));
    for (const side of ['a', 'b']) cardJs += `tl.set('#${sceneId}-${side}${i}',{opacity:1},${at});\n` + (i > 0 ? `tl.set('#${sceneId}-${side}${i - 1}',{opacity:0},${r(at + 0.001)});\n` : '');
  });
}

// report PDF pages scrolled inside the card
function pdfScene(sceneId) {
  const PWID = 1060, PH = Math.round(2105 * PWID / 1489);
  const pages = [
    { file: 'page-1', t: -0.35, from: 0, to: 0.42, at: A('s8', '影像', -0.6), dur: 2.0 },
    { file: 'page-2', t: A('s8', 'AI', -0.34), from: 0.0, to: 0.36, at: A('s8', '醫師判讀', -0.53), dur: 1.6 },
  ];
  pages.forEach((p, i) => {
    const id = `${sceneId}-p${i}`;
    cardHtml += `<div class="shot pdf" id="${id}"><div class="pdf-page" id="${id}-page" data-layout-allow-overflow style="width:${PWID}px;height:${PH}px"><img src="assets/pdf/${p.file}.png" alt=""></div></div>`;
    cardJs += `tl.set('#${id}-page',{y:${-r(p.from * PH)}},0);\n`;
    cardJs += `tl.fromTo('#${id}',{opacity:0},{opacity:1,duration:0.35},${T(sceneId, p.t)});\n`;
    cardJs += `tl.to('#${id}-page',{y:${-r(p.to * PH)},duration:${p.dur},ease:'power2.inOut'},${T(sceneId, p.at)});\n`;
    const next = pages[i + 1];
    cardJs += `tl.to('#${id}',{opacity:0,duration:0.3},${next ? T(sceneId, next.t + 0.05) : T(sceneId, A('s8', '僅供', 0.5))});\n`;
  });
}

for (const s of scenes) {
  if (s.id === 's1') continue;
  const p = PLAN[s.id];
  if (p === 'split') splitScene(s.id); else if (p === 'pdf') pdfScene(s.id); else planShots(s.id, p);
}

let chips = '';
Object.entries(CHIPS).forEach(([sid, [n, who, what]]) => {
  chips += `<div class="chip" id="chip-${sid}"><span class="chip-n">${n}</span><span class="chip-who">${who}</span><span class="chip-what">${esc(what)}</span></div>`;
  const s = sc[sid];
  cardJs += `tl.fromTo('#chip-${sid}',{opacity:0,y:-10},{opacity:1,y:0,duration:0.4,ease:'power2.out'},${r(s.start + 0.1)});\n`;
  const end = sid === 's8' ? T('s8', A('s8', '僅供', 0.5)) : r(s.start + s.dur - 0.3);
  cardJs += `tl.to('#chip-${sid}',{opacity:0,duration:0.25},${end});\n`;
});

// ---------- layer windows ----------
const s1 = sc.s1;
const cardStart = sc.s2.start, cardEnd = T('s8', A('s8', '僅供', 0.85));
const closeStart = T('s8', A('s8', '僅供', 0.55));
cardJs += `tl.fromTo('#card-frame',{opacity:0,y:30,scale:0.97},{opacity:1,y:0,scale:1,duration:0.6,ease:'power3.out'},${r(cardStart)});\n`;
cardJs += `tl.to('#card-frame',{opacity:0,scale:0.98,duration:0.4,ease:'power2.in'},${r(cardEnd - 0.4)});\n`;

// Shift every tween's trailing position argument from global time to the layer's local time.
const localize = (js, offset) => js.replace(/,(-?\d+(?:\.\d+)?)\);$/gm, (_, n) => `,${r(Math.max(0, Number(n) - offset))});`);

const titleJs = `
tl.fromTo('#t-kicker',{opacity:0,y:16},{opacity:1,y:0,duration:0.5,ease:'power2.out'},0.2);
tl.fromTo('#t-title',{opacity:0,y:28},{opacity:1,y:0,duration:0.7,ease:'power3.out'},0.3);
tl.fromTo('#t-note',{opacity:0},{opacity:1,duration:0.6},${T('s1', 1.5)});
tl.fromTo('#t-node-a',{opacity:0,y:24},{opacity:1,y:0,duration:0.5,ease:'back.out(1.6)'},${T('s1', A('s1', '電腦傳送', -0.3))});
tl.fromTo('#t-arrow-1',{opacity:0,scaleX:0},{opacity:1,scaleX:1,duration:0.45,ease:'power2.out'},${T('s1', A('s1', 'B 電腦', -0.51))});
tl.fromTo('#t-node-b',{opacity:0,y:24},{opacity:1,y:0,duration:0.5,ease:'back.out(1.6)'},${T('s1', A('s1', 'B 電腦', -0.06))});
tl.fromTo('#t-arrow-2',{opacity:0,scaleX:0},{opacity:1,scaleX:1,duration:0.45,ease:'power2.out'},${T('s1', A('s1', '產生報告', -0.37))});
tl.fromTo('#t-node-c',{opacity:0,y:24},{opacity:1,y:0,duration:0.5,ease:'back.out(1.6)'},${T('s1', A('s1', '產生報告', -0.02))});
tl.fromTo('#t-backdrop',{opacity:0,scale:1.08},{opacity:0.16,scale:1,duration:${r(s1.dur)},ease:'none'},0);
tl.to('#title-wrap',{opacity:0,y:-20,duration:0.4,ease:'power2.in'},${r(s1.dur - 0.4)});
`;
const closeJs = localize(`
tl.fromTo('#c-line1',{opacity:0,y:24},{opacity:1,y:0,duration:0.6,ease:'power3.out'},${r(closeStart + 0.4)});
tl.fromTo('#c-line2',{opacity:0,y:24},{opacity:1,y:0,duration:0.6,ease:'power3.out'},${T('s8', A('s8', '最終'))});
tl.fromTo('#c-rule',{scaleX:0},{scaleX:1,duration:0.6,ease:'power2.out'},${T('s8', A('s8', '最終', 0.3))});
tl.fromTo('#c-foot',{opacity:0},{opacity:1,duration:0.6},${T('s8', A('s8', '最終', 0.6))});
`, closeStart);
const bgJs = `
tl.fromTo('#bg-glow',{scale:0.9,opacity:0.55},{scale:1.08,opacity:0.8,duration:${r(TOTAL / 2)},ease:'sine.inOut',yoyo:true,repeat:1},0);
tl.fromTo('#bg-grid',{y:0},{y:-64,duration:${TOTAL},ease:'none'},0);
tl.fromTo('#bg-ring1',{rotation:0},{rotation:40,duration:${TOTAL},ease:'none'},0);
tl.fromTo('#bg-ring2',{rotation:0},{rotation:-30,duration:${TOTAL},ease:'none'},0);
`;
let capHtml = '', capJs = '';
captions.forEach((c, i) => {
  capHtml += `<div class="cap" id="cap-${i}">${esc(c.text)}</div>`;
  capJs += `tl.fromTo('#cap-${i}',{opacity:0,y:8},{opacity:1,y:0,duration:0.18,ease:'power2.out'},${c.start});\n`;
  capJs += `tl.to('#cap-${i}',{opacity:0,duration:0.1,ease:'power2.in'},${r(c.end - 0.1)});\n`;
  capJs += `tl.set('#cap-${i}',{opacity:0,visibility:'hidden'},${c.end});\n`;
});

// ---------- writers ----------
const FONT = `@font-face { font-family: "Noto Sans TC"; src: url("assets/fonts/NotoSansTC-subset.woff2") format("woff2"); font-weight: 100 900; font-display: block; }`;
function subcomp(id, duration, css, body, js) {
  return `<!doctype html>
<html lang="zh-Hant">
  <head><meta charset="UTF-8" /><!-- GENERATED by scripts/build.mjs — edit the generator, not this file. --></head>
  <body>
    <template id="${id}-template">
      <style>
        ${FONT}
        #${id}-root { position: absolute; inset: 0; overflow: hidden; font-family: "Noto Sans TC", sans-serif; color: #eef6f5; }
${css}
      </style>
      <div id="${id}-root" data-composition-id="${id}" data-width="1920" data-height="1080" data-duration="${r(duration)}">
        ${body}
      </div>
      <script>
        const tl = gsap.timeline({ paused: true });
${js}
        window.__timelines["${id}"] = tl;
      </script>
    </template>
  </body>
</html>
`;
}

mkdirSync(join(ROOT, 'compositions'), { recursive: true });
const out = (name, s) => writeFileSync(join(ROOT, 'compositions', name + '.html'), s);

out('bg', subcomp('bg', TOTAL, `
        #bg-base { position: absolute; inset: 0; background: radial-gradient(1200px 700px at 50% 38%, #12343a 0%, #0c2125 60%, #081719 100%); }
        #bg-glow { position: absolute; left: 460px; top: 120px; width: 1000px; height: 700px; border-radius: 50%; background: radial-gradient(closest-side, rgba(45,170,160,0.22), rgba(45,170,160,0)); }
        #bg-grid { position: absolute; left: 0; top: 0; width: 1920px; height: 1200px; opacity: 0.08;
          background-image: linear-gradient(#9fd3cc 1px, transparent 1px), linear-gradient(90deg, #9fd3cc 1px, transparent 1px); background-size: 64px 64px; }
        .bg-ring { position: absolute; border-radius: 50%; border: 2px dashed rgba(143,216,204,0.10); }
        #bg-ring1 { left: -320px; top: 520px; width: 900px; height: 900px; }
        #bg-ring2 { left: 1460px; top: -380px; width: 780px; height: 780px; }`,
  `<div id="bg-base"></div><div id="bg-grid"></div><div id="bg-glow"></div><div class="bg-ring" id="bg-ring1" data-layout-allow-overflow></div><div class="bg-ring" id="bg-ring2" data-layout-allow-overflow></div>`, bgJs));

out('title', subcomp('title', s1.dur, `
        #title-wrap { position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: center; padding: 0 180px 120px; }
        #t-backdrop { position: absolute; right: -60px; top: 80px; width: 1100px; height: 619px; border-radius: 18px; background: url("assets/shots/b05_result_images.png") center / cover no-repeat; }
        #t-kicker { font-size: 30px; font-weight: 500; color: #8fd8cc; letter-spacing: 0.12em; }
        #t-title { margin-top: 18px; font-size: 92px; font-weight: 800; line-height: 1.15; color: #f3fbfa; max-width: 1300px; }
        #t-flow { margin-top: 64px; display: flex; align-items: center; gap: 28px; }
        .t-node { display: block; width: 330px; padding: 26px 30px; border-radius: 18px; background: #f3faf9; color: #0e2a2e; box-shadow: 0 18px 40px rgba(0,0,0,0.35); }
        .t-node b { display: block; font-size: 22px; font-weight: 700; color: #0f766e; letter-spacing: 0.08em; }
        .t-node span { display: block; margin-top: 8px; font-size: 38px; font-weight: 800; }
        .t-arrow { display: block; width: 90px; height: 6px; border-radius: 3px; background: #f2b84b; transform-origin: 0 50%; }
        #t-note { margin-top: 48px; font-size: 24px; color: #a9c9c5; }`,
  `<div id="t-backdrop"></div>
        <div id="title-wrap">
          <div id="t-kicker">腎超新｜研究用途原型</div>
          <div id="t-title">腎臟超音波 AI 輔助系統</div>
          <div id="t-flow">
            <div class="t-node" id="t-node-a"><b>A 電腦</b><span>傳送影像</span></div>
            <div class="t-arrow" id="t-arrow-1"></div>
            <div class="t-node" id="t-node-b"><b>B 電腦</b><span>AI 自動分析</span></div>
            <div class="t-arrow" id="t-arrow-2"></div>
            <div class="t-node" id="t-node-c"><b>醫師</b><span>產生報告</span></div>
          </div>
          <div id="t-note">以下畫面皆為本系統實際執行畫面｜示範影像已去識別化</div>
        </div>`, titleJs));

out('card', subcomp('card', cardEnd - cardStart, `
        #card-frame { position: absolute; left: ${CARD.x}px; top: ${CARD.y}px; width: ${CARD.w}px; height: ${CARD.h}px; border-radius: 18px; overflow: hidden; background: #f3f6f8; box-shadow: 0 30px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.08); }
        .shot { position: absolute; inset: 0; opacity: 0; overflow: hidden; }
        .stage { position: absolute; left: 0; top: 0; width: ${IMG.w}px; height: ${IMG.h}px; transform-origin: 0 0; }
        .shot-img, .flip { position: absolute; left: 0; top: 0; width: ${IMG.w}px; height: ${IMG.h}px; display: block; }
        .flip { opacity: 0; }
        .hl { position: absolute; border: 5px solid #f2a93b; border-radius: 14px; box-shadow: 0 0 0 6px rgba(242,169,59,0.25), 0 0 30px rgba(242,169,59,0.45); opacity: 0; }
        .cursor { position: absolute; width: 40px; height: 50px; opacity: 0; }
        .cursor svg { position: absolute; left: 0; top: 0; filter: drop-shadow(0 4px 6px rgba(0,0,0,0.4)); }
        .ripple { position: absolute; left: -40px; top: -40px; width: 80px; height: 80px; border-radius: 50%; border: 5px solid #f2a93b; opacity: 0; }
        .split { display: flex; flex-direction: column; gap: 22px; padding: 18px; background: #dfe8ea; }
        .pane { display: flex; flex-direction: column; width: 1476px; height: 395px; }
        .pane-label { height: 35px; font-size: 24px; font-weight: 700; color: #0f4f4a; }
        .pane-view { position: relative; width: 1476px; height: 360px; overflow: hidden; border-radius: 12px; background: #f3f6f8; box-shadow: 0 6px 18px rgba(0,0,0,0.12); }
        .pdf { background: #d7dfe1; display: flex; justify-content: center; }
        .pdf-page { position: relative; margin-top: 30px; background: #fff; box-shadow: 0 10px 30px rgba(0,0,0,0.25); }
        .pdf-page img { width: 100%; height: 100%; display: block; }
        .chip { position: absolute; left: ${CARD.x}px; top: 28px; height: 50px; display: flex; align-items: center; gap: 14px; opacity: 0; }
        .chip-n { display: flex; align-items: center; justify-content: center; width: 44px; height: 44px; border-radius: 50%; background: #f2b84b; color: #10231f; font-size: 24px; font-weight: 800; }
        .chip-who { font-size: 26px; font-weight: 700; color: #8fd8cc; }
        .chip-what { font-size: 30px; font-weight: 700; color: #f3fbfa; }`,
  `<div id="card-frame">${cardHtml}</div>${chips}`, localize(cardJs, cardStart)));

out('closing', subcomp('closing', TOTAL - closeStart, `
        #closing { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; padding-bottom: 120px; }
        #c-line1 { font-size: 72px; font-weight: 800; color: #f3fbfa; }
        #c-line2 { margin-top: 18px; font-size: 52px; font-weight: 700; color: #f2b84b; }
        #c-rule { margin-top: 44px; width: 420px; height: 4px; border-radius: 2px; background: #2fb3a5; transform-origin: 50% 50%; }
        #c-foot { margin-top: 36px; font-size: 26px; color: #a9c9c5; }`,
  `<div id="closing">
          <div id="c-line1">AI 僅供輔助</div>
          <div id="c-line2">最終判讀由醫師決定</div>
          <div id="c-rule"></div>
          <div id="c-foot">腎超新・雙機傳圖 → AI 分析 → 報告｜研究用途原型，非醫療器材</div>
        </div>`, closeJs));

out('captions', subcomp('captions', TOTAL, `
        .cap { position: absolute; left: 0; top: 966px; width: 1920px; height: 76px; display: flex; align-items: center; justify-content: center; font-size: 44px; font-weight: 600; color: #ffffff; letter-spacing: 0.03em; text-shadow: 0 2px 8px rgba(0,0,0,0.6); opacity: 0; }`,
  capHtml, capJs));

const slot = (id, start, dur, track, extra = '') => `<div id="el-${id}" data-composition-id="${id}" data-composition-src="compositions/${id}.html" data-start="${r(start)}" data-duration="${r(dur)}" data-track-index="${track}" data-width="1920" data-height="1080"${extra}></div>`;
const audio = scenes.map(s => `<audio id="vo-${s.id}" src="assets/vo/${s.id}.mp3" data-start="${r(s.audio)}" data-duration="${VO[s.id]}" data-track-index="10" data-volume="1"></audio>`).join('\n      ');

writeFileSync(join(ROOT, 'index.html'), `<!doctype html>
<html lang="zh-Hant">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <!-- GENERATED by scripts/build.mjs — edit the generator, not this file. -->
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body { width: 1920px; height: 1080px; overflow: hidden; background: #0c2125; }
      #root { position: relative; width: 100%; height: 100%; overflow: hidden; }
      #root > div[data-composition-src] { position: absolute; inset: 0; }
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="${TOTAL}" data-width="1920" data-height="1080">
      ${slot('bg', 0, TOTAL, 0)}
      ${slot('title', 0, s1.dur, 1)}
      ${slot('card', cardStart, cardEnd - cardStart, 2)}
      ${slot('closing', closeStart, TOTAL - closeStart, 3)}
      ${slot('captions', 0, TOTAL, 4, ' data-track-kind="captions"')}
      ${audio}
    </div>
    <script>
      window.__timelines["main"] = gsap.timeline({ paused: true });
    </script>
  </body>
</html>
`);

// characters that need glyphs in the subset font
const allText = [readFileSync(join(ROOT, 'index.html'), 'utf8'), ...['bg', 'title', 'card', 'closing', 'captions'].map(n => readFileSync(join(ROOT, 'compositions', n + '.html'), 'utf8'))].join('');
const textChars = new Set([...allText.replace(/<[^>]+>/g, ' ')].filter(c => c.charCodeAt(0) > 32));
writeFileSync(join(ROOT, 'scripts/chars.txt'), [...textChars].join(''));
console.log('total', TOTAL, 'captions', captions.length);
