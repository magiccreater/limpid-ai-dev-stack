import stat
import tempfile
import unittest
from pathlib import Path

from tests.helpers import STACK, load_module

env_tool = load_module("devstack_env", STACK / "scripts" / "devstack_env.py")


class InitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = self.dir / ".env"
        self.example = STACK / ".env.example"

    def tearDown(self):
        self.tmp.cleanup()

    def values(self):
        return env_tool.parse(self.env.read_text())

    def test_fresh_env_gets_random_secrets_and_private_mode(self):
        env_tool.init(self.env, self.example)
        v = self.values()
        self.assertTrue(v["LITELLM_MASTER_KEY"].startswith("sk-"))
        self.assertGreater(len(v["LITELLM_MASTER_KEY"]), 30)
        for key in ("MYSQL_ROOT_PASSWORD", "MYSQL_PASSWORD", "ANYTHINGLLM_JWT_SECRET"):
            self.assertNotIn(v[key], ("", env_tool.PLACEHOLDER), key)
        self.assertNotIn(env_tool.PLACEHOLDER, v.values())
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)

    def test_two_installs_get_different_keys(self):
        env_tool.init(self.env, self.example)
        first = self.values()["LITELLM_MASTER_KEY"]
        self.env.unlink()
        env_tool.init(self.env, self.example)
        self.assertNotEqual(first, self.values()["LITELLM_MASTER_KEY"])

    def test_upgrade_rotates_published_keys_but_not_mysql_or_user_values(self):
        self.env.write_text(
            "OPENROUTER_API_KEY=sk-or-mine\n"
            "LITELLM_MASTER_KEY=sk-dev-proxy-key\n"
            "MYSQL_ROOT_PASSWORD=rootpassword\n"
            "MYSQL_PASSWORD=my-own-pass\n"
            "ANYTHINGLLM_JWT_SECRET=change-me-in-production\n"
            "# a comment the user wrote\n"
        )
        notes = env_tool.init(self.env, self.example)
        v = self.values()
        self.assertEqual(v["OPENROUTER_API_KEY"], "sk-or-mine")
        self.assertNotEqual(v["LITELLM_MASTER_KEY"], "sk-dev-proxy-key")
        self.assertNotEqual(v["ANYTHINGLLM_JWT_SECRET"], "change-me-in-production")
        self.assertEqual(v["MYSQL_ROOT_PASSWORD"], "rootpassword")  # warned, not changed
        self.assertEqual(v["MYSQL_PASSWORD"], "my-own-pass")
        self.assertIn("ALLOW_FRONTIER", v)  # missing key added from the example
        self.assertEqual(v["ALLOW_FRONTIER"], "0")
        self.assertIn("# a comment the user wrote", self.env.read_text())
        self.assertTrue(any("MYSQL_ROOT_PASSWORD" in n and "WARNING" in n for n in notes))

    def test_upgrade_is_stable_on_second_run(self):
        env_tool.init(self.env, self.example)
        before = self.env.read_text()
        env_tool.init(self.env, self.example)
        self.assertEqual(before, self.env.read_text())


class CheckAndRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = self.dir / ".env"

    def tearDown(self):
        self.tmp.cleanup()

    def test_check_rejects_missing_placeholder_and_published_key(self):
        self.assertTrue(env_tool.check(self.env))
        for value in ("", env_tool.PLACEHOLDER, "sk-dev-proxy-key"):
            self.env.write_text(f"LITELLM_MASTER_KEY={value}\n")
            self.assertTrue(env_tool.check(self.env), value)
        self.env.write_text("LITELLM_MASTER_KEY=sk-random123\n")
        self.assertEqual(env_tool.check(self.env), [])

    def test_render_substitutes_and_keeps_existing_different_output(self):
        self.env.write_text('LITELLM_MASTER_KEY="sk-abc"\n')
        tmpl = self.dir / "t.tmpl"
        tmpl.write_text("key: ${LITELLM_MASTER_KEY}\n")
        out = self.dir / "sub" / "out.yaml"
        env_tool.render(tmpl, out, self.env)
        self.assertEqual(out.read_text(), "key: sk-abc\n")
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)

        out.write_text("user edited\n")
        msg = env_tool.render(tmpl, out, self.env)
        self.assertEqual(out.read_text(), "user edited\n")
        self.assertEqual((self.dir / "sub" / "out.yaml.dev-stack-new").read_text(), "key: sk-abc\n")
        self.assertIn("differs", msg)

        env_tool.render(tmpl, out, self.env, force=True)
        self.assertEqual(out.read_text(), "key: sk-abc\n")

    def test_render_replaces_output_that_still_has_the_published_key(self):
        self.env.write_text("LITELLM_MASTER_KEY=sk-new\n")
        tmpl = self.dir / "t.tmpl"
        tmpl.write_text("key: ${LITELLM_MASTER_KEY}\n")
        out = self.dir / "openclaw.json"
        out.write_text("key: sk-dev-proxy-key\n# my tweak\n")
        env_tool.render(tmpl, out, self.env)
        self.assertEqual(out.read_text(), "key: sk-new\n")
        self.assertIn("my tweak", (self.dir / "openclaw.json.dev-stack-backup").read_text())

    def test_render_refuses_unset_variables(self):
        self.env.write_text("OTHER=1\n")
        tmpl = self.dir / "t.tmpl"
        tmpl.write_text("${LITELLM_MASTER_KEY}")
        with self.assertRaises(SystemExit):
            env_tool.render(tmpl, self.dir / "out", self.env)

    def test_client_templates_only_use_known_variables(self):
        example = env_tool.parse((STACK / ".env.example").read_text())
        for tmpl in (STACK / "clients").glob("*.tmpl"):
            for var in env_tool.VAR.findall(tmpl.read_text()):
                self.assertIn(var, example, f"{tmpl.name} uses {var}")


if __name__ == "__main__":
    unittest.main()
