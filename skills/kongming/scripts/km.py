#!/usr/bin/env python3
"""孔明的统一入口：所有对下游技能的访问都经过这里，并且只用代号。

  km.py scan [--query 需求] [--keywords 多语言关键词] [--limit N]   发现与排序候选
  km.py profile pending [--limit N]                                 列出还没有画像的技能
  km.py profile set --file profiles.json | set <代号> --keywords ... --summary ...
  km.py update <代号>... | --all                                     静默更新（失败即跳过）
  km.py load <代号> [相对路径]                                        读取技能文件（已脱敏）
  km.py ls <代号>                                                     列出技能内文件
  km.py exec <代号> "<命令>"                                          在技能目录中运行命令（输出已脱敏）
  km.py check --draft 文件 --used <代号>... [--context 用户原话]       交付前白标检查
  km.py reveal <代号>... [--once]                                     查看真实名称（仅限出处模式）

技能名、作者、路径不会出现在命令行里；输出中的技能名换成 @代号，作者/品牌换成 [·]，技能目录换成 $SKILL_DIR。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import load_config, read_json, state_dir, write_json  # noqa: E402
import ranker  # noqa: E402
import registry  # noqa: E402
import updater  # noqa: E402
from sanitize_check import GENERIC_PATTERNS, scan as scan_draft  # noqa: E402
from brand import brand_terms  # noqa: E402


def out(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def need(skills: list[dict], ref: str) -> dict:
    s = registry.resolve(ref, skills)
    if s is None:
        raise SystemExit(f"未找到 {ref}")
    return s


def safe_path(skill: dict, rel: str) -> Path:
    base = Path(skill["dir"]).resolve()
    target = (base / rel).resolve()
    if base != target and base not in target.parents:
        raise SystemExit("只能读取技能目录内的文件")
    return target


def cmd_scan(args, skills):
    profiles = ranker.load_profiles()
    visible = [s for s in skills if args.include_user_only or not s["user_only"]]
    query = " ".join(x for x in (args.query, args.keywords) if x)
    ranked = ranker.rank(visible, query, profiles) if query else visible
    if query:
        hits = [s for s in ranked if s["score"] > 0]
        ranked = hits or ranked
    if args.limit:
        ranked = ranked[: args.limit]
    rules = registry.hide_map(skills)
    rows = []
    for s in ranked:
        row = registry.public_view(s, skills, rules, args.max_desc)
        if query:
            row["score"] = s["score"]
            row["concepts"] = s["matched_concepts"]
        p = profiles.get(s["id"])
        row["profile"] = "ok" if p and p.get("hash") == s["hash"] else ("stale" if p else "missing")
        rows.append(row)
    pending = sum(1 for s in visible if (profiles.get(s["id"]) or {}).get("hash") != s["hash"])
    out({"total_installed": len(visible), "profiles_pending": pending, "returned": len(rows), "skills": rows})


def cmd_profile(args, skills):
    path = state_dir() / "profiles.json"
    profiles = ranker.load_profiles()
    if args.action == "pending":
        rules = registry.hide_map(skills)
        rows = [registry.public_view(s, skills, rules) for s in skills
                if (profiles.get(s["id"]) or {}).get("hash") != s["hash"]]
        out({"pending": len(rows), "skills": rows[: args.limit] if args.limit else rows})
        return
    entries = []
    if args.file:
        data = read_json(Path(args.file), default=[])
        entries = data if isinstance(data, list) else [dict(id=k, **v) for k, v in data.items()]
    elif args.id:
        entries = [{"id": args.id, "keywords": args.keywords or "", "summary": args.summary or ""}]
    saved = 0
    by_id = {s["id"]: s for s in skills}
    for e in entries:
        sid = str(e.get("id", "")).lstrip("@")
        if sid not in by_id:
            continue
        kws = e.get("keywords") or []
        if isinstance(kws, str):
            kws = [k.strip() for k in kws.replace("，", ",").split(",") if k.strip()]
        profiles[sid] = {"hash": by_id[sid]["hash"], "keywords": kws, "summary": e.get("summary", "")}
        saved += 1
    write_json(path, profiles)
    out({"saved": saved})


def cmd_update(args, skills):
    if not load_config().get("auto_update", True) and not args.force:
        out({"updated": 0, "unchanged": 0, "skipped": 0})
        return
    targets = skills if args.all or not args.ids else [s for s in (registry.resolve(i, skills) for i in args.ids) if s]
    try:
        counts = updater.update(targets, force=args.force)
    except Exception:
        counts = {"updated": 0, "unchanged": 0, "skipped": len(targets)}
    if counts.get("updated"):
        registry.scan()  # 版本目录可能变了，刷新登记表
    out(counts)


def cmd_load(args, skills):
    s = need(skills, args.id)
    target = safe_path(s, args.rel or "SKILL.md")
    if target.is_dir():
        raise SystemExit("这是目录，请用 ls")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise SystemExit("二进制文件，不能直接读取；如需使用请通过 exec 处理")
    print(registry.scrub(text, skills, s))


def cmd_ls(args, skills):
    s = need(skills, args.id)
    base = Path(s["dir"])
    files = sorted(
        str(p.relative_to(base)) for p in base.rglob("*")
        if p.is_file() and not any(part in registry.SKIP_DIRS for part in p.relative_to(base).parts)
    )
    rules = registry.hide_map(skills)
    out([registry.scrub(f, skills, s, rules) for f in files[:500]])


def cmd_exec(args, skills):
    s = need(skills, args.id)
    try:
        p = subprocess.run(
            ["bash", "-c", args.command], cwd=s["dir"], env=registry.env_for(s),
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=args.timeout,
        )
        code, text = p.returncode, (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    except subprocess.TimeoutExpired:
        code, text = 124, "超时"
    print(registry.scrub(text, skills, s))
    return code


def cmd_check(args, skills):
    draft = Path(args.draft).read_text(encoding="utf-8") if args.draft else sys.stdin.read()
    terms: dict[str, str] = {}
    used = [s for s in (registry.resolve(i, skills) for i in args.used) if s]
    for s in used:
        terms.update({t: k for t, k in brand_terms(Path(s["path"])).items() if t not in terms})
    # 其他已安装技能的名字也不应出现
    for s in skills:
        for t in (s["name"], s["invoke"]):
            if registry.is_hideable(t):
                terms.setdefault(t, "技能名")
    for t in load_config().get("extra_brand_terms") or []:
        terms.setdefault(t, "自定义品牌词")
    context = args.context.lower()
    allowed = {t.lower() for t in terms if context and t.lower() in context}
    hits = scan_draft(draft, terms, allowed)
    # 命中词本身属于品牌信息，报告里换成代号/掩码，避免检查结果反而泄露；先整行脱敏再截断
    rules = registry.hide_map(skills)
    lines = draft.splitlines()
    for h in hits:
        h["match"] = registry.scrub(h["match"], skills, rules=rules)
        h["context"] = registry.scrub(lines[h["line"] - 1], skills, rules=rules)[:160]
    out({"clean": not hits, "hit_count": len(hits), "hits": hits})
    return 0 if not hits else 1


def cmd_reveal(args, skills):
    if load_config().get("show_sources", "off") == "off" and not args.once:
        raise SystemExit("出处显示未开启")
    rows = []
    for i in args.ids:
        s = registry.resolve(i, skills)
        if s:
            rows.append({"id": s["id"], "name": s["name"], "invoke": s["invoke"], "plugin": s["plugin"]})
    out(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--path", action="append", default=[], help="额外扫描目录")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan")
    p.add_argument("--query", default="")
    p.add_argument("--keywords", default="", help="模型补充的多语言关键词，逗号或空格分隔")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--max-desc", type=int, default=400)
    p.add_argument("--include-user-only", action="store_true")

    p = sub.add_parser("profile")
    p.add_argument("action", choices=["pending", "set"])
    p.add_argument("id", nargs="?")
    p.add_argument("--file")
    p.add_argument("--keywords")
    p.add_argument("--summary")
    p.add_argument("--limit", type=int, default=40)

    p = sub.add_parser("update")
    p.add_argument("ids", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--force", action="store_true", help="忽略更新间隔")

    p = sub.add_parser("load")
    p.add_argument("id")
    p.add_argument("rel", nargs="?")

    p = sub.add_parser("ls")
    p.add_argument("id")

    p = sub.add_parser("exec")
    p.add_argument("id")
    p.add_argument("command")
    p.add_argument("--timeout", type=int, default=600)

    p = sub.add_parser("check")
    p.add_argument("--draft")
    p.add_argument("--used", nargs="*", default=[])
    p.add_argument("--context", default="")

    p = sub.add_parser("reveal")
    p.add_argument("ids", nargs="+")
    p.add_argument("--once", action="store_true", help="用户要求本次显示出处")

    args = parser.parse_args()
    skills = registry.scan(args.path)
    handler = {
        "scan": cmd_scan, "profile": cmd_profile, "update": cmd_update, "load": cmd_load, "ls": cmd_ls,
        "exec": cmd_exec, "check": cmd_check, "reveal": cmd_reveal,
    }[args.cmd]
    return handler(args, skills) or 0


if __name__ == "__main__":
    raise SystemExit(main())
