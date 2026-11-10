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


def is_ascii_flowchart(text, lang=''):
    """
    Detects if a code block is an ASCII architecture diagram, flowchart, or component topology.
    """
    lang_lower = (lang or '').lower().strip()
    if lang_lower in ['ascii', 'diagram', 'flowchart', 'topology']:
        return True
    
    # Check for ASCII box drawing patterns and flow connectors
    has_box_corners = bool(re.search(r'\+[-=]{2,}\+', text))
    has_vertical_bars = text.count('|') >= 3
    has_flow_arrows = bool(re.search(r'(?:-->|<--|<-+>|-+>|\|\s*v|\^\s*\||\+-->|\+--\^)', text))
    has_tree_branches = bool(re.search(r'[+`]---|\|   \+--', text))
    
    if has_box_corners and (has_vertical_bars or has_flow_arrows):
        return True
    if has_flow_arrows and has_vertical_bars:
        return True
    if has_tree_branches:
        return True
    return False


def render_mermaid_diagram(code_text):
    """
    Renders a Mermaid flowchart / sequence diagram container with copy action
    and interactive SVG rendering support.
    """
    raw_code = sanitize_mermaid_source(code_text.strip())
    escaped_code = html.escape(raw_code)

    diag_type = "FLOWCHART / SEQUENCE DIAGRAM"
    if "sequenceDiagram" in raw_code:
        diag_type = "INTERACTIVE SEQUENCE FLOWCHART"
    elif "flowchart" in raw_code or "graph " in raw_code:
        diag_type = "INTERACTIVE COMPONENT FLOWCHART"
    elif "classDiagram" in raw_code:
        diag_type = "CLASS ARCHITECTURE DIAGRAM"
    elif "stateDiagram" in raw_code:
        diag_type = "STATE MACHINE FLOWCHART"
    elif "erDiagram" in raw_code:
        diag_type = "ENTITY RELATIONSHIP DIAGRAM"

    return (
        f'<div class="flowchart-card mermaid-card">'
        f'  <div class="flowchart-card-header">'
        f'    <div class="flowchart-header-left">'
        f'      <span class="flowchart-pulse-dot"></span>'
        f'      <span class="flowchart-title">{diag_type}</span>'
        f'      <span class="flowchart-badge mermaid-badge">MERMAID.JS</span>'
        f'    </div>'
        f'    <div class="flowchart-actions">'
        f'      <button type="button" class="btn-flowchart-action" onclick="copyDiagramSource(this)">Copy Source</button>'
        f'    </div>'
        f'  </div>'
        f'  <textarea class="raw-diagram-code" style="display:none;">{escaped_code}</textarea>'
        f'  <div class="mermaid-canvas-wrapper">'
        f'    <pre class="mermaid">{escaped_code}</pre>'
        f'  </div>'
        f'</div>'
    )


def render_ascii_flowchart(code_text):
    """
    Renders an ASCII architecture / system topology diagram inside a high-contrast
    engineering blueprint card with fixed-width character alignment.
    """
    raw_code = code_text.rstrip()
    escaped_code = html.escape(raw_code)

    return (
        f'<div class="flowchart-card ascii-card">'
        f'  <div class="flowchart-card-header">'
        f'    <div class="flowchart-header-left">'
        f'      <span class="flowchart-pulse-dot ascii-dot blueprint-dot"></span>'
        f'      <span class="flowchart-title">SYSTEM ARCHITECTURE TOPOLOGY</span>'
        f'      <span class="flowchart-badge ascii-badge blueprint-badge">BLUEPRINT // FLOWCHART</span>'
        f'    </div>'
        f'    <div class="flowchart-actions">'
        f'      <button type="button" class="btn-flowchart-action" onclick="copyDiagramSource(this)">Copy Topology</button>'
        f'    </div>'
        f'  </div>'
        f'  <textarea class="raw-diagram-code" style="display:none;">{escaped_code}</textarea>'
        f'  <div class="ascii-canvas-wrapper">'
        f'    <pre class="ascii-diagram-pre">{escaped_code}</pre>'
        f'  </div>'
        f'</div>'
    )


def render_code_block(code_text, lang=''):
    """
    Renders a syntax specification code block with language indicator and copy action.
    """
    raw_code = code_text.rstrip()
    escaped_code = html.escape(raw_code)
    lang_label = (lang or 'CODE').upper()

    return (
        f'<div class="spec-code-card">'
        f'  <div class="spec-code-header">'
        f'    <span class="spec-code-lang">{lang_label} SPECIFICATION</span>'
        f'    <button type="button" class="btn-flowchart-action" onclick="copyDiagramSource(this)">Copy Code</button>'
        f'  </div>'
        f'  <textarea class="raw-diagram-code" style="display:none;">{escaped_code}</textarea>'
        f'  <div class="spec-code-wrapper">'
        f'    <pre class="spec-code-pre"><code>{escaped_code}</code></pre>'
        f'  </div>'
        f'</div>'
    )


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

        # Fenced code block or flowchart: starts with ```
        if line_strip.startswith('```'):
            lang = line_strip[3:].strip()
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            if i < n and lines[i].strip().startswith('```'):
                i += 1  # Skip closing ```
            code_text = "\n".join(code_lines)
            
            # Check what kind of code block this is
            if lang.lower() == 'mermaid' or any(k in code_text for k in ['sequenceDiagram', 'flowchart ', 'graph TD', 'graph LR', 'classDiagram', 'stateDiagram', 'erDiagram']):
                blocks.append(render_mermaid_diagram(code_text))
            elif is_ascii_flowchart(code_text, lang):
                blocks.append(render_ascii_flowchart(code_text))
            else:
                blocks.append(render_code_block(code_text, lang))
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


def sanitize_mermaid_source(code: str) -> str:
    """
    Normalizes unicode dashes/quotes and automatically quotes flowchart node/edge labels
    that contain parentheses, braces, or special characters so Mermaid.js parses cleanly.
    """
    if not code:
        return ""
    # 1. Normalize unicode hyphens, dashes, smart quotes
    cleaned = code.replace('\u2011', '-').replace('\u2013', '-').replace('\u2014', '--').replace('\u2212', '-')
    cleaned = cleaned.replace('\u201c', '"').replace('\u201d', '"').replace('\u2018', "'").replace('\u2019', "'")

    lines = cleaned.strip().splitlines()
    first_line = lines[0].strip().lower() if lines else ""
    if not (first_line.startswith('flowchart') or first_line.startswith('graph')):
        return cleaned

    # 2. Fix Stadium ID([label]) containing special chars
    def fix_stadium(m):
        node_id, label = m.group(1), m.group(2).strip()
        if label.startswith('"') and label.endswith('"'):
            return m.group(0)
        if any(c in label for c in '(){}[]:;,=+*?'):
            safe = label.replace('"', "'")
            return f'{node_id}(["{safe}"])'
        return m.group(0)
    cleaned = re.sub(r'(\b[A-Za-z0-9_-]+)\(\[([^\]\n]+?)\]\)', fix_stadium, cleaned)

    # 3. Fix Cylinder ID[(label)] containing special chars
    def fix_cylinder(m):
        node_id, label = m.group(1), m.group(2).strip()
        if label.startswith('"') and label.endswith('"'):
            return m.group(0)
        if any(c in label for c in '(){}[]:;,=+*?'):
            safe = label.replace('"', "'")
            return f'{node_id}[("{safe}")]'
        return m.group(0)
    cleaned = re.sub(r'(\b[A-Za-z0-9_-]+)\[\(([^\n]+?)\)\]', fix_cylinder, cleaned)

    # 4. Fix Rectangle ID[label] (skipping cylinder [(...)], subroutine [[...]], parallelogram [/.../], already quoted ["..."])
    def fix_rect(m):
        node_id, label = m.group(1), m.group(2).strip()
        if label.startswith('"') and label.endswith('"'):
            return m.group(0)
        safe = label.replace('"', "'")
        return f'{node_id}["{safe}"]'
    cleaned = re.sub(r'(\b[A-Za-z0-9_-]+)\[(?![\(\[\/\\"])([^\]\n]*?[\(\)\{\}:;=+*?][^\]\n]*?)\]', fix_rect, cleaned)

    # 5. Fix Subgraph titles containing unquoted parens: subgraph My Title (v1)
    def fix_subgraph(m):
        indent, title = m.group(1), m.group(2).strip()
        if '[' in title or title.startswith('"'):
            return m.group(0)
        if any(c in title for c in '(){}:;=+*?'):
            safe = title.replace('"', "'")
            return f'{indent}subgraph "{safe}"'
        return m.group(0)
    cleaned = re.sub(r'^([ \t]*)subgraph[ \t]+([^\n]+)$', fix_subgraph, cleaned, flags=re.MULTILINE)

    # 6. Fix Edge labels containing parentheses or brackets inside |...|
    def fix_edge_label(m):
        label = m.group(1).strip()
        if label.startswith('"') and label.endswith('"'):
            return m.group(0)
        if any(c in label for c in '(){}[]:;='):
            safe = label.replace('"', "'")
            return f'|"{safe}"|'
        return m.group(0)
    cleaned = re.sub(r'\|([^|\n]+)\|', fix_edge_label, cleaned)

    return cleaned


def validate_mermaid_syntax(source: str, diagram_type: str):
    """
    Validates that a Mermaid source string begins with the expected diagram directive
    and has reasonably balanced delimiters.
    """
    if not source or not source.strip():
        return False, "Mermaid source code is empty."
    
    clean_src = source.strip()
    if clean_src.startswith('```'):
        clean_src = re.sub(r'^```(?:mermaid)?\s*', '', clean_src)
        clean_src = re.sub(r'\s*```$', '', clean_src)
        clean_src = clean_src.strip()
        
    expected_prefixes = {
        'system_architecture': ('flowchart', 'graph'),
        'use_case': ('flowchart', 'graph'),
        'erd': ('erDiagram', 'erdiagram'),
        'class_diagram': ('classDiagram', 'classdiagram'),
        'sequence_diagram': ('sequenceDiagram', 'sequencediagram'),
    }
    
    prefixes = expected_prefixes.get(diagram_type, ('flowchart', 'graph', 'erDiagram', 'classDiagram', 'sequenceDiagram'))
    first_token = clean_src.split(None, 1)[0] if clean_src else ""
    first_line = clean_src.splitlines()[0].strip() if clean_src else ""
    
    matches_prefix = any(first_line.startswith(p) or first_token.startswith(p) for p in prefixes)
    if not matches_prefix:
        return False, f"Invalid Mermaid directive for {diagram_type}. Must start with: {', '.join(prefixes)} (Found: '{first_line[:30]}')"
        
    # Check bracket balance (for ER diagrams, { and } are standard cardinality markers like ||--o{, so skip curly brace count)
    delimiters = [('[', ']'), ('(', ')')]
    if diagram_type != 'erd':
        delimiters.append(('{', '}'))
        
    for opener, closer in delimiters:
        if clean_src.count(opener) != clean_src.count(closer):
            return False, f"Unbalanced delimiter: '{opener}' count ({clean_src.count(opener)}) != '{closer}' count ({clean_src.count(closer)})"
            
    return True, ""


def extract_design_diagrams(artifact_content: str):
    """
    Extracts the 5 formal Design Stage diagrams (3 Essential, 2 Recommended)
    with their metadata, Mermaid source, observations, and syntax validation status.
    Guarantees exactly 5 diagram items in the required order.
    """
    ordered_types = [
        ('system_architecture', 'System Architecture Diagram', 'Essential', 'flowchart TD', True),
        ('use_case', 'Use Case Diagram', 'Essential', 'flowchart LR', True),
        ('erd', 'Entity Relationship Diagram (ERD)', 'Essential', 'erDiagram', True),
        ('class_diagram', 'Class Diagram', 'Recommended', 'classDiagram', False),
        ('sequence_diagram', 'Sequence Diagram', 'Recommended', 'sequenceDiagram', False),
    ]
    
    diagrams = []
    text = artifact_content or ""
    
    diag_section = ""
    if '# System Design Diagrams' in text:
        parts = text.split('# System Design Diagrams', 1)
        diag_section = parts[1]
    else:
        diag_section = text
        
    patterns = {
        'system_architecture': [
            r'#{2,4}\s*(?:\d+\.\s*)?System Architecture[^\n]*\n(.*?)(?=(?:\n#{2,4}\s|\Z))',
            r'\*\*Type:\*\*\s*System Architecture[^\n]*\n(.*?)(?=(?:\n\*\*Type:\*\*|\n#{2,4}\s|\Z))'
        ],
        'use_case': [
            r'#{2,4}\s*(?:\d+\.\s*)?Use Case[^\n]*\n(.*?)(?=(?:\n#{2,4}\s|\Z))',
            r'\*\*Type:\*\*\s*Use Case[^\n]*\n(.*?)(?=(?:\n\*\*Type:\*\*|\n#{2,4}\s|\Z))'
        ],
        'erd': [
            r'#{2,4}\s*(?:\d+\.\s*)?(?:Entity Relationship|ERD)[^\n]*\n(.*?)(?=(?:\n#{2,4}\s|\Z))',
            r'\*\*Type:\*\*\s*(?:Entity Relationship|ERD)[^\n]*\n(.*?)(?=(?:\n\*\*Type:\*\*|\n#{2,4}\s|\Z))'
        ],
        'class_diagram': [
            r'#{2,4}\s*(?:\d+\.\s*)?Class Diagram[^\n]*\n(.*?)(?=(?:\n#{2,4}\s|\Z))',
            r'\*\*Type:\*\*\s*Class Diagram[^\n]*\n(.*?)(?=(?:\n\*\*Type:\*\*|\n#{2,4}\s|\Z))'
        ],
        'sequence_diagram': [
            r'#{2,4}\s*(?:\d+\.\s*)?Sequence Diagram[^\n]*\n(.*?)(?=(?:\n#{2,4}\s|\Z))',
            r'\*\*Type:\*\*\s*Sequence Diagram[^\n]*\n(.*?)(?=(?:\n\*\*Type:\*\*|\n#{2,4}\s|\Z))'
        ],
    }
    
    for dtype, title, category, directive, is_essential in ordered_types:
        block_text = ""
        for pat in patterns[dtype]:
            m = re.search(pat, diag_section, re.DOTALL | re.IGNORECASE)
            if m:
                block_text = m.group(1).strip()
                break
                
        status = "not_generated"
        desc = ""
        mermaid_code = ""
        observations = ""
        
        if block_text:
            status_m = re.search(r'\*\*Status:\*\*\s*([^\n]+)', block_text, re.IGNORECASE)
            if status_m:
                st_val = status_m.group(1).strip().lower()
                if 'not generated' in st_val:
                    status = 'not_generated'
                elif 'generated' in st_val:
                    status = 'generated'
                    
            desc_m = re.search(r'\*\*Description:\*\*\s*([^\n]+(?:\n(?!\*\*|```)[^\n]+)*)', block_text)
            if desc_m:
                desc = desc_m.group(1).strip()
                
            m_code = re.search(r'```(?:mermaid)?\s*\n(.*?)\n```', block_text, re.DOTALL)
            if not m_code:
                m_code = re.search(r'```(?:mermaid)?\s*\n(.*)\Z', block_text, re.DOTALL)
            if m_code:
                mermaid_code = m_code.group(1).strip().rstrip('`').strip()
                if not status_m:
                    status = 'generated'
                    
            obs_m = re.search(r'\*\*Key Observations:\*\*\s*([^\n]+(?:\n(?!\*\*|```|###)[^\n]+)*)', block_text)
            if obs_m:
                observations = obs_m.group(1).strip()
        else:
            # Fallback for inline diagrams or older artifacts
            if dtype == 'sequence_diagram':
                inline_m = re.search(r'```mermaid\s*\n(sequenceDiagram.*?)\n```', text, re.DOTALL)
                if inline_m:
                    mermaid_code = inline_m.group(1).strip()
                    status = 'generated'
                    desc = "Sequence diagram extracted from system lifecycle specifications."
            elif dtype == 'system_architecture':
                inline_m = re.search(r'```mermaid\s*\n((?:flowchart|graph).*?)\n```', text, re.DOTALL)
                if inline_m:
                    mermaid_code = inline_m.group(1).strip()
                    status = 'generated'
                    desc = "System architecture diagram extracted from structural specifications."
            elif dtype == 'erd':
                inline_m = re.search(r'```mermaid\s*\n(erDiagram.*?)\n```', text, re.DOTALL)
                if inline_m:
                    mermaid_code = inline_m.group(1).strip()
                    status = 'generated'
                    desc = "Entity relationship schema diagram extracted from database specifications."
                    
        if status == 'not_generated':
            if not desc:
                if is_essential:
                    desc = f"The {title} has not been generated for this version."
                else:
                    desc = f"Not generated: The approved requirements do not specify sufficient information to model a {title.lower()} without inventing unauthorized information."
            mermaid_code = ""
            is_valid = True
            syntax_err = ""
        else:
            mermaid_code = sanitize_mermaid_source(mermaid_code)
            is_valid, syntax_err = validate_mermaid_syntax(mermaid_code, dtype)
            
        diagrams.append({
            'type': dtype,
            'title': title,
            'category': category,
            'type_label': f"{title} — {category}",
            'directive': directive,
            'is_essential': is_essential,
            'status': status,
            'description': desc,
            'mermaid_source': mermaid_code,
            'observations': observations,
            'is_valid_syntax': is_valid,
            'syntax_error': syntax_err,
        })
        
    return diagrams


def parse_design_doc(raw_text):
    """
    Parses a software design specification document into structured section objects
    and extracts the 5 formal diagrams.
    """
    if not raw_text or not isinstance(raw_text, str):
        return None

    cleaned = raw_text.strip()
    if not cleaned:
        return None

    cleaned = cleaned.replace('\u2011', '-').replace('\u2013', '-').replace('\u2014', '--')

    # Separate written document from # System Design Diagrams
    written_part = cleaned
    if '# System Design Diagrams' in cleaned:
        written_part = cleaned.split('# System Design Diagrams', 1)[0].strip()

    def get_design_section_meta(title):
        t_lower = title.lower()
        if any(w in t_lower for w in ['architecture', 'topology', 'system']):
            return '🏛️', 'ARCHITECTURE', 'System topology, deployment tiers & runtime distribution'
        elif any(w in t_lower for w in ['component', 'module', 'layer']):
            return '🧩', 'COMPONENTS', 'Component boundaries, responsibilities & dependencies'
        elif any(w in t_lower for w in ['database', 'schema', 'storage', 'indexeddb', 'entity']):
            return '🗄️', 'DATABASE', 'Entity schemas, indexes, persistence layer & migrations'
        elif any(w in t_lower for w in ['api', 'interface', 'contract', 'type', 'service']):
            return '🔌', 'API CONTRACTS', 'Service contracts, TypeScript definitions & state actions'
        elif any(w in t_lower for w in ['data flow', 'flow', 'lifecycle', 'scenario']):
            return '🔀', 'DATA FLOW', 'Execution pipelines, message flows & sequence lifecycles'
        elif any(w in t_lower for w in ['security', 'auth', 'threat', 'vulnerability']):
            return '🛡️', 'SECURITY', 'Security perimeter, sanitization, encryption & isolation'
        elif any(w in t_lower for w in ['decision', 'tradeoff', 'adr', 'rationale']):
            return '⚖️', 'DECISIONS', 'Architectural decisions, trade-offs & technical choices'
        elif any(w in t_lower for w in ['assumption', 'prerequisite', 'baseline']):
            return '💡', 'ASSUMPTIONS', 'Platform assumptions, browser support & runtime limits'
        else:
            return '📐', 'DESIGN SPEC', 'Structured system design specification module'

    section_chunks = re.split(r'\n(?=#{1,2}\s+)', written_part)
    sections = []
    numbered_seq = 0

    for chunk in section_chunks:
        chunk_clean = chunk.strip()
        if not chunk_clean:
            continue

        first_line = chunk_clean.split('\n', 1)[0].strip()
        body = chunk_clean.split('\n', 1)[1].strip() if '\n' in chunk_clean else ""

        heading_match = re.match(r'^#{1,3}\s+(.*)$', first_line)
        num_match = None
        if heading_match:
            full_title = heading_match.group(1).strip()
            num_match = re.match(r'^(\d+)\.\s*(.*)$', full_title)
            if num_match:
                title = num_match.group(2).strip()
            else:
                title = full_title
        else:
            title = f"Section {len(sections) + 1}"
            full_title = title
            body = chunk_clean

        t_lower = title.lower()
        is_excluded = (
            t_lower == 'api'
            or t_lower.startswith('api ')
            or 'api design' in t_lower
            or 'api interface' in t_lower
            or 'security considerations' in t_lower
            or t_lower == 'security'
            or 'design decision' in t_lower
            or 'assumption' in t_lower
        )
        if is_excluded:
            continue

        cur_idx = len(sections)
        if num_match:
            numbered_seq += 1
            num = str(numbered_seq)
            full_title = f"{num}. {title}"
        else:
            num = str(cur_idx + 1)

        icon, tag, summary = get_design_section_meta(title)
        has_table = '|' in body
        html_content = render_content_blocks(body)

        sections.append({
            'id': f'sec-{cur_idx}',
            'index': cur_idx,
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

    diagrams = extract_design_diagrams(cleaned)

    return {
        'sections': sections,
        'diagrams': diagrams,
        'has_diagrams': any(d['status'] == 'generated' for d in diagrams),
        'essential_diagrams': [d for d in diagrams if d['is_essential']],
        'recommended_diagrams': [d for d in diagrams if not d['is_essential']],
        'total_sections': len(sections),
        'raw_content': cleaned,
    }


def parse_testing_report(raw_text):
    """
    Parses a Testing Stage artifact into structured report data (4 sections).
    Supports structured JSON reports generated by TestingAgent, malformed edit error handling,
    and graceful legacy Markdown fallback for earlier artifacts.
    """
    if not raw_text or not isinstance(raw_text, str):
        return None

    cleaned = raw_text.strip()
    if not cleaned:
        return None

    # Strip optional markdown code fences around JSON
    json_candidate = cleaned
    if cleaned.startswith('```'):
        m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*(?:```|\Z)', cleaned)
        if m:
            json_candidate = m.group(1).strip()

    # Check if text looks like JSON
    if json_candidate.startswith('{'):
        try:
            data = json.loads(json_candidate)
        except json.JSONDecodeError as e:
            return {
                'is_structured': False,
                'is_legacy_markdown': False,
                'parse_error': f"Malformed JSON structure in Testing Report: {str(e)}. Please fix syntax via Edit or click Regenerate.",
                'raw_content': raw_text,
            }

        if not isinstance(data, dict) or 'generated_test_cases' not in data or not isinstance(data.get('generated_test_cases'), list):
            return {
                'is_structured': False,
                'is_legacy_markdown': False,
                'parse_error': "Incomplete Testing Report JSON: required 'generated_test_cases' section is missing or invalid.",
                'raw_content': raw_text,
            }

        raw_summary = data.get('testing_summary', {}) if isinstance(data.get('testing_summary'), dict) else {}
        raw_cases = data.get('generated_test_cases', []) if isinstance(data.get('generated_test_cases'), list) else []
        raw_issues = data.get('potential_issues', []) if isinstance(data.get('potential_issues'), list) else []
        raw_recs = data.get('recommendations', []) if isinstance(data.get('recommendations'), list) else []

        # Normalize test cases with strict 'Not Executed' enforcement
        test_cases = []
        pos_count = 0
        neg_count = 0
        for idx, tc in enumerate(raw_cases, 1):
            if not isinstance(tc, dict):
                continue
            stype = str(tc.get('scenario_type', 'Positive')).strip()
            is_neg = 'neg' in stype.lower()
            if is_neg:
                neg_count += 1
                stype = 'Negative'
            else:
                pos_count += 1
                stype = 'Positive'

            prio = str(tc.get('priority', 'Medium')).strip().capitalize()
            if prio not in ('High', 'Medium', 'Low'):
                prio = 'Medium'

            test_cases.append({
                'id': str(tc.get('id') or f"TC-{idx:02d}").strip(),
                'scenario': str(tc.get('scenario') or '').strip(),
                'scenario_type': stype,
                'is_negative': is_neg,
                'requirement_ref': str(tc.get('requirement_ref') or 'General').strip(),
                'expected_result': str(tc.get('expected_result') or '').strip(),
                'priority': prio,
                'status': 'Not Executed',  # Hard safety constraint
            })

        # Normalize potential issues
        potential_issues = []
        sev_counts = {'Critical': 0, 'High': 0, 'Medium': 0, 'Low': 0}
        for idx, iss in enumerate(raw_issues, 1):
            if not isinstance(iss, dict):
                continue
            sev = str(iss.get('severity', 'Medium')).strip().capitalize()
            if sev not in sev_counts:
                sev = 'Medium'
            sev_counts[sev] += 1
            potential_issues.append({
                'id': str(iss.get('id') or f"ISS-{idx:02d}").strip(),
                'description': str(iss.get('description') or '').strip(),
                'severity': sev,
                'affected_component': str(iss.get('affected_component') or 'Unspecified Component').strip(),
                'explanation': str(iss.get('explanation') or '').strip(),
                'analysis_type': str(iss.get('analysis_type') or 'AI Static Analysis (Unverified at Runtime)').strip(),
            })

        # Normalize recommendations
        recommendations = []
        for idx, rec in enumerate(raw_recs, 1):
            if isinstance(rec, str) and rec.strip():
                recommendations.append({
                    'title': f"Recommendation {idx}",
                    'action': rec.strip(),
                    'related_ref': '',
                })
            elif isinstance(rec, dict):
                action = str(rec.get('action') or rec.get('description') or '').strip()
                if action:
                    recommendations.append({
                        'title': str(rec.get('title') or f"Recommendation {idx}").strip(),
                        'action': action,
                        'related_ref': str(rec.get('related_ref') or '').strip(),
                    })

        # Recompute summary metrics accurately from actual lists
        covered_reqs = raw_summary.get('covered_requirements', [])
        if not isinstance(covered_reqs, list):
            covered_reqs = []
        uncovered_reqs = raw_summary.get('uncovered_requirements', [])
        if not isinstance(uncovered_reqs, list):
            uncovered_reqs = []
        total_reqs = raw_summary.get('total_requirements_count', len(covered_reqs) + len(uncovered_reqs))
        try:
            total_reqs = int(total_reqs)
        except (ValueError, TypeError):
            total_reqs = len(covered_reqs) + len(uncovered_reqs)

        if total_reqs > 0:
            coverage_pct = round((len(covered_reqs) / total_reqs) * 100.0, 1)
            coverage_pct = min(100.0, max(0.0, coverage_pct))
        else:
            try:
                coverage_pct = round(float(raw_summary.get('requirement_coverage_percentage', 0.0)), 1)
            except (ValueError, TypeError):
                coverage_pct = 0.0

        summary = {
            'total_test_cases': len(test_cases),
            'positive_count': pos_count,
            'negative_count': neg_count,
            'requirement_coverage_percentage': coverage_pct,
            'covered_requirements': covered_reqs,
            'uncovered_requirements': uncovered_reqs,
            'total_requirements_count': total_reqs,
            'potential_issues_count': len(potential_issues),
            'summary_note': str(raw_summary.get('summary_note') or '').strip(),
        }

        return {
            'is_structured': True,
            'is_legacy_markdown': False,
            'parse_error': None,
            'testing_summary': summary,
            'generated_test_cases': test_cases,
            'potential_issues': potential_issues,
            'severity_counts': sev_counts,
            'recommendations': recommendations,
            'raw_content': raw_text,
        }

    # Fallback: legacy markdown / plain text artifact
    return {
        'is_structured': False,
        'is_legacy_markdown': True,
        'parse_error': None,
        'legacy_html': render_content_blocks(cleaned),
        'raw_content': raw_text,
    }


def parse_deployment_report(raw_text):
    """
    Parses a Deployment Stage artifact into the lightweight 3-section consolidated report:
    (A. Deployment Recommendation, B. Deployment Readiness checks, C. Deployment Instructions).
    Handles malformed edited JSON cleanly and falls back gracefully for legacy Markdown reports.
    """
    if not raw_text or not isinstance(raw_text, str):
        return None

    cleaned = raw_text.strip()
    if not cleaned:
        return None

    json_candidate = cleaned
    if cleaned.startswith('```'):
        m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*(?:```|\Z)', cleaned)
        if m:
            json_candidate = m.group(1).strip()

    if json_candidate.startswith('{'):
        try:
            data = json.loads(json_candidate)
        except json.JSONDecodeError as e:
            return {
                'is_structured': False,
                'is_legacy_markdown': False,
                'parse_error': f"Malformed JSON in Deployment Report: {str(e)}. Please correct syntax via Edit or click Regenerate.",
                'raw_content': raw_text,
            }

        required = ('deployment_recommendation', 'deployment_readiness', 'deployment_instructions')
        if not isinstance(data, dict) or not all(k in data for k in required):
            return {
                'is_structured': False,
                'is_legacy_markdown': False,
                'parse_error': "Incomplete Deployment Report JSON: requires deployment_recommendation, deployment_readiness, and deployment_instructions.",
                'raw_content': raw_text,
            }

        rec = data.get('deployment_recommendation', {})
        checks_raw = data.get('deployment_readiness', [])
        instr = data.get('deployment_instructions', {})

        if not isinstance(rec, dict) or not isinstance(checks_raw, list) or not isinstance(instr, dict):
            return {
                'is_structured': False,
                'is_legacy_markdown': False,
                'parse_error': "Invalid section structure inside Deployment Report JSON.",
                'raw_content': raw_text,
            }

        cfg_reqs = rec.get('config_requirements', [])
        if not isinstance(cfg_reqs, list):
            cfg_reqs = [str(cfg_reqs)] if cfg_reqs else []

        recommendation = {
            'hosting_platform': str(rec.get('hosting_platform') or 'Manual / Managed Host').strip(),
            'database_recommendation': str(rec.get('database_recommendation') or 'Not Specified').strip(),
            'config_requirements': [str(c).strip() for c in cfg_reqs if str(c).strip()],
            'explanation': str(rec.get('explanation') or '').strip(),
        }

        readiness = []
        counts = {'Ready': 0, 'Needs Review': 0, 'Missing': 0, 'Not Applicable': 0}
        badge_map = {
            'Ready': 'dep-status-ready',
            'Needs Review': 'dep-status-review',
            'Missing': 'dep-status-missing',
            'Not Applicable': 'dep-status-na',
        }
        icon_map = {
            'Ready': '✓',
            'Needs Review': '!',
            'Missing': '✕',
            'Not Applicable': '—',
        }

        for item in checks_raw:
            if not isinstance(item, dict):
                continue
            status_raw = str(item.get('status') or 'Needs Review').strip()
            s_lower = status_raw.lower()
            if 'ready' in s_lower:
                status = 'Ready'
            elif 'not applicable' in s_lower or s_lower in ('na', 'n/a'):
                status = 'Not Applicable'
            elif 'missing' in s_lower:
                status = 'Missing'
            else:
                status = 'Needs Review'

            counts[status] += 1
            readiness.append({
                'check': str(item.get('check') or '').strip(),
                'status': status,
                'badge_class': badge_map[status],
                'status_icon': icon_map[status],
                'explanation': str(item.get('explanation') or '').strip(),
            })

        steps_raw = instr.get('steps', [])
        if not isinstance(steps_raw, list):
            steps_raw = [str(steps_raw)] if steps_raw else []
        # Strip leading "1. ", "2. " if already numbered so ordered list <ol> renders cleanly
        clean_steps = []
        for s in steps_raw:
            st = re.sub(r'^\d+\.\s*', '', str(s).strip())
            if st:
                clean_steps.append(st)

        chk_raw = instr.get('verification_checklist', [])
        if not isinstance(chk_raw, list):
            chk_raw = [str(chk_raw)] if chk_raw else []
        clean_checklist = [str(v).strip() for v in chk_raw if str(v).strip()]

        return {
            'is_structured': True,
            'is_legacy_markdown': False,
            'parse_error': None,
            'recommendation': recommendation,
            'readiness': readiness,
            'readiness_counts': counts,
            'instructions': {
                'steps': clean_steps,
                'verification_checklist': clean_checklist,
            },
            'raw_content': raw_text,
        }

    # Legacy Markdown fallback
    return {
        'is_structured': False,
        'is_legacy_markdown': True,
        'parse_error': None,
        'legacy_html': render_content_blocks(cleaned),
        'raw_content': raw_text,
    }
