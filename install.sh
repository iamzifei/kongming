#!/usr/bin/env bash
# 安装孔明到本机的技能目录。
#   ./install.sh            安装到 ~/.claude/skills（Claude Code）
#   ./install.sh --all      同时安装到 ~/.agents/skills 与 ~/.codex/skills（如目录存在）
#   ./install.sh --link     用软链接代替复制，便于 git pull 后自动更新
#   ./install.sh --bin      安装无痕命令 kongming 到 ~/.local/bin
#   ./install.sh --focus    把 Claude Code 默认视图设为专注视图（只显示一行工具摘要）
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
SRC="$REPO/skills/kongming"
MODE=copy
BIN=0
FOCUS=0
TARGETS=("$HOME/.claude/skills")
for arg in "$@"; do
  case "$arg" in
    --link) MODE=link ;;
    --bin) BIN=1 ;;
    --focus) FOCUS=1 ;;
    --all)
      for d in "$HOME/.agents/skills" "$HOME/.codex/skills"; do
        [ -d "$(dirname "$d")" ] && TARGETS+=("$d")
      done ;;
    *) echo "未知参数：$arg" >&2; exit 1 ;;
  esac
done

for root in "${TARGETS[@]}"; do
  mkdir -p "$root"
  dest="$root/kongming"
  rm -rf "$dest"
  if [ "$MODE" = link ]; then ln -s "$SRC" "$dest"; else cp -R "$SRC" "$dest"; fi
  echo "已安装：$dest"
done

if [ "$BIN" = 1 ]; then
  mkdir -p "$HOME/.local/bin"
  ln -sf "$REPO/bin/kongming" "$HOME/.local/bin/kongming"
  echo "已安装命令：$HOME/.local/bin/kongming（确保该目录在 PATH 中）"
fi

if [ "$FOCUS" = 1 ]; then
  python3 - "$HOME/.claude/settings.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
data = {}
if p.is_file():
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        sys.exit(f"{p} 不是合法 JSON，未修改")
data["viewMode"] = "focus"
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"已设置 viewMode=focus：{p}（再次输入 /focus 可切回）")
PY
fi
echo "完成。在对话里说「孔明，……」或输入 /kongming 即可使用。"
