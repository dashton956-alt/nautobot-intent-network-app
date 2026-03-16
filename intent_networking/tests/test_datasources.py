"""Unit tests for intent_networking.datasources module.

Tests the .intentignore helpers (_load_ignore_patterns, _is_ignored)
which are pure functions with no Django/Nautobot dependencies.
"""

import os
import tempfile

from django.test import SimpleTestCase

from intent_networking.datasources import (
    INTENTIGNORE_FILENAME,
    _is_ignored,
    _load_ignore_patterns,
)

# ─────────────────────────────────────────────────────────────────────────────
# _load_ignore_patterns
# ─────────────────────────────────────────────────────────────────────────────


class LoadIgnorePatternsTest(SimpleTestCase):
    """Test _load_ignore_patterns() file parsing."""

    def test_no_file_returns_empty(self):
        """No .intentignore → empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_load_ignore_patterns(tmp), [])

    def test_single_file_basic_patterns(self):
        """Parse patterns, skip blank lines and comments."""
        with tempfile.TemporaryDirectory() as tmp:
            ignore = os.path.join(tmp, INTENTIGNORE_FILENAME)
            with open(ignore, "w") as fh:
                fh.write("# comment line\n")
                fh.write("\n")
                fh.write("tests/**\n")
                fh.write("scratch_*.yaml\n")
                fh.write("  \n")
                fh.write("# another comment\n")
                fh.write("archive/*.json\n")

            patterns = _load_ignore_patterns(tmp)
            self.assertEqual(patterns, ["tests/**", "scratch_*.yaml", "archive/*.json"])

    def test_multiple_dirs_merged(self):
        """Patterns from both directories are merged."""
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as child:
            with open(os.path.join(root, INTENTIGNORE_FILENAME), "w") as fh:
                fh.write("root_pattern\n")
            with open(os.path.join(child, INTENTIGNORE_FILENAME), "w") as fh:
                fh.write("child_pattern\n")

            patterns = _load_ignore_patterns(root, child)
            self.assertEqual(patterns, ["root_pattern", "child_pattern"])

    def test_duplicates_removed(self):
        """Duplicate patterns across files are de-duplicated."""
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as child:
            with open(os.path.join(root, INTENTIGNORE_FILENAME), "w") as fh:
                fh.write("same_pattern\n")
            with open(os.path.join(child, INTENTIGNORE_FILENAME), "w") as fh:
                fh.write("same_pattern\n")
                fh.write("unique_pattern\n")

            patterns = _load_ignore_patterns(root, child)
            self.assertEqual(patterns, ["same_pattern", "unique_pattern"])

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is stripped from lines."""
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, INTENTIGNORE_FILENAME), "w") as fh:
                fh.write("  pattern_a  \n")
                fh.write("\tpattern_b\t\n")

            patterns = _load_ignore_patterns(tmp)
            self.assertEqual(patterns, ["pattern_a", "pattern_b"])

    def test_empty_file_returns_empty(self):
        """An .intentignore with only comments and blanks → empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, INTENTIGNORE_FILENAME), "w") as fh:
                fh.write("# only comments\n")
                fh.write("\n")
                fh.write("  \n")

            self.assertEqual(_load_ignore_patterns(tmp), [])


# ─────────────────────────────────────────────────────────────────────────────
# _is_ignored
# ─────────────────────────────────────────────────────────────────────────────


class IsIgnoredTest(SimpleTestCase):
    """Test _is_ignored() pattern matching."""

    def test_no_patterns_never_ignored(self):
        """With no patterns, nothing is ignored."""
        self.assertFalse(_is_ignored("any/file.yaml", []))

    def test_exact_filename_match(self):
        """Pattern matching exact filename."""
        self.assertTrue(_is_ignored("intent_a.yaml", ["intent_a.yaml"]))

    def test_wildcard_extension(self):
        """Glob *.json matches any .json file."""
        self.assertTrue(_is_ignored("some/path/data.json", ["*.json"]))
        self.assertFalse(_is_ignored("some/path/data.yaml", ["*.json"]))

    def test_directory_glob(self):
        """Pattern with directory wildcard matches nested paths."""
        patterns = ["tests/*"]
        self.assertTrue(_is_ignored("tests/fixture.yaml", patterns))
        self.assertFalse(_is_ignored("production/intent.yaml", patterns))

    def test_double_star_glob(self):
        """Double-star matches multiple levels."""
        patterns = ["**/scratch/**"]
        self.assertTrue(_is_ignored("a/scratch/b.yaml", patterns))
        self.assertTrue(_is_ignored("scratch/x.yaml", patterns))

    def test_prefix_pattern(self):
        """test_* matches files starting with test_."""
        patterns = ["test_*"]
        self.assertTrue(_is_ignored("test_fixture.yaml", patterns))
        self.assertTrue(_is_ignored("sub/test_data.json", patterns))
        self.assertFalse(_is_ignored("sub/production.yaml", patterns))

    def test_multiple_patterns(self):
        """File matching any pattern is ignored."""
        patterns = ["*.json", "draft_*"]
        self.assertTrue(_is_ignored("data.json", patterns))
        self.assertTrue(_is_ignored("draft_intent.yaml", patterns))
        self.assertFalse(_is_ignored("production.yaml", patterns))

    def test_no_match_returns_false(self):
        """File not matching any pattern is not ignored."""
        self.assertFalse(_is_ignored("real_intent.yaml", ["test_*", "*.json"]))

    def test_path_separator_normalised(self):
        """Backslash separators are normalised to forward slashes."""
        patterns = ["subdir/*"]
        # Simulate a Windows-style path
        self.assertTrue(_is_ignored("subdir\\file.yaml", patterns))
