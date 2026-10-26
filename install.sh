#!/usr/bin/env bash
# 安装孔明到本机的技能目录。
#   ./install.sh            安装到 ~/.claude/skills（Claude Code）
#   ./install.sh --all      同时安装到 ~/.agents/skills 与 ~/.codex/skills（如目录存在）
#   ./install.sh --link     用软链接代替复制，便于 git pull 后自动更新
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/skills/kongming"
MODE=copy
TARGETS=("$HOME/.claude/skills")
for arg in "$@"; do
  case "$arg" in
    --link) MODE=link ;;
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
echo "完成。在对话里说「孔明，……」或输入 /kongming 即可使用。"
