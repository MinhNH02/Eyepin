"""B18 (buglist.md): phím và tài liệu lệch.

1. `shortcuts._NAMES` thiếu period, comma, greater, less, Return: guide phím hiện tên Tk thô ("period", "Return").
2. `python -m eyepin shortcuts` sinh guide từ `~/.eyepin/settings.json` nên phím cá nhân lọt vào `design/shortcuts.md`; guide của file này
   phải sinh từ phím MẶC ĐỊNH.
3. Docstring đầu `eyepin/gui.py` còn phím cũ (S quét, E xuất, C/V ghim...): phải khớp phím mặc định ở `shortcuts.py`.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from eyepin import shortcuts as sc  # noqa: E402

READABLE = {"Space", "Esc", "Del", "Home", "End", "Tab", "Enter", "←", "→", "↑", "↓"}


class KeyNameTests(unittest.TestCase):
    def test_punctuation_and_return_have_readable_names(self):
        self.assertEqual(sc.pretty("<period>"), ".")
        self.assertEqual(sc.pretty("<comma>"), ",")
        self.assertEqual(sc.pretty("<greater>"), ">")
        self.assertEqual(sc.pretty("<less>"), "<")
        self.assertEqual(sc.pretty("<Return>"), "Enter")
        self.assertEqual(sc.pretty("<Control-Return>"), "Ctrl+Enter")

    def test_every_default_key_prints_a_readable_name(self):
        for a in sc.ACTIONS:
            for k in a.keys:
                shown = sc.pretty(k)
                last = shown.rsplit("+", 1)[-1] or "+"
                ok = len(last) == 1 or last in READABLE or re.fullmatch(r"F\d+", last)
                self.assertTrue(ok, f"{a.id}: phím {k} hiện thành {shown!r}")

    def test_guide_has_no_raw_tk_names(self):
        md = sc.guide_markdown()
        for raw in ("period", "comma", "greater", "less", "Return"):
            self.assertNotRegex(md.split("## Phím CVAT mà EyePin không có")[0], rf"\b{raw}\b")


class CliGuideIgnoresUserSettingsTests(unittest.TestCase):
    def run_cli(self, home, out):
        env = dict(os.environ, EYEPIN_HOME=home, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, "-m", "eyepin", "shortcuts", "--out", out], cwd=ROOT, env=env, capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        with open(out, encoding="utf-8", newline=None) as fh:
            return fh.read()

    def test_cli_guide_uses_default_keys_even_with_personal_settings(self):
        with tempfile.TemporaryDirectory(prefix="eyepin_b18_") as home:
            with open(os.path.join(home, "settings.json"), "w", encoding="utf-8") as fh:
                json.dump({"shortcuts": {"undo": ["<Control-q>"], "frame_next": ["j"]}}, fh)
            self.assertEqual(sc.bindings(sc.load_settings(__import__("pathlib").Path(home) / "settings.json"))["undo"], ("<Control-q>",))
            text = self.run_cli(home, os.path.join(home, "guide.md"))
        self.assertEqual(text.strip(), sc.guide_markdown().strip())
        self.assertNotIn("Ctrl+Q", text)
        self.assertIn("| Hoàn tác | Ctrl+Z |", text)


class GuiDocstringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import eyepin.gui as gui
        cls.doc = gui.__doc__

    @staticmethod
    def key(action_id):
        k = sc.pretty(sc.BY_ID[action_id].keys[0])
        return k.upper() if len(k) == 1 else k

    def described(self, key):
        """Các mô tả đứng ngay sau `key` + hai dấu cách trong docstring (tới dấu " · " kế hoặc hết dòng)."""
        out = []
        for ln in self.doc.splitlines():
            for m in re.finditer(r"(?<![\w+])" + re.escape(key) + "  ", ln):
                out.append(ln[m.end():].split(" · ")[0])
        return out

    def test_old_keys_are_gone(self):
        for key, old in (("S", "quét"), ("E", "xuất file import"), ("C/V", "frame ghim"), ("P", "ghim 4"), ("G", "ghim khi")):
            self.assertFalse([d for d in self.described(key) if d.startswith(old)], f"docstring còn phím cũ {key}  {old}")

    def test_documented_keys_match_the_defaults(self):
        want = {
            "export": "xuất file import", "scan": "quét", "next_keyframe": "frame ghim", "keyframe": "ghim", "undo": "hoàn tác",
            "occluded": "Occluded", "outside": "Outside", "fit": "khung tự động", "toggle_ids": "số điểm", "draw_eye": "vẽ",
            "draw_hidden": "khoé", "new_object": "mới", "cancel": "huỷ",
        }
        for action_id, phrase in want.items():
            key = self.key(action_id)
            self.assertTrue([d for d in self.described(key) if phrase in d], f"docstring thiếu {key!r} + {phrase!r} (hành động {action_id})")


if __name__ == "__main__":
    unittest.main()
