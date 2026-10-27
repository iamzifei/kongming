#!/usr/bin/env python3
"""白标检查：在交付前找出草稿里泄露的技能名、作者、品牌、署名与推广痕迹。

孔明流程中请用 `km.py check`（按代号、报告已脱敏）；本脚本保留为按路径检查的底层工具。

用法：
  python3 sanitize_check.py --draft draft.md --skill /path/to/skillA/SKILL.md --skill /path/to/skillB
  cat draft.md | python3 sanitize_check.py --skill ... --context "用户原始需求"

--skill 传入本轮实际读取过的技能（SKILL.md 路径或其目录）。
--context 传入用户自己的原话：用户自己说出的词不算泄露（例如用户就叫它 SEO）。
输出 JSON：clean 为 true 才可交付；否则逐条给出命中的词、行号与上下文。
脚本只负责“找”，改写由模型完成；改完应再跑一次直到 clean。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import load_config  # noqa: E402
from brand import brand_terms, term_pattern  # noqa: E402

# 通用署名 / 推广 / 调用痕迹：无论来自哪个技能都不该出现在白标输出里
GENERIC_PATTERNS = [
    (r"(?i)\b(powered|generated|made|built|created|written)\s+(by|with)\b", "署名语"),
    (r"(?i)\bvia\s+(the\s+)?[\w-]+\s+skill\b", "调用说明"),
    (r"(?i)\b(using|used|invok(?:e|ed|ing)|call(?:ed|ing)?|load(?:ed|ing)?)\s+(the\s+)?[`'\"]?[\w:-]+[`'\"]?\s+skill\b", "调用说明"),
    (r"(?i)\bskill\s*(name|author|by)\b", "调用说明"),
    (r"(使用|调用|借助|通过|根据|基于|按照)了?\s*[`「“\"]?[\w:\-\u4e00-\u9fff]{1,30}[`」”\"]?\s*(这个|该)?\s*(skill|技能|插件)", "调用说明"),
    (r"(?i)(skill|技能)\s*(出处|来源|作者)", "调用说明"),
    (r"(?<![A-Za-z0-9_./:])/[a-z][A-Za-z0-9_-]*(:[A-Za-z0-9_-]+)?(?=\s|$|[，。,.!?）)\u4e00-\u9fff])", "斜杠命令"),
    (r"🔔", "更新提醒"),
    (r"(?i)\b(star|follow|subscribe)\b.{0,20}\b(github|repo|us|me)\b", "推广语"),
    (r"(关注|订阅|点赞|一键三连|扫码|加群|公众号|小红书号|微信号)", "推广语"),
    (r"(?i)\bcopyright\b|©|版权所有", "版权署名"),
]

def scan(draft: str, terms: dict[str, str], allowed: set[str]) -> list[dict]:
    hits = []
    lines = draft.splitlines()
    compiled = [(term_pattern(t), t, kind) for t, kind in terms.items() if t.lower() not in allowed]
    compiled += [(re.compile(p), None, kind) for p, kind in GENERIC_PATTERNS]
    seen: set[tuple[int, int, int]] = set()
    for no, line in enumerate(lines, 1):
        for regex, term, kind in compiled:
            for m in regex.finditer(line):
                found = term or m.group(0)
                if found.lower() in allowed or (no, m.start(), m.end()) in seen:
                    continue
                seen.add((no, m.start(), m.end()))
                start = max(0, m.start() - 20)
                hits.append({"line": no, "kind": kind, "match": m.group(0), "context": line[start : m.end() + 20]})
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--draft", help="草稿文件；省略则从 stdin 读取")
    parser.add_argument("--skill", action="append", default=[], help="本轮读取过的技能（可多次）")
    parser.add_argument("--term", action="append", default=[], help="额外要隐藏的词")
    parser.add_argument("--context", default="", help="用户原话，其中出现的词不算泄露")
    parser.add_argument("--allow", action="append", default=[], help="明确允许出现的词")
    args = parser.parse_args()

    draft = Path(args.draft).read_text(encoding="utf-8") if args.draft else sys.stdin.read()
    terms: dict[str, str] = {}
    for s in args.skill:
        p = Path(s).expanduser()
        for term, kind in brand_terms(p / "SKILL.md" if p.is_dir() else p).items():
            terms.setdefault(term, kind)
    for t in list(load_config().get("extra_brand_terms") or []) + args.term:
        terms.setdefault(t, "自定义品牌词")

    context = args.context.lower()
    allowed = {a.lower() for a in args.allow}
    allowed |= {t.lower() for t in terms if context and t.lower() in context}

    hits = scan(draft, terms, allowed)
    print(json.dumps({"clean": not hits, "hit_count": len(hits), "hits": hits, "checked_terms": sorted(terms)}, ensure_ascii=False, indent=2))
    return 0 if not hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
