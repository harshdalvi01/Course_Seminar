import json
import re

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
