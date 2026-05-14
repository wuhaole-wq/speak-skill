"""TTS 语音生成：edge_tts 单次调用 → ffplay 文件播放。

单次 API 调用保持整段自然韵律，完整下载后 ffplay 播放确保不丢开头：
- 自然流畅，无句间割裂
- 短文本 ~1s 开始播放，长文本 ~2-4s
- ffplay 不可用时自动回退 MCI

环境变量：
  TTS_TEXT_FILE - 要朗读的文本文件路径（默认：~/.claude/tts-response.txt）
  TTS_VOICE     - Edge TTS 语音名称（默认：zh-CN-XiaoxiaoNeural）
  TTS_RATE      - 语速（默认：+8%）
  TTS_PITCH     - 音调（默认：+0Hz）
"""
import re
import sys
import os
import ctypes
import asyncio
import subprocess
import edge_tts

HOME = os.path.expanduser("~")
TEXT_FILE = os.environ.get("TTS_TEXT_FILE", os.path.join(HOME, ".claude", "tts-response.txt"))
VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
RATE = os.environ.get("TTS_RATE", "+8%")
PITCH = os.environ.get("TTS_PITCH", "+0Hz")
TEMP = os.environ.get("TEMP", os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "Temp"))
LOCK_FILE = os.path.join(TEMP, "tts-lock.txt")

# 按优先级查找 ffplay：环境变量、winget 安装目录、PATH
_FFPLAY_PATHS = [
    os.environ.get("FFPLAY_PATH", ""),
    os.path.join(os.environ.get("LOCALAPPDATA", ""),
                 "Microsoft", "WinGet", "Packages",
                 "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe",
                 "ffmpeg-8.1.1-full_build", "bin", "ffplay.exe"),
]

_EMOJI_RE = re.compile(
    '[\U0001F600-\U0001F64F'
    '\U0001F300-\U0001F5FF'
    '\U0001F680-\U0001F6FF'
    '\U0001F1E0-\U0001F1FF'
    '\U0001F900-\U0001F9FF'
    '\U0001FA00-\U0001FA6F'
    '\U0001FA70-\U0001FAFF'
    '\U00002702-\U000027B0'
    '\U00002600-\U000026FF'
    '\U0000200D'
    '\U0000FE0F'
    '\U000020E3'
    ']+')


def _find_ffplay():
    """查找 ffplay.exe 的路径。"""
    for p in _FFPLAY_PATHS:
        if p and os.path.isfile(p):
            return p
    # 尝试 PATH
    import shutil
    found = shutil.which("ffplay")
    if found:
        return found
    return None


def strip_markdown(text: str) -> str:
    """清理 markdown 格式标记和 emoji，返回纯文本。"""
    # 配对标记 → 先处理包含嵌套的情况（**_text_** 外层**内层_）
    # 重复两轮确保嵌套标记完全剥离
    for _ in range(2):
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        text = re.sub(r'~~(.+?)~~', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        # _斜体_ 需保护 snake_case：仅当 _ 不在 ASCII 字母数字之间时视为标记
        text = re.sub(r'(?<![a-zA-Z0-9])_(.+?)_(?![a-zA-Z0-9])', r'\1', text)
        text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
    # 裸 URL（http/https）→ 移除，避免 TTS 读出"斜杠斜杠"
    text = re.sub(r'https?://\S+', '', text)
    # 行级标记 → 整行移除标记
    text = re.sub(r'(?m)^#{1,6}\s+', '', text)
    text = re.sub(r'(?m)^>\s+', '', text)
    text = re.sub(r'(?m)^[\*\-\+]\s+', '', text)
    text = re.sub(r'(?m)^\d+\.\s+', '', text)
    # 表格
    text = text.replace('|', ' ')
    text = re.sub(r'---+', '', text)
    # 表情
    text = _EMOJI_RE.sub('', text)
    # 残留的未配对标记：
    # * 和 ~ 直接清除（中文文本中无合法用途）
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'~+', '', text)
    # _ 仅在 ASCII 字母数字边界外清除（保护 snake_case）
    text = re.sub(r'(?<![a-zA-Z0-9])_+(?![a-zA-Z0-9])', '', text)
    # 反斜杠转义符
    text = text.replace('\\', '')
    # 合并多余空格和空行
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _play_mci_blocking(path: str):
    """MCI 阻塞播放（ffplay 不可用时的回退方案）。"""
    path = os.path.abspath(path).replace("'", "''")
    ctypes.windll.winmm.mciSendStringW(f'open "{path}" type mpegvideo alias tts', None, 0, 0)
    ctypes.windll.winmm.mciSendStringW('play tts wait', None, 0, 0)
    ctypes.windll.winmm.mciSendStringW('close tts', None, 0, 0)


def _wrap_ssml(text: str) -> str:
    """包裹为 SSML，开头 80ms 静音防止播放器启动时吞首音节。"""
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-CN">'
        f'<voice name="{VOICE}">'
        f'<prosody rate="{RATE}" pitch="{PITCH}">'
        '<break time="80ms"/>'
        f'{text}'
        '</prosody>'
        '</voice>'
        '</speak>'
    )


async def _play_ffplay(text: str, ffplay_path: str):
    """SSML 包裹 → edge_tts 生成 MP3 → ffplay 文件播放。"""
    mp3 = os.path.join(TEMP, f"tts-{os.getpid()}.mp3")
    try:
        ssml = _wrap_ssml(text)
        communicate = edge_tts.Communicate(ssml, VOICE, rate=RATE, pitch=PITCH)
        with open(mp3, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
        # ffplay 播放完整文件，不会丢开头
        proc = subprocess.Popen(
            [ffplay_path, '-nodisp', '-autoexit', '-loglevel', 'quiet', mp3],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        proc.wait(timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    finally:
        if os.path.exists(mp3):
            os.remove(mp3)


async def _fallback_mci(text: str):
    """回退方案：SSML 包裹 → 下载完整 MP3 → MCI 播放。"""
    mp3 = os.path.join(TEMP, f"tts-{os.getpid()}.mp3")
    try:
        ssml = _wrap_ssml(text)
        communicate = edge_tts.Communicate(ssml, VOICE, rate=RATE, pitch=PITCH)
        with open(mp3, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
        _play_mci_blocking(mp3)
    finally:
        if os.path.exists(mp3):
            os.remove(mp3)


async def main():
    """主流程：获取锁 → 读取文本 → 清理格式 → 流式播放。"""
    # 等待上一个播放完成（最多等 8 秒）
    waited = 0
    while os.path.exists(LOCK_FILE) and waited < 8:
        await asyncio.sleep(0.2)
        waited += 0.2
    with open(LOCK_FILE, "w") as f:
        f.write("locked")

    try:
        if not os.path.exists(TEXT_FILE):
            sys.exit(1)
        with open(TEXT_FILE, "r", encoding="utf-8") as f:
            text = f.read()
        text = strip_markdown(text)
        if not text:
            sys.exit(1)

        ffplay_path = _find_ffplay()
        if ffplay_path:
            await _play_ffplay(text, ffplay_path)
        else:
            await _fallback_mci(text)
    finally:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)


if __name__ == "__main__":
    asyncio.run(main())
