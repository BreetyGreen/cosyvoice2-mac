# AGENTS.md — 给 AI 助手 / 接手者的项目交接说明

> 这份文件是给**任何接手本项目的人或 AI 助手**看的（Claude Code / Cursor / WorkBuddy 等）。
> 换一台设备 clone 下来后，先读这份文件，就能明白项目的来龙去脉、当前进度、已有决策，从而**无缝续作**，不用从零重新理解。
>
> 面向用户的使用说明在 [README.md](README.md)（中）/ [README.en.md](README.en.md)（英）。本文件聚焦「为什么这么做」和「接下来做什么」。

---

## 1. 这个项目是什么

在 **macOS（Apple Silicon）** 上零基础部署 **CosyVoice2-0.5B**（阿里 FunAudioLLM 的开源零样本 TTS 音色克隆模型），用一段参考音频克隆音色，给任意文字配音。

- **动机**：起点是"想免费/私有化使用剪映那种热门配音音色"。结论是剪映音色是闭源商业资产、拿不到；开源世界里唯一可行的路是**自己用一段干净音频做零样本克隆**（详见第 4 节的关键结论）。
- **痛点**：CosyVoice 官方主要面向 Linux + NVIDIA GPU，Mac 上按官方步骤走会连环报错。本项目把在 **M4 Pro / 48G / macOS** 上实测跑通的流程固化为脚本 + 命令行工具 + 踩坑文档。
- **仓库不含大文件**：模型权重（约 3.4G）和 CosyVoice 官方源码由 `install.sh` 自动拉取，`.gitignore` 已排除 `*.pt/*.onnx/*.safetensors/*.wav/*.mp3` 及 `CosyVoice/`、`pretrained_models/`。

---

## 2. 当前状态（截至最近一次提交）

### ✅ 已完成（项目主体功能已就绪，可用）

| 模块 | 文件 | 状态 |
|---|---|---|
| 一键安装脚本（幂等、断点续传） | `install.sh` | ✅ 实测跑通 |
| 命令行合成工具 | `tts.py` | ✅ 三种模式全通 |
| 中文文档 | `README.md` | ✅ |
| 英文文档 | `README.en.md` | ✅ |
| 项目封面 banner | `assets/banner.png` + `banner.html` | ✅ |
| 许可证 | `LICENSE`（MIT） | ✅ |

`tts.py` 已支持的能力：
1. **zero-shot 模式**（默认）：参考音频 + 参考文字。参考文字可 `--prompt-text` 手动给，或 whisper 自动识别。
2. **cross-lingual 模式**（`--no-prompt-text`）：只喂参考音频，跳过 whisper，避免听写错误导致音色跑偏。
3. **参考音频自动清洗管线**（默认开启）：高通去低频噪 → FFT 降噪(afftdn) → 响度归一化(loudnorm) → 切静音(silenceremove) → 16k 单声道；开关 `--no-clean` / `--no-denoise` / `--clip-seconds N`。

### 🔲 待办 / 后续可做（按优先级）

1. **【需用户提供素材，最高价值】用一段干净参考音频验证克隆相似度。**
   目前测试一直用 `manbo.mp3`，该素材本身太脏（中英混杂 + 背景音 + 重复念白 + 疑似多段拼接），是"音色不够像"的**根本原因**（不是代码问题）。
   → 下一步等用户提供**单人、无背景音乐、吐字清楚、纯中文、5~10 秒**的音频，重新克隆对比。**这一步只有用户能提供素材，AI 无法代劳。**
2. 可选：把克隆好的音色存成 `spk2info.pt`，实现"存一次、以后点名复用"（对应 `inference_sft` 预训练音色模式）。当前 0.5B 官方版**不带**音色库，`list_available_spks()` 返回空。
3. 可选：加个简单的批量合成脚本（一个文本文件多行 → 批量出多条 wav）。
4. 可选：examples 目录放一对"参考音频 + 合成结果"的授权示例，方便他人上手（注意版权，`.gitignore` 默认排除音频）。

---

## 3. 如何在新设备上续作（接手步骤）

```bash
# 1. clone 本仓库
git clone https://github.com/BreetyGreen/cosyvoice2-mac.git
cd cosyvoice2-mac

# 2. 一键安装（装 ffmpeg/miniforge、建 conda 环境、拉官方源码、下模型）
bash install.sh

# 3. 跑一条验证（把参考音频换成你自己的）
cd CosyVoice
CONDA_BASE=$(conda info --base)
"$CONDA_BASE/envs/cosyvoice/bin/python" ../tts.py \
    --ref ~/Desktop/你的参考音频.mp3 \
    --text "要合成的目标文字" \
    --no-prompt-text --clip-seconds 8 \
    --out ../result.wav
```

**AI 助手接手时的建议动作：**
- 先读本文件 + 两个 README，理解已做决策，**不要推翻已有架构从零重来**。
- 环境是否装好，用 `conda env list | grep cosyvoice` 判断；模型是否下全，检查 `CosyVoice/pretrained_models/CosyVoice2-0.5B/` 下有无 `flow.pt / hift.pt / llm.pt / CosyVoice-BlankEN/model.safetensors / speech_tokenizer_v2.onnx`。
- 若用户抱怨"不像"，**先怀疑参考音频质量**（第 4 节），而不是去调脚本/换模型——历史上在这里绕了很多弯路。

---

## 4. 关键技术决策与结论（避免接手者重走弯路）

1. **克隆"像不像"约 70% 由参考音频质量决定**，脚本/参数只占一小半。理想参考音频：单人、无背景音乐、吐字清楚、纯一种语言、5~10 秒、情绪平稳。**脏音频用什么模式、什么参数都救不回来。**

2. **whisper 是可选的辅助"听写员"，不是生成的一部分。** zero-shot 需要"音频↔文字"配对，whisper 用来自动生成这个文字。它一旦听错（small 会听错、medium 遇到复读音频会陷入循环），音色就崩。因此对脏音频**优先用 cross-lingual 模式**绕开它。

3. **CosyVoice2 的内核是一个 LLM**（底座为 Qwen2.5-0.5B，见 `CosyVoice-BlankEN/model.safetensors`）。它把语音离散成 token，用自回归"预测下一个语音 token"的方式生成，参考音频被编码成 token 当作 prompt 前缀。声码器（Flow Matching + HiFi-GAN）负责把 token 还原成波形。

4. **剪映的猴哥/熊二/皇上等音色拿不到**：闭源商业资产 + 配音演员版权，只能在剪映内用。开源世界不存在这些文件。别在这条路上浪费时间。

5. **RVC ≠ CosyVoice2，模型不通用。** RVC 是"变声"（改造一段已有声音的音色），不会自己说话；CosyVoice2 是 TTS（文字→语音）。weights.gg 等社区下的 RVC `.pth` 塞不进 CosyVoice2。若真想用社区海量音色，只能 TTS+RVC 两级串联（多一套环境、多一道工序）。

---

## 5. 环境事实（开发者本机，供参考，新设备会不同）

> 以下是原开发机的绝对路径，**新设备上不要照抄**，用 `conda info --base` 等命令动态获取。

- 开发机：Apple M4 Pro / 48G / macOS
- conda 环境名：`cosyvoice`（Python 3.10）
- **版本锚点（实测可用组合）**：Python 3.10.20 · pynini 2.1.5 · torch 2.3.1（MPS 可用）· numpy 1.26.4 · gradio 5.4.0 · lightning 2.2.4
- 官方源码与模型位于安装后自动生成的 `CosyVoice/` 子目录内

### Mac 部署六大坑（install.sh 均已自动处理）

| # | 现象 | 根因 | 解法 |
|---|---|---|---|
| 1 | `pynini` pip 编译失败 | 需编译 C++ 的 OpenFst | 用 conda-forge 装，别用 pip |
| 2 | `requirements.txt` 报错/慢 | 首行 `--extra-index-url ...cu121`（CUDA 源） | Mac 无 CUDA，删该行 |
| 3 | whisper 报 `No module named 'pkg_resources'` | setuptools≥81 移除了它 | 装 `setuptools<81` + `--no-build-isolation` |
| 4 | `pyworld` 编译报缺 numpy | `--no-build-isolation` 不自动备构建依赖 | 先装 `numpy==1.26.4` + `cython` |
| 5 | `import gradio`/`lightning` 失败 | 上一步只装了附属包，主包被漏 | 单独装 `gradio==5.4.0 lightning==2.2.4` |
| 6 | 推理缺 `model.safetensors`/`speech_tokenizer_v2.onnx` | 模型下载被网络中断 | 重跑下载，断点续传补齐 |

**另一个已修 bug**：`tts.py` 独立于 CosyVoice 仓库运行时曾报 `ModuleNotFoundError: No module named 'cosyvoice'`。根因是 `os.chdir` 只改工作目录、不改 Python 的 import 搜索路径，需把仓库根目录 `sys.path.insert(0, ...)` 进去（已修）。

---

## 6. 目录结构速览

```
cosyvoice2-mac/
├── AGENTS.md          # 本文件：项目交接说明
├── README.md          # 中文使用文档
├── README.en.md       # 英文使用文档
├── LICENSE            # MIT
├── install.sh         # 一键安装（幂等、断点续传）
├── tts.py             # 命令行合成工具（三种模式 + 清洗管线）
├── .gitignore         # 排除模型/音频/官方源码等大文件
├── assets/            # banner.png + banner.html（封面）
├── examples/          # 示例占位（音频默认被 gitignore）
└── CosyVoice/         # ← install.sh 自动生成，不入库（含模型权重）
```
