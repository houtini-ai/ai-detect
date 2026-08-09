# The signs of AI writing, measured

The eight structural patterns below are what actually move an AI detector, ranked by how hard they hit. Missing contractions are the single strongest signal: "The software has been significantly improved" scores **92.6% AI**, while "software's got a lot better" — the same fact, contracted — scores **0.03%**. Formal verbs are next: "provides excellent stability" scores 99.6%, "doesn't flex" scores 0.01%. Every number here comes from a paired test, the same information written twice.

The finding underneath all of it: **detectors have learned what clean, balanced, professional prose looks like, because that's what AI writes.** Formality is the tell, not vocabulary. There's no word list to avoid.

**Tested:** 70+ paired sentence variations, February 2026
**Model:** desklib/ai-text-detector-v1.01 (DeBERTa-v3-large, 304M parameters, RAID benchmark #1)
**Previous model:** dejanseo/ai-cop (DeBERTa-v3-small fine-tune) — replaced 2026-02-16
**Tool:** `ai-detect` (see the [README](../README.md)) — run any of these yourself

## How the tests were run

Each test was a paired comparison: a formal, AI-style sentence against a conversational rewrite carrying the same information. Pairing matters — it isolates *structure* from *subject*, so the gap can only come from how the sentence is built. Score one sentence on its own and you learn very little; write the same fact two ways and you can see what the model's reacting to.

## The eight patterns

### 1. Contractions Are the #1 Signal

| Without contraction | AI prob | With contraction | AI prob |
|---|---|---|---|
| "The software has been significantly improved" | 92.6% | "Software's got a lot better" | 0.03% |
| "Fanatec is not the cheapest option available" | 53.4% | "Fanatec aren't cheap" | 0.05% |
| "They have partnered with several leading brands" | 98.8% | "They've partnered with Porsche, BMW, Bentley" | 0.01% |

### 2. "Provides/Offers/Delivers" Are Detector Magnets

| With formal verb | AI prob | With colloquial verb | AI prob |
|---|---|---|---|
| "provides excellent stability" | 99.6% | "doesn't flex" | 0.01% |
| "offers comprehensive software support" | 99.9% | "app's actually pretty good now" | 0.01% |
| "delivers impressive performance" | 92.5% | "genuinely impressive for what you're paying" | 17.0% |
| "encompasses multiple price points" | 99.5% | "ranges from basic stuff to high-end" | 0.02% |

### 3. "For [group] who [condition]" Is a Strong AI Signal

| AI frame | AI prob | Human frame | AI prob |
|---|---|---|---|
| "For PC-only buyers who don't need console support, Moza offer..." | 99.1% | "If you don't care about PlayStation, Moza will save you money" | 0.8% |
| Same, subject-first variant | 86.8% | "No PlayStation? Moza are cheaper" | 1.2% |

### 4. Formal Transitions Are Instant Flags

| With transition | AI prob | Without | AI prob |
|---|---|---|---|
| "Additionally, the QR2 provides..." | 99.6% | "The QR2 doesn't flex and..." | 0.01% |
| "Furthermore, Fanatec offers..." | 99.9% | "The Fanatec app replaced FanaLab and..." | 0.01% |
| "In conclusion, Fanatec remains..." | 99.9% | "Look, Fanatec make good kit" | 0.05% |
| "It's important to note that..." | 99.8% | "Prices vary by region, obviously" | 0.12% |
| "This represents a significant upgrade" | 99.8% | "Massive upgrade over the old version" | 0.8% |

### 5. Specific Names Beat Vague Abstractions

"several leading automotive brands" → 98.8% AI
"Porsche, BMW, Bentley and the WRC" → 0.01% AI

### 6. Trailing Opinions Lower AI Probability

Removing a trailing personal clause ("and I haven't seen much disagreement on that") INCREASED AI probability from 1.6% to 18.6%.

### 7. Patterns That Always Pass as Human

- Typos: 0.0% AI
- Colloquial idioms ("how far down the rabbit hole"): 0.25% AI
- "I reckon" + trailing "honestly": 0.3% AI
- Fragment questions ("No PlayStation?"): 2.9% AI
- Short blunt statements ("Fanatec aren't cheap"): 0.05% AI
- Dash-interrupted sentences with opinion: 0.01-0.03% AI
- Possessive contractions ("Software's got"): 0.03% AI

### 8. The Word "Noticeably" Is Flaggy

"The consensus has shifted noticeably" triggers AI regardless of framing (78-82% AI).
"The mood has definitely changed" passes (5.4% AI).

## The rule underneath all eight

**Simplify, don't engineer.** Every formal construction has a casual equivalent that reads as human. The detector has learned what clean, balanced, professional prose looks like — and that's what AI writes. Write like you're explaining something to a mate, not writing a press release.

## What this is not

It isn't a guide to beating a detector. The patterns run one way: formal phrasing reads as machine-written *because machines are trained on formal phrasing*, so fixing a flagged sentence and fixing a badly written one are the same edit. Contract the verbs, name the actual brands, put the opinion back in.

It also isn't a verdict engine. A confident writer who contracts their verbs sails through, and a careful human writing a spec sheet will flag. Across a batch of forty articles the signal is real; on any one sentence it is a prompt to look closer, not a finding.

## Checking your own text

```bash
pip install .
ai-detect --file draft.md
```

Every sentence is scored, and every flagged one comes back with the pattern that triggered it and a plain rewrite. The full tool, the model choices and the privacy position are in the [README](../README.md).
