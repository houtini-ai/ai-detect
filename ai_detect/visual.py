"""Visual-shape tells, read from the rendered page's geometry (no model).

Input is the ``visual`` snapshot that ai_detect/assets/extract.js takes from the
live DOM: bounding boxes and a few computed styles. The rules are deterministic
and local. They describe the page's shape; they do not look at pixels.

Every tell carries ``rect`` ([x, y, width, height] in page pixels) so the web UI
can outline it on the screenshot. Image tells are worded as candidates and give
their basis (a file name, an alt text): nothing here can tell whether a picture
was generated.

An optional second opinion from a vision model is in ``vision_review()``. It is
off unless the caller passes an endpoint, and it sends the screenshot to that
endpoint.
"""

import base64
import json
import re
import statistics
import urllib.request

_AI_IMAGE_RX = re.compile(
    r"dall[-_ ]?e|midjourney|stable[-_ ]?diffusion|sdxl|gemini[-_ ]generated|imagen[-_ ]|"
    r"firefly|flux[-_ ]|ai[-_ ]generated|generated[-_ ]by[-_ ]ai|chatgpt[-_ ]image|openai|"
    r"leonardo[-_ ]ai|ideogram|nano[-_ ]?banana", re.IGNORECASE)
_STOCK_RX = re.compile(
    r"shutterstock|istock|gettyimages|unsplash|pexels|pixabay|adobestock|adobe[-_ ]stock|"
    r"freepik|undraw|storyset|depositphotos|dreamstime|stock[-_ ]photo|stock[-_ ]image",
    re.IGNORECASE)


def _tell(id, label, severity, suggestion, example, rect, detail="", rects=None):
    return {"id": id, "family": "visual", "label": label, "severity": severity,
            "block": None, "blocks": [], "example": example, "suggestion": suggestion,
            "detail": detail, "rect": rect, "rects": rects or ([rect] if rect else [])}


def _union(rects):
    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[0] + r[2] for r in rects)
    y1 = max(r[1] + r[3] for r in rects)
    return [x0, y0, x1 - x0, y1 - y0]


def find_visual_tells(visual, document=None):
    """Return a list of visual tells for one page snapshot."""
    tells = []
    visual = visual or {}

    hero = visual.get("hero")
    if hero:
        traits = [name for name, on in (
            ("gradient background", hero.get("gradient")),
            ("centred headline", hero.get("centred")),
            ("two buttons", hero.get("buttons") == 2),
        ) if on]
        if len(traits) == 3:
            tells.append(_tell(
                "gradient_hero", "Gradient hero, centred headline, two buttons", "high",
                "Lead with something specific to this product: a real screenshot, a number, "
                "one clear action.",
                hero.get("heading", ""), hero["rect"],
                "Buttons: " + ", ".join(hero.get("button_labels", []))))
        elif hero.get("centred") and hero.get("buttons") == 2:
            tells.append(_tell(
                "centred_hero", "Centred headline with two buttons", "medium",
                "The default landing-page opening. One action is usually enough.",
                hero.get("heading", ""), hero["rect"],
                "Buttons: " + ", ".join(hero.get("button_labels", []))))

    for group in visual.get("groups", []):
        items = group["items"]
        headed = sum(1 for it in items if it["heading"])
        iconed = sum(1 for it in items if it["icon"])
        blurbs = [it["blurb_words"] for it in items if it["heading"]]
        if headed < len(items) or not blurbs or max(blurbs) > 60 or min(blurbs) < 4:
            continue
        names = ", ".join(it["heading"] for it in items[:4])
        even = max(blurbs) - min(blurbs) <= 6
        if group["count"] == 3 and group["same_row"]:
            tells.append(_tell(
                "card_grid_of_three",
                "Three identical cards" + (" (icon, heading, blurb)" if iconed == 3 else ""),
                "high" if iconed == 3 else "medium",
                "Three matched cards is the default feature section. Show the one thing "
                "that matters at full width, or let the items differ in size.",
                names, group["rect"],
                f"Blurbs of {min(blurbs)}-{max(blurbs)} words each."
                + (" All three the same length." if even else ""),
                rects=[it["rect"] for it in items]))
        elif iconed == len(items) and group["count"] in (4, 6, 8, 9):
            tells.append(_tell(
                "icon_feature_grid", f"Grid of {group['count']} icon-heading-blurb blocks", "medium",
                "A grid of equal icon blocks reads as filler. Keep the ones with a real "
                "claim and give them room.",
                names, group["rect"], f"Blurbs of {min(blurbs)}-{max(blurbs)} words each.",
                rects=[it["rect"] for it in items]))

    sections = [s for s in visual.get("sections", []) if s["rect"][3] > 0]
    heights = [s["rect"][3] for s in sections]
    if len(heights) >= 4:
        cv = statistics.pstdev(heights) / statistics.fmean(heights)
        centred = sum(1 for s in sections if s.get("centred"))
        if cv < 0.15 or (centred == len(sections) and cv < 0.3):
            tells.append(_tell(
                "uniform_section_rhythm", "Every section the same height", "medium",
                "Let sections take the space their content needs.",
                f"{len(sections)} sections, {min(heights)}-{max(heights)} px tall",
                _union([s["rect"] for s in sections]),
                f"Height variation {cv:.2f}; {centred} of {len(sections)} have a centred heading.",
                rects=[s["rect"] for s in sections]))

    for image in visual.get("images", []):
        haystack = " ".join((image.get("src", "").rsplit("/", 1)[-1], image.get("alt", ""),
                             image.get("title", ""), image.get("caption", "")))
        m = _AI_IMAGE_RX.search(haystack)
        if m:
            tells.append(_tell(
                "ai_image_candidate", "Possible AI-generated image", "low",
                "Check where the image came from. A photo or screenshot of the real thing "
                "is stronger.",
                image.get("alt") or image.get("src", "").rsplit("/", 1)[-1], image["rect"],
                f"Flagged only because its file name, alt text or caption contains "
                f"\"{m.group(0)}\". This is a lead, not a finding."))
            continue
        m = _STOCK_RX.search(image.get("src", "") + " " + image.get("alt", ""))
        if m:
            tells.append(_tell(
                "stock_image_candidate", "Possible stock image", "low",
                "A stock picture says nothing about the subject. Use your own, or none.",
                image.get("alt") or image.get("src", "").rsplit("/", 1)[-1], image["rect"],
                f"Flagged only because its address or alt text contains \"{m.group(0)}\"."))

    generator = (visual.get("generator") or "").strip()
    if document is not None:
        tells.extend(_block_shape_tells(document))
    if generator:
        for t in tells:
            t.setdefault("page_generator", generator)
    return tells


def _block_shape_tells(document):
    """Shapes that need the article blocks: long bullet walls, icon bullets."""
    out, lists = [], {}
    for block in document.blocks:
        if block.kind == "list_item" and block.meta.get("rect"):
            lists.setdefault(block.meta.get("list"), []).append(block)
    for members in lists.values():
        rects = [b.meta["rect"] for b in members]
        if len(members) >= 7:
            out.append(_tell(
                "wall_of_bullets", f"Wall of {len(members)} bullets", "medium",
                "Group them, cut the weak ones, or write the important three as a paragraph.",
                members[0].text[:90], _union(rects), rects=rects))
        icons = [b for b in members if b.meta.get("icon_lead") or b.meta.get("emoji_lead")]
        if len(icons) >= 3:
            out.append(_tell(
                "icon_bullets", "Icon or emoji bullets", "medium",
                "Ordinary bullets read as a person's list.", icons[0].text[:90],
                _union([b.meta["rect"] for b in icons]),
                f"{len(icons)} items start with an icon or emoji.",
                rects=[b.meta["rect"] for b in icons]))
    return out


# ---------------------------------------------------------------------------
# Optional: a vision model's second opinion
# ---------------------------------------------------------------------------

VISION_PROMPT = (
    "You are reviewing a screenshot of a web page for generic, template-like design. "
    "List up to six concrete things in the layout that make it look machine-made or "
    "like a default template (for example: three identical feature cards, a gradient "
    "hero with a centred headline and two buttons, stock illustrations, emoji bullets). "
    "If it looks hand-made, say so. Reply as JSON: "
    '{"verdict": "generic" | "mixed" | "distinctive", "observations": ["..."]}'
)


def is_local_endpoint(endpoint):
    from urllib.parse import urlparse
    host = (urlparse(endpoint).hostname or "").lower()
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost")


def vision_review(screenshot, endpoint, model, api_key=None, timeout=120):
    """Ask an OpenAI-compatible vision model about the screenshot.

    OFF unless called. The screenshot is sent to ``endpoint``: if that is not
    this machine, the picture of the page leaves it. Returns
    ``{verdict, observations, endpoint, model, local}`` or raises RuntimeError.
    """
    if not screenshot:
        raise RuntimeError("No screenshot to review (URL or HTML input only).")
    body = {
        "model": model, "max_tokens": 700,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": VISION_PROMPT},
            {"type": "image_url", "image_url": {
                "url": "data:image/jpeg;base64," + base64.b64encode(screenshot).decode()}},
        ]}],
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    url = endpoint.rstrip("/") + "/chat/completions"
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            content = json.loads(r.read())["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Vision endpoint {url} failed: {e}") from e
    parsed = {"verdict": "unparsed", "observations": [content.strip()[:1500]]}
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            parsed = {"verdict": str(data.get("verdict", "unparsed")),
                      "observations": [str(o) for o in data.get("observations", [])][:8]}
        except ValueError:
            pass
    parsed.update(endpoint=endpoint, model=model, local=is_local_endpoint(endpoint))
    return parsed
