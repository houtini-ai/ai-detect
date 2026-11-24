# Third-party models

ai-detect is MIT licensed. It does not contain or redistribute any model weights. When you select a model, its files are downloaded from the authors' own Hugging Face repository to your machine, and that model's licence applies to your use of it.

Licences and sizes were read from each model card and the Hugging Face API on 24 Nov 2026. Check the card before commercial use: a licence can change.

| Model id | Weights from | Licence of the weights | Size |
|---|---|---|---|
| `desklib` | [desklib/ai-text-detector-v1.01](https://huggingface.co/desklib/ai-text-detector-v1.01) | MIT | 1736 MB |
| `light` | [onnx-community/tmr-ai-text-detector-ONNX](https://huggingface.co/onnx-community/tmr-ai-text-detector-ONNX) | MIT | 126 MB |
| `gpttrace-150m` | [nakas/gpttrace-ettin150-text-v5e](https://huggingface.co/nakas/gpttrace-ettin150-text-v5e) | CC-BY-SA-4.0 | 151 MB |
| `gpttrace-1b` | [nakas/gpttrace-v8s-1b](https://huggingface.co/nakas/gpttrace-v8s-1b) | CC-BY-SA-4.0 | 951 MB |
| `tabularis` | [tabularisai/ai-text-detection](https://huggingface.co/tabularisai/ai-text-detection) | MIT | 598 MB |
| `conpara` | [SES-Lab-OTH/deberta-conpara](https://huggingface.co/SES-Lab-OTH/deberta-conpara) | MIT | 1738 MB |
| `conpara` (tokenizer and config) | [microsoft/deberta-v3-large](https://huggingface.co/microsoft/deberta-v3-large) | MIT | under 5 MB |
| perplexity readout (opt-in) | [openai-community/gpt2](https://huggingface.co/openai-community/gpt2) | MIT | 548 MB |

## What the licences mean here

- **MIT** (desklib, light, tabularis, conpara, GPT-2): use, including commercial use, with the copyright notice kept.
- **CC BY-SA 4.0** (gpttrace-150m, gpttrace-1b): the GPTTrace cards say the weights are share-alike because part of the human training text is from Wikipedia. Running the model to score text places no condition on your text or on ai-detect's code. If you redistribute the weights, or publish a model adapted from them, you must credit the authors and release it under the same licence. ai-detect only downloads the files from the authors' repository at run time.
- This is a plain-language summary, not legal advice.

## Vendored code

`ai_detect/_vendor/conpara_unicode.py` is the input normaliser from https://github.com/SES-Lab-OTH/deberta-conpara (MIT, Copyright (c) 2026 Mohamed Mady), carried unmodified because the DeBERTa-ConPara model is only robust when its input goes through exactly that normaliser. Its licence text is in `ai_detect/_vendor/LICENSE-conpara`.
