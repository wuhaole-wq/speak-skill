---
name: speak-skill
description: 当用户想让 Claude 在 Windows 上朗读回复，或安装/配置语音输出时使用。触发词：安装语音、添加语音、TTS 设置、语音输出、让 AI 说话。
---

# 语音朗读 Skill

给 Claude Code 添加文字转语音功能，每次 AI 回复后自动朗读。通过 **edge_tts → ffplay 管道流式播放**，首块音频到达后约 100ms 即开始播放，单次 API 调用保持自然韵律，无句间割裂。

## 环境要求

- Windows 10 或更高版本
- Python 3.8+（带 `pip`）
- FFmpeg（提供 ffplay 流式播放）
- 网络连接（调用微软 Edge TTS 免费 API）

## 安装步骤

### 1. 安装依赖

```bash
pip install edge-tts
winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
```

### 2. 复制 tts_all.py 脚本

```bash
cp ./tts_all.py ~/.claude/tts_all.py
```

### 3. 配置 Stop 钩子

在 `~/.claude/settings.local.json` 中添加：

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "tee \"$HOME/.claude/tts-debug.json\" | python -c \"import sys,json; d=json.load(sys.stdin); print(d.get('last_assistant_message',''))\" 2>/dev/null > \"$HOME/.claude/tts-response.txt\" && if [ -s \"$HOME/.claude/tts-response.txt\" ]; then python \"$HOME/.claude/tts_all.py\"; fi",
            "async": true,
            "timeout": 60
          }
        ]
      }
    ]
  }
}
```

已有 `settings.local.json` 则合并 `hooks` 部分。

### 4. 重启 Claude Code

钩子在下个回复后生效。

## 语音选择

默认语音 `zh-CN-XiaoxiaoNeural`（中文女声）。可选语音：

| 语言 | 推荐语音 |
|------|----------|
| 中文女声 | `zh-CN-XiaoxiaoNeural`（温暖）、`zh-CN-XiaoyiNeural`（活泼） |
| 中文男声 | `zh-CN-YunxiNeural`（阳光）、`zh-CN-YunyangNeural`（专业） |
| 英文女声 | `en-US-AvaNeural`、`en-US-JennyNeural` |
| 英文男声 | `en-US-AndrewNeural`、`en-US-BrianNeural` |

在钩子中设置 `TTS_VOICE` 环境变量，或直接改 `tts_all.py`。

## 自定义配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TTS_VOICE` | `zh-CN-XiaoxiaoNeural` | Edge TTS 语音名称 |
| `TTS_RATE` | `+8%` | 语速 |
| `TTS_PITCH` | `+0Hz` | 音调 |
| `FFPLAY_PATH` | 自动查找 | ffplay.exe 路径 |

## 工作原理

```
edge_tts API（单次调用，保持自然韵律）
   ↓ MP3 音频块流式产出
stdin 管道
   ↓ 实时传输，首块 ~100ms 开始播放
ffplay（解码 + 播放，无临时文件）
```

1. **Stop 钩子触发** — 每次 AI 回复完成后自动执行
2. **提取文字** — 从 Stop 事件 JSON 提取 `last_assistant_message`
3. **清理格式** — 去除 markdown（粗体、代码、链接等）和 emoji
4. **流式生成** — 调用微软 Edge TTS 免费 API，无需 API Key
5. **管道直传** — 音频块通过 stdin 管道直传 ffplay，边下边播
6. **自动回退** — 找不到 ffplay 时回退到 MCI 播放（完整下载后播放）

## 常见问题

| 问题 | 解决方法 |
|------|----------|
| 没有声音 | 手动运行 `python ~/.claude/tts_all.py` 查看报错 |
| ffplay 找不到 | 运行 `winget install Gyan.FFmpeg` 或设置 `FFPLAY_PATH` 环境变量 |
| 声音延迟大 | 检查是否回退到了 MCI 模式（ffplay 未安装），安装 ffmpeg 即可 |
| 声音不流畅 | 确认 ffplay 可用：`ffplay -version` |
| edge-tts 未找到 | `pip install edge-tts` |
| 多个声音重叠 | 脚本内置锁机制，等待 8 秒；若持续重叠，重启 Claude Code |
