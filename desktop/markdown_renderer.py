"""
Professional Markdown & Syntax Highlighted Code Output Renderer for Ace AI Companion.

Features:
- Full GitHub Flavored Markdown support (headings, bold, italic, lists, checklists, blockquotes, tables).
- Pygments syntax highlighting across 20+ languages with dark obsidian styling.
- Dedicated code block containers with language header, line numbers, and interactive Copy links.
- Code registry storing raw source code (line numbers strictly excluded from clipboard copy).
- Response-level copy action.
- Resilient streaming renderer (safely renders unclosed code fences without crashing).
"""

import re
import html
from typing import Dict, Tuple, Optional
import pygments
from pygments.lexers import get_lexer_by_name, guess_lexer, TextLexer
from pygments.formatters import HtmlFormatter

# Pre-compiled regex patterns
CODE_BLOCK_PATTERN = re.compile(r"```([a-zA-Z0-9_\-\.\+#]*)\n(.*?)```", re.DOTALL)
UNCLOSED_CODE_BLOCK_PATTERN = re.compile(r"```([a-zA-Z0-9_\-\.\+#]*)\n(.*)$", re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"`([^`\n]+)`")
BOLD_PATTERN = re.compile(r"\*\*([^\*\n]+)\*\*")
ITALIC_PATTERN = re.compile(r"(?<!\*)\*([^\*\n]+)\*(?!\*)")
STRIKE_PATTERN = re.compile(r"~~([^~\n]+)~~")
CHECKLIST_CHECKED_PATTERN = re.compile(r"^(\s*)-\s*\[[xX]\]\s+(.*)$", re.MULTILINE)
CHECKLIST_UNCHECKED_PATTERN = re.compile(r"^(\s*)-\s*\[\s\]\s+(.*)$", re.MULTILINE)
TABLE_ROW_PATTERN = re.compile(r"^\|(.+)\|$")

# Friendly language name mappings
LANGUAGE_NAMES = {
    "python": "Python",
    "py": "Python",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "jsx": "JSX",
    "tsx": "TSX",
    "html": "HTML",
    "css": "CSS",
    "json": "JSON",
    "sql": "SQL",
    "bash": "Bash",
    "sh": "Shell",
    "shell": "Shell",
    "zsh": "Zsh",
    "powershell": "PowerShell",
    "ps1": "PowerShell",
    "markdown": "Markdown",
    "md": "Markdown",
    "yaml": "YAML",
    "yml": "YAML",
    "xml": "XML",
    "c": "C",
    "cpp": "C++",
    "c++": "C++",
    "csharp": "C#",
    "cs": "C#",
    "java": "Java",
    "php": "PHP",
    "rust": "Rust",
    "rs": "Rust",
    "go": "Go",
    "golang": "Go",
    "ruby": "Ruby",
    "rb": "Ruby",
    "dockerfile": "Dockerfile",
    "text": "Plain Text",
    "txt": "Plain Text"
}

# Lexer alias mappings
LEXER_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
    "ps1": "powershell",
    "c++": "cpp",
    "cs": "csharp",
    "rs": "rust",
    "yml": "yaml",
    "md": "markdown",
    "golang": "go",
    "rb": "ruby"
}


class CodeRegistry:
    """Stores raw code snippets and assistant responses indexed by unique IDs for clipboard copying."""

    def __init__(self):
        self._code_snippets: Dict[str, str] = {}
        self._response_texts: Dict[str, str] = {}
        self._code_counter = 0
        self._response_counter = 0

    def register_code(self, raw_code: str) -> str:
        self._code_counter += 1
        cid = f"code_{self._code_counter}"
        self._code_snippets[cid] = raw_code
        return cid

    def get_code(self, cid: str) -> Optional[str]:
        return self._code_snippets.get(cid)

    def register_response(self, raw_text: str) -> str:
        self._response_counter += 1
        rid = f"resp_{self._response_counter}"
        self._response_texts[rid] = raw_text
        return rid

    def get_response(self, rid: str) -> Optional[str]:
        return self._response_texts.get(rid)

    def clear(self):
        self._code_snippets.clear()
        self._response_texts.clear()
        self._code_counter = 0
        self._response_counter = 0


# Global shared registry for the active chat session
code_registry = CodeRegistry()


def highlight_code_pygments(code: str, lang: str) -> str:
    """Highlights code using Pygments with inline styles compatible with PyQt5 rich text."""
    clean_lang = (lang or "").lower().strip()
    clean_lang = LEXER_ALIASES.get(clean_lang, clean_lang)

    try:
        if clean_lang:
            lexer = get_lexer_by_name(clean_lang, stripall=False)
        else:
            lexer = guess_lexer(code)
    except Exception:
        lexer = TextLexer(stripall=False)

    # Use inline styles (noclasses=True) with monokai theme
    formatter = HtmlFormatter(nowrap=True, noclasses=True, style="monokai")
    try:
        highlighted = pygments.highlight(code, lexer, formatter)
        return highlighted
    except Exception:
        return html.escape(code)


def render_code_block(raw_code: str, lang: str, registry: CodeRegistry = code_registry) -> str:
    """
    Renders a complete, dedicated code container with:
    - Language header label
    - Interactive [ Copy ] button anchor
    - Line numbers (multi-line) in a separate non-copyable column
    - Horizontal scroll container
    - Preserved whitespace and indentation
    """
    clean_lang = (lang or "").strip()
    display_lang = LANGUAGE_NAMES.get(clean_lang.lower(), clean_lang.capitalize() if clean_lang else "Code")

    # Register raw code for click-to-copy
    cid = registry.register_code(raw_code)

    # Highlight code
    highlighted_raw = highlight_code_pygments(raw_code, clean_lang)

    # Split lines for line numbering
    lines = highlighted_raw.split("\n")
    if lines and not lines[-1].strip():
        lines.pop()

    line_count = len(lines)
    is_multiline = line_count > 1

    if is_multiline:
        # Build 2-column table: Left = Line Numbers, Right = Code Lines
        table_rows = []
        for idx, line_content in enumerate(lines, start=1):
            table_rows.append(
                f"<tr>"
                f"<td style='user-select: none; -webkit-user-select: none; color: #475569; "
                f"text-align: right; padding-right: 12px; font-size: 11px; font-family: Consolas, monospace; "
                f"border-right: 1px solid #232a3b; vertical-align: top;'>{idx}</td>"
                f"<td style='padding-left: 12px; font-size: 11px; font-family: Consolas, monospace; "
                f"white-space: pre; vertical-align: top;'>{line_content if line_content else '&nbsp;'}</td>"
                f"</tr>"
            )
        inner_content = f"<table style='border-collapse: collapse; margin: 0; padding: 0;'>{''.join(table_rows)}</table>"
    else:
        single_line = lines[0] if lines else ""
        inner_content = f"<div style='font-size: 11px; font-family: Consolas, monospace; white-space: pre;'>{single_line}</div>"

    # Modern Dark Code Block HTML Container
    block_html = (
        f"<div style='background-color: #0f1219; border: 1px solid #22293a; border-radius: 8px; "
        f"margin: 8px 0; overflow-x: auto;'>"
        # Header Bar
        f"<div style='background-color: #171d2b; padding: 5px 12px; border-bottom: 1px solid #22293a; "
        f"border-top-left-radius: 7px; border-top-right-radius: 7px;'>"
        f"<table width='100%' style='border-collapse: collapse; margin: 0; padding: 0;'><tr>"
        f"<td align='left' style='color: #38bdf8; font-size: 10px; font-weight: 700; "
        f"text-transform: uppercase; letter-spacing: 0.5px;'>{html.escape(display_lang)}</td>"
        f"<td align='right'>"
        f"<a href='copy_code:{cid}' style='color: #94a3b8; text-decoration: none; font-size: 10px; "
        f"font-weight: 600; padding: 2px 8px; background-color: #21283b; border-radius: 4px; "
        f"border: 1px solid #2f3a54;'>📋 Copy</a>"
        f"</td>"
        f"</tr></table>"
        f"</div>"
        # Code Body
        f"<div style='padding: 10px 12px; overflow-x: auto; color: #f8fafc; line-height: 1.5; "
        f"white-space: pre; font-family: Consolas, \"JetBrains Mono\", monospace;'>"
        f"{inner_content}"
        f"</div>"
        f"</div>"
    )
    return block_html


def format_markdown_tables(text: str) -> str:
    """Parses markdown table syntax into styled HTML tables with dark theme aesthetics."""
    lines = text.split("\n")
    output_lines = []
    in_table = False
    table_rows = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            in_table = True
            # Check if this is a separator row e.g. |---|---| or |:---|:---|
            if re.match(r"^\|(\s*:?-+:?\s*\|)+$", stripped):
                continue
            cells = [c.strip() for c in stripped[1:-1].split("|")]
            table_rows.append(cells)
        else:
            if in_table:
                # Flush table
                output_lines.append(_build_table_html(table_rows))
                table_rows = []
                in_table = False
            output_lines.append(line)

    if in_table and table_rows:
        output_lines.append(_build_table_html(table_rows))

    return "\n".join(output_lines)


def _build_table_html(rows: list) -> str:
    if not rows:
        return ""

    header = rows[0]
    data_rows = rows[1:]

    html_parts = [
        "<div style='overflow-x: auto; margin: 8px 0;'>",
        "<table style='border-collapse: collapse; width: 100%; border: 1px solid #22293a; "
        "border-radius: 6px; font-size: 11px;'>",
        "<thead><tr style='background-color: #171d2b;'>"
    ]
    for h in header:
        html_parts.append(
            f"<th style='padding: 6px 10px; border: 1px solid #22293a; color: #38bdf8; "
            f"font-weight: 700; text-align: left;'>{html.escape(h)}</th>"
        )
    html_parts.append("</tr></thead><tbody>")

    for idx, row in enumerate(data_rows):
        bg = "#121622" if idx % 2 == 0 else "#0e111a"
        html_parts.append(f"<tr style='background-color: {bg};'>")
        for cell in row:
            html_parts.append(
                f"<td style='padding: 6px 10px; border: 1px solid #22293a; color: #e2e8f0;'>"
                f"{html.escape(cell)}</td>"
            )
        html_parts.append("</tr>")

    html_parts.append("</tbody></table></div>")
    return "".join(html_parts)


def format_markdown_elements(text: str) -> str:
    """Formats markdown headings, blockquotes, lists, checklists, bold, italic, and inline code."""
    # 1. Tables
    text = format_markdown_tables(text)

    # 2. Checklists
    text = CHECKLIST_CHECKED_PATTERN.sub(r"\1<span style='color: #10b981; font-weight: bold;'>☑</span> \2", text)
    text = CHECKLIST_UNCHECKED_PATTERN.sub(r"\1<span style='color: #64748b;'>☐</span> \2", text)

    # 3. Headings
    text = re.sub(
        r"^### (.*)$",
        r"<div style='color: #7dd3fc; font-size: 13px; font-weight: 700; margin: 8px 0 4px 0;'>\1</div>",
        text,
        flags=re.MULTILINE
    )
    text = re.sub(
        r"^## (.*)$",
        r"<div style='color: #38bdf8; font-size: 14px; font-weight: 700; margin: 10px 0 5px 0; border-bottom: 1px solid #202738; padding-bottom: 3px;'>\1</div>",
        text,
        flags=re.MULTILINE
    )
    text = re.sub(
        r"^# (.*)$",
        r"<div style='color: #f8fafc; font-size: 16px; font-weight: 800; margin: 12px 0 6px 0; border-bottom: 1px solid #263147; padding-bottom: 4px;'>\1</div>",
        text,
        flags=re.MULTILINE
    )

    # 4. Blockquotes
    text = re.sub(
        r"^>\s+(.*)$",
        r"<div style='border-left: 3px solid #38bdf8; background-color: #121622; padding: 4px 10px; margin: 6px 0; color: #cbd5e1; font-style: italic; border-radius: 2px;'>\1</div>",
        text,
        flags=re.MULTILINE
    )

    # 5. Horizontal rules
    text = re.sub(r"^---+$", r"<hr style='border: none; border-top: 1px solid #202738; margin: 10px 0;'>", text, flags=re.MULTILINE)

    # 6. Unordered and ordered lists
    text = re.sub(r"^\s*[\*\-]\s+(.*)$", r"<div style='margin-left: 12px; margin-top: 2px;'>• \1</div>", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*(\d+)\.\s+(.*)$", r"<div style='margin-left: 12px; margin-top: 2px;'><b style='color: #94a3b8;'>\1.</b> \2</div>", text, flags=re.MULTILINE)

    # 7. Inline code: `var`
    text = INLINE_CODE_PATTERN.sub(
        r"<code style='background-color: #171d2b; color: #38bdf8; padding: 2px 6px; border-radius: 4px; font-family: Consolas, monospace; font-size: 11px; border: 1px solid #252f45;'>\1</code>",
        text
    )

    # 8. Bold & Italic & Strike
    text = BOLD_PATTERN.sub(r"<b style='color: #ffffff; font-weight: 700;'>\1</b>", text)
    text = ITALIC_PATTERN.sub(r"<i style='color: #cbd5e1;'>\1</i>", text)
    text = STRIKE_PATTERN.sub(r"<s style='color: #64748b;'>\1</s>", text)

    # 9. Clean linebreaks outside divs/tables
    text = text.replace("\n", "<br>")
    return text


def render_full_markdown(raw_text: str, is_streaming: bool = False, registry: CodeRegistry = code_registry) -> str:
    """
    Converts complete markdown text into rich developer HTML:
    - Extracts and highlights code blocks with Pygments, line numbers, and Copy anchors
    - Gracefully handles unclosed code blocks during streaming
    - Formats headings, tables, blockquotes, lists, bold, italic
    - Appends message-level Copy Response button
    """
    if not raw_text:
        return ""

    working_text = raw_text

    # Streaming tolerance: if an unclosed code block exists, temporarily close it
    if is_streaming and working_text.count("```") % 2 == 1:
        working_text += "\n```"

    parts = []
    last_idx = 0

    for match in CODE_BLOCK_PATTERN.finditer(working_text):
        pre_text = working_text[last_idx:match.start()]
        if pre_text:
            parts.append(format_markdown_elements(pre_text))

        lang = match.group(1).strip()
        code_body = match.group(2)
        parts.append(render_code_block(code_body, lang, registry))
        last_idx = match.end()

    remaining = working_text[last_idx:]
    if remaining:
        parts.append(format_markdown_elements(remaining))

    formatted_body = "".join(parts)

    # Register response for response-level copy
    if not is_streaming:
        rid = registry.register_response(raw_text)
        action_footer = (
            f"<div style='margin-top: 8px; padding-top: 4px;'>"
            f"<a href='copy_response:{rid}' style='color: #64748b; text-decoration: none; font-size: 10px; "
            f"font-weight: 600; padding: 2px 6px; background-color: #121622; border-radius: 4px; "
            f"border: 1px solid #1f2738;'>📄 Copy Response</a>"
            f"</div>"
        )
        formatted_body += action_footer

    return formatted_body
