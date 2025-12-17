import re
import os

def parse_markdown_schema(file_path: str):
    """
    Parses the Markdown schema file into a structured dictionary.
    Returns:
        tables (dict): { 'table_name': 'full_markdown_content' }
        summaries (dict): { 'table_name': 'brief_description' }
    """
    if not os.path.exists(file_path):
        return {}, {}

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    tables = {}
    summaries = {}

    # Regex to find sections like "#### 1. 資料表：`cue_lists` (說明)"
    # Pattern explanation:
    # ^#### [\d\\.]+\s+資料表：`([\w_]+)` \(([^)]+)\)
    pattern = re.compile(r"^#### [\d\\.]+\s+資料表：`([\w_]+)` \(([^)]+)\)", re.MULTILINE)
    
    matches = list(pattern.finditer(content))
    
    for i, match in enumerate(matches):
        table_name = match.group(1)
        description = match.group(2)
        start_index = match.start()
        
        # Determine end index (start of next match or end of file)
        end_index = matches[i+1].start() if i + 1 < len(matches) else len(content)
        
        # Extract content
        table_content = content[start_index:end_index].strip()
        
        tables[table_name] = table_content
        summaries[table_name] = description

    return tables, summaries

def get_glossary_content(file_path: str):
    """Extracts the Glossary sections to append globally."""
    # Assuming Glossary is marked clearly, or we just append specific sections
    # For now, simplistic approach: if section doesn't match table pattern, it might be glossary.
    # But better approach: Split by headers.
    # Let's simple return the whole file content minus the tables if needed, 
    # but for now, the Schema Selector focuses on Tables. 
    # The 'Glossary' usually follows tables.
    
    # Simple extraction for "名詞解釋"
    if not os.path.exists(file_path):
        return ""
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    glossary_pattern = re.compile(r"^#### \d+\. (?:新增)?名詞解釋", re.MULTILINE)
    matches = list(glossary_pattern.finditer(content))
    
    glossary_text = ""
    for match in matches:
        start = match.start()
        # Find next header ####
        next_header = re.search(r"^#### \d+\.", content[start+1:], re.MULTILINE)
        end = (start + 1 + next_header.start()) if next_header else len(content)
        glossary_text += content[start:end] + "\n\n"
        
    return glossary_text
