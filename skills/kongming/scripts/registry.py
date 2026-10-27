"""技能登记表：扫描本机技能，给每个技能分配不透明代号，并负责输出脱敏。

代号由技能目录的真实路径哈希而来（如 s3fa91c），稳定、不含任何名称信息。
孔明在工具调用里只使用代号，技能名、作者、路径都不会出现在命令行或输出中。
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
from pathlib import Path

from _common import SELF_NAME, as_text, home, load_config, parse_frontmatter, read_json, state_dir, write_json
from brand import brand_terms, is_hideable, term_pattern

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
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
BRAND_MASK = "[·]"


def plugin_origin(plugin_root: Path | None) -> tuple[str, str]:
    """插件缓存路径 …/plugins/cache/<市场>/<插件>/<版本>/ → (市场, 插件)；不在缓存里时返回空。"""
    if plugin_root is None:
        return "", ""
    parts = plugin_root.parts
    if "cache" in parts:
        i = len(parts) - 1 - parts[::-1].index("cache")
        if len(parts) > i + 2:
            return parts[i + 1], parts[i + 2]
    return "", ""


def alias_for(skill_dir: Path, plugin_root: Path | None = None) -> str:
    """代号只取决于技能身份：插件技能用 市场/插件/相对路径（升级换版本目录后代号不变），其余用真实路径。"""
    market, plugin = plugin_origin(plugin_root)
    if market:
        key = f"plugin:{market}:{plugin}:{skill_dir.relative_to(plugin_root).as_posix()}"
    else:
        try:
            key = str(skill_dir.resolve())
        except OSError:
            key = str(skill_dir)
    return "s" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:6]


def iter_skill_files(root: Path, max_depth: int = MAX_DEPTH):
    if not root.is_dir():
        return
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
            if child.name not in SKIP_DIRS:
                stack.append((child, depth + 1))


def find_plugin_root(skill_dir: Path) -> Path | None:
    for parent in skill_dir.parents:
        if (parent / ".claude-plugin" / "plugin.json").is_file():
            return parent
        if parent.name == "plugins" and parent.parent.name == ".claude":
            break
    return None


def plugin_name(root: Path | None) -> str:
    if root is None:
        return ""
    data = read_json(root / ".claude-plugin" / "plugin.json")
    return as_text(data.get("name")) if isinstance(data, dict) and data.get("name") else root.name


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
    proot = find_plugin_root(skill_dir) if scope == "plugin" else None
    plugin = plugin_name(proot)
    market, _ = plugin_origin(proot)
    return {
        "id": alias_for(skill_dir, proot),
        "marketplace": market,
        "name": name,
        "invoke": f"{plugin}:{name}" if plugin else name,
        "description": description,
        "path": str(path),
        "dir": str(skill_dir),
        "real_dir": str(skill_dir.resolve()),
        "plugin_root": str(proot) if proot else "",
        "scope": scope,
        "plugin": plugin,
        "user_only": bool(meta.get("disable-model-invocation")),
        "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "mtime": path.stat().st_mtime,
    }


def _roots(extra_paths: list[str], cwd: Path) -> list[tuple[Path, str]]:
    roots = [(cwd / r, "project") for r in PROJECT_ROOTS]
    roots += [(home() / r, "user") for r in USER_ROOTS]
    roots += [(home() / r, "plugin") for r in PLUGIN_ROOTS]
    roots += [(Path(p).expanduser(), "extra") for p in extra_paths]
    return roots


def _dedupe(skills: list[dict]) -> list[dict]:
    """同一调用名保留第一份（优先级最高）；插件缓存里的多个版本保留最新。内容相同的副本只留一份。"""
    by_key: dict[str, dict] = {}
    order: list[str] = []
    for s in skills:
        key = s["invoke"].lower()
        if key not in by_key:
            by_key[key] = s
            order.append(key)
        elif s["scope"] == by_key[key]["scope"] == "plugin" and s["mtime"] > by_key[key]["mtime"]:
            by_key[key] = s
    result, hashes = [], set()
    for key in order:
        s = by_key[key]
        if s["hash"] not in hashes:
            hashes.add(s["hash"])
            result.append(s)
    return result


def _excluded(skill: dict, patterns: list[str]) -> bool:
    return any(
        fnmatch.fnmatch(skill["name"].lower(), p.lower()) or fnmatch.fnmatch(skill["invoke"].lower(), p.lower())
        for p in patterns
    )


def _is_self(skill: dict) -> bool:
    return skill["real_dir"] == str(SELF_DIR) or skill["name"].lower() == SELF_NAME


def scan(extra_paths: list[str] | None = None, cwd: Path | None = None, include_excluded: bool = False) -> list[dict]:
    config = load_config(cwd)
    cwd = cwd or Path.cwd()
    found, seen = [], set()
    for root, scope in _roots(list(config.get("extra_paths") or []) + list(extra_paths or []), cwd):
        for path in iter_skill_files(root):
            try:
                real = path.resolve()
            except OSError:
                continue
            if real in seen:
                continue
            seen.add(real)
            skill = load_skill(path, scope)
            if skill:
                found.append(skill)
    skills = [s for s in _dedupe(found) if not _is_self(s)]
    if not include_excluded:
        skills = [s for s in skills if not _excluded(s, list(config.get("exclude") or []))]
    write_json(state_dir() / "registry.json", {s["id"]: s for s in skills})
    return skills


def resolve(ref: str, skills: list[dict] | None = None) -> dict | None:
    """代号、调用名或路径 → 技能记录。"""
    ref = ref.strip().lstrip("@")
    pool = skills if skills is not None else scan(include_excluded=True)
    for s in pool:
        if ref in (s["id"], s["invoke"], s["name"]):
            return s
    p = Path(ref).expanduser()
    if p.exists():
        skill_md = p / "SKILL.md" if p.is_dir() else p
        for s in pool:
            if Path(s["path"]).resolve() == skill_md.resolve():
                return s
        return load_skill(skill_md, "extra") if skill_md.is_file() else None
    return None


# ---------- 脱敏 ----------

def hide_map(skills: list[dict]) -> list[tuple[re.Pattern, str]]:
    """把所有技能的名称换成代号，作者/品牌换成 [·]，路径换成代号路径。长词优先替换。"""
    replacements: dict[str, str] = {}
    for s in skills:
        tag = "@" + s["id"]
        for term in {s["name"], s["invoke"], s["name"].replace("-", " "), Path(s["dir"]).name, s["plugin"]}:
            if term and is_hideable(term):
                replacements.setdefault(term, tag if term != s["plugin"] else BRAND_MASK)
        for term, kind in brand_terms(Path(s["path"])).items():
            replacements.setdefault(term, tag if kind.startswith("技能") else BRAND_MASK)
    for t in load_config().get("extra_brand_terms") or []:
        replacements.setdefault(t, BRAND_MASK)
    ordered = sorted(replacements.items(), key=lambda kv: len(kv[0]), reverse=True)
    rules: list[tuple[re.Pattern, str]] = []
    for term, repl in ordered:
        pat = term_pattern(term)
        if repl.startswith("@"):
            # 顺带吃掉前面的斜杠：/foo-skill → @s123abc
            pat = re.compile(r"/?" + pat.pattern, pat.flags)
        rules.append((pat, repl))
    return rules


def scrub(text: str, skills: list[dict], current: dict | None = None, rules=None) -> str:
    if current is not None:
        for d in {current["dir"], current["real_dir"]}:
            text = text.replace(d, "$SKILL_DIR")
        if current.get("plugin_root"):
            text = text.replace(current["plugin_root"], "$CLAUDE_PLUGIN_ROOT")
    for s in sorted(skills, key=lambda s: len(s["dir"]), reverse=True):
        for d in {s["dir"], s["real_dir"]}:
            text = text.replace(d, "@" + s["id"])
    home_str = str(home())
    text = text.replace(home_str, "~")
    for pat, repl in rules if rules is not None else hide_map(skills):
        text = pat.sub(repl, text)
    return text


def public_view(skill: dict, skills: list[dict], rules=None, max_desc: int = 0) -> dict:
    desc = scrub(skill["description"], skills, skill, rules)
    if max_desc and len(desc) > max_desc:
        desc = desc[:max_desc] + "…"
    return {"id": skill["id"], "description": desc, "user_only": skill["user_only"]}


def env_for(skill: dict) -> dict:
    env = dict(os.environ, SKILL_DIR=skill["dir"])
    if skill.get("plugin_root"):
        env["CLAUDE_PLUGIN_ROOT"] = skill["plugin_root"]
    return env

