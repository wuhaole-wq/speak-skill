"""TTS 语音生成：通过 Edge TTS 生成 MP3，调用 Win32 MCI 播放。

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
import edge_tts

HOME = os.path.expanduser("~")
TEXT_FILE = os.environ.get("TTS_TEXT_FILE", os.path.join(HOME, ".claude", "tts-response.txt"))
VOICE = os.environ.get("TTS_VOICE", "zh-CN-XiaoxiaoNeural")
RATE = os.environ.get("TTS_RATE", "+8%")
PITCH = os.environ.get("TTS_PITCH", "+0Hz")
TEMP = os.environ.get("TEMP", os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "Temp"))
LOCK_FILE = os.path.join(TEMP, "tts-lock.txt")  # 锁文件，防止多个语音同时播放

# emoji 表情符号正则，用于过滤掉朗读时不需要的表情字符
_EMOJI_RE = re.compile(
    '[\U0001F600-\U0001F64F'   # 表情符号
    '\U0001F300-\U0001F5FF'    # 杂项符号和象形文字
    '\U0001F680-\U0001F6FF'    # 交通和地图符号
    '\U0001F1E0-\U0001F1FF'    # 国旗
    '\U0001F900-\U0001F9FF'    # 补充符号
    '\U0001FA00-\U0001FA6F'    # 象棋符号
    '\U0001FA70-\U0001FAFF'    # 扩展符号
    '\U00002702-\U000027B0'    # 印刷装饰符号
    '\U00002600-\U000026FF'    # 杂项符号
    '\U0000200D'               # 零宽连接符
    '\U0000FE0F'               # 变体选择符
    '\U000020E3'               # 组合封闭按键符
    ']+')

def strip_markdown(text: str) -> str:
    """清理 markdown 格式标记和 emoji，返回纯文本。"""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)       # **粗体**
    text = re.sub(r'\*(.+?)\*', r'\1', text)           # *斜体*
    text = re.sub(r'__(.+?)__', r'\1', text)           # __下划线粗体__
    text = re.sub(r'~~(.+?)~~', r'\1', text)           # ~~删除线~~
    text = re.sub(r'`(.+?)`', r'\1', text)             # `代码`
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)    # [链接文字](url)
    text = re.sub(r'(?m)^#{1,6}\s+', '', text)         # ### 标题
    text = re.sub(r'(?m)^>\s+', '', text)              # > 引用
    text = re.sub(r'(?m)^[\*\-\+]\s+', '', text)       # * - + 列表标记
    text = re.sub(r'(?m)^\d+\.\s+', '', text)          # 1. 有序列表
    text = text.replace('|', ' ')                      # | 表格分隔符
    text = re.sub(r'---+', '', text)                   # --- 水平线
    text = _EMOJI_RE.sub('', text)                     # 去除 emoji
    text = re.sub(r'  +', ' ', text)                   # 合并多余空格
    return text.strip()

def play_mp3(path: str):
    """通过 Win32 MCI 播放 MP3 文件（无窗口、无额外依赖）。"""
    path = os.path.abspath(path).replace("'", "''")
    ctypes.windll.winmm.mciSendStringW(f'open "{path}" type mpegvideo alias tts', None, 0, 0)
    ctypes.windll.winmm.mciSendStringW('play tts wait', None, 0, 0)
    ctypes.windll.winmm.mciSendStringW('close tts', None, 0, 0)

async def main():
    """主流程：获取锁 → 读取文本 → 清理格式 → 生成 MP3 → 播放 → 清理。"""
    # 等待上一个播放完成（最多等 30 秒）
    waited = 0
    while os.path.exists(LOCK_FILE) and waited < 30:
        await asyncio.sleep(0.3)
        waited += 0.3
    # 创建锁
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

        # 用进程 ID 作文件名，避免多实例冲突
        mp3 = os.path.join(TEMP, f"tts-{os.getpid()}.mp3")
        communicate = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH)
        with open(mp3, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])

        play_mp3(mp3)
        os.remove(mp3)
    finally:
        # 释放锁（无论成功或失败都要释放）
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)

if __name__ == "__main__":
    asyncio.run(main())
