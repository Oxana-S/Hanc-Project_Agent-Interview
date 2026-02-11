"""
Anketa Exporter — MD + Print-ready HTML for PDF export.
"""

from typing import Any, Optional


def export_markdown(anketa_md: str, company_name: str = "") -> tuple[bytes, str]:
    """
    Return markdown content as downloadable bytes.

    Returns: (content_bytes, filename)
    """
    safe_name = "".join(c for c in company_name if c.isalnum() or c in " _-")[:30].strip() or "anketa"
    filename = f"{safe_name}.md"
    return anketa_md.encode("utf-8"), filename


def export_print_html(anketa_md: str, company_name: str = "", session_type: str = "consultation") -> tuple[bytes, str]:
    """
    Convert anketa markdown to a styled HTML page optimized for browser print-to-PDF.

    Returns: (html_bytes, filename)
    """
    safe_name = "".join(c for c in company_name if c.isalnum() or c in " _-")[:30].strip() or "anketa"
    filename = f"{safe_name}.html"

    # Convert simple markdown to HTML (no external deps)
    html_body = _md_to_html(anketa_md)

    type_label = "Интервью" if session_type == "interview" else "Консультация"

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hanc.AI — {_escape(company_name or 'Анкета')}</title>
<style>
  @page {{ margin: 2cm; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    max-width: 800px; margin: 0 auto; padding: 2rem;
    color: #1a1a2e; line-height: 1.6; font-size: 14px;
  }}
  .header {{
    border-bottom: 2px solid #6366f1; padding-bottom: 1rem; margin-bottom: 2rem;
  }}
  .header h1 {{ color: #6366f1; margin: 0 0 0.25rem; font-size: 1.5rem; }}
  .header .meta {{ color: #666; font-size: 0.85rem; }}
  h2 {{ color: #312e81; border-bottom: 1px solid #e5e7eb; padding-bottom: 0.5rem; margin-top: 2rem; }}
  h3 {{ color: #4338ca; margin-top: 1.5rem; }}
  ul, ol {{ padding-left: 1.5rem; }}
  li {{ margin-bottom: 0.25rem; }}
  strong {{ color: #1e1b4b; }}
  .section {{ margin-bottom: 1.5rem; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
  th, td {{ border: 1px solid #e5e7eb; padding: 0.5rem 0.75rem; text-align: left; }}
  th {{ background: #f3f4f6; font-weight: 600; }}
  blockquote {{
    border-left: 3px solid #6366f1; margin: 1rem 0; padding: 0.5rem 1rem;
    background: #f8f7ff; font-style: italic;
  }}
  .print-btn {{
    position: fixed; top: 1rem; right: 1rem; padding: 0.5rem 1.5rem;
    background: #6366f1; color: white; border: none; border-radius: 0.5rem;
    cursor: pointer; font-size: 0.9rem; z-index: 100;
  }}
  .print-btn:hover {{ background: #4f46e5; }}
  @media print {{
    .print-btn {{ display: none; }}
    body {{ padding: 0; max-width: none; }}
  }}
</style>
</head>
<body>
<button class="print-btn" onclick="window.print()">Сохранить как PDF</button>
<div class="header">
  <h1>Hanc.AI — {_escape(company_name or 'Анкета')}</h1>
  <div class="meta">{type_label}</div>
</div>
{html_body}
</body>
</html>"""

    return html.encode("utf-8"), filename


def _escape(text: str) -> str:
    """HTML-escape a string."""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;"))


def _md_to_html(md: str) -> str:
    """
    Convert simple markdown to HTML. Handles:
    - # headings (h1-h4)
    - **bold**
    - *italic*
    - - list items
    - numbered lists
    - > blockquotes
    - empty lines → paragraph breaks
    """
    if not md:
        return "<p>Анкета пуста</p>"

    lines = md.split("\n")
    html_parts = []
    in_list = False
    in_ol = False
    in_blockquote = False

    for line in lines:
        stripped = line.strip()

        # Close open lists/quotes if needed
        if in_list and not stripped.startswith("- ") and not stripped.startswith("* "):
            html_parts.append("</ul>")
            in_list = False
        if in_ol and not (stripped and stripped[0].isdigit() and ". " in stripped[:4]):
            html_parts.append("</ol>")
            in_ol = False
        if in_blockquote and not stripped.startswith(">"):
            html_parts.append("</blockquote>")
            in_blockquote = False

        # Empty line
        if not stripped:
            continue

        # Headings
        if stripped.startswith("#### "):
            html_parts.append(f"<h4>{_inline(stripped[5:])}</h4>")
        elif stripped.startswith("### "):
            html_parts.append(f"<h3>{_inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            html_parts.append(f"<h2>{_inline(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            html_parts.append(f"<h1>{_inline(stripped[2:])}</h1>")
        # Blockquote
        elif stripped.startswith(">"):
            if not in_blockquote:
                html_parts.append("<blockquote>")
                in_blockquote = True
            html_parts.append(f"<p>{_inline(stripped[1:].strip())}</p>")
        # Unordered list
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{_inline(stripped[2:])}</li>")
        # Ordered list
        elif stripped and stripped[0].isdigit() and ". " in stripped[:4]:
            if not in_ol:
                html_parts.append("<ol>")
                in_ol = True
            text = stripped.split(". ", 1)[1] if ". " in stripped else stripped
            html_parts.append(f"<li>{_inline(text)}</li>")
        # Horizontal rule
        elif stripped in ("---", "***", "___"):
            html_parts.append("<hr>")
        # Regular paragraph
        else:
            html_parts.append(f"<p>{_inline(stripped)}</p>")

    # Close any open tags
    if in_list:
        html_parts.append("</ul>")
    if in_ol:
        html_parts.append("</ol>")
    if in_blockquote:
        html_parts.append("</blockquote>")

    return "\n".join(html_parts)


def _inline(text: str) -> str:
    """Process inline markdown: **bold**, *italic*."""
    import re
    text = _escape(text)
    # Bold: **text**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # Italic: *text*
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    return text
