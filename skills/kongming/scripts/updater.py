"""静默更新技能：调用前把技能更新到最新。

更新途径（按技能来源自动判断）：
- 插件技能：claude plugin marketplace update <市场> + claude plugin update <插件>@<市场>
- git 安装的技能（含 --link 软链接到 git 仓库）：工作区干净且有上游时 git pull --ff-only
- skills CLI 安装的技能（锁文件里有记录）：npx skills update <名称>
技能自己声明的版本检查/更新步骤由模型按 SKILL.md 执行（见孔明 SKILL.md）。

任何失败、超时、无网络都直接跳过；输出里只有数量，不含任何技能名或路径。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path

from _common import home, load_config, read_json, state_dir, write_json

_DEVNULL = subprocess.DEVNULL
# 静默更新绝不等待输入：禁止 git 弹出凭据/主机确认提示
_ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="true", GIT_SSH_COMMAND="ssh -oBatchMode=yes", CI="1")


def _run(cmd: list[str], cwd: Path | None, timeout: int) -> bool:
    try:
        p = subprocess.run(cmd, cwd=cwd, env=_ENV, stdin=_DEVNULL, stdout=_DEVNULL, stderr=_DEVNULL, timeout=timeout)
        return p.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _capture(cmd: list[str], cwd: Path, timeout: int) -> str | None:
    try:
        p = subprocess.run(cmd, cwd=cwd, env=_ENV, stdin=_DEVNULL, capture_output=True, text=True, timeout=timeout)
        return p.stdout if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _git_root(skill: dict) -> Path | None:
    """只更新“技能自己的仓库”：仓库根必须在技能目录本身或其上 3 层以内，且不能是家目录、工具配置目录或当前项目。"""
    if skill["scope"] in ("project", "plugin"):
        return None
    start = Path(skill["real_dir"])
    stops = {home(), home() / ".claude", home() / ".agents", home() / ".codex", Path.cwd(), Path("/")}
    stops |= {p.resolve() for p in stops if p.exists()}
    for depth, d in enumerate([start, *start.parents]):
        if depth > 3 or d in stops:
            return None
        if (d / ".git").exists():
            return d
    return None


def _git_update(root: Path, timeout: int) -> str:
    if _capture(["git", "status", "--porcelain"], root, timeout) not in ("",):
        return "skipped"  # 有本地改动或不是可用仓库：不碰
    if _capture(["git", "rev-parse", "--abbrev-ref", "@{u}"], root, timeout) is None:
        return "skipped"
    before = _capture(["git", "rev-parse", "HEAD"], root, timeout)
    if not _run(["git", "pull", "--ff-only", "--quiet"], root, timeout):
        return "skipped"
    return "updated" if _capture(["git", "rev-parse", "HEAD"], root, timeout) != before else "unchanged"


def _plugin_update(market: str, plugin: str, timeout: int) -> str:
    claude = shutil.which("claude")
    if not claude or not market or market == "synced":
        return "skipped"
    _run([claude, "plugin", "marketplace", "update", market], None, timeout)
    return "updated" if _run([claude, "plugin", "update", f"{plugin}@{market}"], None, timeout) else "skipped"


def _skills_cli_names() -> set[str]:
    names: set[str] = set()
    for lock in (home() / ".agents" / ".skill-lock.json", Path.cwd() / "skills-lock.json"):
        data = read_json(lock)
        skills = data.get("skills") if isinstance(data, dict) else None
        if isinstance(skills, dict):
            names |= set(skills)
        elif isinstance(skills, list):
            names |= {s.get("name") for s in skills if isinstance(s, dict) and s.get("name")}
    return names


def _skills_cli_update(name: str, timeout: int) -> str:
    npx = shutil.which("npx")
    if not npx:
        return "skipped"
    return "updated" if _run([npx, "--yes", "skills", "update", name], None, timeout) else "skipped"


def plan(skills: list[dict]) -> dict[str, tuple]:
    """把技能归并成更新单元：同一仓库 / 同一插件只更新一次。"""
    units: dict[str, tuple] = {}
    cli_names = _skills_cli_names()
    for s in skills:
        if s["scope"] == "plugin":
            if s.get("marketplace"):
                units[f"plugin:{s['marketplace']}:{s['plugin']}"] = ("plugin", s["marketplace"], s["plugin"])
            continue
        root = _git_root(s)
        if root is not None:
            units[f"git:{root}"] = ("git", root)
        elif s["name"] in cli_names:
            units[f"cli:{s['name']}"] = ("cli", s["name"])
    return units


def update(skills: list[dict], force: bool = False) -> dict:
    config = load_config()
    timeout = int(config.get("update_timeout_seconds") or 20)
    interval = float(config.get("update_interval_minutes") or 0) * 60
    log_path = state_dir() / "updates.json"
    log = read_json(log_path)
    if not isinstance(log, dict):
        log = {}
    now = time.time()
    counts = {"updated": 0, "unchanged": 0, "skipped": 0}
    units = plan(skills)
    todo = {k: u for k, u in units.items() if force or now - float(log.get(k, 0)) >= interval}
    counts["unchanged"] += len(units) - len(todo)  # 间隔内刚更新过

    def work(unit: tuple) -> str:
        kind = unit[0]
        if kind == "git":
            return _git_update(unit[1], timeout)
        if kind == "plugin":
            return _plugin_update(unit[1], unit[2], timeout)
        return _skills_cli_update(unit[1], timeout)

    if todo:
        pool = ThreadPoolExecutor(max_workers=min(8, len(todo)))
        futures = {pool.submit(work, u): k for k, u in todo.items()}
        done, pending = wait(futures, timeout=timeout * 2 + 5)
        for f in done:
            result = f.result() if not f.exception() else "skipped"
            counts[result] = counts.get(result, 0) + 1
            if result != "skipped":
                log[futures[f]] = now
        counts["skipped"] += len(pending)
        pool.shutdown(wait=False, cancel_futures=True)
    write_json(log_path, log)
    return counts
