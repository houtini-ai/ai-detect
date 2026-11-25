// ai-detect dashboard. Plain JavaScript, no build step, no external requests.
'use strict';
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = (p) => (p == null ? '' : Math.round(p * 100) + '%');
const main = $('#main');
let STATE = null;
let poll = null;

async function api(path, options) {
  const res = await fetch(path, options && options.body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, ...options, body: JSON.stringify(options.body) } : options);
  const data = (res.headers.get('content-type') || '').includes('json') ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && data.error) || data || res.statusText);
  return data;
}
const loadState = async () => (STATE = await api('/api/state'));
const chosen = () => {
  let ids = [];
  try { ids = JSON.parse(localStorage.getItem('ai-detect-models') || '[]'); } catch (e) { ids = []; }
  ids = ids.filter((id) => STATE.models.some((m) => m.id === id));
  return ids.length ? ids : [STATE.default_model];
};
const heat = (p) => (p == null ? 'skip' : p < 0.2 ? 'h0' : p < 0.4 ? 'h1' : p < 0.6 ? 'h2' : p < 0.8 ? 'h3' : 'h4');
const score = (s) => (s.label === 'Skipped' ? null : (s.calibrated_prob ?? s.ai_prob));
const size = (mb) => (mb >= 1000 ? (mb / 1000).toFixed(2) + ' GB' : mb + ' MB');
const raid = (m) => (m.raid ? `#${m.raid.rank} of ${m.raid.of}` : 'unranked');
// Time left, in the same words as the server's message (downloads.eta_text).
const etaText = (s) => (!s || s <= 0 ? '' : s < 45 ? ', less than a minute left' : ', about ' + Math.max(1, Math.round(s / 60)) + ' min left');

// ---------------------------------------------------------------- theme, nav
$('#theme').addEventListener('click', () => {
  const next = document.documentElement.className === 'dark' ? 'light' : 'dark';
  document.documentElement.className = next;
  localStorage.setItem('ai-detect-theme', next);
  $('#theme').textContent = next === 'dark' ? 'Light' : 'Dark';
});
$('#theme').textContent = document.documentElement.className === 'dark' ? 'Light' : 'Dark';

const routes = { '': scanPage, compare: comparePage, batch: batchPage, history: historyPage, models: modelsPage, scan: resultPage };
async function route() {
  clearInterval(poll);
  const [name, arg] = location.hash.replace(/^#\/?/, '').split('/');
  const page = routes[name] || scanPage;
  $$('.top nav a').forEach((a) => a.toggleAttribute('aria-current', false));
  const nav = $(`.top nav a[data-nav="${name === '' || name === 'scan' ? 'scan' : name}"]`);
  if (nav) nav.setAttribute('aria-current', 'page');
  try {
    await loadState();
    $('#version').textContent = 'v' + STATE.version;
    $('#foot-url').textContent = location.origin;
    await page(arg);
  } catch (e) { main.innerHTML = `<section class="page narrow"><div class="error">${esc(e.message)}</div></section>`; }
  main.focus({ preventScroll: true });
}
addEventListener('hashchange', route);

// ---------------------------------------------------------------- progress
function progressView(box, job) {
  const p = job.progress || {};
  const lines = [];
  const line = (name, frac, note, busy) => lines.push(`<div class="line"><span>${esc(name)}</span><span class="bar${busy ? ' busy' : ''}"><i style="width:${Math.round((frac || 0) * 100)}%"></i></span><span class="hint mono">${esc(note || '')}</span></div>`);
  if (p.side) lines.push(`<div class="hint">Version ${esc(p.side.toUpperCase())}</div>`);
  if (p.of && p.item != null && p.stage !== 'loading' && p.stage !== 'scoring') line(`Item ${Math.min(p.item + 1, p.of)} of ${p.of}`, p.item / p.of, '');
  if (p.stage === 'downloading') {
    for (const m of p.models) line(m.model, m.percent / 100, m.status === 'ready' ? 'ready' : `${m.percent}% of ${size(m.approx_mb)}${etaText(m.eta_seconds)}`);
    lines.unshift('<div class="hint">Downloading models from Hugging Face (one time). Nothing is uploaded.</div>');
  } else if (p.stage === 'loading' || p.stage === 'scoring') {
    for (let i = 0; i < p.of; i++) {
      const done = i < p.index;
      const name = i === p.index ? p.model : (done ? 'done' : 'waiting');
      line(i === p.index ? p.model : `model ${i + 1}`, done ? 1 : 0, i === p.index ? p.stage : name, i === p.index);
    }
  } else line({ queued: 'Queued', fetching: 'Fetching the page', reading: 'Reading', tells: 'Structure and style', perplexity: 'Perplexity (GPT-2)', batch: 'Batch' }[p.stage] || 'Working', 0, '', true);
  box.hidden = false;
  box.innerHTML = lines.join('');
}
function runJob(kind, body, box, button, done, onTick) {
  button.disabled = true;
  box.hidden = false;
  box.innerHTML = '<div class="line"><span>Starting</span><span class="bar busy"><i></i></span><span></span></div>';
  const fail = (msg) => { box.innerHTML = `<div class="error">${esc(msg)}</div>`; button.disabled = false; };
  api('/api/start/' + kind, { body }).then(({ job_id }) => {
    poll = setInterval(async () => {
      try {
        const job = await api('/api/jobs/' + job_id);
        if (job.state === 'failed') { clearInterval(poll); return fail(job.error); }
        if (job.state === 'done') { clearInterval(poll); button.disabled = false; box.hidden = true; return done(job.result); }
        progressView(box, job);
        if (onTick) onTick(job);
      } catch (e) { clearInterval(poll); fail(e.message); }
    }, 500);
  }).catch((e) => fail(e.message));
}

// ---------------------------------------------------------------- scan page
function modelPicker(el) {
  const picked = new Set(chosen());
  el.innerHTML = STATE.models.map((m) => `<label>
    <input type="checkbox" value="${esc(m.id)}" ${picked.has(m.id) ? 'checked' : ''}>
    <span><b>${esc(m.id)}</b>${m.id === STATE.default_model ? ' <span class="hint">default</span>' : ''}</span>
    <span class="hint wide">${esc(m.summary)}</span>
    <span class="num">${size(m.approx_mb)}</span>
    <span class="num" title="RAID leaderboard, ${esc(m.raid ? m.raid.metric + ', read ' + m.raid.read : '')}">RAID ${raid(m)}</span>
    <span class="state ${esc(m.status)} wide">${m.status === 'ready' ? 'ready' : m.status === 'downloading' ? m.percent + '%' : m.status === 'failed' ? 'failed' : 'downloads on use'}</span>
  </label>`).join('');
  el.addEventListener('change', () => {
    let ids = $$('input:checked', el).map((i) => i.value);
    if (ids.length > 5) { ids = ids.slice(0, 5); $$('input', el).forEach((i) => (i.checked = ids.includes(i.value))); }
    localStorage.setItem('ai-detect-models', JSON.stringify(ids));
  });
}
const readFile = (file) => new Promise((ok, bad) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = () => bad(r.error); r.readAsText(file); });
function dropTarget(el, onFiles) {
  el.addEventListener('dragover', (e) => { e.preventDefault(); el.classList.add('over'); });
  el.addEventListener('dragleave', () => el.classList.remove('over'));
  el.addEventListener('drop', (e) => { e.preventDefault(); el.classList.remove('over'); if (e.dataTransfer.files.length) onFiles(Array.from(e.dataTransfer.files)); });
}
async function scanPage() {
  main.replaceChildren($('#t-scan').content.cloneNode(true));
  modelPicker($('#model-picker'));
  let src = 'text', file = null;
  const show = (name) => {
    src = name;
    $$('#scan-form [role=tab]').forEach((b) => b.setAttribute('aria-selected', b.dataset.src === name));
    $$('#scan-form [data-pane]').forEach((p) => (p.hidden = p.dataset.pane !== name));
  };
  $$('#scan-form [role=tab]').forEach((b) => b.addEventListener('click', () => show(b.dataset.src)));
  if (!STATE.url_input) $('#url-hint').innerHTML = 'URL input needs Playwright, which is not installed. In the ai-detect folder run <code>pip install ".[web]"</code> then <code>playwright install chromium</code>.';
  const setFile = (files) => { file = files[0]; $('#file-name').textContent = `${file.name} (${Math.ceil(file.size / 1024)} KB)`; show('file'); };
  dropTarget($('#text'), setFile);
  dropTarget($('#drop'), setFile);
  $('#file').addEventListener('change', (e) => e.target.files.length && setFile(Array.from(e.target.files)));
  $('#scan-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = { models: chosen(), perplexity: $('#opt-ppl').checked, low_memory: $('#opt-lowmem').checked };
    if (src === 'url') body.url = $('#url').value;
    else if (src === 'file' && file) { body.file_name = file.name; body.file_content = await readFile(file); }
    else body.text = $('#text').value;
    runJob('scan', body, $('#scan-progress'), $('#scan-form .primary'), (r) => (location.hash = '#/scan/' + r.scan_id));
  });
}

// ---------------------------------------------------------------- result page
function verdictStrip(r, compact) {
  const a = r.assessment, b = a.breakdown;
  const op = r.operating_point || {};
  const scored = r.ai_count + r.human_count;
  return `<div class="verdict">
    <div><div class="src">${esc(r.source.title || r.source.label)}${r.source.kind === 'url' ? ' · ' + esc(r.source.label) : ''}</div><div class="label">${esc(a.label)}</div></div>
    <div class="stat"><div class="k">Document score</div><div class="v">${a.ai_pct.toFixed(1)}<small>% AI</small></div></div>
    ${compact ? '' : `<div class="stat"><div class="k">Confidence</div><div class="v">${esc(a.confidence)}</div></div>
    <div class="stat"><div class="k">Flagged</div><div class="v">${op.flagged_sentences ?? r.ai_count}<small> / ${scored}</small></div></div>`}
    <div><div class="split" role="img" aria-label="By words: ${b.ai}% reads as AI, ${b.uncertain}% uncertain, ${b.human}% reads as human">
      <i class="ai" style="width:${b.ai}%"></i><i class="mid" style="width:${b.uncertain}%"></i><i class="human" style="width:${b.human}%"></i></div>
      <div class="key"><span><b>${b.ai}%</b> AI</span><span><b>${b.uncertain}%</b> uncertain</span><span><b>${b.human}%</b> human</span></div></div>
  </div>`;
}
function markSentence(s) {
  let out = '', at = 0;
  const spans = (s.diagnostics || []).filter((d) => d.end > d.start).sort((x, y) => x.start - y.start);
  for (const d of spans) {
    if (d.start < at) continue;
    out += esc(s.sentence.slice(at, d.start)) + `<mark title="${esc(d.pattern.replace(/_/g, ' ') + ': ' + d.suggestion)}">${esc(s.sentence.slice(d.start, d.end))}</mark>`;
    at = d.end;
  }
  return out + esc(s.sentence.slice(at));
}
function docView(r) {
  const byBlock = new Map();
  for (const s of r.sentences) { if (!byBlock.has(s.block)) byBlock.set(s.block, []); byBlock.get(s.block).push(s); }
  const html = [];
  let inList = false;
  for (const [block, list] of byBlock) {
    const kind = list[0].kind;
    if (kind !== 'list_item' && inList) { html.push('</ul>'); inList = false; }
    const inner = list.map((s) => `<span class="s ${heat(score(s))}" data-i="${s.index}" tabindex="${s.label === 'Skipped' ? -1 : 0}" title="${s.label === 'Skipped' ? 'not scored' : pct(score(s)) + ' AI'}">${markSentence(s)}</span>`).join(' ');
    if (kind === 'heading') html.push(`<h3 class="blk" data-b="${block}">${esc(list[0].sentence)}</h3>`);
    else if (kind === 'list_item') { if (!inList) { html.push('<ul>'); inList = true; } html.push(`<li class="blk" data-b="${block}">${inner}</li>`); }
    else html.push(`<p class="blk" data-b="${block}">${inner}</p>`);
  }
  if (inList) html.push('</ul>');
  return `<div class="doc">${html.join('')}</div>`;
}
function tableView(r) {
  const multi = r.models.length > 1;
  const rows = r.sentences.filter((s) => s.label !== 'Skipped').map((s) => `<tr class="link" data-i="${s.index}">
    <td>${esc(s.sentence)}</td>
    ${r.models.map((m) => `<td class="num"><span class="heat ${heat(s.calibrated ? s.calibrated[m] : s.scores[m])}" title="raw ${pct(s.scores[m])}">${pct(s.calibrated ? s.calibrated[m] : s.scores[m])}</span></td>`).join('')}
    ${multi ? `<td class="num"><span class="pips">${r.models.map((m) => `<i class="${s.flags[m] ? 'on' : ''}"></i>`).join('')}</span></td><td class="num"><span class="heat ${heat(score(s))}">${pct(score(s))}</span></td>` : ''}
    ${r.perplexity ? `<td class="num">${s.perplexity ?? ''}</td>` : ''}</tr>`).join('');
  return `<div class="tablewrap" tabindex="0" role="region" aria-label="Sentence scores"><table><thead><tr><th>Sentence</th>${r.models.map((m) => `<th class="num">${esc(m)}</th>`).join('')}${multi ? '<th class="num">Agree</th><th class="num">Combined</th>' : ''}${r.perplexity ? '<th class="num">Perplexity</th>' : ''}</tr></thead><tbody>${rows}</tbody></table></div>
  <p class="hint">Calibrated scores: 50% is the point 5% of human-written sentences reach on the local evaluation set. Hover a figure for the model's raw probability.</p>`;
}
function pageView(r, tells) {
  const w = r.page.page.width;
  // One outline per region, smallest on top so every one can be clicked. A
  // whole-page tell (many regions) is drawn only while it is selected.
  const boxes = tells.filter((t) => t.rects && t.rects.length).flatMap((t) => t.rects.map((q, i) => ({ t, q, i })))
    .sort((a, b) => b.q[2] * b.q[3] - a.q[2] * a.q[3])
    .map(({ t, q, i }) => `<div class="box ${t.family === 'visual' ? 'visual' : 'structure'}${t.rects.length > 6 ? ' wide' : ''}" data-t="${t.n}" title="${esc(t.label)}" style="left:${(q[0] / w) * 100}%;top:calc(${q[1]} * var(--k));width:${(q[2] / w) * 100}%;height:calc(${q[3]} * var(--k))">${i === 0 ? `<b>${t.n + 1}</b>` : ''}</div>`).join('');
  return `<div class="shot" id="shot"><img src="/api/scans/${esc(r.scan_id)}/screenshot.jpg" alt="Screenshot of the scanned page with flagged regions outlined">${boxes}</div>
  <p class="hint">Outlined regions are numbered to match the Tells panel. Red: page shape. Amber: structure and style.${r.page.clipped_at ? ' The screenshot stops at ' + r.page.clipped_at + ' px.' : ''}</p>`;
}
const tellCard = (t) => `<div class="card click" data-t="${t.n}"><div><b>${t.n + 1}. ${esc(t.label)}</b><span class="sev ${esc(t.severity)}">${esc(t.severity)}</span></div>
  ${t.example ? `<q>${esc(t.example)}</q>` : ''}<div class="fix">${esc(t.suggestion)}</div>${t.detail ? `<div class="hint">${esc(t.detail)}</div>` : ''}</div>`;
function sentenceCard(r, s) {
  if (!s) return '<p class="empty">Click a sentence to see why it scored the way it did.</p>';
  const rows = r.models.map((m) => `<dt>${esc(m)}${s.flags && s.flags[m] ? ' <span class="sev high">flag</span>' : ''}</dt><dd>${pct(s.calibrated ? s.calibrated[m] : s.scores[m])} <span class="hint">raw ${pct(s.scores[m])}</span></dd>`).join('');
  return `<div class="card"><q>${esc(s.sentence)}</q></div>
  <h2>Model scores</h2><dl class="kv">${rows}${r.models.length > 1 ? `<dt>Combined (calibrated mean)</dt><dd>${pct(score(s))}</dd><dt>Agreement</dt><dd>${s.agreement} of ${r.models.length}</dd>` : ''}${s.perplexity != null ? `<dt>GPT-2 perplexity</dt><dd>${s.perplexity}</dd>` : ''}</dl>
  <h2 style="margin-top:18px">Why</h2>${(s.why || []).map((w) => `<div class="card">${esc(w)}</div>`).join('') || '<p class="hint">Nothing specific: the score comes from the model alone.</p>'}
  ${(s.diagnostics || []).length ? `<h2 style="margin-top:18px">Rewrite</h2>${s.diagnostics.map((d) => `<div class="card"><b>${esc(d.match)}</b><div class="fix">${esc(d.suggestion)}</div></div>`).join('')}` : ''}`;
}
function sidePanels(r, tells) {
  const flagged = r.sentences.filter((s) => score(s) != null && (score(s) >= 0.5 || (s.diagnostics || []).length)).sort((a, b) => score(b) - score(a));
  const sum = r.tells.summary || {};
  const models = r.models.map((m) => {
    const info = r.model_info[m], pm = (r.per_model || {})[m];
    return `<div class="card"><b>${esc(info.label)}</b>
      <dl class="kv"><dt>RAID</dt><dd>${info.raid ? `#${info.raid.rank} of ${info.raid.of} (${info.raid.score})` : 'unranked'}</dd><dt>Licence</dt><dd>${esc(info.licence)}</dd><dt>Size</dt><dd>${size(info.approx_mb)}</dd>
      ${pm ? `<dt>Document, raw</dt><dd>${pm.document_ai_pct}%</dd><dt>Sentences flagged</dt><dd>${pm.flagged_sentences}</dd><dt>Calls the document AI</dt><dd>${pm.document_flag ? 'yes' : 'no'}</dd>` : ''}</dl>
      ${info.raid ? `<div class="hint">${esc(info.raid.metric)}, read ${esc(info.raid.read)}. <a href="${esc(info.raid.source)}" target="_blank" rel="noreferrer">source</a>${info.raid.note ? '. ' + esc(info.raid.note) : ''}</div>` : ''}
      ${info.caveats.map((c) => `<div class="hint">${esc(c)}</div>`).join('')}</div>`;
  }).join('');
  const p = r.perplexity, tm = r.text_metrics || {};
  return {
    sentence: sentenceCard(r, null),
    tells: `<p class="hint">${esc(r.tells.note)}</p>${tells.length ? `<p class="hint mono">${sum.total || tells.length} hits, ${sum.distinct || ''} kinds${sum.per_1000_words ? ', ' + sum.per_1000_words + ' per 1,000 words' : ''}</p>` + tells.map(tellCard).join('') : '<p class="empty">No structure or style tells found.</p>'}`,
    rewrite: flagged.length ? flagged.map((s) => `<div class="card click" data-i="${s.index}"><span class="heat ${heat(score(s))} mono">${pct(score(s))}</span><q>${esc(s.sentence)}</q>${(s.diagnostics || []).map((d) => `<div class="fix"><b>${esc(d.match)}</b>: ${esc(d.suggestion)}</div>`).join('') || '<div class="hint">No pattern matched. Try contracting the verbs and naming the specific thing.</div>'}</div>`).join('') : '<p class="empty">Nothing flagged and no pattern hits.</p>',
    models: models + (r.ensemble ? `<p class="hint">${esc(r.ensemble.note)}</p>` : '') + `<p class="hint">${esc((r.operating_point || {}).note || '')}</p>`,
    signals: `<h2>Sentence length</h2><dl class="kv"><dt>Mean words</dt><dd>${tm.mean ?? ''}</dd><dt>Variation (CV)</dt><dd>${tm.cv ?? ''}</dd><dt>Reading</dt><dd>${esc(tm.verdict || '')}</dd></dl>
      <h2 style="margin-top:18px">Perplexity and burstiness</h2>${p ? `<dl class="kv"><dt>Document perplexity</dt><dd>${p.document}</dd><dt>Mean per sentence</dt><dd>${p.mean}</dd><dt>Burstiness (spread)</dt><dd>${p.burstiness}</dd><dt>Burstiness (CV)</dt><dd>${p.burstiness_cv}</dd></dl><p class="hint">${esc(p.note)}</p>` : '<p class="hint">Not run. Tick "Perplexity and burstiness" on the scan form.</p>'}
      <h2 style="margin-top:18px">Passages</h2><table><thead><tr><th>Words</th><th class="num">Score</th>${r.models.length > 1 ? '<th class="num">Agree</th>' : ''}</tr></thead><tbody>${r.passages.map((x) => `<tr><td class="num" style="text-align:left">${x.words}${x.short ? ' <span class="hint">short</span>' : ''}</td><td class="num"><span class="heat ${heat(x.calibrated_prob)}">${pct(x.calibrated_prob)}</span></td>${r.models.length > 1 ? `<td class="num">${x.agreement}/${r.models.length}</td>` : ''}</tr>`).join('')}</tbody></table>
      ${r.source.has_screenshot ? `<h2 style="margin-top:18px">Vision second opinion</h2><p class="hint">Off by default. Sends the screenshot to the OpenAI-compatible endpoint you give. A local server keeps it on this machine; any other address uploads the picture.</p>
      <form id="vision"><label for="v-end">Endpoint</label><input id="v-end" type="text" placeholder="http://127.0.0.1:8000/v1"><label for="v-model" style="margin-top:8px">Model</label><input id="v-model" type="text"><label for="v-key" style="margin-top:8px">API key (optional, not stored)</label><input id="v-key" type="password" autocomplete="off">
      <label class="check" style="margin-top:8px"><input type="checkbox" id="v-remote"> I understand a non-local endpoint receives the screenshot</label><div class="row"><button class="ghost" type="submit">Ask the vision model</button></div><div id="v-out"></div></form>` : ''}`,
  };
}
async function resultPage(id) {
  const r = await api('/api/scans/' + encodeURIComponent(id));
  const tells = [...r.tells.structure, ...r.tells.visual];
  const panels = sidePanels(r, tells);
  const hasPage = r.source.has_screenshot && r.page;
  main.innerHTML = `<section class="page">${verdictStrip(r)}
    ${r.assessment.notes.length ? `<ul class="notes">${r.assessment.notes.map((n) => `<li>${esc(n)}</li>`).join('')}</ul>` : ''}
    <div class="toolbar"><div class="seg" id="view"><button aria-pressed="true" data-v="text">Text</button><button aria-pressed="false" data-v="table">Sentences</button>${hasPage ? '<button aria-pressed="false" data-v="page">Page</button>' : ''}</div>
      <span class="hint mono">${esc(r.models.join(' + '))} · ${r.words} words · ${esc(r.created || '')}</span><span class="sp"></span>
      <a class="ghost" href="/api/scans/${esc(id)}/export.html" style="text-decoration:none">Report (HTML)</a><a class="ghost" href="/api/scans/${esc(id)}/export.csv" style="text-decoration:none">CSV</a><a class="ghost" href="/api/scans/${esc(id)}/export.json" style="text-decoration:none">JSON</a><button class="ghost danger" id="del">Delete</button></div>
    <div class="work"><div id="left"></div>
      <aside class="side" aria-label="Details"><div class="tabs" role="tablist">${['sentence', 'tells', 'rewrite', 'models', 'signals'].map((t, i) => `<button role="tab" data-p="${t}" aria-selected="${i === 0}">${t[0].toUpperCase() + t.slice(1)}${t === 'tells' ? ` <span class="mono">${tells.length}</span>` : ''}</button>`).join('')}</div><div id="panel"></div></aside></div></section>`;
  const left = $('#left'), panel = $('#panel');
  const views = { text: () => docView(r), table: () => tableView(r), page: () => pageView(r, tells) };
  const tab = (name) => { $$('.side [role=tab]').forEach((b) => b.setAttribute('aria-selected', b.dataset.p === name)); panel.innerHTML = panels[name]; };
  const view = (name) => {
    $$('#view button').forEach((b) => b.setAttribute('aria-pressed', b.dataset.v === name));
    // The Sentences table needs the full width: the side panel moves under it.
    $('.work').classList.toggle('stacked', name === 'table');
    left.innerHTML = views[name]();
    const shot = $('#shot');
    if (shot) { const fit = () => shot.style.setProperty('--k', shot.clientWidth / r.page.page.width + 'px'); fit(); new ResizeObserver(fit).observe(shot); }
  };
  const pickSentence = (i) => {
    const s = r.sentences.find((x) => x.index === i);
    if (!s || s.label === 'Skipped') return;
    panels.sentence = sentenceCard(r, s);
    tab('sentence');
    $$('.s.on, tr.on').forEach((e) => e.classList.remove('on'));
    const el = $(`.s[data-i="${i}"]`);
    if (el) { el.classList.add('on'); el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
    const row = $(`#left tr[data-i="${i}"]`);
    if (row) { row.classList.add('on'); $('.side').scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
  };
  const pickTell = (n) => {
    const t = tells.find((x) => x.n === n);
    $$('.blk.lit, .box.on, .card.on').forEach((e) => e.classList.remove('lit', 'on'));
    if (!$('.card[data-t]', panel)) tab('tells');
    const card = $(`.card[data-t="${n}"]`, panel);
    if (card) { card.classList.add('on'); card.scrollIntoView({ block: 'nearest' }); }
    const boxes = $$(`.box[data-t="${n}"]`);
    if (boxes.length) { boxes.forEach((b) => b.classList.add('on')); boxes[boxes.length - 1].scrollIntoView({ block: 'center', behavior: 'smooth' }); return; }
    if (!$('.doc')) view('text');
    const blocks = (t.blocks || []).map((b) => $(`.blk[data-b="${b}"]`)).filter(Boolean);
    blocks.forEach((b) => b.classList.add('lit'));
    if (blocks[0]) blocks[0].scrollIntoView({ block: 'center', behavior: 'smooth' });
  };
  main.addEventListener('click', (e) => {
    const t = e.target.closest('[data-t]'); if (t) return pickTell(+t.dataset.t);
    const s = e.target.closest('[data-i]'); if (s) { if (s.matches('.card')) view('text'); return pickSentence(+s.dataset.i); }
    const v = e.target.closest('#view button'); if (v) return view(v.dataset.v);
    const p = e.target.closest('.side [role=tab]'); if (p) return tab(p.dataset.p);
  });
  main.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('.s')) pickSentence(+e.target.dataset.i); });
  main.addEventListener('submit', async (e) => {
    if (e.target.id !== 'vision') return;
    e.preventDefault();
    const out = $('#v-out'); out.innerHTML = '<p class="hint">Asking...</p>';
    try {
      const v = await api(`/api/scans/${encodeURIComponent(id)}/vision`, { body: { endpoint: $('#v-end').value, model: $('#v-model').value, api_key: $('#v-key').value, confirm_remote: $('#v-remote').checked } });
      out.innerHTML = `<div class="card"><b>${esc(v.verdict)}</b> <span class="hint">${esc(v.model)}, ${v.local ? 'local endpoint' : 'remote endpoint'}</span>${v.observations.map((o) => `<div class="fix">${esc(o)}</div>`).join('')}</div>`;
    } catch (err) { out.innerHTML = `<div class="error">${esc(err.message)}</div>`; }
  });
  $('#del').addEventListener('click', async () => { if (confirm('Delete this scan from history?')) { await api('/api/scans/' + encodeURIComponent(id), { method: 'DELETE' }); location.hash = '#/history'; } });
  view('text');
  tab(tells.length && !r.ai_count ? 'tells' : 'sentence');
}

// ---------------------------------------------------------------- compare
async function comparePage() {
  main.replaceChildren($('#t-compare').content.cloneNode(true));
  $('#cmp-models').textContent = 'Models: ' + chosen().join(' + ') + ' (change on the Scan page)';
  const side = (v) => (/^https?:\/\/\S+$/.test(v.trim()) ? { url: v.trim() } : { text: v });
  $('#compare-form').addEventListener('submit', (e) => {
    e.preventDefault();
    runJob('compare', { a: side($('#cmp-a').value), b: side($('#cmp-b').value), models: chosen() }, $('#compare-progress'), $('#compare-form .primary'), async (res) => {
      const [a, b] = await Promise.all([api('/api/scans/' + res.a), api('/api/scans/' + res.b)]);
      const c = res.compare;
      const row = (k, pair, unit = '') => `<tr><td>${k}</td><td class="num">${pair[0]}${unit}</td><td class="num">${pair[1]}${unit}</td><td class="num">${typeof pair[0] === 'number' ? (pair[1] - pair[0] > 0 ? '+' : '') + (Math.round((pair[1] - pair[0]) * 10) / 10) + unit : ''}</td></tr>`;
      // One model: its own figures are on its raw scale and are labelled so.
      // An ensemble's are already calibrated means, and its document figure is the score above.
      const isRaw = (c.raw_scale || []).some(Boolean);
      const rawRows = isRaw
        ? row('Document score, raw', c.document_ai_pct, '%') + row('Mean sentence score, raw', c.sentence_ai_pct, '%') + row('Sentences over 50%, raw', c.flagged_sentences)
        : row('Mean sentence score', c.sentence_ai_pct, '%');
      $('#compare-result').innerHTML = `<div class="cols" style="margin-top:28px"><div><h2>Before</h2>${verdictStrip(a, true)}<p><a href="#/scan/${esc(a.scan_id)}">Open the full result</a></p></div><div><h2>After</h2>${verdictStrip(b, true)}<p><a href="#/scan/${esc(b.scan_id)}">Open the full result</a></p></div></div>
        <table style="margin-top:20px"><thead><tr><th>Measure</th><th class="num">Before</th><th class="num">After</th><th class="num">Change</th></tr></thead><tbody>
        ${row('Verdict', c.verdicts)}${row('Document score', c.calibrated_document_pct, '%')}${row('Sentences flagged', c.operating_point_flagged)}${rawRows}${row('Sentence pattern hits', c.patterns)}${row('Structure and style tells', c.tells)}</tbody></table>
        ${isRaw ? '<p class="hint">Rows marked raw are the model\'s own probabilities before calibration. The verdict and the document score are read at the calibrated operating point, as on the result page.</p>' : ''}`;
    });
  });
}

// ---------------------------------------------------------------- batch
const scanRows = (rows) => rows.map((x) => x.error ? `<tr><td>${esc(x.label)}</td><td colspan="6" style="color:var(--ai)">${esc(x.error)}</td></tr>`
  : `<tr class="link" data-open="${esc(x.scan_id)}"><td>${esc(x.title || x.label)}<div class="hint">${esc(x.kind === 'url' ? x.label : (x.created || '').replace('T', ' '))}</div></td><td>${esc(x.verdict)}</td><td class="num">${x.calibrated_document_pct ?? x.document_ai_pct ?? ''}%</td><td class="num">${x.sentence_ai_pct ?? ''}%${x.raw_scale ? ' <span class="hint">raw</span>' : ''}</td><td class="num">${x.flagged ?? ''}</td><td class="num">${x.tells ?? ''}</td><td class="num">${x.words ?? ''}</td></tr>`).join('');
const scanTable = (rows) => `<table><thead><tr><th>Source</th><th>Verdict</th><th class="num" title="Calibrated document score, as on the result page">Document</th><th class="num" title="Mean sentence score. Marked raw when one model ran: its own probabilities, before calibration">Sentences</th><th class="num">Flagged</th><th class="num">Tells</th><th class="num">Words</th></tr></thead><tbody>${scanRows(rows)}</tbody></table>`;
main.addEventListener('click', (e) => { const row = e.target.closest('tr[data-open]'); if (row) location.hash = '#/scan/' + row.dataset.open; });
async function batchPage() {
  main.replaceChildren($('#t-batch').content.cloneNode(true));
  $('#batch-models').textContent = 'Models: ' + chosen().join(' + ') + ' (change on the Scan page)';
  let files = [];
  const add = (list) => { files = files.concat(list); $('#batch-file-names').textContent = files.map((f) => f.name).join(', '); };
  dropTarget($('.drop.small'), add);
  $('#batch-files').addEventListener('change', (e) => add(Array.from(e.target.files)));
  $('#batch-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = { items: $('#batch-items').value.split('\n'), models: chosen(), files: await Promise.all(files.map(async (f) => ({ name: f.name, content: await readFile(f) }))) };
    const out = $('#batch-result');
    const show = (rows) => (out.innerHTML = `<div style="margin-top:24px">${scanTable(rows)}</div>`);
    runJob('batch', body, $('#batch-progress'), $('#batch-form .primary'), (res) => {
      show(res.rows);
      out.insertAdjacentHTML('beforeend', `<p><a class="ghost" style="text-decoration:none" href="/api/batches/${esc(res.batch_id)}/export.csv">Download the summary as CSV</a></p>`);
    }, (job) => job.progress.rows && job.progress.rows.length && show(job.progress.rows));
  });
}

// ---------------------------------------------------------------- history, models
async function historyPage() {
  const h = await api('/api/scans');
  main.innerHTML = `<section class="page"><h1>History</h1>
    <p class="lede">Scans are saved as files on this machine${STATE.history.enabled ? '' : ' only while this window is open, because saving is off'}. <span class="mono hint">${esc(STATE.history.folder)}</span></p>
    <div class="toolbar"><label class="check"><input type="checkbox" id="h-on" ${h.enabled ? 'checked' : ''}> Save scans to disk</label><span class="sp"></span><button class="ghost danger" id="h-clear">Clear history</button></div>
    ${h.scans.length ? scanTable(h.scans) : '<p class="empty">No scans yet.</p>'}</section>`;
  $('#h-on').addEventListener('change', async (e) => { await api('/api/settings', { body: { history: e.target.checked } }); route(); });
  $('#h-clear').addEventListener('click', async () => { if (confirm('Delete every saved scan? This cannot be undone.')) { await api('/api/scans', { method: 'DELETE' }); route(); } });
}
async function modelsPage() {
  const draw = () => {
    main.innerHTML = `<section class="page"><h1>Models</h1>
      <p class="lede">Weights download from Hugging Face on first use and are cached on this machine. RAID ranks are from the leaderboard's all-attacks view, read on the date shown. They describe whole documents, not single sentences.</p>
      <table><thead><tr><th>Model</th><th class="num">Size</th><th>Licence</th><th>RAID</th><th>Runs on</th><th>Status</th><th></th></tr></thead><tbody>
      ${STATE.models.map((m) => `<tr><td><b style="color:var(--text)">${esc(m.id)}</b>${m.id === STATE.default_model ? ' <span class="hint">default</span>' : ''}<div>${esc(m.label)}</div><div class="hint">${esc(m.summary)} <a href="${esc(m.card)}" target="_blank" rel="noreferrer">model card</a></div>${m.caveats.map((c) => `<div class="hint">${esc(c)}</div>`).join('')}</td>
        <td class="num">${size(m.approx_mb)}</td><td>${esc(m.licence)}</td>
        <td>${m.raid ? `<span class="mono">#${m.raid.rank} of ${m.raid.of}</span><div class="hint">${m.raid.score} ${esc(m.raid.metric)}<br>read ${esc(m.raid.read)}, <a href="${esc(m.raid.source)}" target="_blank" rel="noreferrer">source</a></div>` : 'unranked'}</td>
        <td>${esc(m.runtime)}${m.extra ? `<div class="hint">extra: ${esc(m.extra)}</div>` : ''}</td>
        <td><span class="state ${esc(m.status)}">${esc(m.status.replace('_', ' '))}</span>${m.status === 'downloading' ? `<div class="bar" style="margin-top:6px"><i style="width:${m.percent}%"></i></div><div class="hint mono">${m.percent}%${etaText(m.eta_seconds)}</div>` : ''}${m.error ? `<div class="hint" style="color:var(--ai)">${esc(m.error)}</div>` : ''}</td>
        <td>${m.status === 'ready' || m.status === 'downloading' ? '' : `<button class="ghost" data-dl="${esc(m.id)}">${m.status === 'failed' ? 'Retry' : 'Download'}</button>`}</td></tr>`).join('')}</tbody></table></section>`;
  };
  draw();
  main.onclick = async (e) => { const b = e.target.closest('[data-dl]'); if (b) { await api(`/api/models/${b.dataset.dl}/download`, { method: 'POST' }); await loadState(); draw(); } };
  poll = setInterval(async () => { if (STATE.models.some((m) => m.status === 'downloading')) { await loadState(); draw(); } }, 1000);
}
route();
