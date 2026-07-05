#!/usr/bin/env bash
#
# install.sh — 在 macOS (Apple Silicon) 上一键部署 CosyVoice2-0.5B
#
# 覆盖本项目 README 记录的全部踩坑修复：
#   - 用 conda(miniforge) 装难缠的 pynini（pip 装几乎必失败）
#   - 去掉 requirements 里的 CUDA extra-index-url（Mac 无 CUDA）
#   - 修 openai-whisper 的 pkg_resources 报错（setuptools<81 + --no-build-isolation）
#   - 修 pyworld 编译缺 numpy（先手动装 numpy/cython）
#   - 补装 gradio / lightning 主包（--no-build-isolation 会漏）
#
# 用法：  bash install.sh
# 幂等：  已完成的步骤会自动跳过，可反复运行。
set -e

# ---------- 可配置项 ----------
ENV_NAME="cosyvoice"
PY_VER="3.10"
PYNINI_VER="2.1.5"
NUMPY_VER="1.26.4"
GRADIO_VER="5.4.0"
LIGHTNING_VER="2.2.4"
WORKDIR="$(cd "$(dirname "$0")" && pwd)"
COSYVOICE_DIR="$WORKDIR/CosyVoice"
# --------------------------------

echo "=========================================="
echo " CosyVoice2 macOS 一键部署"
echo " 工作目录: $WORKDIR"
echo "=========================================="

# 0. 基础检查
if [[ "$(uname)" != "Darwin" ]]; then
  echo "⚠️  本脚本面向 macOS。其他系统请参考官方仓库。"
fi

# 1. Homebrew
if ! command -v brew >/dev/null 2>&1; then
  echo "❌ 未检测到 Homebrew，请先安装：https://brew.sh"
  exit 1
fi
echo "✅ Homebrew 就绪"

# 2. ffmpeg（音频转码需要）
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo ">>> 安装 ffmpeg ..."
  brew install ffmpeg
fi
echo "✅ ffmpeg 就绪"

# 3. miniforge（提供 conda，用来装 pynini）
if ! command -v conda >/dev/null 2>&1; then
  echo ">>> 安装 miniforge（提供 conda）..."
  brew install --cask miniforge
fi
# 载入 conda
CONDA_BASE="$(conda info --base 2>/dev/null || echo /opt/homebrew/Caskroom/miniforge/base)"
source "$CONDA_BASE/etc/profile.d/conda.sh"
echo "✅ conda 就绪: $CONDA_BASE"

# 4. 创建 python3.10 环境 + pynini（用 conda 装，成功率最高）
if ! conda env list | grep -q "$ENV_NAME"; then
  echo ">>> 创建 conda 环境 $ENV_NAME (python $PY_VER + pynini $PYNINI_VER)..."
  conda create -n "$ENV_NAME" -c conda-forge python="$PY_VER" pynini="$PYNINI_VER" -y
fi
ENV_PY="$CONDA_BASE/envs/$ENV_NAME/bin/python"
ENV_PIP="$CONDA_BASE/envs/$ENV_NAME/bin/pip"
echo "✅ 环境就绪: $($ENV_PY --version)"

# 5. 克隆 CosyVoice 官方源码（含子模块 Matcha-TTS）
if [[ ! -d "$COSYVOICE_DIR" ]]; then
  echo ">>> 克隆 CosyVoice 官方仓库..."
  git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git "$COSYVOICE_DIR"
else
  echo "✅ CosyVoice 源码已存在，跳过克隆"
fi

# 6. 生成 Mac 专用 requirements（去掉 CUDA 源）
cd "$COSYVOICE_DIR"
grep -v -- '--extra-index-url' requirements.txt > requirements.mac.txt
echo "✅ 已生成 requirements.mac.txt（去除 CUDA extra-index-url）"

# 7. 先装兼容层：setuptools<81（带 pkg_resources）+ numpy + cython
echo ">>> 预装构建依赖（修复 whisper / pyworld 编译坑）..."
"$ENV_PIP" install "setuptools<81" wheel "numpy==$NUMPY_VER" cython

# 8. 装项目依赖（--no-build-isolation 复用上面的 setuptools/numpy）
echo ">>> 安装项目依赖（较耗时，torch 等大包）..."
"$ENV_PIP" install --no-build-isolation -r requirements.mac.txt || true

# 9. 补装容易漏的主包 gradio / lightning
echo ">>> 补装 gradio / lightning 主包..."
"$ENV_PIP" install "gradio==$GRADIO_VER" "lightning==$LIGHTNING_VER"

# 10. 下载模型权重（modelscope 国内源，断点续传）
echo ">>> 下载 CosyVoice2-0.5B 模型权重（约 3.4G，支持断点续传）..."
"$ENV_PY" - <<'PYEOF'
from modelscope import snapshot_download
snapshot_download('iic/CosyVoice2-0.5B',
                  local_dir='pretrained_models/CosyVoice2-0.5B')
print('MODEL_DOWNLOAD_DONE')
PYEOF

# 11. 校验关键文件
echo ">>> 校验关键权重文件..."
MISS=0
for f in llm.pt flow.pt hift.pt campplus.onnx speech_tokenizer_v2.onnx \
         cosyvoice2.yaml CosyVoice-BlankEN/model.safetensors CosyVoice-BlankEN/vocab.json; do
  if [[ -f "pretrained_models/CosyVoice2-0.5B/$f" ]]; then
    echo "  ✅ $f"
  else
    echo "  ❌ 缺失 $f —— 请重新运行本脚本（会断点续传补齐）"
    MISS=1
  fi
done

echo "=========================================="
if [[ "$MISS" == "0" ]]; then
  echo "🎉 部署完成！接下来用法："
  echo "  cd CosyVoice"
  echo "  \"$ENV_PY\" ../tts.py --ref 你的参考音频.mp3 --text \"要合成的文字\""
else
  echo "⚠️  有文件缺失，请再次运行： bash install.sh"
fi
echo "=========================================="
