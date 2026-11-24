# Dashboard UX review, November 2026

The web UI (`ai_detect/web/static/`) checked against ordinary interface practice on 24 Nov 2026, what was changed because of it, and what is still wrong. "Tested" means one of the 29 browser tests in `tests/ui/test_dashboard.py` exercises it.

Design source: the Houtini site theme (`src/styles/global.css` and `docs/design.md` in the site repo, read only). Taken from it: zinc grounds, one accent per theme (emerald in light, violet in dark), hairline rules in place of shadows and cards, measured numbers in a monospace face, a serif for the text being read. No web font is loaded, because the page makes no external request; the named faces are used if installed and system faces otherwise. The layout idea of "verdict first, highlighted text, details at the side" is common to detector products; the wording, palette, type and components here are our own.

## Checks

| Practice | State | Evidence or change |
|---|---|---|
| One primary action per screen | Met | Each form has one filled button (Run scan, Compare, Run batch); everything else is an outline button. |
| Verdict first, then evidence | Met | The result page opens with the label, the calibrated document score, the confidence and the notes, then the text, then the detail panel. |
| The verdict does not overclaim | **Changed** | The first version printed "Likely AI" at 52% with low confidence. The label now has an "Uncertain" band from 40% to 60%, and is based on the calibrated score, not the raw one. |
| Visible system status | Met, tested | Progress lists each model by name while downloading (percent, size, minutes left), then loading and scoring one at a time; fetching and tells stages are named. The Models page shows live download bars. |
| Empty, loading and error states | Met for the main paths, tested | Empty text, a bad URL, an unreachable URL, an unknown scan id and a failed download each show a message and re-enable the button. Empty history and "no tells" have their own text. |
| Colour is not the only carrier | **Changed** | Score bands were shown by background colour only. Added: an underline that changes with the band (none, dotted, dashed, solid), the percentage as a tooltip on every sentence, and a Sentences table with the figures. Flags say "FLAG" in text; severities are words; agreement is given as "2 of 5" beside the dots. |
| Keyboard access | Met with a cost, tested | Every control is a native button, link, input or label. Sentences are focusable and Enter opens them. Cost: a long article adds one tab stop per sentence. A "skip to content" link is the first stop. Not fixed: no arrow-key movement between sentences. |
| Focus visible | Met | A 2 px accent outline on `:focus-visible`. |
| Readable line length | Met | The text column is capped at 70 characters at 17 px with 1.75 line height. |
| Clickable regions do not overlap | **Changed**, found by test | On the Page view every tell drew one box around all its regions, so a page-wide tell covered the others and they could not be clicked. Now each region is its own outline, smaller ones sit on top, and a tell with more than six regions is drawn only while selected. |
| Responsive, laptop to wide desktop | Met, tested at 800 px and 1440 px | Two columns above 980 px; under it the detail panel moves below the text. Content is capped at 1240 px on wide screens. Not designed for phones. |
| Light and dark | Met, tested | Dark by default, following the system setting on first visit; the choice is remembered. Both have screenshots. |
| Destructive actions confirm | Met, tested | Delete scan and Clear history ask first. |
| Limits are enforced where they are chosen | Met, tested | A sixth model tick is undone at once. |
| Says where data goes | Met | "local only" in the header with a tooltip; the vision option states that a non-local address uploads the screenshot and needs a tick. |
| Reduced motion | Met | The indeterminate progress bar stops animating under `prefers-reduced-motion`. |

## Still wrong or unverified

- **Contrast was not measured.** Colours were chosen for contrast by eye in both themes; no tool was run. The muted grey on the panel grey in light mode is the pair most worth checking.
- The result toolbar wraps: on a 1440 px window the Delete button drops to a second row.
- The Page view shows the third-party page at reduced size; small text in it is not readable. It is for locating regions, not reading.
- The Sentence tab shows the raw and calibrated figures without explaining the difference in place; the explanation is one tab away, under Models.
- No screen reader was used. Roles and labels are present (tablist, status regions, an `aria-label` on the breakdown bar) but untested with assistive software.
- Model choice lives only on the Scan page; Compare and Batch say so in a line of text and offer no picker of their own.
- A long-running scan cannot be cancelled from the page.

## Test results

```
$ python -m pytest tests/ui -q
29 passed, 2 warnings in 141.52s (0:02:21)
```

Covered: navigation, theme toggle and persistence, source tabs, text scan, sentence click and keyboard open, all five side tabs, text and table views, rewrite list, three exports, two-model ensemble columns, the five-model cap, URL scan with the page view and tells, tell-to-text highlighting, file upload, empty text, bad URL, unreachable URL, compare, batch with one failing item and its CSV, history open, history toggle and clear, delete, model download, failed download and retry, a scan that first downloads its model, an unknown scan id, the foreign-Host refusal, and the narrow layout. Not covered by a browser test: dragging a file onto the page (the file picker path is), the perplexity option, the vision form, and the low-memory option.
