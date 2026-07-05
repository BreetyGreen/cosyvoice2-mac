#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tts.py — CosyVoice2 音色克隆命令行工具

支持两种克隆模式：

  1) zero-shot（默认）：参考音频 + 参考文字(prompt text) 一起喂给模型。
     参考文字可手动给(--prompt-text)，也可用 whisper 自动识别。
     音频干净、能准确听写时效果最好。

  2) cross-lingual（--no-prompt-text）：只喂参考音频，不需要参考文字。
     纯从音频里抽音色，彻底跳过 whisper，避免"听写错误导致音色崩"。
     拿到一段音频就想直接克隆、懒得校对文字时用这个。

放置位置：
  把本文件放在 CosyVoice 官方仓库根目录下运行（脚本会自动处理路径）。
  或从任意位置运行，用 --cosyvoice-dir 指定 CosyVoice 仓库路径。

用法示例：
  # zero-shot：自动识别参考音频文字
  python tts.py --ref ~/Desktop/manbo.mp3 --text "家人们注意了，这条干货记得收藏！"

  # zero-shot：手动指定参考文字（更快，跳过 whisper）
  python tts.py --ref ref.wav --prompt-text "参考音频里说的那句话" \
                --text "要合成的目标文字" --out result.wav

  # 免 prompt 文本（推荐音频有杂音/中英混杂/懒得校对时用）
  python tts.py --ref ~/Desktop/manbo.mp3 --text "要合成的目标文字" \
                --no-prompt-text --out result.wav

音频清洗（默认开启，决定克隆"像不像"的最关键一步）：
  参考音频进来会先自动清洗：高通去低频噪 → FFT 降噪 → 响度归一化 →
  切掉首尾静音和过长停顿 → 重采样 16k。脏音频（背景音/忽大忽小）能明显改善。

  # 只取清洗后最干净的前 8 秒作参考（参考音频 5~10 秒最佳）
  python tts.py --ref ~/Desktop/manbo.mp3 --text "要合成的文字" \
                --no-prompt-text --clip-seconds 8 --out result.wav

  # 人声本来很干净、不想被降噪弄闷：关掉降噪
  python tts.py --ref clean.wav --text "..." --no-denoise

  # 完全关闭清洗，用原始音频（对照实验用）
  python tts.py --ref ref.wav --text "..." --no-clean
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


def _run_ffmpeg(args: list):
    """跑一条 ffmpeg 命令，失败时抛出带 stderr 的异常方便定位。"""
    proc = subprocess.run(
        ["ffmpeg", "-y", *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "ffmpeg 执行失败：\n" + proc.stderr.decode("utf-8", "ignore")[-800:]
        )


def _probe_duration(path: str) -> float:
    """返回音频时长（秒）。ffprobe 不可用时返回 0。"""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        ).stdout.decode().strip()
        return float(out)
    except Exception:
        return 0.0


def to_16k_mono(src: str, dst: str) -> str:
    """最基础转换：16k 单声道 wav（不做任何清洗，供 --no-clean 使用）。"""
    _run_ffmpeg(["-i", src, "-ar", "16000", "-ac", "1", dst])
    return dst


def preprocess_audio(src: str, dst: str, clip_seconds: float = 0.0,
                     denoise: bool = True) -> str:
    """参考音频清洗管线 —— 决定克隆"像不像"的最关键一步（约 70% 权重）。

    依次做：
      1) 转单声道                     多声道/立体声会干扰音色提取
      2) highpass=80Hz               滤掉低频轰鸣/空调/电流底噪
      3) afftdn (FFT 降噪)           压制稳态背景噪声          [denoise=True 时]
      4) loudnorm (EBU R128)         响度归一化，音量忽大忽小会让音色不稳
      5) silenceremove               切掉首尾静音和句间过长停顿
      6) 重采样到 16k                CosyVoice 前端最稳的输入采样率

    clip_seconds > 0 时，只保留清洗后的前 N 秒（参考音频 5~10 秒最佳，
    太长反而引入更多变数）。
    """
    # 组装滤镜链：顺序有讲究，先去噪再归一化再切静音
    chain = ["aformat=channel_layouts=mono", "highpass=f=80"]
    if denoise:
        # afftdn: nf=-25 适度降噪，过猛会让人声发闷失真
        chain.append("afftdn=nf=-25")
    chain.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    # 切静音：首尾静音去掉；中间超过 0.8s 的停顿压到 0.5s 以内
    chain.append(
        "silenceremove=start_periods=1:start_silence=0.1:start_threshold=-45dB:"
        "stop_periods=-1:stop_silence=0.5:stop_threshold=-45dB"
    )
    af = ",".join(chain)

    args = ["-i", src, "-af", af, "-ar", "16000", "-ac", "1"]
    if clip_seconds and clip_seconds > 0:
        # 放在输出侧，对清洗后的结果截取前 clip_seconds 秒
        args += ["-t", f"{clip_seconds:.2f}"]
    args.append(dst)
    _run_ffmpeg(args)

    dur = _probe_duration(dst)
    print(f">>> 清洗完成：{os.path.basename(dst)}  时长 {dur:.1f}s "
          f"(降噪={'开' if denoise else '关'}"
          f"{'，截取前 %.0fs' % clip_seconds if clip_seconds else ''})")
    if dur < 2.0:
        print("⚠️  清洗后音频不足 2 秒，可能是静音阈值切太狠或原音频太短，"
              "可加 --no-clean 关闭清洗对比看看。")
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
        description="CosyVoice2 音色克隆配音工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--ref", required=True, help="参考音频路径（wav/mp3 等）")
    ap.add_argument("--text", required=True, help="要合成的目标文字")
    ap.add_argument("--prompt-text", default=None,
                    help="参考音频对应的文字；不给则用 whisper 自动识别（仅 zero-shot 模式）")
    ap.add_argument("--no-prompt-text", action="store_true",
                    help="免参考文字模式：走 cross-lingual，只用音频抽音色，跳过 whisper")
    ap.add_argument("--out", default="output.wav", help="输出 wav 路径")
    ap.add_argument("--no-clean", action="store_true",
                    help="关闭参考音频清洗管线（默认开启：降噪+响度归一化+切静音）")
    ap.add_argument("--no-denoise", action="store_true",
                    help="清洗时不做 FFT 降噪（人声本来很干净、降噪反而发闷时用）")
    ap.add_argument("--clip-seconds", type=float, default=0.0,
                    help="只取清洗后的前 N 秒作参考（5~10 最佳，0=不截取）")
    ap.add_argument("--model-dir", default="pretrained_models/CosyVoice2-0.5B",
                    help="模型权重目录（相对 CosyVoice 仓库）")
    ap.add_argument("--cosyvoice-dir", default=None, help="CosyVoice 仓库根目录")
    ap.add_argument("--lang", default="zh", help="whisper 识别语言，默认 zh")
    args = ap.parse_args()

    # 定位并切换到 CosyVoice 仓库，把仓库根目录和子模块加进 path
    cv_dir = find_cosyvoice_dir(args.cosyvoice_dir)
    os.chdir(cv_dir)
    # 关键：仓库根目录本身要进 sys.path，否则 `import cosyvoice` 找不到包
    # （os.chdir 只改工作目录，不影响 import 搜索路径）
    sys.path.insert(0, cv_dir)
    sys.path.insert(0, os.path.join(cv_dir, "third_party", "Matcha-TTS"))
    print(f">>> CosyVoice 仓库：{cv_dir}")

    ref = os.path.abspath(os.path.expanduser(args.ref))
    if not os.path.isfile(ref):
        sys.exit(f"❌ 参考音频不存在：{ref}")

    # 参考音频预处理：默认走清洗管线（决定像不像的关键），--no-clean 退回基础转换
    prompt_wav = os.path.join(cv_dir, "_ref_16k.wav")
    if args.no_clean:
        print(">>> 转换参考音频为 16k 单声道（未清洗）...")
        to_16k_mono(ref, prompt_wav)
    else:
        print(">>> 清洗参考音频（降噪 + 响度归一化 + 切静音）...")
        preprocess_audio(ref, prompt_wav,
                         clip_seconds=args.clip_seconds,
                         denoise=not args.no_denoise)

    # 参考文字：仅 zero-shot 模式需要（免 prompt 模式直接跳过 whisper）
    prompt_text = None
    if not args.no_prompt_text:
        prompt_text = args.prompt_text or transcribe(prompt_wav, args.lang)

    # 加载模型并合成
    import torch  # noqa: F401
    import torchaudio
    from cosyvoice.cli.cosyvoice import CosyVoice2

    print(">>> 加载 CosyVoice2 模型（首次较慢）...")
    # Mac：fp32 + 关闭 jit/trt，兼容 MPS/CPU
    cosyvoice = CosyVoice2(args.model_dir, load_jit=False, load_trt=False, fp16=False)

    out_abs = os.path.abspath(os.path.expanduser(args.out))
    if args.no_prompt_text:
        print(">>> 开始合成（免 prompt 文本 / cross-lingual 模式）...")
        gen = cosyvoice.inference_cross_lingual(args.text, prompt_wav, stream=False)
    else:
        print(">>> 开始合成（zero-shot 模式）...")
        gen = cosyvoice.inference_zero_shot(
            args.text, prompt_text, prompt_wav, stream=False)

    for i, j in enumerate(gen):
        target = out_abs if i == 0 else f"{out_abs}.{i}.wav"
        torchaudio.save(target, j["tts_speech"], cosyvoice.sample_rate)
        print(f"✅ 已保存：{target}")

    print("🎉 完成！")


if __name__ == "__main__":
    main()
