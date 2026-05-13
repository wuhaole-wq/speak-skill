---
name: speak-skill
description: 当用户想让 Claude 在 Windows 上朗读回复，或安装/配置语音输出时使用。触发词：安装语音、添加语音、TTS 设置、语音输出、让 AI 说话。
---

# 语音朗读 Skill

给 Claude Code 添加文字转语音功能，每次 AI 回复后自动朗读，适配 Windows 平台。

## 环境要求

- Windows 10 或更高版本
- Python 3.8+（带 `pip`）
- 网络连接（调用微软 Edge TTS 免费 API）

## 安装步骤

### 1. 安装 edge-tts 包

```bash
pip install edge-tts
```

### 2. 复制 tts_all.py 脚本

将 `tts_all.py` 复制到 `~/.claude/tts_all.py`：

```bash
cp ./tts_all.py ~/.claude/tts_all.py
```

### 3. 配置 Stop 钩子

在 `~/.claude/settings.local.json` 中添加以下配置：

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

如果已有 `settings.local.json`，只需将 `hooks` 部分合并进去。

### 4. 重启 Claude Code

钩子在下次会话（或下次回复）生效。

## 语音选择

默认语音为 `zh-CN-XiaoxiaoNeural`（中文女声）。可选语音：

| 语言 | 推荐语音 |
|------|----------|
| 中文女声 | `zh-CN-XiaoxiaoNeural`（温暖）、`zh-CN-XiaoyiNeural`（活泼） |
| 中文男声 | `zh-CN-YunxiNeural`（阳光）、`zh-CN-YunyangNeural`（专业） |
| 英文女声 | `en-US-AvaNeural`、`en-US-JennyNeural` |
| 英文男声 | `en-US-AndrewNeural`、`en-US-BrianNeural` |

在钩子命令中设置 `TTS_VOICE` 环境变量，或直接修改 `tts_all.py`。

## 自定义配置

可在钩子命令中设置以下环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TTS_VOICE` | `zh-CN-XiaoxiaoNeural` | Edge TTS 语音名称 |
| `TTS_RATE` | `+8%` | 语速（`+20%` = 更快） |
| `TTS_PITCH` | `+0Hz` | 音调调整 |

## 工作原理

1. **Stop 钩子触发** — 每次 AI 回复完成后自动执行
2. **提取文字** — 从 Stop 事件的 JSON 中提取 `last_assistant_message` 字段
3. **清理格式** — 自动去除 markdown（`**粗体**`、`` `代码` ``、`[链接]` 等）和 emoji 表情
4. **生成语音** — 调用微软 Edge TTS 免费 API 生成 MP3（无需 API Key）
5. **播放音频** — 通过 Win32 MCI 直接播放（无弹窗、无需额外依赖）

## 常见问题

| 问题 | 解决方法 |
|------|----------|
| 没有声音 | 手动运行 `python ~/.claude/tts_all.py` 查看报错 |
| 声音机械 | Edge TTS 神经语音已非常自然，用 `python -m edge_tts --list-voices` 确认语音名称 |
| 权限错误 | 检查 `~/.claude/tts-response.txt` 是否可写入 |
| edge-tts 未找到 | 运行 `pip install edge-tts` 安装 |
| 多个声音重叠 | 检查是否多个 Stop 钩子同时触发，重启 Claude Code 试试 |
