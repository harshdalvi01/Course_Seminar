import json
import re
import html

def parse_code_files(raw_text):
    """
    Safely parses an AI code artifact into a structured list of file objects:
    [{'path': str, 'purpose': str, 'content': str}]
    Works even if the LLM output is wrapped in markdown or truncated.
    """
    if not raw_text or not isinstance(raw_text, str):
        return []

    # Clean markdown code fences if present
    cleaned = raw_text.strip()
    if '```' in cleaned:
        # Match inside ```json ... ``` or ``` ... ```
        m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*(?:```|\Z)', cleaned)
        if m:
            cleaned = m.group(1).strip()

    # Attempt 1: Standard JSON parse
    try:
        # Try finding array bounds
        start = cleaned.find('[')
        end = cleaned.rfind(']')
        json_candidate = cleaned[start:end+1] if (start != -1 and end != -1 and end > start) else cleaned
        data = json.loads(json_candidate)
        if isinstance(data, list):
            valid_files = [f for f in data if isinstance(f, dict) and 'path' in f]
            if valid_files:
                return valid_files
    except Exception:
        pass

    # Attempt 2: Line-by-line / structural extraction for truncated or malformed JSON
    files = []
    # Find all "path": "...", "purpose": "...", "content": "..."
    # We match each object block
    items = re.findall(r'\{\s*"path"\s*:\s*"([^"]+)"\s*,\s*"purpose"\s*:\s*"([^"]*)"\s*,\s*"content"\s*:\s*"(.*?)(?=(?:"\s*\},|\"\s*\}\s*\]|\"\s*\}\s*\Z))', cleaned, re.DOTALL)
    for path, purpose, content in items:
        # Unescape escaped characters in JSON string
        try:
            content = json.loads(f'"{content}"')
        except Exception:
            content = content.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\').replace('\\t', '\t')
        files.append({
            'path': path,
            'purpose': purpose,
            'content': content
        })

    if files:
        return files

    # Attempt 3: If still empty, try extracting "path": "..." items more loosely
    path_blocks = re.split(r'\{\s*"path"\s*:\s*"', cleaned)
    for block in path_blocks[1:]:
        try:
            path_part, rest = block.split('"', 1)
            purpose = ""
            if '"purpose":' in rest:
                p_match = re.search(r'"purpose"\s*:\s*"([^"]*)"', rest)
                if p_match:
                    purpose = p_match.group(1)
            content = ""
            if '"content":' in rest:
                c_match = re.search(r'"content"\s*:\s*"([\s\S]*?)(?=(?:"\s*\}|\Z))', rest)
                if c_match:
                    content_raw = c_match.group(1)
                    content = content_raw.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
            files.append({
                'path': path_part.strip(),
                'purpose': purpose.strip(),
                'content': content
            })
        except Exception:
            continue

    return files


def format_inline_markdown(text):
    """
    Escapes raw text and renders inline Markdown formatting:
    `code`, **bold**, *italic*, and key badges.
    """
    if not text:
        return ""
    # Normalize unicode non-breaking hyphens / dashes to standard hyphens
    text = text.replace('\u2011', '-').replace('\u2013', '-').replace('\u2014', '--')
    escaped = html.escape(text)

    # Inline code: `code`
    escaped = re.sub(r'`([^`]+)`', r'<code class="req-inline-code">\1</code>', escaped)

    # Bold: **text** or __text__
    escaped = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', escaped)
    escaped = re.sub(r'__([^_]+)__', r'<strong>\1</strong>', escaped)

    # Italic: *text* or _text_
    escaped = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', escaped)
    escaped = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'<em>\1</em>', escaped)

    return escaped


def render_markdown_table(lines):
    """
    Renders markdown pipe table lines into responsive, clean HTML tables
    with priority badges, monospace ID chips, and hover highlights.
    """
    if len(lines) < 2:
        return ""

    raw_header = lines[0].strip().strip('|')
    headers = [c.strip() for c in raw_header.split('|')]
    if not headers or all(h == '' for h in headers):
        return ""

    # Detect special column positions
    priority_col = -1
    id_col = -1
    category_col = -1
    for i, h in enumerate(headers):
        h_lower = h.lower()
        if 'priority' in h_lower:
            priority_col = i
        elif h_lower in ['id', 'req id', 'fr id', 'ac id', 'criterion id']:
            id_col = i
        elif h_lower in ['category', 'role', 'type']:
            category_col = i

    html_parts = ['<div class="req-table-wrapper"><table class="req-table"><thead><tr>']
    for h in headers:
        html_parts.append(f'<th>{format_inline_markdown(h)}</th>')
    html_parts.append('</tr></thead><tbody>')

    # Data rows (skipping divider line at index 1)
    for line in lines[2:]:
        line_clean = line.strip()
        if not line_clean or '|' not in line_clean:
            continue
        cells = [c.strip() for c in line_clean.strip('|').split('|')]
        while len(cells) < len(headers):
            cells.append('')

        html_parts.append('<tr>')
        for idx, cell in enumerate(cells[:len(headers)]):
            cell_formatted = format_inline_markdown(cell)

            # Special badge styling for priority
            if idx == priority_col:
                clean_p = cell.strip('*- ').lower()
                if 'high' in clean_p:
                    cell_formatted = '<span class="req-priority req-priority-high">HIGH</span>'
                elif 'med' in clean_p:
                    cell_formatted = '<span class="req-priority req-priority-medium">MEDIUM</span>'
                elif 'low' in clean_p:
                    cell_formatted = '<span class="req-priority req-priority-low">LOW</span>'
            # Special badge styling for IDs (e.g. FR-01, AC-01)
            elif idx == id_col and cell.strip():
                clean_id = re.sub(r'[*_`]', '', cell).strip()
                cell_formatted = f'<span class="req-id-pill">{html.escape(clean_id)}</span>'
            # Special badge styling for Categories / Roles
            elif idx == category_col and cell.strip():
                clean_cat = re.sub(r'[*_`]', '', cell).strip()
                cell_formatted = f'<strong class="req-cat-pill">{html.escape(clean_cat)}</strong>'

            html_parts.append(f'<td>{cell_formatted}</td>')
        html_parts.append('</tr>')

    html_parts.append('</tbody></table></div>')
    return "".join(html_parts)


def render_content_blocks(content_text):
    """
    Parses section content into clean HTML elements:
    tables, lists, key-value rows, blockquotes, subheadings, and paragraphs.
    """
    if not content_text:
        return ""

    lines = content_text.strip().split('\n')
    blocks = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        line_strip = line.strip()

        # Blank line
        if not line_strip:
            i += 1
            continue

        # Horizontal divider
        if re.match(r'^(?:-{3,}|\*{3,}|_{3,})$', line_strip):
            blocks.append('<hr class="req-divider">')
            i += 1
            continue

        # Markdown table detection
        if '|' in line_strip and (i + 1 < n and re.match(r'^\s*\|?\s*[-:]+[-| :]*\|?\s*$', lines[i + 1].strip())):
            table_lines = [line_strip]
            i += 1
            table_lines.append(lines[i].strip())  # divider line
            i += 1
            while i < n and '|' in lines[i].strip() and lines[i].strip():
                table_lines.append(lines[i].strip())
                i += 1
            rendered_tbl = render_markdown_table(table_lines)
            if rendered_tbl:
                blocks.append(rendered_tbl)
            continue

        # Sub-headings: ##, ###, ####
        sub_heading = re.match(r'^(#{2,4})\s+(.*)$', line_strip)
        if sub_heading:
            level = len(sub_heading.group(1))
            htext = format_inline_markdown(sub_heading.group(2).strip())
            blocks.append(f'<h{level} class="req-subheading req-h{level}">{htext}</h{level}>')
            i += 1
            continue

        # Unordered list: starts with - , * , +
        if re.match(r'^[-*+]\s+', line_strip):
            list_items = []
            while i < n and re.match(r'^\s*[-*+]\s+', lines[i]):
                item_text = re.sub(r'^\s*[-*+]\s+', '', lines[i]).strip()
                list_items.append(f'<li>{format_inline_markdown(item_text)}</li>')
                i += 1
            blocks.append(f'<ul class="req-list req-ul">{"".join(list_items)}</ul>')
            continue

        # Ordered list: starts with 1. , 2. etc
        if re.match(r'^\d+\.\s+', line_strip):
            list_items = []
            while i < n and re.match(r'^\s*\d+\.\s+', lines[i]):
                item_text = re.sub(r'^\s*\d+\.\s+', '', lines[i]).strip()
                list_items.append(f'<li>{format_inline_markdown(item_text)}</li>')
                i += 1
            blocks.append(f'<ol class="req-list req-ol">{"".join(list_items)}</ol>')
            continue

        # Blockquote: starts with >
        if line_strip.startswith('>'):
            quote_lines = []
            while i < n and lines[i].strip().startswith('>'):
                quote_lines.append(re.sub(r'^\s*>\s?', '', lines[i].strip()))
                i += 1
            q_text = format_inline_markdown(" ".join(quote_lines))
            blocks.append(f'<blockquote class="req-blockquote">{q_text}</blockquote>')
            continue

        # Key-Value spec item: **Key:** Value
        kv_match = re.match(r'^\*\*([^*:]+):\*\*\s*(.*)$', line_strip)
        if kv_match:
            k_name = format_inline_markdown(kv_match.group(1).strip())
            v_val = format_inline_markdown(kv_match.group(2).strip())
            if v_val:
                blocks.append(
                    f'<div class="req-kv-card">'
                    f'<span class="req-kv-label">{k_name}:</span> '
                    f'<span class="req-kv-value">{v_val}</span>'
                    f'</div>'
                )
            else:
                blocks.append(f'<h4 class="req-block-heading">{k_name}</h4>')
            i += 1
            continue

        # Standard paragraph
        p_lines = [line_strip]
        i += 1
        while (
            i < n
            and lines[i].strip()
            and not lines[i].strip().startswith('#')
            and not (
                '|' in lines[i].strip()
                and (i + 1 < n and re.match(r'^\s*\|?\s*[-:]+[-| :]*\|?\s*$', lines[i + 1].strip()))
            )
            and not re.match(r'^[-*+]\s+', lines[i].strip())
            and not re.match(r'^\d+\.\s+', lines[i].strip())
            and not lines[i].strip().startswith('>')
            and not re.match(r'^(?:-{3,}|\*{3,}|_{3,})$', lines[i].strip())
            and not re.match(r'^\*\*([^*:]+):\*\*', lines[i].strip())
        ):
            p_lines.append(lines[i].strip())
            i += 1
        p_text = format_inline_markdown(" ".join(p_lines))
        blocks.append(f'<p class="req-p">{p_text}</p>')

    return "\n".join(blocks)


def parse_requirements_doc(raw_text):
    """
    Parses a requirements markdown specification into structured section objects
    with rich HTML rendering, table formatting, and metadata badges.
    """
    if not raw_text or not isinstance(raw_text, str):
        return None

    cleaned = raw_text.strip()
    if not cleaned:
        return None

    # Normalize unicode non-breaking hyphens / dashes throughout the document
    cleaned = cleaned.replace('\u2011', '-').replace('\u2013', '-').replace('\u2014', '--')

    def get_section_meta(title):
        t_lower = title.lower()
        if any(w in t_lower for w in ['overview', 'project', 'introduction']):
            return '📋', 'OVERVIEW', 'Core scope, goals & operational boundaries'
        elif 'functional' in t_lower and 'non' not in t_lower:
            return '⚡', 'FUNCTIONAL', 'System capabilities & user action specifications'
        elif any(w in t_lower for w in ['non-functional', 'non?functional', 'quality', 'security']):
            return '🛡️', 'NON-FUNCTIONAL', 'Performance, security, portability & reliability SLAs'
        elif any(w in t_lower for w in ['role', 'user', 'actor', 'persona']):
            return '👥', 'ROLES', 'Actor personas, authentication & access permissions'
        elif 'feature' in t_lower:
            return '🧩', 'FEATURES', 'Primary operational workflows & feature breakdown'
        elif any(w in t_lower for w in ['constraint', 'limitation']):
            return '⛔', 'CONSTRAINTS', 'Technical boundaries, runtime limitations & storage limits'
        elif any(w in t_lower for w in ['acceptance', 'criteria', 'test']):
            return '✅', 'ACCEPTANCE', 'Verifiable test conditions & user acceptance gates'
        elif 'assumption' in t_lower:
            return '💡', 'ASSUMPTIONS', 'Operational prerequisites & client context baselines'
        elif any(w in t_lower for w in ['question', 'open question']):
            return '❓', 'DISCOVERY', 'Unresolved architectural decisions & discovery items'
        else:
            return '📄', 'SPECIFICATION', 'Structured requirement specification module'

    # Split into sections by top-level Markdown headings (# or ##)
    section_chunks = re.split(r'\n(?=#\s+|\n##\s+)', cleaned)
    sections = []

    for idx, chunk in enumerate(section_chunks):
        chunk_clean = chunk.strip()
        if not chunk_clean:
            continue

        first_line = chunk_clean.split('\n', 1)[0].strip()
        body = chunk_clean.split('\n', 1)[1].strip() if '\n' in chunk_clean else ""

        # Extract title from heading
        heading_match = re.match(r'^#{1,3}\s+(.*)$', first_line)
        if heading_match:
            full_title = heading_match.group(1).strip()
            num_match = re.match(r'^(\d+)\.\s*(.*)$', full_title)
            if num_match:
                num = num_match.group(1)
                title = num_match.group(2).strip()
            else:
                num = str(idx + 1)
                title = full_title
        else:
            num = str(idx + 1)
            title = f"Section {num}"
            full_title = title
            body = chunk_clean

        icon, tag, summary = get_section_meta(title)
        has_table = '|' in body
        html_content = render_content_blocks(body)

        sections.append({
            'id': f'sec-{idx}',
            'index': idx,
            'num': num,
            'title': title,
            'full_title': full_title,
            'icon': icon,
            'tag': tag,
            'summary': summary,
            'has_table': has_table,
            'html_content': html_content,
            'raw_content': chunk_clean,
        })

    if not sections:
        html_content = render_content_blocks(cleaned)
        sections.append({
            'id': 'sec-0',
            'index': 0,
            'num': '1',
            'title': 'Requirements Specification',
            'full_title': 'Requirements Specification',
            'icon': '📋',
            'tag': 'SPECIFICATION',
            'summary': 'General requirement specifications',
            'has_table': '|' in cleaned,
            'html_content': html_content,
            'raw_content': cleaned,
        })

    return {
        'sections': sections,
        'total_sections': len(sections),
        'has_tables': any(s['has_table'] for s in sections),
        'raw_content': cleaned,
    }

