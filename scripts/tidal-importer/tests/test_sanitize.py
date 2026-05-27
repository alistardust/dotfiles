"""Tests for sanitize.py."""
from tidal_importer.sanitize import sanitize_for_terminal, sanitize_exception, truncate


class TestSanitizeForTerminal:
    def test_strips_csi_color_codes(self):
        assert sanitize_for_terminal("\x1b[31mRed Text\x1b[0m") == "Red Text"

    def test_strips_osc_title_change(self):
        assert sanitize_for_terminal("\x1b]0;evil title\x07Normal") == "Normal"

    def test_strips_cursor_movement(self):
        assert sanitize_for_terminal("\x1b[2J\x1b[HCleared") == "Cleared"

    def test_preserves_normal_text(self):
        assert sanitize_for_terminal("Hello World") == "Hello World"

    def test_preserves_unicode_printable(self):
        assert sanitize_for_terminal("Cafe\u0301") == "Cafe\u0301"

    def test_strips_null_bytes(self):
        assert sanitize_for_terminal("Hello\x00World") == "HelloWorld"

    def test_preserves_newlines_and_tabs(self):
        assert sanitize_for_terminal("Line1\nLine2\tTabbed") == "Line1\nLine2\tTabbed"

    def test_empty_string(self):
        assert sanitize_for_terminal("") == ""


class TestSanitizeException:
    def test_redacts_access_token(self):
        result = sanitize_exception(Exception("access_token=abc123xyz"))
        assert "abc123xyz" not in result
        assert "<REDACTED>" in result

    def test_redacts_bearer(self):
        result = sanitize_exception(Exception("Authorization: Bearer eyJhbGciOiJ"))
        assert "eyJhbGciOiJ" not in result
        assert "<REDACTED>" in result

    def test_preserves_non_token_message(self):
        result = sanitize_exception(Exception("Connection refused"))
        assert result == "Connection refused"

    def test_redacts_refresh_token(self):
        result = sanitize_exception(Exception("refresh_token: secret123"))
        assert "secret123" not in result


class TestTruncate:
    def test_short_string_unchanged(self):
        assert truncate("hello", 500) == "hello"

    def test_long_string_truncated(self):
        long_s = "a" * 600
        result = truncate(long_s, 500)
        assert len(result) == 500

    def test_exact_length_unchanged(self):
        s = "x" * 500
        assert truncate(s, 500) == s

    def test_empty_string(self):
        assert truncate("", 500) == ""
