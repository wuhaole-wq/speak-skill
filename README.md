# speak-skill

让 Claude Code 具备语音朗读能力。基于微软 Edge TTS 免费 API + ffplay 管道流式播放。

## 特性

- **低延迟**：首块音频 ~100ms 即开始播放，无需等待完整下载
- **自然流畅**：单次 API 调用保持整段韵律，无句间割裂
- **无临时文件**：音频通过管道直传 ffplay
- **免费**：Edge TTS API 无需 Key，ffmpeg 开源
- **自动回退**：无 ffplay 时回退 MCI 播放

## 快速安装

```bash
pip install edge-tts
winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
cp ./tts_all.py ~/.claude/tts_all.py
# 然后将 SKILL.md 中的 hooks 配置合并到 ~/.claude/settings.local.json
```

## 项目结构

- `SKILL.md` — Skill 定义和安装文档
- `tts_all.py` — TTS 核心脚本（edge_tts → ffplay 管道流式播放）
