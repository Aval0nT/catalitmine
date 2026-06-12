"""lineformer_hf_infer.py — mmdet-equivalent inference for the HF-ported LineFormer.

Replicates, in plain torch/cv2, exactly what `mmdet.apis.inference_detector`
did around the network in the Modal probe (LineFormer test pipeline, mmdet
2.28 Mask2Former instance branch):

  preprocess   keep-ratio resize so the long edge fits 512 (mmcv.imrescale:
               scale = min(512/long, 512/short), new = int(dim*scale + 0.5),
               cv2 bilinear), BGR->RGB, ImageNet normalize. No padding —
               the test pipeline has no Pad step; Swin pads internally.
  postprocess  upsample mask logits to network input size, then to the
               original size (both bilinear, align_corners=False);
               score = softmax(cls)[:, line] * mean(sigmoid(mask logits)
               inside the mask>0 region); keep score > score_thr (the probe
               ran infer.do_instance with score_thr=0.3).

Returns boolean instance masks at original resolution + scores — the exact
input contract of LineFormer's line_utils keypoint extraction (Phase 3).

Instance ORDER is not part of the parity contract: upstream selects queries
via topk(..., sorted=False) whose order is implementation-defined (the Modal
goldens came from a CUDA kernel). We emit a deterministic order instead —
descending classification score, which is what upstream's CPU path happens
to produce. Consumers must not attach identity to position.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

MEAN = np.array([123.675, 116.28, 103.53], dtype=np.float32)
STD = np.array([58.395, 57.12, 57.375], dtype=np.float32)


def load_model(model_dir: str | Path, device: str = "cpu"):
    from transformers import Mask2FormerForUniversalSegmentation

    model = Mask2FormerForUniversalSegmentation.from_pretrained(model_dir)
    model.eval().to(device)
    return model


def preprocess_mmdet(img_bgr: np.ndarray, long_edge: int = 512) -> torch.Tensor:
    """mmcv.imrescale + Normalize(to_rgb) + HWC->CHW, as the test pipeline did."""
    h, w = img_bgr.shape[:2]
    scale = min(long_edge / max(h, w), long_edge / min(h, w))
    new_w, new_h = int(w * scale + 0.5), int(h * scale + 0.5)
    resized = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
    rgb = (rgb - MEAN) / STD
    return torch.from_numpy(rgb.transpose(2, 0, 1))[None]


@torch.no_grad()
def get_instance_masks(
    model,
    img_bgr: np.ndarray,
    score_thr: float = 0.3,
    device: str = "cpu",
) -> tuple[np.ndarray, np.ndarray]:
    """-> (masks: bool (N, H0, W0) at original resolution, scores: float (N,))."""
    h0, w0 = img_bgr.shape[:2]
    pixel_values = preprocess_mmdet(img_bgr).to(device)
    out = model(pixel_values=pixel_values)
    cls_logits = out.class_queries_logits[0].cpu()  # (100, num_labels+1)
    mask_logits = out.masks_queries_logits[0].cpu()  # (100, H'/4, W'/4)

    # mmdet: logits -> batch_input_shape -> crop img_shape (no-op, no pad) -> ori_shape
    in_h, in_w = pixel_values.shape[-2:]
    mask_logits = F.interpolate(
        mask_logits[None], size=(in_h, in_w), mode="bilinear", align_corners=False
    )
    mask_logits = F.interpolate(
        mask_logits, size=(h0, w0), mode="bilinear", align_corners=False
    )[0]

    assert cls_logits.shape[-1] == 2, "port assumes the single 'line' class"
    cls_scores = F.softmax(cls_logits, dim=-1)[:, :-1].flatten()
    binary = mask_logits > 0
    denom = binary.flatten(1).sum(1).float() + 1e-6
    mask_scores = (mask_logits.sigmoid() * binary).flatten(1).sum(1) / denom
    det_scores = cls_scores * mask_scores

    kept = torch.nonzero(det_scores > score_thr).flatten()
    kept = kept[torch.argsort(cls_scores[kept], descending=True, stable=True)]
    return binary[kept].numpy(), det_scores[kept].numpy()
