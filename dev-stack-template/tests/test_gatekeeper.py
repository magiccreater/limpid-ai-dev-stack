import tempfile
import unittest
from pathlib import Path

from tests.helpers import STACK, load_module

gatekeeper = load_module("gatekeeper_agent", STACK / "examples" / "gatekeeper-agent" / "agent.py")


def scan(files: dict[str, str]) -> list[str]:
    with tempfile.TemporaryDirectory() as d:
        for name, text in files.items():
            (Path(d) / name).write_text(text)
        return [f["issue"] for f in gatekeeper.scan_path(Path(d))["findings"]]


class TemplateXssTests(unittest.TestCase):
    def test_escaped_interpolation_is_not_flagged(self):
        self.assertEqual(scan({
            "a.blade.php": "<p>{{ $user->name }}</p>",
            "b.html": "<p>{{ name }}</p>",
            "c.vue": "<template><p>{{ msg }}</p></template>",
        }), [])

    def test_raw_output_forms_are_flagged(self):
        issues = scan({
            "a.blade.php": "<div>{!! $html !!}</div>",
            "b.html": "<div>{{ body|safe }}</div>{% autoescape false %}",
            "c.twig": "{{ body | raw }}",
            "d.html": "<div>{{{ body }}}</div>",
        })
        self.assertEqual(len(issues), 5, issues)


if __name__ == "__main__":
    unittest.main()
