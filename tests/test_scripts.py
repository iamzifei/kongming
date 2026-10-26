"""孔明脚本的基本测试：python3 -m unittest discover tests"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "kongming" / "scripts"


def write_skill(root: Path, name: str, description: str, body: str = "", extra: str = "") -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n{extra}---\n\n{body}\n", encoding="utf-8"
    )
    return d


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.cwd = Path(self.tmp.name) / "proj"
        self.home.mkdir()
        self.cwd.mkdir()
        self.env = dict(os.environ, KONGMING_HOME=str(self.home))
        self.env.pop("KONGMING_CONFIG", None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, name, *args, stdin=None):
        p = subprocess.run(
            [sys.executable, str(SCRIPTS / name), *args],
            cwd=self.cwd, env=self.env, input=stdin, capture_output=True, text=True,
        )
        return p


class DiscoverTest(Base):
    def test_discovers_dedupes_and_excludes_self(self):
        user = self.home / ".claude" / "skills"
        write_skill(user, "seo-writer", "Write SEO articles that rank on Google")
        write_skill(user, "topic-finder", "选题：为公众号和小红书找爆款选题")
        write_skill(user, "kongming", "router itself")
        write_skill(self.cwd / ".claude" / "skills", "seo-writer", "project override version")
        plugin = self.home / ".claude" / "plugins" / "cache" / "mkt" / "growth" / "1.0.0"
        (plugin / ".claude-plugin").mkdir(parents=True)
        (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "growth"}')
        write_skill(plugin / "skills", "copy-polish", "Polish marketing copy")

        out = json.loads(self.run_script("discover_skills.py").stdout)
        names = {s["invoke"]: s for s in out["skills"]}
        self.assertNotIn("kongming", names)
        self.assertEqual(names["seo-writer"]["scope"], "project")
        self.assertIn("growth:copy-polish", names)
        self.assertEqual(out["total_installed"], 3)

    def test_query_ranks_chinese(self):
        user = self.home / ".claude" / "skills"
        write_skill(user, "seo-writer", "Write SEO articles")
        write_skill(user, "topic-finder", "选题：为公众号和小红书找爆款选题")
        out = json.loads(self.run_script("discover_skills.py", "--query", "帮我想几个小红书选题").stdout)
        self.assertEqual(out["skills"][0]["name"], "topic-finder")

    def test_config_exclude(self):
        user = self.home / ".claude" / "skills"
        write_skill(user, "seo-writer", "Write SEO articles")
        write_skill(user, "beta-thing", "Experimental")
        self.run_script("kongming_config.py", "add", "exclude", "beta-*")
        out = json.loads(self.run_script("discover_skills.py").stdout)
        self.assertEqual([s["name"] for s in out["skills"]], ["seo-writer"])


class ConfigTest(Base):
    def test_set_alias_and_project_override(self):
        self.run_script("kongming_config.py", "set", "show_sources", "显示")
        self.assertEqual(json.loads(self.run_script("kongming_config.py", "get", "show_sources").stdout), "brief")
        self.run_script("kongming_config.py", "--project", "set", "show_sources", "full")
        self.assertEqual(json.loads(self.run_script("kongming_config.py", "get", "show_sources").stdout), "full")

    def test_rejects_bad_value(self):
        p = self.run_script("kongming_config.py", "set", "mode", "chaos")
        self.assertNotEqual(p.returncode, 0)


class SanitizeTest(Base):
    def make_branded_skill(self):
        return write_skill(
            self.home, "acme-seo-pro",
            "SEO by acme",
            body="Made by AcmeLabs. See https://github.com/acmelabs2024/acme-skills",
            extra="author: Jane Acme\n",
        )

    def test_flags_brand_leaks(self):
        skill = self.make_branded_skill()
        draft = textwrap.dedent("""\
            这是用acme-seo-pro做的分析。
            作者 Jane Acme 推荐这样写。
            Powered by acmelabs
            输入 /acme-seo-pro 继续
            正文：SEO 标题要包含关键词。
        """)
        p = self.run_script("sanitize_check.py", "--skill", str(skill), "--context", "帮我做 SEO", stdin=draft)
        result = json.loads(p.stdout)
        self.assertFalse(result["clean"])
        self.assertEqual(p.returncode, 1)
        lines = {h["line"] for h in result["hits"]}
        self.assertEqual(lines, {1, 2, 3, 4})

    def test_clean_draft_passes(self):
        skill = self.make_branded_skill()
        draft = "SEO 标题要包含主关键词，路径 src/app，比例 50/50，参考 https://example.com/a/b。\n"
        p = self.run_script("sanitize_check.py", "--skill", str(skill), "--context", "帮我做 SEO", stdin=draft)
        self.assertTrue(json.loads(p.stdout)["clean"], p.stdout)
        self.assertEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
