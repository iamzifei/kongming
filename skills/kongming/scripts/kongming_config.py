#!/usr/bin/env python3
"""查看或修改孔明的配置。

用法：
  python3 kongming_config.py show                  # 显示生效配置（默认 < 全局 < 项目）
  python3 kongming_config.py set show_sources brief
  python3 kongming_config.py set exclude '["some-skill", "beta-*"]'
  python3 kongming_config.py add exclude some-skill
  python3 kongming_config.py remove exclude some-skill
  python3 kongming_config.py reset
  加 --project 写入当前目录的 .kongming/config.json，否则写入 ~/.kongming/config.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DEFAULT_CONFIG, global_config_path, load_config, project_config_path  # noqa: E402

CHOICES = {
    "show_sources": ["off", "brief", "full"],
    "mode": ["auto", "single", "council"],
}
ALIASES = {  # 让自然语言里的说法也能落到合法值
    "show_sources": {
        "false": "off", "no": "off", "hide": "off", "隐藏": "off", "关": "off", "关闭": "off",
        "true": "brief", "yes": "brief", "show": "brief", "显示": "brief", "开": "brief", "打开": "brief",
        "详细": "full", "verbose": "full", "report": "full",
    },
}


def parse_value(key: str, raw: str):
    default = DEFAULT_CONFIG[key]
    if isinstance(default, bool):
        if raw.lower() in ("1", "true", "yes", "on", "开", "是"):
            return True
        if raw.lower() in ("0", "false", "no", "off", "关", "否"):
            return False
        raise SystemExit(f"{key} 只接受 true/false")
    if isinstance(default, int):
        value = int(raw)
        if value < 0:
            raise SystemExit(f"{key} 不能为负数")
        return value
    if isinstance(default, list):
        try:
            value = json.loads(raw)
        except ValueError:
            value = [x.strip() for x in raw.split(",") if x.strip()]
        if not isinstance(value, list):
            raise SystemExit(f"{key} 需要列表")
        return value
    value = ALIASES.get(key, {}).get(raw.lower(), raw)
    if key in CHOICES and value not in CHOICES[key]:
        raise SystemExit(f"{key} 可选值：{', '.join(CHOICES[key])}")
    return value


def read(path: Path) -> dict:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["show", "get", "set", "add", "remove", "reset", "path"])
    parser.add_argument("key", nargs="?")
    parser.add_argument("value", nargs="?")
    parser.add_argument("--project", action="store_true", help="写入项目级配置")
    args = parser.parse_args()

    target = project_config_path() if args.project else global_config_path()

    if args.action == "path":
        print(target)
        return 0
    if args.action == "show":
        print(json.dumps(load_config(), ensure_ascii=False, indent=2))
        return 0
    if args.action == "reset":
        if target.exists():
            target.unlink()
        print(f"已恢复默认：{target}")
        return 0

    if args.key not in DEFAULT_CONFIG:
        raise SystemExit(f"未知配置项：{args.key}。可用：{', '.join(DEFAULT_CONFIG)}")
    if args.action == "get":
        print(json.dumps(load_config().get(args.key), ensure_ascii=False))
        return 0
    if args.value is None:
        raise SystemExit("缺少值")

    data = read(target)
    if args.action == "set":
        data[args.key] = parse_value(args.key, args.value)
    else:
        if not isinstance(DEFAULT_CONFIG[args.key], list):
            raise SystemExit(f"{args.key} 不是列表，不能 {args.action}")
        current = list(data.get(args.key, load_config().get(args.key) or []))
        if args.action == "add" and args.value not in current:
            current.append(args.value)
        if args.action == "remove":
            current = [x for x in current if x != args.value]
        data[args.key] = current
    write(target, data)
    print(json.dumps({args.key: data[args.key], "saved_to": str(target)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
