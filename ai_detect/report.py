"""Report export helpers for ai_detect."""
import json
import csv
import io
import html


def _cell(value):
    """Stop a spreadsheet treating scanned text as a formula."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def to_json(report) -> str:
    """Serialize the report dict to JSON text."""
    return json.dumps(report, indent=2, ensure_ascii=False)


def to_csv(report) -> str:
    """One CSV row per sentence."""
    models = report.get("models", [])
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    header = ["index", "kind", "label", "ai_prob", "calibrated_prob", "agreement"]
    header += ["score_" + m for m in models]
    header += ["perplexity", "patterns", "suggestions", "sentence"]
    writer.writerow(header)
    for s in report.get("sentences", []):
        row = [s.get("index", ""), s.get("kind", ""), s.get("label", ""),
               s.get("ai_prob", ""), s.get("calibrated_prob", ""), s.get("agreement", "")]
        scores = s.get("scores", {})
        row += [scores.get(m, "") for m in models]
        row += ["", "; ".join(d.get("pattern", "") for d in s.get("diagnostics", [])),
                "; ".join(d.get("match", "") + ": " + d.get("suggestion", "") for d in s.get("diagnostics", [])),
                s.get("sentence", "")]
        writer.writerow([_cell(v) for v in row])
    return buf.getvalue()


def batch_to_csv(rows) -> str:
    """One CSV row per batch dict."""
    keys = ["label", "verdict", "confidence", "document_ai_pct", "sentence_ai_pct",
            "words", "flagged", "tells", "scan_id", "error"]
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(keys)
    for r in rows:
        writer.writerow([_cell("" if r.get(k) is None else r.get(k)) for k in keys])
    return buf.getvalue()


def _heat(prob):
    if prob < 0.2:
        return 0
    if prob < 0.4:
        return 1
    if prob < 0.6:
        return 2
    if prob < 0.8:
        return 3
    return 4


def to_html(report) -> str:
    """Self-contained HTML5 report page."""
    src = report.get("source", {})
    title = html.escape(str(src.get("title") or src.get("label") or ""))
    models = report.get("models", [])
    model_str = ", ".join(html.escape(m) for m in models)
    created = report.get("created", "")
    words = report.get("words", "")
    assessment = report.get("assessment", {})
    label = html.escape(str(assessment.get("label", "")))
    doc_pct = report.get("document_ai_pct", "")
    conf = html.escape(str(assessment.get("confidence", "")))
    notes = assessment.get("notes", [])
    bd = assessment.get("breakdown", {})
    ai_w = bd.get("ai", 0)
    unc_w = bd.get("uncertain", 0)
    hum_w = bd.get("human", 0)
    mi = report.get("model_info", {})
    pm = report.get("per_model")
    sents = report.get("sentences", [])
    tells = report.get("tells", {})
    perplexity = report.get("perplexity")
    op = report.get("operating_point")

    css = (
        ":root{--canvas:#fafafa;--panel:#f4f4f5;--text:#18181b;--muted:#6b6b76;--line:#e4e4e7;--accent:#0f7a5a}"
        "@media(prefers-color-scheme:dark){:root{--canvas:#131316;--panel:#1a1a1e;--text:#fafafa;--muted:#a1a1aa;--line:#2e2e33;--accent:#b596f5}}"
        "body{background:var(--canvas);color:var(--text);font-family:system-ui,sans-serif;font-size:16px;line-height:1.6;max-width:860px;margin:0 auto;padding:40px 24px}"
        "header{margin-bottom:24px}"
        "header small{color:var(--muted);text-transform:uppercase;letter-spacing:.08em;font-size:12px}"
        "h1{margin:6px 0 10px;font-size:28px}"
        "header .meta{color:var(--muted);font-size:14px;margin:4px 0}"
        "header .meta span{font-family:ui-monospace,monospace}"
        ".verdict{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:18px 20px;margin:0 0 24px}"
        ".verdict h2{margin:0 0 8px;font-size:22px}"
        ".verdict .row{font-size:14px;margin:4px 0;color:var(--muted)}"
        ".verdict .row b{color:var(--text);font-family:ui-monospace,monospace}"
        ".verdict p{font-size:14px;margin:4px 0}"
        ".bar{display:flex;height:12px;border-radius:6px;overflow:hidden;margin:14px 0 6px}"
        ".bar span{display:inline-block;height:100%}"
        ".legend{font-size:13px;color:var(--muted);font-family:ui-monospace,monospace}"
        "section{margin:0 0 28px}"
        "section h2{font-size:18px;border-bottom:1px solid var(--line);padding-bottom:6px;margin:0 0 14px}"
        "table{width:100%;border-collapse:collapse;font-size:14px;text-align:left}"
        "th,td{border-bottom:1px solid var(--line);padding:8px 10px;vertical-align:top}"
        "th{color:var(--muted);font-weight:600}"
        "td.num{font-family:ui-monospace,monospace}"
        ".text{font-family:Georgia,serif;font-size:17px}"
        ".text p{margin:0 0 10px}"
        "h3{font-size:20px;margin:18px 0 8px}"
        ".s{padding:1px 3px;border-radius:3px}"
        ".s0{background:transparent}"
        ".s1{background:rgba(217,119,6,.10)}"
        ".s2{background:rgba(217,119,6,.22)}"
        ".s3{background:rgba(220,38,38,.22)}"
        ".s4{background:rgba(220,38,38,.38)}"
        ".skip{color:var(--muted)}"
        "ul{margin:4px 0 12px;padding-left:20px}"
        "li{margin:2px 0;font-size:14px}"
        ".note{font-size:14px;color:var(--muted);margin:0 0 12px}"
        "footer{margin-top:32px;padding-top:14px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}"
        "@media print{body{max-width:none;padding:0}}"
    )

    out = []
    out.append("<!DOCTYPE html>")
    out.append('<html lang="en">')
    out.append("<head>")
    out.append('<meta charset="utf-8">')
    out.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    out.append("<title>ai-detect report</title>")
    out.append("<style>" + css + "</style>")
    out.append("</head>")
    out.append("<body>")

    out.append("<header>")
    out.append('<small>ai-detect report</small>')
    out.append("<h1>" + title + "</h1>")
    out.append('<div class="meta">Created: ' + html.escape(str(created)) + "</div>")
    out.append('<div class="meta">Models: <span>' + model_str + "</span></div>")
    out.append('<div class="meta">Words: <span>' + html.escape(str(words)) + "</span></div>")
    out.append("</header>")

    out.append('<div class="verdict">')
    out.append("<h2>" + label + "</h2>")
    out.append('<div class="row">Document score: <b>' + html.escape(str(doc_pct)) + "%</b></div>")
    out.append('<div class="row">Confidence: <b>' + conf + "</b></div>")
    for n in notes:
        out.append("<p>" + html.escape(str(n)) + "</p>")
    out.append('<div class="bar">')
    out.append('<span style="width:' + str(ai_w) + '%;background:rgba(220,38,38,.7)"></span>')
    out.append('<span style="width:' + str(unc_w) + '%;background:rgba(217,119,6,.6)"></span>')
    out.append('<span style="width:' + str(hum_w) + '%;background:var(--accent)"></span>')
    out.append("</div>")
    legend = "AI " + str(ai_w) + "% · Uncertain " + str(unc_w) + "% · Human " + str(hum_w) + "%"
    out.append('<div class="legend">' + html.escape(legend) + "</div>")
    out.append("</div>")

    out.append("<section>")
    out.append("<h2>Models</h2>")
    out.append("<table>")
    cols = ["Model", "Licence", "RAID rank"]
    if pm is not None:
        cols += ["Doc score", "Flagged"]
    out.append("<tr>" + "".join("<th>" + html.escape(c) + "</th>" for c in cols) + "</tr>")
    for mid in models:
        info = mi.get(mid, {})
        raid = info.get("raid")
        if raid:
            rank_text = str(raid.get("rank", "")) + " of " + str(raid.get("of", "")) + " (" + str(raid.get("read", "")) + ")"
        else:
            rank_text = "not ranked"
        cells = [mid, info.get("licence", ""), rank_text]
        if pm is not None:
            pm_row = pm.get(mid, {})
            cells.append(str(pm_row.get("document_ai_pct", "")))
            cells.append(str(pm_row.get("flagged_sentences", "")))
        tds = []
        for i, c in enumerate(cells):
            if i in (3, 4):
                tds.append('<td class="num">' + html.escape(str(c)) + "</td>")
            else:
                tds.append("<td>" + html.escape(str(c)) + "</td>")
        out.append("<tr>" + "".join(tds) + "</tr>")
    out.append("</table>")
    out.append("</section>")

    out.append("<section class=\"text\">")
    out.append("<h2>Text</h2>")
    prev_block = None
    open_p = False
    for s in sents:
        kind = s.get("kind")
        block = s.get("block")
        text = html.escape(str(s.get("sentence", "")))
        if kind == "heading":
            if open_p:
                out.append("</p>")
                open_p = False
            out.append("<h3>" + text + "</h3>")
            prev_block = None
            continue
        prob = s.get("calibrated_prob", s.get("ai_prob", 0)) or 0
        if s.get("label") == "Skipped":
            cls = "skip"
            pct = 0
        else:
            cls = "s" + str(_heat(float(prob)))
            pct = int(round(float(prob) * 100))
        title_attr = str(pct) + "% (calibrated)"
        span = '<span class="s ' + cls + '" title="' + title_attr + '">' + text + "</span>"
        if open_p and block == prev_block:
            out.append(" ")
            out.append(span)
        else:
            if open_p:
                out.append("</p>")
            out.append("<p>")
            out.append(span)
            open_p = True
        prev_block = block
    if open_p:
        out.append("</p>")
    out.append("</section>")

    out.append("<section>")
    out.append("<h2>Flagged sentences</h2>")
    flagged_any = False
    for s in sents:
        prob = s.get("calibrated_prob", s.get("ai_prob", 0)) or 0
        if float(prob) < 0.5:
            continue
        flagged_any = True
        out.append("<div>")
        out.append("<p>" + html.escape(str(s.get("sentence", ""))) + ": <b class='num'>" + str(int(round(float(prob) * 100))) + "%</b></p>")
        why = s.get("why", [])
        if why:
            out.append("<ul>")
            for w in why:
                out.append("<li>" + html.escape(str(w)) + "</li>")
            out.append("</ul>")
        diag = s.get("diagnostics", [])
        suggestions = [d.get("match", "") + ": " + d.get("suggestion", "") for d in diag if d.get("suggestion")]
        if suggestions:
            out.append("<ul>")
            for sg in suggestions:
                out.append("<li>" + html.escape(sg) + "</li>")
            out.append("</ul>")
        out.append("</div>")
    if not flagged_any:
        out.append("<p>No sentence is over the flagging threshold.</p>")
    out.append("</section>")

    out.append("<section>")
    out.append("<h2>Structure and style</h2>")
    note = tells.get("note")
    if note:
        out.append('<p class="note">' + html.escape(str(note)) + "</p>")
    rows = list(tells.get("structure", [])) + list(tells.get("visual", []))
    if not rows:
        out.append("<p>No structure or style tells detected.</p>")
    else:
        out.append("<table>")
        out.append("<tr><th>Label</th><th>Severity</th><th>Example</th><th>Suggestion</th></tr>")
        for r in rows:
            out.append("<tr>")
            out.append("<td>" + html.escape(str(r.get("label", ""))) + "</td>")
            out.append("<td>" + html.escape(str(r.get("severity", ""))) + "</td>")
            out.append("<td>" + html.escape(str(r.get("example", ""))) + "</td>")
            out.append("<td>" + html.escape(str(r.get("suggestion", ""))) + "</td>")
            out.append("</tr>")
        out.append("</table>")
    out.append("</section>")

    if perplexity:
        out.append("<section>")
        out.append("<h2>Perplexity</h2>")
        # Keys as ai_detect/perplexity.py returns them.
        for row_label, key in (("Document perplexity", "document"),
                               ("Mean sentence perplexity", "mean"),
                               ("Burstiness", "burstiness"),
                               ("Burstiness (coefficient of variation)", "burstiness_cv")):
            value = perplexity.get(key)
            shown = "not available" if value is None else str(value)
            out.append('<div class="row">' + row_label + ': <b class="num">' + html.escape(shown) + "</b></div>")
        if perplexity.get("note"):
            out.append('<p class="note">' + html.escape(str(perplexity.get("note"))) + "</p>")
        out.append("</section>")

    out.append("<footer>")
    out.append("<p>Generated locally by ai-detect. A detector score is evidence, not proof.</p>")
    if op and op.get("note"):
        out.append("<p>" + html.escape(str(op.get("note"))) + "</p>")
    out.append("</footer>")

    out.append("</body>")
    out.append("</html>")
    return "\n".join(out)
