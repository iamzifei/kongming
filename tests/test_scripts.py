"""孔明脚本测试：python3 -m unittest discover tests"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "kongming" / "scripts"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def write_skill(root: Path, name: str, description: str, body: str = "", extra: str = "") -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n{extra}---\n\n{body}\n", encoding="utf-8")
    return d


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.home, self.cwd = base / "home", base / "proj"
        self.home.mkdir()
        self.cwd.mkdir()
        self.user = self.home / ".claude" / "skills"
        self.env = dict(os.environ, KONGMING_HOME=str(self.home), **GIT_ENV)
        for k in ("KONGMING_CONFIG", "KONGMING_STATE"):
            self.env.pop(k, None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, name, *args, stdin=None):
        return subprocess.run([sys.executable, str(SCRIPTS / name), *args], cwd=self.cwd, env=self.env,
                              input=stdin, capture_output=True, text=True)

    def km(self, *args, stdin=None):
        return self.run_script("km.py", *args, stdin=stdin)

    def km_json(self, *args, stdin=None):
        p = self.km(*args, stdin=stdin)
        self.assertIn(p.returncode, (0, 1), p.stderr)
        return json.loads(p.stdout)

    def ids(self):
        sys.path.insert(0, str(SCRIPTS))
        os.environ["KONGMING_HOME"] = str(self.home)
        old = os.getcwd()
        os.chdir(self.cwd)
        try:
            import registry
            return {s["name"]: s["id"] for s in registry.scan()}
        finally:
            os.chdir(old)


class ScanTest(Base):
    def test_discovers_dedupes_excludes_self_and_hides_names(self):
        write_skill(self.user, "acme-seo-writer", "Write SEO articles that rank on Google")
        write_skill(self.user, "kongming", "router itself")
        write_skill(self.cwd / ".claude" / "skills", "acme-seo-writer", "project override version")
        plugin = self.home / ".claude" / "plugins" / "cache" / "mkt" / "growth" / "1.0.0"
        (plugin / ".claude-plugin").mkdir(parents=True)
        (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "growthkit"}')
        write_skill(plugin / "skills", "copy-polish", "Polish marketing copy for growthkit users")

        p = self.km("scan")
        out = json.loads(p.stdout)
        self.assertEqual(out["total_installed"], 2)
        for word in ("acme-seo-writer", "copy-polish", "growthkit", str(self.home)):
            self.assertNotIn(word, p.stdout)
        self.assertTrue(all(s["id"].startswith("s") and len(s["id"]) == 7 for s in out["skills"]))

    def test_plugin_alias_survives_version_bump(self):
        def install(version):
            root = self.home / ".claude" / "plugins" / "cache" / "mkt" / "growth" / version
            (root / ".claude-plugin").mkdir(parents=True)
            (root / ".claude-plugin" / "plugin.json").write_text('{"name": "growth"}')
            write_skill(root / "skills", "copy-polish", f"Polish copy {version}")
            return root
        install("1.0.0")
        first = self.km_json("scan")["skills"][0]["id"]
        new = install("1.1.0")
        os.utime(new / "skills" / "copy-polish" / "SKILL.md", (2e9, 2e9))
        out = self.km_json("scan")
        self.assertEqual(out["skills"][0]["id"], first)
        self.assertIn("1.1.0", out["skills"][0]["description"])

    def test_config_exclude(self):
        write_skill(self.user, "seo-writer", "Write SEO articles")
        write_skill(self.user, "beta-thing", "Experimental")
        self.run_script("kongming_config.py", "add", "exclude", "beta-*")
        self.assertEqual(self.km_json("scan")["total_installed"], 1)


class MultilingualTest(Base):
    def setUp(self):
        super().setUp()
        write_skill(self.user, "topic-finder", "选题策划：为公众号和小红书找爆款选题")
        write_skill(self.user, "seo-writer", "Write long-form blog articles optimized for search engine ranking")
        write_skill(self.user, "deck-maker", "Create presentation slides and pitch decks")
        write_skill(self.user, "contract-check", "Review legal contracts for risky clauses")

    def top(self, query, keywords=""):
        args = ["scan", "--query", query] + (["--keywords", keywords] if keywords else [])
        return self.km_json(*args)["skills"][0]["id"]

    def test_cross_language(self):
        ids = self.ids()
        self.assertEqual(self.top("帮我写一篇能上谷歌首页的博客文章，做好搜索引擎优化"), ids["seo-writer"])
        self.assertEqual(self.top("Give me content ideas for my Xiaohongshu account"), ids["topic-finder"])
        self.assertEqual(self.top("来週のプレゼン用スライドを作って"), ids["deck-maker"])
        self.assertEqual(self.top("이 계약서 검토해줘"), ids["contract-check"])
        self.assertEqual(self.top("revisa este contrato"), ids["contract-check"])

    def test_profile_improves_ranking(self):
        write_skill(self.user, "zz-tool", "Utility")
        ids = self.ids()
        out = self.km_json("profile", "pending")
        self.assertEqual(out["pending"], 5)
        prof = self.cwd / "p.json"
        prof.write_text(json.dumps([{"id": ids["zz-tool"], "keywords": ["播客", "podcast", "ポッドキャスト"],
                                     "summary": "Turns podcast audio into show notes / 播客转文字稿"}]))
        self.assertEqual(self.km_json("profile", "set", "--file", str(prof))["saved"], 1)
        self.assertEqual(self.top("把这期播客整理成节目笔记"), ids["zz-tool"])
        self.assertEqual(self.km_json("profile", "pending")["pending"], 4)


class LoadExecTest(Base):
    def setUp(self):
        super().setUp()
        self.skill = write_skill(
            self.user, "acme-seo-pro", "SEO by acme",
            body="Author: JaneAcme\nRun `bash scripts/hello.sh` then see /acme-seo-pro docs.\nhttps://github.com/acmelabs2024/acme-skills",
            extra="author: JaneAcme\n",
        )
        (self.skill / "scripts").mkdir()
        (self.skill / "scripts" / "hello.sh").write_text('echo "hello from $(basename "$SKILL_DIR") at $SKILL_DIR, by acmelabs"\n')
        self.id = self.ids()["acme-seo-pro"]

    def test_load_is_scrubbed(self):
        p = self.km("load", self.id)
        self.assertEqual(p.returncode, 0, p.stderr)
        for word in ("acme-seo-pro", "JaneAcme", "acmelabs", str(self.skill)):
            self.assertNotIn(word, p.stdout)
        self.assertIn("@" + self.id, p.stdout)
        self.assertIn("bash scripts/hello.sh", p.stdout)

    def test_ls_and_path_escape(self):
        self.assertIn("scripts/hello.sh", self.km_json("ls", self.id))
        self.assertNotEqual(self.km("load", self.id, "../../../etc/passwd").returncode, 0)

    def test_exec_runs_in_skill_dir_and_scrubs(self):
        p = self.km("exec", self.id, "bash scripts/hello.sh")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("$SKILL_DIR", p.stdout)
        for word in ("acme-seo-pro", "acmelabs", str(self.home)):
            self.assertNotIn(word, p.stdout)

    def test_check_flags_and_report_is_scrubbed(self):
        draft = textwrap.dedent("""\
            这是用acme-seo-pro做的分析。
            作者 JaneAcme 推荐这样写。
            Powered by acmelabs
            输入 /acme-seo-pro 继续
            正文：SEO 标题要包含关键词，路径 src/app，比例 50/50。
        """)
        p = self.km("check", "--used", self.id, "--context", "帮我做 SEO", stdin=draft)
        self.assertEqual(p.returncode, 1)
        result = json.loads(p.stdout)
        self.assertEqual({h["line"] for h in result["hits"]}, {1, 2, 3, 4})
        for word in ("acme-seo-pro", "JaneAcme", "acmelabs"):
            self.assertNotIn(word, p.stdout)

    def test_clean_draft_passes(self):
        p = self.km("check", "--used", self.id, "--context", "SEO", stdin="SEO 标题要包含主关键词，参考 https://example.com/a/b。\n")
        self.assertEqual(p.returncode, 0, p.stdout)

    def test_reveal_gated(self):
        self.assertNotEqual(self.km("reveal", self.id).returncode, 0)
        self.assertEqual(self.km_json("reveal", self.id, "--once")[0]["name"], "acme-seo-pro")
        self.run_script("kongming_config.py", "set", "show_sources", "brief")
        self.assertEqual(self.km_json("reveal", self.id)[0]["name"], "acme-seo-pro")


class UpdateTest(Base):
    def git(self, cwd, *args):
        subprocess.run(["git", *args], cwd=cwd, env=self.env, check=True, capture_output=True)

    def setUp(self):
        super().setUp()
        remote = Path(self.tmp.name) / "remote.git"
        seed = Path(self.tmp.name) / "seed"
        self.git(self.tmp.name, "init", "-q", "--bare", "-b", "main", str(remote))
        seed.mkdir()
        (seed / "SKILL.md").write_text("---\nname: secret-writer\ndescription: v1 skill\n---\n")
        self.git(seed, "init", "-q", "-b", "main")
        self.git(seed, "add", ".")
        self.git(seed, "commit", "-qm", "v1")
        self.git(seed, "push", "-q", str(remote), "main")
        self.user.mkdir(parents=True)
        self.git(self.user, "clone", "-q", str(remote), "secret-writer")
        self.seed, self.remote = seed, remote
        self.id = self.ids()["secret-writer"]

    def push_v2(self):
        (self.seed / "SKILL.md").write_text("---\nname: secret-writer\ndescription: v2 skill\n---\n")
        self.git(self.seed, "commit", "-qam", "v2")
        self.git(self.seed, "push", "-q", str(self.remote), "main")

    def test_updates_silently(self):
        self.push_v2()
        p = self.km("update", self.id)
        self.assertEqual(json.loads(p.stdout)["updated"], 1)
        self.assertNotIn("secret-writer", p.stdout + p.stderr)
        self.assertIn("v2 skill", self.km("load", self.id).stdout)

    def test_dirty_or_offline_is_skipped_silently(self):
        clone = self.user / "secret-writer"
        (clone / "local.txt").write_text("my change")
        p = self.km("update", self.id)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)["skipped"], 1)
        (clone / "local.txt").unlink()
        self.git(clone, "remote", "set-url", "origin", "https://invalid.invalid/none.git")
        p = self.km("update", self.id)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(json.loads(p.stdout)["skipped"], 1)
        self.assertNotIn("secret-writer", p.stdout + p.stderr)


class ConfigTest(Base):
    def test_set_alias_and_project_override(self):
        self.run_script("kongming_config.py", "set", "show_sources", "显示")
        self.assertEqual(json.loads(self.run_script("kongming_config.py", "get", "show_sources").stdout), "brief")
        self.run_script("kongming_config.py", "--project", "set", "show_sources", "full")
        self.assertEqual(json.loads(self.run_script("kongming_config.py", "get", "show_sources").stdout), "full")

    def test_rejects_bad_value(self):
        self.assertNotEqual(self.run_script("kongming_config.py", "set", "mode", "chaos").returncode, 0)


if __name__ == "__main__":
    unittest.main()
