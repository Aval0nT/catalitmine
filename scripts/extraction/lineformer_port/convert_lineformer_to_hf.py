"""convert_lineformer_to_hf.py — port the LineFormer mmdet checkpoint to HF transformers.

LineFormer (Lin et al., ICDAR 2023) is stock Mask2Former (Swin-T backbone,
1 thing class 'line', 100 queries, 9 decoder layers) trained in
MMDetection 2.28. This script maps every tensor of the mmdet checkpoint
onto `Mask2FormerForUniversalSegmentation` so inference needs only
`transformers` — no mmcv/mmdet (dead on py>=3.12).

Non-trivial transforms (everything else is renaming):
  1. Swin attention: mmdet stores fused qkv; HF stores separate q/k/v
     → chunk(3) along dim 0.
  2. PatchMerging: mmdet (mmcv) gathers the 2x2 patch window via nn.Unfold
     → channel-major layout c*4 + (kh*2+kw); HF concatenates the four
     spatial groups → group-major layout g*C + c with groups ordered
     [(0,0), (1,0), (0,1), (1,1)]. The columns of downsample.reduction.weight
     and the elements of downsample.norm.{weight,bias} must be permuted.
     (This inverts mmdet's own `swin_converter.correct_unfold_*` which was
     applied at training time because the config sets convert_weights=True.)
  3. Decoder self-attn: mmdet nn.MultiheadAttention fused in_proj
     → HF separate q_proj/k_proj/v_proj. (Cross-attn stays fused:
     HF also uses nn.MultiheadAttention there.)

Self-checks: every mmdet key consumed exactly once; every HF parameter
assigned exactly once; shapes equal tensor-by-tensor; the checkpoint's
relative_position_index buffers must equal HF's freshly initialized ones
(proves the window-attention indexing conventions agree).

Run:  venv/bin/python scripts/extraction/lineformer_port/convert_lineformer_to_hf.py
Out:  models/lineformer_hf/  (config + safetensors + image-processor config)
"""
from __future__ import annotations

from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[3]
CKPT = ROOT / "models" / "lineformer_mmdet" / "iter_3000.pth"
OUT = ROOT / "models" / "lineformer_hf"

BASE = "facebook/mask2former-swin-tiny-coco-instance"  # architecture donor (config only)
DEPTHS = (2, 2, 6, 2)


def unfold_to_group_perm(four_c: int) -> torch.Tensor:
    """Index permutation taking mmdet/unfold channel order -> HF group order.

    hf_index j = g*C + c  with spatial groups g: [(0,0), (1,0), (0,1), (1,1)]
    mm_index   = c*4 + (kh*2 + kw)
    returns perm with hf_tensor[..., j] = mm_tensor[..., perm[j]].
    """
    c_dim = four_c // 4
    kh = torch.tensor([0, 1, 0, 1])
    kw = torch.tensor([0, 0, 1, 1])
    g = torch.arange(4).repeat_interleave(c_dim)  # group of each hf index
    c = torch.arange(c_dim).repeat(4)             # channel of each hf index
    return c * 4 + kh[g] * 2 + kw[g]


def build_mapping() -> dict[str, str]:
    """mmdet key -> HF key for all pure renames (no tensor transform)."""
    m: dict[str, str] = {}
    enc = "model.pixel_level_module.encoder"
    dec = "model.pixel_level_module.decoder"
    tm = "model.transformer_module"

    # --- Swin backbone ---
    m["backbone.patch_embed.projection.weight"] = f"{enc}.embeddings.patch_embeddings.projection.weight"
    m["backbone.patch_embed.projection.bias"] = f"{enc}.embeddings.patch_embeddings.projection.bias"
    m["backbone.patch_embed.norm.weight"] = f"{enc}.embeddings.norm.weight"
    m["backbone.patch_embed.norm.bias"] = f"{enc}.embeddings.norm.bias"
    for i, depth in enumerate(DEPTHS):
        for j in range(depth):
            src = f"backbone.stages.{i}.blocks.{j}"
            dst = f"{enc}.encoder.layers.{i}.blocks.{j}"
            for s in ("weight", "bias"):
                m[f"{src}.norm1.{s}"] = f"{dst}.layernorm_before.{s}"
                m[f"{src}.norm2.{s}"] = f"{dst}.layernorm_after.{s}"
                m[f"{src}.attn.w_msa.proj.{s}"] = f"{dst}.attention.output.dense.{s}"
                m[f"{src}.ffn.layers.0.0.{s}"] = f"{dst}.intermediate.dense.{s}"
                m[f"{src}.ffn.layers.1.{s}"] = f"{dst}.output.dense.{s}"
            m[f"{src}.attn.w_msa.relative_position_bias_table"] = (
                f"{dst}.attention.self.relative_position_bias_table"
            )
            m[f"{src}.attn.w_msa.relative_position_index"] = (
                f"{dst}.attention.self.relative_position_index"
            )
        # out-norm per stage (mmdet: backbone.norm{i} for out_indices 0..3)
        for s in ("weight", "bias"):
            m[f"backbone.norm{i}.{s}"] = f"{enc}.hidden_states_norms.stage{i + 1}.{s}"

    # --- pixel decoder (MSDeformAttn) ---
    for i in range(3):  # input projections, built high-stride -> low on both sides
        m[f"panoptic_head.pixel_decoder.input_convs.{i}.conv.weight"] = f"{dec}.input_projections.{i}.0.weight"
        m[f"panoptic_head.pixel_decoder.input_convs.{i}.conv.bias"] = f"{dec}.input_projections.{i}.0.bias"
        m[f"panoptic_head.pixel_decoder.input_convs.{i}.gn.weight"] = f"{dec}.input_projections.{i}.1.weight"
        m[f"panoptic_head.pixel_decoder.input_convs.{i}.gn.bias"] = f"{dec}.input_projections.{i}.1.bias"
    for i in range(6):  # deformable encoder layers
        src = f"panoptic_head.pixel_decoder.encoder.layers.{i}"
        dst = f"{dec}.encoder.layers.{i}"
        for part in ("sampling_offsets", "attention_weights", "value_proj", "output_proj"):
            for s in ("weight", "bias"):
                m[f"{src}.attentions.0.{part}.{s}"] = f"{dst}.self_attn.{part}.{s}"
        for s in ("weight", "bias"):
            m[f"{src}.norms.0.{s}"] = f"{dst}.self_attn_layer_norm.{s}"
            m[f"{src}.norms.1.{s}"] = f"{dst}.final_layer_norm.{s}"
            m[f"{src}.ffns.0.layers.0.0.{s}"] = f"{dst}.fc1.{s}"
            m[f"{src}.ffns.0.layers.1.{s}"] = f"{dst}.fc2.{s}"
    m["panoptic_head.pixel_decoder.level_encoding.weight"] = f"{dec}.level_embed"
    m["panoptic_head.pixel_decoder.lateral_convs.0.conv.weight"] = f"{dec}.adapter_1.0.weight"
    m["panoptic_head.pixel_decoder.lateral_convs.0.gn.weight"] = f"{dec}.adapter_1.1.weight"
    m["panoptic_head.pixel_decoder.lateral_convs.0.gn.bias"] = f"{dec}.adapter_1.1.bias"
    m["panoptic_head.pixel_decoder.output_convs.0.conv.weight"] = f"{dec}.layer_1.0.weight"
    m["panoptic_head.pixel_decoder.output_convs.0.gn.weight"] = f"{dec}.layer_1.1.weight"
    m["panoptic_head.pixel_decoder.output_convs.0.gn.bias"] = f"{dec}.layer_1.1.bias"
    m["panoptic_head.pixel_decoder.mask_feature.weight"] = f"{dec}.mask_projection.weight"
    m["panoptic_head.pixel_decoder.mask_feature.bias"] = f"{dec}.mask_projection.bias"

    # --- transformer decoder ---
    m["panoptic_head.query_embed.weight"] = f"{tm}.queries_embedder.weight"
    m["panoptic_head.query_feat.weight"] = f"{tm}.queries_features.weight"
    m["panoptic_head.level_embed.weight"] = f"{tm}.level_embed.weight"
    for i in range(9):
        src = f"panoptic_head.transformer_decoder.layers.{i}"
        dst = f"{tm}.decoder.layers.{i}"
        # operation_order = (cross_attn, norm, self_attn, norm, ffn, norm)
        # -> attentions.0 = cross (stays fused MHA on HF side too)
        m[f"{src}.attentions.0.attn.in_proj_weight"] = f"{dst}.cross_attn.in_proj_weight"
        m[f"{src}.attentions.0.attn.in_proj_bias"] = f"{dst}.cross_attn.in_proj_bias"
        for s in ("weight", "bias"):
            m[f"{src}.attentions.0.attn.out_proj.{s}"] = f"{dst}.cross_attn.out_proj.{s}"
            m[f"{src}.attentions.1.attn.out_proj.{s}"] = f"{dst}.self_attn.out_proj.{s}"
            m[f"{src}.norms.0.{s}"] = f"{dst}.cross_attn_layer_norm.{s}"
            m[f"{src}.norms.1.{s}"] = f"{dst}.self_attn_layer_norm.{s}"
            m[f"{src}.norms.2.{s}"] = f"{dst}.final_layer_norm.{s}"
            m[f"{src}.ffns.0.layers.0.0.{s}"] = f"{dst}.fc1.{s}"
            m[f"{src}.ffns.0.layers.1.{s}"] = f"{dst}.fc2.{s}"
    m["panoptic_head.transformer_decoder.post_norm.weight"] = f"{tm}.decoder.layernorm.weight"
    m["panoptic_head.transformer_decoder.post_norm.bias"] = f"{tm}.decoder.layernorm.bias"
    m["panoptic_head.cls_embed.weight"] = "class_predictor.weight"
    m["panoptic_head.cls_embed.bias"] = "class_predictor.bias"
    for k, j in zip((0, 2, 4), (0, 1, 2)):  # nn.Sequential(L,ReLU,L,ReLU,L) -> blocks
        for s in ("weight", "bias"):
            m[f"panoptic_head.mask_embed.{k}.{s}"] = (
                f"{tm}.decoder.mask_predictor.mask_embedder.{j}.0.{s}"
            )
    return m


def convert() -> None:
    from transformers import Mask2FormerConfig, Mask2FormerForUniversalSegmentation

    ckpt = torch.load(CKPT, map_location="cpu", weights_only=False)
    mm = dict(ckpt["state_dict"])
    print(f"mmdet checkpoint: {len(mm)} tensors (meta: iter {ckpt.get('meta', {}).get('iter')})")

    cfg = Mask2FormerConfig.from_pretrained(BASE)
    cfg.num_labels = 1
    cfg.id2label = {0: "line"}
    cfg.label2id = {"line": 0}
    model = Mask2FormerForUniversalSegmentation(cfg)
    model.eval()
    hf_ref = model.state_dict()

    hf_new: dict[str, torch.Tensor] = {}

    def assign(dst: str, t: torch.Tensor, src: str) -> None:
        assert dst in hf_ref, f"{src} -> {dst}: no such HF key"
        assert dst not in hf_new, f"{dst} assigned twice"
        assert hf_ref[dst].shape == t.shape, (
            f"{src} -> {dst}: shape {tuple(t.shape)} != {tuple(hf_ref[dst].shape)}"
        )
        hf_new[dst] = t.to(hf_ref[dst].dtype)

    consumed: set[str] = set()
    mapping = build_mapping()
    for src, dst in mapping.items():
        assert src in mm, f"mapping source missing in checkpoint: {src}"
        assign(dst, mm[src], src)
        consumed.add(src)

    enc = "model.pixel_level_module.encoder"
    tm = "model.transformer_module"

    # 1. Swin fused qkv -> separate q/k/v
    for i, depth in enumerate(DEPTHS):
        for j in range(depth):
            src = f"backbone.stages.{i}.blocks.{j}.attn.w_msa.qkv"
            dst = f"{enc}.encoder.layers.{i}.blocks.{j}.attention.self"
            for s in ("weight", "bias"):
                q, k, v = mm[f"{src}.{s}"].chunk(3, dim=0)
                assign(f"{dst}.query.{s}", q, f"{src}.{s}")
                assign(f"{dst}.key.{s}", k, f"{src}.{s}")
                assign(f"{dst}.value.{s}", v, f"{src}.{s}")
                consumed.add(f"{src}.{s}")

    # 2. PatchMerging unfold->group channel permutation (stages 0..2 have downsample)
    for i in range(3):
        src = f"backbone.stages.{i}.downsample"
        dst = f"{enc}.encoder.layers.{i}.downsample"
        perm = unfold_to_group_perm(mm[f"{src}.norm.weight"].numel())
        assign(f"{dst}.reduction.weight", mm[f"{src}.reduction.weight"][:, perm], f"{src}.reduction.weight")
        assign(f"{dst}.norm.weight", mm[f"{src}.norm.weight"][perm], f"{src}.norm.weight")
        assign(f"{dst}.norm.bias", mm[f"{src}.norm.bias"][perm], f"{src}.norm.bias")
        consumed |= {f"{src}.reduction.weight", f"{src}.norm.weight", f"{src}.norm.bias"}

    # 3. decoder self-attn fused in_proj -> q/k/v projections
    for i in range(9):
        src = f"panoptic_head.transformer_decoder.layers.{i}.attentions.1.attn"
        dst = f"{tm}.decoder.layers.{i}.self_attn"
        for s, hf_s in (("in_proj_weight", "weight"), ("in_proj_bias", "bias")):
            q, k, v = mm[f"{src}.{s}"].chunk(3, dim=0)
            assign(f"{dst}.q_proj.{hf_s}", q, f"{src}.{s}")
            assign(f"{dst}.k_proj.{hf_s}", k, f"{src}.{s}")
            assign(f"{dst}.v_proj.{hf_s}", v, f"{src}.{s}")
            consumed.add(f"{src}.{s}")

    # --- exhaustiveness ---
    leftover_mm = sorted(set(mm) - consumed)
    assert not leftover_mm, f"unconsumed mmdet keys: {leftover_mm}"
    unassigned = sorted(set(hf_ref) - set(hf_new))
    # criterion.empty_weight is a loss-time buffer; HF builds it from config
    # (no_object_weight=0.1 == mmdet class_weight[-1]) — inference-irrelevant.
    allowed = {"criterion.empty_weight"}
    bad = [k for k in unassigned if k not in allowed]
    assert not bad, f"unassigned HF keys: {bad}"
    print(f"mapped {len(hf_new)} tensors; unassigned (whitelisted): {unassigned}")

    # sanity: ckpt's relative_position_index buffers == HF's fresh ones
    for k, v in hf_new.items():
        if k.endswith("relative_position_index"):
            assert torch.equal(v.long(), hf_ref[k].long()), f"window indexing mismatch at {k}"
    print("relative_position_index buffers identical — window conventions agree")

    missing, unexpected = model.load_state_dict(hf_new, strict=False)
    assert not unexpected, unexpected
    assert set(missing) == allowed, missing

    OUT.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUT)

    # processor config for casual HF-API use; NB its PIL-based resize rounds
    # differently from mmcv's cv2 path — the parity/production path uses
    # preprocess_mmdet() from lineformer_hf_infer.py instead.
    from transformers import Mask2FormerImageProcessor

    proc = Mask2FormerImageProcessor(
        do_resize=True,
        size={"shortest_edge": 512, "longest_edge": 512},
        do_normalize=True,
        image_mean=[123.675 / 255, 116.28 / 255, 103.53 / 255],
        image_std=[58.395 / 255, 57.12 / 255, 57.375 / 255],
        ignore_index=255,
    )
    proc.save_pretrained(OUT)
    print(f"saved HF model + processor -> {OUT}")


if __name__ == "__main__":
    convert()
