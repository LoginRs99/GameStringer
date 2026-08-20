import re
from collections import Counter

_HTML_TAG_RE = re.compile(r'<(\/?[a-zA-Z0-9_-]+)[^>]*>')

def check_html_tags(source: str, target: str, entry_id: str = "") -> list[str]:
    source_tags = _HTML_TAG_RE.findall(source)
    target_tags = _HTML_TAG_RE.findall(target)
    
    if not source_tags and not target_tags:
        return []
        
    source_counter = Counter(source_tags)
    target_counter = Counter(target_tags)
    
    issues = []
    
    loc = f"id='{entry_id}'" if entry_id else "entry"
    
    for tag, count in source_counter.items():
        if target_counter[tag] < count:
            missing = count - target_counter[tag]
            issues.append(f"{loc}: hianyzik a HTML/XML tag a targetbol: <{tag}> ({missing}x)")
            
    for tag, count in target_counter.items():
        if source_counter[tag] < count:
            extra = count - source_counter[tag]
            issues.append(f"{loc}: target-ben extra HTML/XML tag (forrasban nincs): <{tag}> ({extra}x)")
            
    return issues
