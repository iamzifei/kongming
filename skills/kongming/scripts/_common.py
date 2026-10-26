"""孔明脚本共用的工具：SKILL.md frontmatter 解析、配置路径。

只依赖标准库；装了 PyYAML 时优先用它解析 frontmatter。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

SELF_NAME = "kongming"


def split_frontmatter(text: str) -> tuple[str, str]:
    """返回 (frontmatter 原文, 正文)。没有 frontmatter 时前者为空。"""
    if not text.startswith("---"):
        return "", text
    lines = text.splitlines(keepends=True)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "".join(lines[1:i]), "".join(lines[i + 1 :])
    return "", text


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _fallback_yaml(raw: str) -> dict:
    """极简 YAML 子集：顶层 key、块标量 | >、一层嵌套映射。"""
    result: dict = {}
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#") or line[0].isspace():
            i += 1
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        block: list[str] = []
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j][0].isspace()):
            block.append(lines[j])
            j += 1
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            parts = [b.strip() for b in block if b.strip()]
            result[key] = ("\n" if value.startswith("|") else " ").join(parts)
        elif value:
            result[key] = _strip_quotes(value)
        else:
            nested: dict = {}
            for b in block:
                if ":" in b and b.strip():
                    k, _, v = b.strip().partition(":")
                    nested[k.strip()] = _strip_quotes(v)
            result[key] = nested
        i = j
    return result


def parse_frontmatter(text: str) -> dict:
    raw, _ = split_frontmatter(text)
    if not raw:
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return _fallback_yaml(raw)


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(as_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(as_text(v) for v in value.values())
    return re.sub(r"\s+", " ", str(value)).strip()


def home() -> Path:
    return Path(os.environ.get("KONGMING_HOME", Path.home()))


def global_config_path() -> Path:
    env = os.environ.get("KONGMING_CONFIG")
    if env:
        return Path(env)
    return home() / ".kongming" / "config.json"


def project_config_path(cwd: Path | None = None) -> Path:
    return (cwd or Path.cwd()) / ".kongming" / "config.json"


DEFAULT_CONFIG: dict = {
    # off：完全不显示出处；brief：文末列出用到的方法来源；full：附带交叉验证报告
    "show_sources": "off",
    # auto：按任务自动选择直答 / 单将 / 连环 / 会审；也可固定为 single / council
    "mode": "auto",
    # 会审时最多同时参与的技能数（不含模型本家）
    "max_skills": 3,
    # 会审时是否加入不依赖任何技能的模型本家作为一方
    "native_voice": True,
    # 修改与复审最多几轮
    "max_review_rounds": 2,
    # 永不调用的技能名（支持 * 通配）
    "exclude": [],
    # 额外扫描的技能目录
    "extra_paths": [],
    # 输出前额外要清除的品牌词、作者名
    "extra_brand_terms": [],
}


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_config(cwd: Path | None = None) -> dict:
    """默认值 < 全局配置 < 项目配置。"""
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    for path in (global_config_path(), project_config_path(cwd)):
        if path.is_file():
            config.update(_read_json(path))
    return config
