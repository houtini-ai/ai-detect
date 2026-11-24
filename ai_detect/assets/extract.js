// Runs inside the fetched page (read-only: it clicks nothing, submits nothing,
// follows no link). Returns the article structure and a geometry snapshot:
//   { title, url, lang, blocks: [...], visual: { page, hero, groups, images, sections } }
// Coordinates are CSS pixels from the top-left of the full page, so they map
// straight onto a full-page screenshot.
() => {
  const NOISE = /cookie|consent|gdpr|newsletter|subscribe|share|social|related|comment|sidebar|breadcrumb|toc\b|table-of-contents|promo|advert|popup|modal|banner/i;
  const SKIP_TAGS = new Set(['NAV', 'HEADER', 'FOOTER', 'ASIDE', 'FORM', 'SCRIPT', 'STYLE', 'NOSCRIPT',
    'TEMPLATE', 'IFRAME', 'SVG', 'BUTTON', 'SELECT', 'DIALOG', 'PRE', 'CODE']);
  const SKIP_ROLES = new Set(['navigation', 'banner', 'contentinfo', 'complementary', 'search', 'dialog', 'alertdialog']);
  const EMOJI = /^\s*(?:\p{Extended_Pictographic}|[✓✔✅➡→▶⭐])/u;

  const sx = window.scrollX, sy = window.scrollY;
  const rectOf = (el) => {
    const r = el.getBoundingClientRect();
    return [Math.round(r.left + sx), Math.round(r.top + sy), Math.round(r.width), Math.round(r.height)];
  };
  const visible = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
    if (el.getAttribute('aria-hidden') === 'true' || el.hidden) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const isNoise = (el) => {
    if (SKIP_TAGS.has(el.tagName.toUpperCase())) return true;
    if (SKIP_ROLES.has(el.getAttribute('role') || '')) return true;
    const name = (el.id || '') + ' ' + (typeof el.className === 'string' ? el.className : '');
    return NOISE.test(name);
  };
  const insideNoise = (el, stop) => {
    for (let n = el; n && n !== stop; n = n.parentElement) if (isNoise(n)) return true;
    return false;
  };

  // ---- main content root: <article>/<main> if it holds real text, else the
  // container holding the most paragraph text.
  const textIn = (el) => Array.from(el.querySelectorAll('p')).reduce((n, p) => n + clean(p.innerText).length, 0);
  let root = null, best = 0;
  for (const el of document.querySelectorAll('article, main, [role="main"], [itemprop="articleBody"]')) {
    if (!visible(el) || insideNoise(el, document.body)) continue;
    const n = textIn(el);
    if (n > best) { best = n; root = el; }
  }
  if (!root || best < 400) {
    const totals = new Map();
    for (const p of document.querySelectorAll('p')) {
      if (!visible(p) || insideNoise(p, document.body)) continue;
      const len = clean(p.innerText).length;
      let n = p.parentElement, depth = 0;
      while (n && n !== document.documentElement && depth < 4) {
        totals.set(n, (totals.get(n) || 0) + len / (depth + 1));
        n = n.parentElement; depth++;
      }
    }
    for (const [el, n] of totals) if (n > best && el !== document.body) { best = n; root = el; }
  }
  root = root || document.body;

  // ---- blocks, in document order
  const blocks = [];
  let listSeq = 0;
  const listIds = new Map();
  const boldLead = (el) => {
    const first = Array.from(el.childNodes).find((n) => n.nodeType === 1 || clean(n.textContent));
    if (!first || first.nodeType !== 1 || !/^(STRONG|B)$/.test(first.tagName)) return null;
    const label = clean(first.innerText);
    const rest = clean(el.innerText).slice(label.length);
    if (!label || label.length > 60 || !rest) return null;
    return /:$/.test(label) || /^\s*[:–—-]/.test(rest) ? label.replace(/:$/, '') : null;
  };
  const push = (kind, el, extra) => {
    const text = clean(el.innerText);
    if (!text) return;
    const meta = Object.assign({ rect: rectOf(el) }, extra || {});
    if (el.querySelector && el.querySelector('strong, b')) meta.bold = true;
    const lead = boldLead(el);
    if (lead) meta.bold_lead = lead;
    if (EMOJI.test(text)) meta.emoji_lead = true;
    blocks.push({ kind, text, level: extra && extra.level ? extra.level : 0, meta });
  };
  const walk = (el) => {
    for (const child of el.children) {
      if (!visible(child) || isNoise(child)) continue;
      const tag = child.tagName.toUpperCase();
      if (/^H[1-6]$/.test(tag)) { push('heading', child, { level: +tag[1] }); continue; }
      if (tag === 'P') { push('paragraph', child); continue; }
      if (tag === 'BLOCKQUOTE') { push('quote', child); continue; }
      if (tag === 'FIGCAPTION' || tag === 'CAPTION') { push('caption', child); continue; }
      if (tag === 'LI') {
        const list = child.closest('ul, ol');
        if (!listIds.has(list)) listIds.set(list, ++listSeq);
        let depth = 0;
        for (let n = list && list.parentElement; n && n !== root; n = n.parentElement) if (/^(UL|OL)$/.test(n.tagName)) depth++;
        const own = child.cloneNode(true);
        own.querySelectorAll('ul, ol').forEach((n) => n.remove());
        const text = clean(own.textContent);
        if (text) {
          const meta = { rect: rectOf(child), list: listIds.get(list), ordered: !!list && list.tagName === 'OL', depth };
          if (child.querySelector(':scope > strong, :scope > b, :scope > p > strong, :scope > p > b')) meta.bold = true;
          const lead = boldLead(child.querySelector(':scope > p') || child);
          if (lead) meta.bold_lead = lead;
          if (EMOJI.test(text)) meta.emoji_lead = true;
          if (child.querySelector(':scope > svg, :scope > img, :scope > i[class*="icon"], :scope > span[class*="icon"]')) meta.icon_lead = true;
          blocks.push({ kind: 'list_item', text, level: 0, meta });
        }
        for (const sub of child.querySelectorAll(':scope > ul, :scope > ol')) walk(sub);
        continue;
      }
      if (tag === 'TABLE') {
        const rows = Array.from(child.querySelectorAll('tr')).map((tr) =>
          Array.from(tr.querySelectorAll('th, td')).map((c) => clean(c.innerText)));
        if (rows.length) blocks.push({ kind: 'table', text: rows.map((r) => r.join(' | ')).join('\n'), level: 0, meta: { rect: rectOf(child), rows } });
        const cap = child.querySelector('caption');
        if (cap) push('caption', cap);
        continue;
      }
      if (tag === 'IMG' || tag === 'PICTURE' || tag === 'VIDEO') continue;
      if (child.children.length === 0) {
        // A bare <div>/<span> of text with no block children still reads as a paragraph.
        if (clean(child.innerText).split(' ').length >= 8 && getComputedStyle(child).display !== 'inline') push('paragraph', child);
        continue;
      }
      walk(child);
    }
  };
  walk(root);

  // ---- geometry snapshot for the visual tells (whole page, not just the article)
  const doc = document.documentElement;
  const page = { width: doc.scrollWidth, height: doc.scrollHeight, viewport: [window.innerWidth, window.innerHeight] };

  const isButtonLike = (el) => {
    if (!visible(el)) return false;
    if (el.tagName === 'BUTTON') return true;
    const cs = getComputedStyle(el);
    const filled = cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && cs.backgroundColor !== 'transparent';
    const bordered = parseFloat(cs.borderTopWidth) > 0 && cs.borderTopStyle !== 'none';
    return (filled || bordered) && parseFloat(cs.paddingLeft) >= 8 && clean(el.innerText).length > 0 && clean(el.innerText).length < 40;
  };
  const gradientBehind = (el) => {
    for (let n = el; n && n !== doc; n = n.parentElement) {
      const bg = getComputedStyle(n).backgroundImage || '';
      if (/gradient\(/.test(bg)) return true;
    }
    return /gradient\(/.test(getComputedStyle(document.body).backgroundImage || '');
  };
  let hero = null;
  const h1 = Array.from(document.querySelectorAll('h1')).find(visible);
  if (h1) {
    const r = rectOf(h1);
    if (r[1] < page.viewport[1] * 1.2) {
      let box = h1.parentElement;
      for (let i = 0; i < 4 && box && box.parentElement && box !== document.body; i++) {
        if (box.getBoundingClientRect().height > 260) break;
        box = box.parentElement;
      }
      box = box || h1;
      const buttons = Array.from(box.querySelectorAll('a, button')).filter(isButtonLike);
      const centre = r[0] + r[2] / 2;
      hero = {
        rect: rectOf(box), heading: clean(h1.innerText), heading_rect: r,
        centred: getComputedStyle(h1).textAlign === 'center' && Math.abs(centre - page.width / 2) < page.width * 0.08,
        buttons: buttons.length, button_labels: buttons.slice(0, 4).map((b) => clean(b.innerText)),
        gradient: gradientBehind(h1),
        subheading: !!(h1.nextElementSibling && /^(P|H2|DIV)$/.test(h1.nextElementSibling.tagName)),
      };
    }
  }

  // Sibling groups: 3+ visible children with the same tag and class, similar
  // size. Rows of cards, feature blocks, pricing tiers.
  const groups = [];
  for (const parent of document.querySelectorAll('div, section, ul, ol')) {
    if (!visible(parent) || insideNoise(parent, document.body)) continue;
    const kids = Array.from(parent.children).filter(visible);
    if (kids.length < 3 || kids.length > 12) continue;
    const sig = (k) => k.tagName + '.' + (typeof k.className === 'string' ? k.className.trim().split(/\s+/).sort().join('.') : '');
    if (!kids.every((k) => sig(k) === sig(kids[0]))) continue;
    const rects = kids.map(rectOf);
    const w = rects.map((r) => r[2]), h = rects.map((r) => r[3]);
    const spread = (a) => (Math.max(...a) - Math.min(...a)) / Math.max(1, Math.max(...a));
    if (Math.min(...w) < 120 || Math.min(...h) < 60 || spread(w) > 0.08) continue;
    const sameRow = rects.every((r) => Math.abs(r[1] - rects[0][1]) < 8);
    const items = kids.map((k, i) => {
      const heading = k.querySelector('h2, h3, h4, h5, strong, b');
      const icon = k.querySelector('svg, img, i[class*="icon"], span[class*="icon"]');
      const iconRect = icon ? icon.getBoundingClientRect() : null;
      const text = clean(k.innerText);
      return {
        rect: rects[i], heading: heading ? clean(heading.innerText).slice(0, 80) : '',
        icon: !!(iconRect && iconRect.width <= 96 && iconRect.height <= 96) || EMOJI.test(text),
        words: text ? text.split(' ').length : 0,
        blurb_words: heading ? Math.max(0, text.split(' ').length - clean(heading.innerText).split(' ').length) : 0,
      };
    });
    if (items.filter((it) => it.words >= 4).length < 3) continue;
    groups.push({ rect: rectOf(parent), count: kids.length, same_row: sameRow, height_spread: +spread(h).toFixed(3), in_article: root.contains(parent), items });
  }
  // Keep the outermost of any nested groups.
  const outer = groups.filter((g) => !groups.some((o) => o !== g && o.rect[0] <= g.rect[0] && o.rect[1] <= g.rect[1] &&
    o.rect[0] + o.rect[2] >= g.rect[0] + g.rect[2] && o.rect[1] + o.rect[3] >= g.rect[1] + g.rect[3] && o.count === g.count));

  // A broken image collapses to its alt text, so fall back to its declared size.
  const images = Array.from(document.images).filter((img) => getComputedStyle(img).display !== 'none').map((img) => {
    const fig = img.closest('figure');
    const r = rectOf(img);
    const w = Math.max(r[2], +img.getAttribute('width') || 0), h = Math.max(r[3], +img.getAttribute('height') || 0);
    return {
      rect: [r[0], r[1], w, h], src: (img.getAttribute('src') || img.currentSrc || '').slice(0, 300), alt: (img.alt || '').slice(0, 200),
      title: (img.title || '').slice(0, 120), natural: [img.naturalWidth, img.naturalHeight],
      caption: fig && fig.querySelector('figcaption') ? clean(fig.querySelector('figcaption').innerText).slice(0, 200) : '',
      in_article: root.contains(img),
    };
  }).filter((im) => im.rect[2] >= 120 && im.rect[3] >= 80 && !/^data:image\/gif/.test(im.src) || /generat|dall|midjourney/i.test(im.alt));

  const sections = Array.from(document.querySelectorAll('main > section, body > section, main > div > section, [class*="section"]'))
    .filter((s) => visible(s) && !insideNoise(s, document.body) && s.getBoundingClientRect().height > 120)
    .slice(0, 40).map((s) => {
      const heading = s.querySelector('h1, h2, h3');
      return {
        rect: rectOf(s), heading: heading ? clean(heading.innerText).slice(0, 80) : '',
        paragraphs: s.querySelectorAll('p').length, bullets: s.querySelectorAll('li').length,
        centred: getComputedStyle(heading || s).textAlign === 'center',
      };
    });

  const meta = (name) => { const m = document.querySelector(`meta[name="${name}"], meta[property="${name}"]`); return m ? m.content : ''; };
  return {
    title: clean(document.title) || (h1 ? clean(h1.innerText) : ''), url: location.href, lang: doc.lang || '',
    root: { tag: root.tagName.toLowerCase(), rect: rectOf(root) },
    generator: meta('generator'), description: meta('description') || meta('og:description'),
    blocks, visual: { page, hero, groups: outer.slice(0, 40), images: images.slice(0, 80), sections },
  };
}
