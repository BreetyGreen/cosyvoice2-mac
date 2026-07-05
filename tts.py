#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tts.py — CosyVoice2 零样本(zero-shot)音色克隆命令行工具

功能：
  给一段参考音频 + 要合成的文字，用参考音色念出来。
  参考音频对应的文字(prompt text)可手动给，也可用 whisper 自动识别。

放置位置：
  把本文件放在 CosyVoice 官方仓库根目录下运行（脚本会自动处理路径）。
  或从任意位置运行，用 --cosyvoice-dir 指定 CosyVoice 仓库路径。

用法示例：
  # 最简：自动识别参考音频文字
  python tts.py --ref ~/Desktop/manbo.mp3 --text "家人们注意了，这条干货记得收藏！"

  # 手动指定参考文字（更快，跳过 whisper）
  python tts.py --ref ref.wav --prompt-text "参考音频里说的那句话" \
                --text "要合成的目标文字" --out result.wav
"""
import argparse
import os
import subprocess
import sys


def find_cosyvoice_dir(user_dir: str) -> str:
    """定位 CosyVoice 官方仓库根目录。"""
    candidates = []
    if user_dir:
        candidates.append(user_dir)
    # 当前目录、脚本同级的 CosyVoice 子目录
    here = os.path.dirname(os.path.abspath(__file__))
    candidates += [os.getcwd(), here, os.path.join(here, "CosyVoice")]
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "cosyvoice", "cli", "cosyvoice.py")):
            return os.path.abspath(c)
    sys.exit(
        "❌ 未找到 CosyVoice 仓库。请在 CosyVoice 目录下运行，"
        "或用 --cosyvoice-dir 指定路径。"
    )


def to_16k_mono(src: str, dst: str) -> str:
    """用 ffmpeg 把参考音频转成 16k 单声道 wav（最稳定的输入格式）。"""
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", dst],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return dst


def transcribe(wav: str, lang: str = "zh") -> str:
    """用 whisper 自动识别参考音频里说的文字。"""
    import whisper

    print(">>> 用 whisper 识别参考音频文字（首次会下载模型）...")
    model = whisper.load_model("small")
    result = model.transcribe(wav, language=lang, fp16=False)
    text = result["text"].strip()
    print(f">>> 识别到参考文字：{text}")
    return text


def main():
    ap = argparse.ArgumentParser(
        description="CosyVoice2 零样本音色克隆配音工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--ref", required=True, help="参考音频路径（wav/mp3 等）")
    ap.add_argument("--text", required=True, help="要合成的目标文字")
    ap.add_argument("--prompt-text", default=None,
                    help="参考音频对应的文字；不给则用 whisper 自动识别")
    ap.add_argument("--out", default="output.wav", help="输出 wav 路径")
    ap.add_argument("--model-dir", default="pretrained_models/CosyVoice2-0.5B",
                    help="模型权重目录（相对 CosyVoice 仓库）")
    ap.add_argument("--cosyvoice-dir", default=None, help="CosyVoice 仓库根目录")
    ap.add_argument("--lang", default="zh", help="whisper 识别语言，默认 zh")
    args = ap.parse_args()

    # 定位并切换到 CosyVoice 仓库，把子模块加进 path
    cv_dir = find_cosyvoice_dir(args.cosyvoice_dir)
    os.chdir(cv_dir)
    sys.path.append(os.path.join(cv_dir, "third_party", "Matcha-TTS"))
    print(f">>> CosyVoice 仓库：{cv_dir}")

    ref = os.path.abspath(os.path.expanduser(args.ref))
    if not os.path.isfile(ref):
        sys.exit(f"❌ 参考音频不存在：{ref}")

    # 参考音频转 16k 单声道
    prompt_wav = os.path.join(cv_dir, "_ref_16k.wav")
    print(">>> 转换参考音频为 16k 单声道 ...")
    to_16k_mono(ref, prompt_wav)

    # 参考文字：手动 or whisper
    prompt_text = args.prompt_text or transcribe(prompt_wav, args.lang)

    # 加载模型并合成
    import torch  # noqa: F401
    import torchaudio
    from cosyvoice.cli.cosyvoice import CosyVoice2

    print(">>> 加载 CosyVoice2 模型（首次较慢）...")
    # Mac：fp32 + 关闭 jit/trt，兼容 MPS/CPU
    cosyvoice = CosyVoice2(args.model_dir, load_jit=False, load_trt=False, fp16=False)

    print(">>> 开始合成 ...")
    out_abs = os.path.abspath(os.path.expanduser(args.out))
    for i, j in enumerate(cosyvoice.inference_zero_shot(
            args.text, prompt_text, prompt_wav, stream=False)):
        target = out_abs if i == 0 else f"{out_abs}.{i}.wav"
        torchaudio.save(target, j["tts_speech"], cosyvoice.sample_rate)
        print(f"✅ 已保存：{target}")

    print("🎉 完成！")


if __name__ == "__main__":
    main()
