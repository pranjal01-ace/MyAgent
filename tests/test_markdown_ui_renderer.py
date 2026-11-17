"""
Unit Tests for Desktop Markdown & Pygments Code Output Renderer (Phase 2).
"""

import pytest
from desktop.markdown_renderer import (
    render_full_markdown,
    highlight_code_pygments,
    render_code_block,
    format_markdown_elements,
    format_markdown_tables,
    CodeRegistry,
    code_registry
)


class TestMarkdownRenderer:

    @pytest.fixture(autouse=True)
    def clean_registry(self):
        code_registry.clear()

    def test_heading_rendering(self):
        md = "# Main Header\n## Sub Header\n### Section"
        html = render_full_markdown(md)
        assert "Main Header" in html
        assert "Sub Header" in html
        assert "Section" in html
        assert "font-weight: 800" in html or "font-weight: 700" in html

    def test_bold_italic_inline_code(self):
        md = "This is **bold** and *italic* and `inline_code()`."
        html = render_full_markdown(md)
        assert "<b style=" in html and "bold</b>" in html
        assert "<i style=" in html and "italic</i>" in html
        assert "<code style=" in html and "inline_code()</code>" in html

    def test_lists_and_checklists(self):
        md = "- Item 1\n- Item 2\n- [x] Done Task\n- [ ] Pending Task"
        html = render_full_markdown(md)
        assert "• Item 1" in html
        assert "• Item 2" in html
        assert "☑" in html and "Done Task" in html
        assert "☐" in html and "Pending Task" in html

    def test_blockquotes_and_rules(self):
        md = "> Important notice\n---\nNormal text"
        html = render_full_markdown(md)
        assert "Important notice" in html
        assert "border-left: 3px solid" in html
        assert "<hr style=" in html

    def test_markdown_tables(self):
        md = (
            "| Method | Purpose |\n"
            "| --- | --- |\n"
            "| read() | Read file |\n"
            "| write() | Write file |"
        )
        html = render_full_markdown(md)
        assert "<table" in html
        assert "<th" in html and "Method" in html
        assert "<td" in html and "read()" in html

    def test_python_code_block_rendering(self):
        code = (
            "```python\n"
            "def calculate(a, b):\n"
            "    # Add numbers\n"
            "    return a + b\n"
            "```"
        )
        html = render_full_markdown(code)
        assert "Python" in html
        assert "copy_code:code_1" in html
        assert "📋 Copy" in html
        # Check that line numbers exist in html
        assert ">1</td>" in html
        assert ">2</td>" in html
        assert ">3</td>" in html
        # Check raw code in registry does NOT contain line numbers
        raw_stored = code_registry.get_code("code_1")
        assert raw_stored is not None
        assert "def calculate(a, b):" in raw_stored
        assert "return a + b" in raw_stored
        assert "1" not in raw_stored.splitlines()[0]

    def test_multilanguage_syntax_highlighting(self):
        languages = ["javascript", "sql", "bash", "json", "html", "css", "cpp"]
        for lang in languages:
            snippet = f"```{lang}\ncode line\n```"
            html = render_full_markdown(snippet)
            assert "copy_code:" in html

    def test_copy_code_preserves_indentation(self):
        indented_code = (
            "```python\n"
            "class MyClass:\n"
            "    def __init__(self):\n"
            "        self.x = 10\n"
            "        if self.x > 5:\n"
            "            print('Indented!')\n"
            "```"
        )
        render_full_markdown(indented_code)
        retrieved = code_registry.get_code("code_1")
        assert retrieved is not None
        lines = retrieved.strip().splitlines()
        assert lines[0] == "class MyClass:"
        assert lines[1] == "    def __init__(self):"
        assert lines[2] == "        self.x = 10"
        assert lines[3] == "        if self.x > 5:"
        assert lines[4] == "            print('Indented!')"

    def test_response_level_copy(self):
        msg = "Here is an explanation of the topic."
        html = render_full_markdown(msg)
        assert "copy_response:resp_1" in html
        assert "📄 Copy Response" in html
        assert code_registry.get_response("resp_1") == msg

    def test_streaming_unclosed_code_fence(self):
        # Incomplete stream chunk
        partial_md = "Here is code:\n```python\nprint('hello"
        html = render_full_markdown(partial_md, is_streaming=True)
        assert html is not None
        assert "Python" in html
        assert "print" in html

    def test_malformed_markdown_no_crash(self):
        malformed = "# Heading without text\n```\nUnclosed code\n| broken | table\n>>> weird\n`unclosed inline"
        html = render_full_markdown(malformed)
        assert isinstance(html, str)
        assert len(html) > 0
