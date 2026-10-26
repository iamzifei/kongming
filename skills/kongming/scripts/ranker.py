"""多语言需求—技能匹配。

三层信号，叠加后用 BM25 排序：
1. 字面：拉丁文字做大小写/重音归一与轻量词干化；中日韩文字切成二元组。
2. 概念：lexicon.json 把同一概念的多语言说法映射到同一个概念 ID（如“选题”“topic ideas”“ネタ”→ #topic_ideation），
   需求和技能描述用不同语言写也能对上。
3. 画像：模型为每个技能写下的多语言关键词与摘要（profiles.json），补足描述本身的缺漏。
最终是否入选仍由模型对前若干名做语义判断。
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from _common import read_json, state_dir

_HERE = Path(__file__).resolve().parent
_CJK = r"぀-ヿ㐀-䶿一-鿿가-힯豈-﫿"
_CJK_RUN = re.compile(f"[{_CJK}]+")
_HAS_CJK = re.compile(f"[{_CJK}]")
_LATIN_WORD = re.compile(r"[a-z0-9]+(?:[.+#][a-z0-9]+)*")
_SUFFIXES = ("izations", "ization", "isation", "ations", "ation", "ings", "ing", "ies", "es", "ed", "ly", "s")
_STOP = {"the", "and", "for", "with", "this", "that", "use", "used", "when", "you", "your", "from", "into", "any",
         "are", "can", "will", "not", "all", "how", "what", "who", "its", "also", "such", "like", "user", "users", "skill"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    # 去掉拉丁字母的重音：análisis → analisis
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", text)


def stem(word: str) -> str:
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 4:
            return word[: -len(suf)]
    return word


def latin_stems(text: str) -> list[str]:
    return [stem(w) for w in _LATIN_WORD.findall(text) if len(w) > 1 and w not in _STOP]


def cjk_grams(text: str) -> list[str]:
    out: list[str] = []
    for run in _CJK_RUN.findall(text):
        out += [run[i : i + 2] for i in range(len(run) - 1)] if len(run) > 1 else [run]
    return out


@lru_cache(maxsize=1)
def lexicon() -> tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]:
    """返回 (概念, 中日韩说法, 拉丁说法[已词干化]) 列表。用户词表可追加或覆盖。"""
    data = read_json(_HERE / "lexicon.json")
    user = read_json(state_dir() / "lexicon.json")
    if isinstance(user, dict):
        for k, v in user.items():
            if isinstance(v, list):
                data[k] = list(dict.fromkeys((data.get(k) or []) + v))
    entries = []
    for concept, terms in data.items():
        if concept.startswith("_") or not isinstance(terms, list):
            continue
        cjk, latin = [], []
        for t in terms:
            t = normalize(str(t))
            if _HAS_CJK.search(t):
                cjk.append(re.sub(r"\s+", "", t))
            else:
                stems = latin_stems(t) or [w for w in _LATIN_WORD.findall(t)]
                if stems:
                    latin.append(" ".join(stems))
        entries.append((concept, tuple(cjk), tuple(latin)))
    return tuple(entries)


def concepts(text: str) -> set[str]:
    norm = normalize(text)
    compact = re.sub(r"\s+", "", norm)
    stemmed = " " + " ".join(stem(w) for w in _LATIN_WORD.findall(norm)) + " "
    found = set()
    for concept, cjk, latin in lexicon():
        if any(t in compact for t in cjk) or any(f" {t} " in stemmed for t in latin):
            found.add(concept)
    return found


def bag(text: str, weight: int = 1) -> list[str]:
    norm = normalize(text)
    toks = latin_stems(norm) + cjk_grams(norm)
    toks += ["#" + c for c in concepts(text)] * 2
    return toks * weight


def load_profiles() -> dict:
    data = read_json(state_dir() / "profiles.json")
    return data if isinstance(data, dict) else {}


def profile_text(profile: dict | None) -> str:
    if not profile:
        return ""
    parts = [profile.get("summary", "")]
    kws = profile.get("keywords") or []
    parts.append(" ".join(kws) if isinstance(kws, list) else str(kws))
    return " ".join(p for p in parts if p)


def rank(skills: list[dict], query: str, profiles: dict | None = None, k1: float = 1.2, b: float = 0.75) -> list[dict]:
    """给 skills 加 score 与 matched_concepts，按分数降序返回。"""
    profiles = profiles if profiles is not None else load_profiles()
    q_bag = bag(query)
    q_terms = set(q_bag)
    q_concepts = {t[1:] for t in q_terms if t.startswith("#")}
    docs = []
    for s in skills:
        ptext = profile_text(profiles.get(s["id"]))
        tokens = bag(s["name"].replace("-", " ").replace("_", " "), 3) + bag(s["description"]) + bag(ptext, 2)
        docs.append(tokens)
    n = len(docs) or 1
    avgdl = sum(len(d) for d in docs) / n or 1
    df: dict[str, int] = {}
    for d in docs:
        for t in set(d):
            df[t] = df.get(t, 0) + 1
    for s, d in zip(skills, docs):
        tf: dict[str, int] = {}
        for t in d:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for t in q_terms:
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            boost = 1.5 if t.startswith("#") else 1.0
            score += boost * idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avgdl))
        s["score"] = round(score, 3)
        s["matched_concepts"] = sorted(q_concepts & {t[1:] for t in tf if t.startswith("#")})
    return sorted(skills, key=lambda s: s["score"], reverse=True)


if __name__ == "__main__":
    import sys

    print(json.dumps(sorted(concepts(" ".join(sys.argv[1:]))), ensure_ascii=False))
