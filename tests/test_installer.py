"""Tests for install_dev_stack.sh: fresh install, re-run, upgrade from the old layout, dry run."""

import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "install_dev_stack.sh"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def run_installer(target: Path, *extra: str) -> str:
    res = subprocess.run(["bash", str(INSTALLER), "--target", str(target), *extra],
                         capture_output=True, text=True, env={**os.environ, **GIT_ENV})
    if res.returncode != 0:
        raise AssertionError(f"installer failed ({res.returncode}):\n{res.stdout}\n{res.stderr}")
    return res.stdout


def env_values(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if ".git" in p.parts:
            continue
        h.update(str(p.relative_to(root)).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name) / "dev-stack"

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_install_creates_stack_env_and_git(self):
        out = run_installer(self.target)
        self.assertIn("installing", out)
        self.assertTrue((self.target / "justfile").is_file())
        self.assertTrue((self.target / ".vscode" / "extensions.json").is_file())
        self.assertTrue(os.access(self.target / "setup.sh", os.X_OK))
        self.assertTrue((self.target / "aws" / "README.md").is_file())
        env = env_values(self.target / ".env")
        self.assertTrue(env["LITELLM_MASTER_KEY"].startswith("sk-"))
        self.assertNotEqual(env["LITELLM_MASTER_KEY"], "sk-dev-proxy-key")
        self.assertEqual(oct((self.target / ".env").stat().st_mode & 0o777), "0o600")
        tracked = subprocess.run(["git", "-C", str(self.target), "ls-files"], capture_output=True, text=True).stdout
        self.assertIn("justfile", tracked)
        self.assertNotIn(".env", tracked.split("\n"))

    def test_local_build_leftovers_are_not_copied(self):
        run_installer(self.target)
        for leftover in self.target.rglob("*"):
            self.assertNotIn(leftover.name, {".venv", "__pycache__", "uv.lock"}, leftover)

    def test_rerun_changes_nothing(self):
        run_installer(self.target)
        env_before = (self.target / ".env").read_text()
        out = run_installer(self.target)
        self.assertIn("0 added, 0 updated", out)
        self.assertEqual(env_before, (self.target / ".env").read_text())
        self.assertFalse((self.target / ".dev-stack-backup").exists())

    def make_old_install(self):
        t = self.target
        (t / "vscode").mkdir(parents=True)
        (t / "shared").mkdir()
        (t / "vscode" / "continue-config.json").write_text('{"apiKey": "sk-dev-proxy-key"}')
        (t / "shared" / "llm.py").write_text("# old\n")
        (t / "scripts" / "windows").mkdir(parents=True)
        (t / "scripts" / "start_llama_server.sh").write_text("llama-server --host 127.0.0.1\n")
        (t / "scripts" / "windows" / "llama-server.ps1").write_text("# old\n")
        (t / "litellm_config.yaml").write_text("general_settings:\n  master_key: sk-dev-proxy-key\n")
        (t / "justfile").write_text("litellm:\n  litellm --host 0.0.0.0\n")
        (t / ".env").write_text("OPENROUTER_API_KEY=sk-or-mine\nLITELLM_MASTER_KEY=sk-dev-proxy-key\n"
                                "MYSQL_ROOT_PASSWORD=rootpassword\n")
        (t / "my-notes.txt").write_text("keep me")

    def test_upgrade_from_old_layout_keeps_user_data_and_closes_the_gateway(self):
        self.make_old_install()
        out = run_installer(self.target)
        t = self.target
        backups = list((t / ".dev-stack-backup").iterdir())
        self.assertEqual(len(backups), 1)
        b = backups[0]
        # old files backed up, not lost
        self.assertIn("sk-dev-proxy-key", (b / "litellm_config.yaml").read_text())
        self.assertIn("0.0.0.0", (b / "justfile").read_text())
        self.assertTrue((b / "vscode" / "continue-config.json").is_file())
        # old config with the published key is replaced, not kept side by side
        self.assertNotIn("sk-dev-proxy-key", (t / "litellm_config.yaml").read_text())
        self.assertFalse((t / "litellm_config.yaml.dev-stack-new").exists())
        self.assertNotIn("--host 0.0.0.0", (t / "justfile").read_text())
        # obsolete files retired
        self.assertFalse((t / "vscode").exists())
        self.assertFalse((t / "shared" / "llm.py").exists())
        self.assertTrue((t / "shared" / "devstack_shared" / "llm.py").is_file())
        self.assertFalse((t / "scripts" / "start_llama_server.sh").exists())
        self.assertFalse((t / "scripts" / "windows").exists())
        self.assertTrue((b / "scripts" / "start_llama_server.sh").is_file())
        self.assertTrue((t / "aws" / "bedrock-access.yaml").is_file())
        # user data untouched, key rotated, MySQL password left (with a warning)
        self.assertEqual((t / "my-notes.txt").read_text(), "keep me")
        env = env_values(t / ".env")
        self.assertEqual(env["OPENROUTER_API_KEY"], "sk-or-mine")
        self.assertNotEqual(env["LITELLM_MASTER_KEY"], "sk-dev-proxy-key")
        self.assertEqual(env["MYSQL_ROOT_PASSWORD"], "rootpassword")
        self.assertIn("WARNING: MYSQL_ROOT_PASSWORD", out)

    def test_customised_litellm_config_is_kept(self):
        run_installer(self.target)
        cfg = self.target / "litellm_config.yaml"
        cfg.write_text(cfg.read_text() + "\n# my change\n")
        out = run_installer(self.target)
        self.assertIn("# my change", cfg.read_text())
        self.assertTrue((self.target / "litellm_config.yaml.dev-stack-new").is_file())
        self.assertIn("keep     litellm_config.yaml", out)

    def test_unedited_previous_litellm_config_is_upgraded(self):
        previous = subprocess.run(["git", "-C", str(REPO), "show", "2282ca3:dev-stack-template/litellm_config.yaml"],
                                  capture_output=True, text=True)
        if previous.returncode != 0:
            self.skipTest("git history not available")
        run_installer(self.target)
        cfg = self.target / "litellm_config.yaml"
        cfg.write_text(previous.stdout)
        out = run_installer(self.target)
        self.assertIn("update   litellm_config.yaml", out)
        self.assertIn("private-coder", cfg.read_text())
        self.assertFalse((self.target / "litellm_config.yaml.dev-stack-new").exists())

    def test_dry_run_changes_nothing(self):
        self.make_old_install()
        before = tree_digest(self.target)
        out = run_installer(self.target, "--dry-run")
        self.assertIn("Dry run:", out)
        self.assertEqual(before, tree_digest(self.target))


if __name__ == "__main__":
    unittest.main()
