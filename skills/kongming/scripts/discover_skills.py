#!/usr/bin/env python3
"""发现本机已安装的全部技能，输出候选清单（JSON）供孔明点将。

用法：
  python3 discover_skills.py                     # 列出全部候选
  python3 discover_skills.py --query "写一篇SEO文章" --limit 15
  python3 discover_skills.py --path /some/dir    # 额外扫描目录（可多次）

扫描顺序即优先级：项目目录 > 用户目录 > 插件目录 > 配置/参数中的额外目录。
同名技能只保留优先级最高的一份；内容完全相同的副本只保留一份。
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SELF_NAME, as_text, home, load_config, parse_frontmatter  # noqa: E402

SELF_DIR = Path(__file__).resolve().parent.parent

PROJECT_ROOTS = [".claude/skills", ".agents/skills", ".codex/skills"]
USER_ROOTS = [
    ".claude/skills",
    ".agents/skills",
    ".codex/skills",
    ".gemini/skills",
    ".cursor/skills",
    ".config/opencode/skills",
]
PLUGIN_ROOTS = [".claude/plugins"]
MAX_DEPTH = 8


def iter_skill_files(root: Path, max_depth: int = MAX_DEPTH):
    """在 root 下找 SKILL.md，跳过 .git / node_modules 等目录。"""
    if not root.is_dir():
        return
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv"}
    stack = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        skill = current / "SKILL.md"
        if skill.is_file():
            yield skill
            continue  # 技能目录内部不再向下找
        if depth >= max_depth:
            continue
        try:
            children = sorted(p for p in current.iterdir() if p.is_dir())
        except OSError:
            continue
        for child in reversed(children):
            if child.name not in skip:
                stack.append((child, depth + 1))


def find_plugin(skill_dir: Path) -> str:
    for parent in skill_dir.parents:
        manifest = parent / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            try:
                return json.loads(manifest.read_text(encoding="utf-8")).get("name", "") or parent.name
            except (OSError, ValueError):
                return parent.name
        if parent.name in ("plugins", "skills") and parent.parent.name in (".claude", ".agents"):
            break
    return ""


def is_self(skill_dir: Path, name: str) -> bool:
    try:
        if skill_dir.resolve() == SELF_DIR:
            return True
    except OSError:
        pass
    return name.lower() == SELF_NAME


def load_skill(path: Path, scope: str) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    meta = parse_frontmatter(text)
    skill_dir = path.parent
    name = as_text(meta.get("name")) or skill_dir.name
    description = as_text(meta.get("description"))
    if not description:
        return None
    plugin = find_plugin(skill_dir) if scope == "plugin" else ""
    return {
        "name": name,
        "invoke": f"{plugin}:{name}" if plugin else name,
        "description": description,
        "path": str(path),
        "dir": str(skill_dir),
        "scope": scope,
        "plugin": plugin,
        "user_only": bool(meta.get("disable-model-invocation")),
        "_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "_mtime": path.stat().st_mtime,
    }


def collect(extra_paths: list[str], cwd: Path) -> list[dict]:
    roots: list[tuple[Path, str]] = []
    roots += [(cwd / r, "project") for r in PROJECT_ROOTS]
    roots += [(home() / r, "user") for r in USER_ROOTS]
    roots += [(home() / r, "plugin") for r in PLUGIN_ROOTS]
    roots += [(Path(p).expanduser(), "extra") for p in extra_paths]

    found: list[dict] = []
    seen_paths: set[Path] = set()
    for root, scope in roots:
        for path in iter_skill_files(root):
            try:
                real = path.resolve()
            except OSError:
                continue
            if real in seen_paths:
                continue
            seen_paths.add(real)
            skill = load_skill(path, scope)
            if skill:
                found.append(skill)
    return found


def dedupe(skills: list[dict]) -> list[dict]:
    """同一 invoke 名保留第一份（优先级最高）；插件缓存里的多个版本保留最新。"""
    by_key: dict[str, dict] = {}
    order: list[str] = []
    for s in skills:
        key = s["invoke"].lower()
        if key not in by_key:
            by_key[key] = s
            order.append(key)
        elif s["scope"] == "plugin" and by_key[key]["scope"] == "plugin" and s["_mtime"] > by_key[key]["_mtime"]:
            by_key[key] = s
    result, hashes = [], set()
    for key in order:
        s = by_key[key]
        if s["_hash"] in hashes:
            continue
        hashes.add(s["_hash"])
        result.append(s)
    return result


def excluded(skill: dict, patterns: list[str]) -> bool:
    return any(
        fnmatch.fnmatch(skill["name"].lower(), p.lower()) or fnmatch.fnmatch(skill["invoke"].lower(), p.lower())
        for p in patterns
    )


_CJK = re.compile(r"[一-鿿]+")
_WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    text = text.lower()
    out = [w for w in _WORD.findall(text) if len(w) > 1]
    for run in _CJK.findall(text):
        out += [run[i : i + 2] for i in range(len(run) - 1)] or [run]
    return out


def rank(skills: list[dict], query: str) -> list[dict]:
    q = set(tokens(query))
    if not q:
        return skills
    docs = [(set(tokens(s["name"].replace("-", " "))), set(tokens(s["description"]))) for s in skills]
    n = len(skills)
    df: dict[str, int] = {}
    for name_t, desc_t in docs:
        for t in name_t | desc_t:
            df[t] = df.get(t, 0) + 1
    for s, (name_t, desc_t) in zip(skills, docs):
        score = 0.0
        for t in q:
            idf = math.log(1 + n / (1 + df.get(t, 0)))
            if t in name_t:
                score += 3 * idf
            if t in desc_t:
                score += idf
        s["score"] = round(score, 3)
    return sorted(skills, key=lambda s: s["score"], reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--query", default="", help="用户需求原文，用于粗排（最终由模型判断）")
    parser.add_argument("--limit", type=int, default=0, help="最多返回几项，0 为全部")
    parser.add_argument("--path", action="append", default=[], help="额外扫描的目录")
    parser.add_argument("--max-desc", type=int, default=400, help="description 截断长度，0 为不截断")
    parser.add_argument("--include-user-only", action="store_true", help="包含标记为仅限用户调用的技能")
    args = parser.parse_args()

    config = load_config()
    skills = collect(list(config.get("extra_paths") or []) + args.path, Path.cwd())
    skills = [
        s
        for s in dedupe(skills)
        if not is_self(Path(s["dir"]), s["name"])
        and not excluded(s, list(config.get("exclude") or []))
        and (args.include_user_only or not s["user_only"])
    ]
    total = len(skills)
    if args.query:
        skills = [s for s in rank(skills, args.query) if s["score"] > 0] or skills
    if args.limit:
        skills = skills[: args.limit]
    for s in skills:
        s.pop("_hash", None)
        s.pop("_mtime", None)
        if args.max_desc and len(s["description"]) > args.max_desc:
            s["description"] = s["description"][: args.max_desc] + "…"
    print(json.dumps({"total_installed": total, "returned": len(skills), "skills": skills}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
