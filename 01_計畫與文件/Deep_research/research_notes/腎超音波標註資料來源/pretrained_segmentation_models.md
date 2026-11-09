# Pretrained / Foundation Segmentation Models for Kidney (and Cortex/Sinus/Liver/Spleen) in B-mode Ultrasound

Scope note: research done 2026-10-23 with about 15 tool calls. Where a fact was not verified from a primary page in this session, it is placed in Gaps or marked "(unverified)". kidneyus-bench (GitHub, 2026) is a non-peer-reviewed repository, so treat its numbers as preliminary.

## Q1. Candidate models: data, prompts, size, licenses, weights, setup

### Takeaway
For offline, non-commercial use with box prompts on 8 GB VRAM, the most practical choices are **SAM 2.1 (Apache-2.0, small checkpoints)**, **MedSAM / LiteMedSAM (Apache-2.0 code)** and **UltraSam (ultrasound-specific, trained on data that includes a kidney US set, but CC BY-NC-SA 4.0 and an old mmdet/torch 2.0 stack)**. nnU-Net v2 remains the strongest trained baseline. None of the foundation models were shown to separate cortex from sinus, or to segment liver or spleen, in ultrasound without fine-tuning. BiomedParse's ultrasound coverage does not include kidney. SAMUS and USFM training data do not clearly include kidney, and USFM is licensed CC-BY-NC.

### Cited Findings

**SAM 2 / SAM 2.1 (Meta, 2024)**
- Checkpoints, demo code and training code are all Apache 2.0. A third-party `cc_torch` component carries its own licence file. — [facebookresearch/sam2](https://github.com/facebookresearch/sam2)
- SAM 2.1 sizes and speeds (A100, torch 2.5.1): hiera_tiny 38.9M params at 91.2 FPS; small 46M at 84.8 FPS; base_plus 80.8M at 64.1 FPS; large 224.4M at 39.5 FPS. — [sam2 README](https://github.com/facebookresearch/sam2)
- Requires Python ≥3.10 and torch ≥2.5.1. A CUDA toolkit matching the PyTorch build may be needed to compile an optional custom kernel. On Windows the README "strongly recommend[s]" WSL with Ubuntu. — [sam2 README](https://github.com/facebookresearch/sam2)

**MedSAM / LiteMedSAM (Bo Wang lab, U Toronto; Nature Communications 2024)**
- MedSAM was fine-tuned on 1,570,263 image-mask pairs covering 10 imaging modalities. — [arXiv 2304.12306](https://arxiv.org/abs/2304.12306)
- Code is Apache-2.0. The `medsam_vit_b` checkpoint is on Google Drive. LiteMedSAM was released 2024-01-15 on the `LiteMedSAM` branch, with a 3D Slicer plugin, and is described as "10x faster than MedSAM". Training used 20 A100-80GB GPUs. The README gives no inference VRAM figure. Setup uses Python 3.10 and PyTorch 2.0, and the GUI needs PyQt5. — [bowang-lab/MedSAM](https://github.com/bowang-lab/MedSAM)
- MedSAM did not support point prompts in UltraSam's comparison table (box only). — [UltraSam arXiv 2411.16222v2](https://arxiv.org/html/2411.16222v2)

**MedSAM2 (Bo Wang lab, 2025)**
- Code is Apache-2.0. — [bowang-lab/MedSAM2](https://github.com/bowang-lab/MedSAM2)
- The weights page metadata says cc-by-sa-4.0, but its licence text says the weights "can only be used for research and education purposes". **The licence is inconsistent, so treat it as research-only.** — [HF wanglab/MedSAM2](https://huggingface.co/wanglab/MedSAM2)
- Checkpoints: MedSAM2_2411.pt, MedSAM2_US_Heart.pt (heart ultrasound video), MedSAM2_MRI_LiverLesion.pt, MedSAM2_CTLesion.pt and MedSAM2_latest.pt. Built on SAM 2.1. Trained on "455,000+ 3D image-mask pairs and 76,000+ annotated video frames". — [HF wanglab/MedSAM2](https://huggingface.co/wanglab/MedSAM2)
- The paper reports ultrasound training of 19,232 frames (with 56,462 for endoscopy). Dice >95% for kidneys refers to CT-style organs, not ultrasound. — [MedSAM2 arXiv 2504.03600](https://arxiv.org/html/2504.03600v1) (via search snippet)
- Install pins PyTorch 2.5.1 with CUDA 12.4 on Linux. There are no Windows notes. — [bowang-lab/MedSAM2](https://github.com/bowang-lab/MedSAM2)

**SAM-Med2D (OpenGVLab / Shanghai AI Lab, 2023)**
- Code is Apache 2.0, with no separate weights licence stated. Trained on SA-Med2D-20M: about 4.6M images and 19.7M masks across 10 modalities and 31 organs. The ultrasound share is not given. Supports box and 1/3/5-point prompts. Input is 256×256. Weights are on Google Drive and Baidu. — [OpenGVLab/SAM-Med2D](https://github.com/OpenGVLab/SAM-Med2D)

**SAMUS (2023)**
- MIT licence. Trained on US30K: TN3K, DDTI, TG3K (thyroid), BUSI, UDIAT (breast), CAMUS (heart) and HMC-QU (heart). **No kidney data.** A ViT-B SAM initialisation. The README says one 24 GB 3090 Ti is enough. Weights are on Google Drive. — [xianlin7/SAMUS](https://github.com/xianlin7/SAMUS)

**UltraSam (CAMMA, Univ. Strasbourg; arXiv 2411.16222, IJCARS 2025)**
- A SAM-style model initialised from SAM ViT-B, with a 12-layer ViT encoder and a 2-layer decoder. Accepts point and box prompts. Trained on US-43d: 43 open datasets, over 280k masks, 58 structures. US-43d includes **KidneyUS (487 images/masks)**, but kidney is not among the test sets. Results are reported as mAP, not Dice. — [UltraSam arXiv v2](https://arxiv.org/html/2411.16222v2); [CAMMA-public/UltraSam](https://github.com/CAMMA-public/UltraSam)
- The repository LICENSE file is **CC BY-NC-SA 4.0 (NonCommercial, ShareAlike)**. That is fine for academic use, but derived models must be shared under the same terms. — [UltraSam LICENSE](https://raw.githubusercontent.com/CAMMA-public/UltraSam/main/LICENSE)
- The weights file UltraSam.pth is hosted at s3.unistra.fr. The stack is OpenMMLab (mmengine, mmcv 2.1.0, mmdet, mmpretrain) with Python 3.8, PyTorch 2.0.0 and CUDA 11.8. — [CAMMA-public/UltraSam](https://github.com/CAMMA-public/UltraSam)
- Zero-shot point prompts fail on radial probe views (GIST514-DB mAP 9.3). — [UltraSam arXiv v2](https://arxiv.org/html/2411.16222v2)

**USFM (OpenMedLab, ultrasound foundation model)**
- Code is under **CC-BY-NC 4.0**. Pretrained on about 2M ultrasound images from multiple organs, centres and devices. Kidney inclusion is not stated. It is an encoder for fine-tuning (segmentation and classification), not promptable. Weights are on Google Drive. Requires PyTorch 2.4.1 with CUDA 11.8, mmcv 2.2.0 and a modified mmsegmentation fork. — [openmedlab/USFM](https://github.com/openmedlab/USFM)

**BiomedParse (Microsoft; v1 2024, v2 later)**
- Code is Apache-2.0. Weights are "for research and development use only" (HF `microsoft/BiomedParse`; biomedparse_v2.ckpt is about 4.46 GB). Prompted by text, e.g. "liver" or "right kidney". Ultrasound targets are cardiac, thyroid, carotid, jugular vein, brain tumour and calf muscle. **Kidney is listed for CT only.** v2 weights are 3D; dedicated 2D v2 weights are "not yet released". Validated with PyTorch 2.6 and CUDA 12.4. — [microsoft/BiomedParse](https://github.com/microsoft/BiomedParse)

**Other ultrasound-specific work from 2024–2026 (identified only; details not verified)**
- A multi-organ universal ultrasound segmentation model with task prompts and an anatomical prior (Chen et al., IEEE TMI 2025). — [PubMed 39361457](https://pubmed.ncbi.nlm.nih.gov/39361457/)
- Grounding DINO-US-SAM: text-prompted multi-organ ultrasound segmentation with LoRA. — [arXiv 2506.23903](https://arxiv.org/pdf/2506.23903)
- UniUSNet, a promptable universal ultrasound framework. — [arXiv 2406.01154](https://arxiv.org/pdf/2406.01154)
- UltraSAM3, a concept-driven (text) universal ultrasound model. — [arXiv 2607.29200](https://arxiv.org/pdf/2607.29200)
- An open ultrasound foundation model for segmentation and clinical measurement. — [arXiv 2609.19230](https://arxiv.org/pdf/2609.19230)
- MedSAM3, with medical concept prompts. — [arXiv 2511.19046](https://arxiv.org/pdf/2511.19046)
- UltraBench 2, which concludes that ultrasound-specific pretraining still leads on classification, while general-purpose models "have drawn level on segmentation". — [arXiv 2609.28610](https://arxiv.org/abs/2609.28610)

### Inferences
- **Licences (relevant to a non-commercial academic project):** all candidates are usable. The share-alike or research-only terms of UltraSam (CC BY-NC-SA), USFM (CC BY-NC), MedSAM2 weights (research/education) and BiomedParse weights (research) mainly constrain redistributing derived weights. SAM 2.1, SAMUS (MIT), SAM-Med2D code and MedSAM code are permissive.
- **8 GB VRAM:** inference with ViT-B-sized models (SAM, MedSAM, SAM-Med2D, SAMUS, UltraSam) and with SAM 2.1 tiny or small should fit on 8 GB. This is an inference from the model sizes; no repository states an 8 GB figure. Full fine-tuning of a ViT-B on 8 GB will likely need small batches, mixed precision, a frozen encoder or LoRA.
- **Blackwell (sm_120, PyTorch ≥2.7 with CUDA 12.8):** pure-PyTorch repositories (SAM 2 without its optional CUDA extension, MedSAM, LiteMedSAM, SAM-Med2D, SAMUS, nnU-Net v2) should run once the pinned torch is replaced with ≥2.7 cu128. The OpenMMLab stacks (UltraSam with mmcv 2.1, USFM with mmcv 2.2) are the biggest risk: prebuilt mmcv wheels for cu128 or sm_120 are unlikely, so mmcv would have to be compiled from source on Windows. A workaround is to export the UltraSam weights into a plain SAM ViT-B loader, since the architecture is SAM ViT-B.
- **Windows:** SAM 2 recommends WSL. MedSAM2 is Linux-oriented. Plan on WSL2 with Ubuntu as the safest offline setup. It still runs locally, so patient images never leave the machine.

### Gaps
- Exact per-modality ultrasound counts in MedSAM's training data (the Nature Comms page was paywall-redirected). I believe ultrasound is included, but this was not verified here.
- Licence files for SAM v1 (believed to be Apache-2.0), nnU-Net v2 (believed to be Apache-2.0) and TotalSegmentator (believed to be Apache-2.0 code with some restricted-licence weights, CT/MR only) were not fetched in this session.
- Inference VRAM measurements and native-Windows instructions for UltraSam and USFM were not found.
- LoRA or adapter fine-tuning scripts: kidneyus-bench used SAM+LoRA, and Medical SAM Adapter exists ([arXiv 2304.12620](https://arxiv.org/pdf/2304.12620)). Official LoRA support in each repository was not checked.

## Q2. Evidence of performance on kidney ultrasound specifically

### Takeaway
Two kidney-specific comparisons exist. In both, **nnU-Net trained on kidney US matches or beats YOLO-box→MedSAM pipelines**, and nnU-Net generalises best to a new cohort. When MedSAM is given good boxes, it nearly reaches inter-observer agreement on an external cohort. The weak point is the automatic box, not the segmenter.

### Cited Findings
- Luijten et al. 2025 used the Open Kidney US dataset (323 images after QC, 512×512, RTX 3090). Dice, IoU and inference time:

  | Pipeline | Dice | IoU | Inference |
  |---|---|---|---|
  | nnU-Net | 79.4 | 68.2 | 338 ms |
  | Segmenter | 74.7 | 61.8 | 23 ms |
  | YOLOv11 + MedSAM | 68.6 | 55.1 | 335 ms |
  | YOLOv11 + LiteMedSAM | 66.0 | 51.9 | 77 ms |

  On a 20-image in-house set, nnU-Net scored 70.8/64.5 Dice (coronal/transverse) and YOLO+MedSAM scored 50.3/56.3. nnU-Net was the most robust to rib shadowing. — [arXiv 2506.23721](https://arxiv.org/html/2506.23721)
- kidneyus-bench (2026, non-peer-reviewed, preregistered, MIT code): models were trained on the Open Kidney Dataset and tested on the external TRUSTED 3D-US cohort (18,322 slices).

  | Model | OKD test Dice | TRUSTED Dice (YOLO auto box) | TRUSTED Dice (oracle box) |
  |---|---|---|---|
  | MedSAM | 0.960 | 0.442 | 0.884 |
  | SAM+LoRA | 0.956 | 0.440 | 0.872 |
  | SAMUS | 0.903 | 0.418 | 0.762 |
  | nnU-Net v2 | 0.933 | **0.624** (best) | n/a |
  | USFM | 0.862 | 0.471 | n/a |
  | U-Net | 0.676 | 0.289 | n/a |

  Inter-observer Dice was 0.906. — [doge-ac-cn/kidneyus-bench](https://github.com/doge-ac-cn/kidneyus-bench)
- The original Open Kidney US Data Set paper reports a baseline Dice of 0.85 for capsule segmentation. It includes native and transplant kidneys, with fine-grained annotations from two sonographers. Those annotations cover capsule, cortex/medulla/central echo complex regions (the region detail is from memory, not verified here). — [arXiv 2206.06657](https://arxiv.org/abs/2206.06657)
- The Open Kidney Dataset licence is CC BY-NC-SA and requires registration. — [kidneyus-bench README](https://github.com/doge-ac-cn/kidneyus-bench)

### Inferences
- Open Kidney's fine-grained labels (if region labels such as sinus/central echo complex are confirmed) are the most direct public resource for training **cortex vs sinus** separation. Combining them with the 975 in-house outlines is plausible within its NC-SA terms.
- Zero-shot liver or spleen segmentation in ultrasound has no kidney-adjacent evidence. Expect to fine-tune, or to use box prompts on those organs with heavy correction.

### Gaps
- No published zero-shot (no fine-tuning) Dice for SAM 2.1 or UltraSam on kidney US was found.
- No ultrasound results for cortex/sinus or liver/spleen from foundation models were found.

## Q3. Can a box built from two caliper endpoints serve as a prompt? Sensitivity to box quality

### Takeaway
Yes. A box prompt is the strongest mode for SAM-family models, and an accurate box gave about 0.88 Dice even on an external kidney cohort. Performance drops sharply when boxes are poorly placed, and MedSAM is known to be weak with boxes that are too small. Calipers mark the long axis (length) and width, so building a box that encloses both diameters with a 5–10% margin should be close to an "oracle" box.

### Cited Findings
- With oracle boxes, foundation models reached about 0.88 Dice externally. With detector boxes they reached about 0.44. The bottleneck is "box-localization quality, not coverage". Detector self-training cut missed detections from 48.5% to 5.8% and raised Dice to about 0.69. — [kidneyus-bench](https://github.com/doge-ac-cn/kidneyus-bench)
- Box quality degrades SAM's robustness. One abstract notes MedSAM "under reduced bounding box prompts remains suboptimal" and proposes box-perturbation training. — [arXiv 2308.10382](https://arxiv.org/abs/2308.10382v1); [MICCAI 2025 paper 1075](https://papers.miccai.org/miccai-2025/0641-Paper1075.html) (search snippets)
- FNPC-SAM improved SAM's robustness to inaccurate prompts in ultrasound by using multi-box prompt augmentation. — [SPIE FNPC-SAM](https://electronicimaging.spiedigitallibrary.org/conference-proceedings-of-spie/12926/1292602/FNPC-SAM--uncertainty-guided-false-negative-positive-control-for/10.1117/12.3006867.full)
- Boundary discontinuities about halve Dice (0.326 vs 0.688). Edge slices score near zero for all models. — [kidneyus-bench](https://github.com/doge-ac-cn/kidneyus-bench)

### Inferences
- Caliper length endpoints lie on the kidney poles, which define the box's long side. Width endpoints define the short side. Because the long axis is often oblique, use an axis-aligned box enclosing all four points, padded slightly, rather than a tight box. Optionally add the four endpoints as positive point prompts (SAM 2.1, SAM-Med2D and UltraSam accept points; MedSAM does not).
- Images without calipers can get boxes from the 975 old outline masks (mask → box), or from a small detector trained on them.
- Multi-box test-time augmentation (jitter the box and average or vote the masks) is a cheap way to reduce sensitivity, following FNPC-SAM.

### Gaps
- No study quantifying Dice versus box jitter for kidney US specifically was found.

## Q4. Recommended practical pipeline for few labels; feasibility on 8 GB and offline Windows

### Takeaway
Build boxes from calipers or old masks, then use MedSAM or SAM 2.1 (or UltraSam) to propose masks. Correct a subset by hand, train nnU-Net v2 (2D) on the corrected and filtered pseudo-labels, and iterate with uncertainty-based active learning. Published kidney-US evidence favours nnU-Net as the final model and SAM-family models as annotation accelerators.

### Cited Findings
- nnU-Net had the best accuracy and artifact robustness in the kidney US comparison. — [arXiv 2506.23721](https://arxiv.org/html/2506.23721)
- nnU-Net v2 had the best cross-cohort retention (0.669) and the best external Dice (0.624). — [kidneyus-bench](https://github.com/doge-ac-cn/kidneyus-bench)
- MedSAM with an accurate box reached 97.6% of inter-observer agreement externally, supporting its use as a correction-assist tool when a human supplies or validates the box. — [kidneyus-bench](https://github.com/doge-ac-cn/kidneyus-bench)
- LiteMedSAM runs about 10× faster and has a 3D Slicer plugin, which enables an offline click-and-correct annotation UI. — [bowang-lab/MedSAM](https://github.com/bowang-lab/MedSAM)
- An ultrasound self-supervised encoder (USFM, about 2M images) is available for fine-tuning but is non-commercial, and it underperformed MedSAM and nnU-Net on kidney US in kidneyus-bench (0.862 OKD Dice). — [openmedlab/USFM](https://github.com/openmedlab/USFM); [kidneyus-bench](https://github.com/doge-ac-cn/kidneyus-bench)

### Inferences (proposed pipeline)
1. **Whole kidney:** derive a box from calipers or the old masks, then run MedSAM, SAM 2.1-small and UltraSam zero-shot. Pick the best on about 30–50 physician- or student-verified masks. Use the old smooth masks as a sanity filter (low IoU → flag).
2. **Correction:** correct the flagged or low-confidence cases in 3D Slicer (MedSAM/LiteMedSAM plugin) or CVAT running locally.
3. **Train nnU-Net v2 2D** on all accepted masks. nnU-Net 2D on 512-px images typically fits in 8 GB; this is an assumption, not verified here.
4. **Active learning:** rank cases by nnU-Net ensemble disagreement, or by disagreement between nnU-Net and MedSAM, then correct the top-k.
5. **Cortex/sinus and liver/spleen:** expect no zero-shot solution. Annotate a small multi-class set, possibly bootstrapped from Open Kidney's fine-grained labels (non-commercial, share-alike), and train nnU-Net multi-class. Box-prompted SAM can still speed up drawing the sinus (hyperechoic central region) and the liver/spleen.
6. **Optional:** fine-tune MedSAM or SAM with LoRA on the corrected masks for a better proposal model, using batch size 1–2 and AMP on 8 GB.
7. **Offline Windows:** download weights once, then run under WSL2 with Ubuntu and PyTorch ≥2.7 cu128. Avoid the OpenMMLab-based repositories unless mmcv builds for sm_120.

### Gaps
- No measured VRAM or speed on an RTX 5050 or other Blackwell laptop GPU was found for any of these models.
- No published study of active learning or pseudo-label pipelines specifically for kidney US with SAM proposals was found in this session.
- Whether SAM 2's optional CUDA extension compiles on sm_120 under Windows/WSL is unverified.
