"""从一个技能里提取需要隐藏的词：名称、作者、插件、仓库主、显式品牌字段。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from _common import as_text, parse_frontmatter, split_frontmatter

# 这些词太常见，单独出现不当作技能名（但组合名如 seo-audit 仍会检查）
COMMON_WORDS = {
    "seo", "copy", "write", "writing", "writer", "review", "research", "docs", "doc", "pdf", "xlsx",
    "docx", "pptx", "content", "data", "design", "code", "test", "plan", "report", "analysis",
    "product", "marketing", "summary", "translate", "translation", "title", "edit", "editor",
    "skill", "skills", "update", "help", "init", "loop", "run", "debug", "search", "image", "video",
}

GITHUB_RE = re.compile(r"github\.com/([\w.-]+)(?:/([\w.-]+))?", re.I)
_IGNORED_OWNERS = {"anthropics", "openai", "features", "orgs", "apps", "settings", "user-attachments"}


# 署名的明确形式：行首的 Author:/作者：/by，或 made/created/powered/maintained by X
_HANDLE = r"@?([A-Za-z0-9\u4e00-\u9fff][\w.\u4e00-\u9fff-]{1,30})"
_SIGNATURE_RES = [
    re.compile(r"(?im)^[\s>*_-]*(?:author|authors|maintainer|作者|出品|开发者)\s*[:：]\s*" + _HANDLE),
    re.compile(r"(?im)^[\s>*_-]*by\s+" + _HANDLE + r"\s*$"),
    re.compile(r"(?i)\b(?:made|created|built|powered|maintained|developed|written)\s+by\s+" + _HANDLE),
]
_GENERIC_DIRS = {"skills", ".claude", ".agents", ".codex", "plugins", "cache", "home", "root", "src", "user", "repo"}
_STOPWORDS = {
    "the", "this", "that", "a", "an", "you", "your", "me", "us", "them", "default", "claude", "hand", "name",
    "someone", "people", "user", "users", "it", "its", "their", "what", "how", "using", "anthropic",
}


def is_hideable(term: str) -> bool:
    return len(term) >= 3 and term.lower() not in COMMON_WORDS


def brand_terms(path: Path) -> dict[str, str]:
    """返回 {词: 类别}。path 是 SKILL.md。"""
    terms: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return terms
    meta = parse_frontmatter(text)
    name = as_text(meta.get("name")) or path.parent.name

    def add(term: str, kind: str) -> None:
        term = term.strip().strip("@")
        if not is_hideable(term):
            return
        terms.setdefault(term, kind)
        # 品牌常见变体：去掉尾部数字（foo2025 → foo）、去掉 -skills / -plugin 后缀
        for variant in (re.sub(r"[\d_-]+$", "", term), re.sub(r"(?i)[-_ ](skills?|plugins?|toolkit|tools)$", "", term)):
            if variant != term and len(variant) >= 4 and is_hideable(variant):
                terms.setdefault(variant, kind)

    add(name, "技能名")
    add(name.replace("-", " ").replace("_", " "), "技能名")
    add(path.parent.name, "技能目录名")
    # 系列技能的品牌前缀：foo-bar → fooskill / foo-skills / foo skills
    prefix = re.split(r"[-_:]", name)[0]
    if prefix != name and len(prefix) >= 2:
        for suffix in ("skill", "skills", "-skill", "-skills", " skills", "-kit"):
            add(prefix + suffix, "作者/品牌")
    # 技能所在仓库/集合的目录名（git 仓库根或带清单的根），例如 xxx-skills
    for parent in list(path.parents)[1:5]:
        if (parent / ".git").exists() or (parent / ".claude-plugin").is_dir() or (parent / "package.json").is_file():
            label = parent.name
            if re.fullmatch(r"v?\d+(?:\.\d+)*[\w.+-]*", label):  # 插件缓存的版本目录 → 取插件目录名
                label = parent.parent.name
            if label.lower() not in _GENERIC_DIRS:
                add(label, "仓库名")
            break
    metadata = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
    for key in ("author", "authors", "owner", "maintainer", "brand", "homepage", "repository"):
        for source in (meta, metadata):
            value = source.get(key)
            if isinstance(value, dict):
                value = value.get("name") or value.get("url")
            if value:
                add(as_text(value), "作者/品牌")
    _, body = split_frontmatter(text)
    for owner, repo in GITHUB_RE.findall(text):
        if owner.lower() not in _IGNORED_OWNERS:
            add(owner, "仓库作者")
        if repo:
            add(re.sub(r"\.git$", "", repo), "仓库名")
    for regex in _SIGNATURE_RES:
        for m in regex.finditer(body):
            handle = m.group(1).rstrip(".-")
            if handle.lower() not in _STOPWORDS:
                add(handle, "作者/品牌")
    for parent in path.parents:
        for manifest in (parent / ".claude-plugin" / "plugin.json", parent / ".claude-plugin" / "marketplace.json"):
            if not manifest.is_file():
                continue
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except ValueError:
                continue
            add(as_text(data.get("name")), "插件/市场名")
            for k in ("author", "owner"):
                v = data.get(k)
                if isinstance(v, dict):
                    add(as_text(v.get("name")), "作者/品牌")
                elif v:
                    add(as_text(v), "作者/品牌")
    return terms


def term_pattern(term: str) -> re.Pattern:
    if re.fullmatch(r"[\w .:-]+", term, re.ASCII):
        # 只用 ASCII 做边界：中文字符紧贴英文名时（“这是dbs-spread的”）也要能命中
        body = re.escape(term).replace(r"\ ", r"[\s_-]+")
        return re.compile(r"(?<![A-Za-z0-9_-])" + body + r"(?![A-Za-z0-9_-])", re.I)
    return re.compile(re.escape(term), re.I)
