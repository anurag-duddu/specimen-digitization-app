# Reading model marks

Retrieved October 3, 2026. These assets identify the recorded model family,
independently of the service hosting inference. Unknown families receive no mark.
The complete recorded model identifier remains visible beside its reading.

## Qwen3-VL

- Official source: https://github.com/QwenLM/Qwen3-VL
- Original PNG linked in that project's README:
  https://qianwen-res.oss-accelerate.aliyuncs.com/Qwen3-VL/qwen3vllogo.png
- Local `qwen3-vl.png` preserves the original download bytes.
- SHA-256: `605e83f1c4e3bbeaf9402ce1e7e98ab2081bb72dc9a959f211ba19b73e6dd078`
- Used only for recorded Qwen3-VL family identifiers; this mark is not applied to
  older Qwen versions or unrelated hosting providers.

## Muse

- Official source: https://muse.ai/ , linked from Meta's announcement:
  https://about.fb.com/news/2026/09/introducing-muse-personal-ai-agent/
- That publisher explicitly says "Meta built Muse from the ground up" and
  directly links `http://muse.ai` in its rollout paragraph. The current site
  identifies its product as "Muse — Your Personal AI Agent" and its footer
  identifies Meta; this is not a mark sourced from the historical video service.
- Recorded model authority:
  https://research.meta.ai/blog/introducing-muse-glimmer-open-agentic-model
  links https://huggingface.co/meta-models/Muse-Glimmer-30B and says
  "We trained Muse Glimmer on Muse Spark's outputs". The publisher's Glimmer
  page at https://dev.meta.ai/models/muse-glimmer also links Muse Connectors
  on `muse.ai`.
- Original favicon: https://muse.ai/favicon.ico
- Local `muse-favicon.ico` preserves the original container bytes.
- Container SHA-256: `487d1ada58c7ab7958d447b6bd1653b5b1caf66ca974638a9dddfed573f407a2`
- `muse.png` is the unchanged 128 by 128 PNG payload embedded in that ICO.
  Extraction reads the ICO image-directory offset and length; it does not
  redraw, recolor, resize, or otherwise modify the PNG.
- PNG SHA-256: `3524e5dfc3b63a458edcee9c269428a69f5ff61f7140b62e1578a7907bc5b105`
- This is the publisher's Muse family/app mark, not a separate Glimmer-specific
  logo. Used only for recorded Muse-Glimmer identifiers. It does not identify
  DeepInfra or assert an unrecorded model version; other Muse-named models
  receive text alone until their matching mark is verified.

These are the original publishers' marks; attribution and source custody are
retained here. Flutter bundles only the two PNG assets declared in pubspec.yaml.
