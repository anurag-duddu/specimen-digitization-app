"""Pinned Hugging Face Hub assets that require application-owned serving."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HuggingFaceHubModel:
    """An immutable Hub model reference and its intended execution boundary."""

    asset_id: str
    repo_id: str
    revision: str
    task: str
    serving_mode: str
    gated: bool = False


SAM3_MODEL = HuggingFaceHubModel(
    asset_id="sam3-segmentation",
    repo_id="facebook/sam3",
    revision="3c879f39826c281e95690f02c7821c4de09afae7",  # pragma: allowlist secret
    task="mask-generation",
    serving_mode="gpu-worker",
    gated=True,
)


# Nemotron is retained as a proven evaluation candidate, but Hugging Face's
# routed API does not currently serve this VLM.  It therefore belongs behind a
# separately deployed OpenAI-compatible vLLM/SGLang endpoint rather than the
# Inference Providers gateway.
NEMOTRON_VLM_MODEL = HuggingFaceHubModel(
    asset_id="nemotron-vlm-candidate",
    repo_id="nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8",
    revision="e9550fdec09682d12e8c3e41548b2e05b16db7c1",  # pragma: allowlist secret
    task="image-text-to-text",
    serving_mode="self-hosted-openai-compatible",
)
