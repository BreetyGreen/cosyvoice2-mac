# mac-cosyvoice2-quickstart

> 在 **macOS（Apple Silicon）** 上零基础部署 **CosyVoice2-0.5B**，用一段参考音频克隆音色，给任意文字配音。

这是一份「踩完所有坑之后」整理出来的极简部署方案。CosyVoice 官方主要面向 Linux + NVIDIA GPU，在 Mac 上直接按官方步骤走会连续报错。本项目把在 **Apple M4 Pro / 48G / macOS** 上实测跑通的流程固化成一个脚本 + 一个命令行工具，让你 clone 下来就能复现。

- ✅ 纯本地运行，免费、离线、不依赖剪映或任何云服务
- ✅ 零样本（zero-shot）克隆：丢一段 3~10 秒参考音频，当场就能用那个音色念任意文本，**无需训练**
- ✅ Apple 芯片 Metal(MPS) 加速
- ✅ 一键安装脚本，自动绕过 Mac 上的全部依赖坑

> ⚠️ 本仓库**不含**模型权重和 CosyVoice 官方源码（分别约 3.4G 和几十 M），它们由安装脚本自动拉取。仓库里只有部署脚本、封装工具和教程。

---

## 一、适用环境

| 项 | 要求 |
|---|---|
| 系统 | macOS（推荐 Apple Silicon：M1/M2/M3/M4 系列） |
| 内存 | 建议 ≥ 16G（实测 48G 很宽裕） |
| 磁盘 | 预留 ≥ 8G（模型 3.4G + 依赖 + 缓存） |
| 前置 | 已安装 [Homebrew](https://brew.sh) |

> Intel Mac 理论上能跑但会很慢，不推荐。

---

## 二、一键安装

```bash
git clone https://github.com/BreetyGreen/cosyvoice2-mac.git
cd cosyvoice2-mac
bash install.sh
```

脚本会自动完成：

1. 装 `ffmpeg`、`miniforge`（提供 conda）
2. 建独立 conda 环境 `cosyvoice`（Python 3.10 + pynini），**不污染系统 Python**
3. 克隆 CosyVoice 官方源码（含子模块 Matcha-TTS）
4. 生成 Mac 专用依赖清单并安装（已绕过 CUDA 源等坑）
5. 从 ModelScope 国内源下载 `CosyVoice2-0.5B` 权重（约 3.4G，支持断点续传）
6. 校验关键权重文件是否齐全

> 脚本是**幂等**的：中途网络断了或某步失败，直接 `bash install.sh` 再跑一次，已完成的会自动跳过、缺的会断点续传补齐。

---

## 三、生成第一条配音

安装完成后：

```bash
# 进入官方仓库目录（模型和源码都在这）
cd CosyVoice

# 用你的参考音频，自动识别参考文字，合成目标文本
CONDA_BASE=$(conda info --base)
"$CONDA_BASE/envs/cosyvoice/bin/python" ../tts.py \
    --ref ~/Desktop/manbo.mp3 \
    --text "家人们注意了，今天这条干货直接收藏，看完记得三连，我们下期见！" \
    --out ../result.wav
```

参数说明：

| 参数 | 说明 |
|---|---|
| `--ref` | 参考音频（想模仿谁的声线就给谁一段干净人声，wav/mp3 均可，别带背景音乐） |
| `--text` | 要合成的目标文字 |
| `--prompt-text` | （可选）参考音频里说的那句话。不给则自动用 whisper 识别；手动给会更快 |
| `--out` | 输出 wav 路径，默认 `output.wav` |

### 更快：手动给参考文字，跳过 whisper

```bash
"$CONDA_BASE/envs/cosyvoice/bin/python" ../tts.py \
    --ref ref.wav \
    --prompt-text "参考音频里实际说的那句话" \
    --text "要合成的目标文字" \
    --out ../result.wav
```

### 想要网页界面

CosyVoice 官方自带 WebUI（拖音频、输文字、点按钮）：

```bash
cd CosyVoice
"$CONDA_BASE/envs/cosyvoice/bin/python" webui.py --port 8000 \
    --model_dir pretrained_models/CosyVoice2-0.5B
# 浏览器打开 http://localhost:8000
```

---

## 四、踩坑记录（Mac 部署为什么会失败）

这一节是本项目的核心价值。以下每个坑 `install.sh` 都已自动处理，列出来供你理解原理、或手动排障时参考。

| # | 现象 | 根因 | 解法 |
|---|---|---|---|
| 1 | `pynini` pip 安装编译失败 | 需要编译 C++ 的 OpenFst | 用 **conda**（conda-forge）装，别用 pip |
| 2 | `requirements.txt` 拖慢/报错 | 首行有 `--extra-index-url ...cu121`（CUDA 源） | Mac 无 CUDA，删掉该行 → `requirements.mac.txt` |
| 3 | `openai-whisper` 报 `No module named 'pkg_resources'` | 新版 setuptools(≥81) 移除了 pkg_resources | 装 `setuptools<81` + `--no-build-isolation` |
| 4 | `pyworld` 编译报 `No module named 'numpy'` | `--no-build-isolation` 不再自动准备构建依赖 | 先手动装 `numpy==1.26.4` 和 `cython` |
| 5 | `import gradio` / `import lightning` 失败 | 上一步只装了附属包，主包被漏掉 | 单独 `pip install gradio==5.4.0 lightning==2.2.4` |
| 6 | 推理时报缺 `model.safetensors` / `speech_tokenizer_v2.onnx` | 模型下载被网络中断，大文件没下全 | 重跑下载即可断点续传补齐 |

**版本锚点**（实测可用组合）：Python 3.10.20 · pynini 2.1.5 · torch 2.3.1（MPS 可用）· numpy 1.26.4 · gradio 5.4.0 · lightning 2.2.4。

---

## 五、常见问题

**Q：第一次合成很慢？**
首次要加载 llm/flow/hift 三个模型 + Qwen 底座进内存，约 1~2 分钟；之后每条几秒到十几秒。

**Q：想变速（1.2 倍速那种）？**
CosyVoice 生成的是 1 倍速原声，变速在剪辑软件里对音频轨调「变速」即可。

**Q：合成的音色不够像？**
换一段更干净、更长（10 秒左右）、无背景音乐的参考音频；并确保 `--prompt-text` 和参考音频内容一致。

---

## 六、⚠️ 合规与法律提醒

语音克隆技术强大，但「能做」不等于「能用」：

- ✅ 克隆**你自己的声音**做数字分身
- ✅ 克隆**已明确获得授权**的配音员声音
- ✅ 使用模型自带的默认音色
- ⛔ **不要**克隆影视角色、特定艺人的声线拿去商用——涉及声音权、肖像权、IP 授权，法律风险很高

请在合法合规的前提下使用本项目。

---

## 七、致谢

- [CosyVoice](https://github.com/FunAudioLLM/CosyVoice) by FunAudioLLM / 阿里通义实验室（Apache-2.0）
- 模型权重来自 [ModelScope: iic/CosyVoice2-0.5B](https://www.modelscope.cn/models/iic/CosyVoice2-0.5B)

本项目仅为部署脚本与教程，模型与源码版权归原作者所有。
