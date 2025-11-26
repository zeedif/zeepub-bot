
import re

def extract_title_logic(content):
    # 1. Try epub:type="fulltitle"
    # Capture the tag name to match the closing tag
    fulltitle_pattern = re.compile(r'<(\w+)[^>]*epub:type="fulltitle"[^>]*>(.*?)</\1>', re.IGNORECASE | re.DOTALL)
    match = fulltitle_pattern.search(content)
    
    if match:
        inner_html = match.group(2)
        print(f"Found fulltitle inner: {inner_html.strip()}")
        
        # Try to find title and subtitle specifically
        title_pat = re.compile(r'epub:type="title"[^>]*>(.*?)<', re.IGNORECASE | re.DOTALL)
        subtitle_pat = re.compile(r'epub:type="subtitle"[^>]*>(.*?)<', re.IGNORECASE | re.DOTALL)
        
        t_match = title_pat.search(inner_html)
        s_match = subtitle_pat.search(inner_html)
        
        if t_match and s_match:
            t_text = re.sub(r'<[^>]+>', '', t_match.group(1)).strip()
            s_text = re.sub(r'<[^>]+>', '', s_match.group(1)).strip()
            
            # Check for punctuation
            if t_text and s_text:
                if not t_text.endswith(':') and not t_text.endswith('-'):
                    return f"{t_text}: {s_text}"
                return f"{t_text} {s_text}"
        
        # If no specific sub-tags, just clean HTML
        # Replace <br> with space
        clean = re.sub(r'<br\s*/?>', ' ', inner_html, flags=re.IGNORECASE)
        clean = re.sub(r'<[^>]+>', '', clean).strip()
        return clean

    # 2. Fallback to old logic (simplified here)
    return "FALLBACK"

# Test cases
html1 = """
<h1 class="titulo" title="Página de título" epub:type="fulltitle">
  <span class="grande" epub:type="title">Arifureta</span>
  <br/><span epub:type="subtitle" role="doc-subtitle">From Commonplace to World’s Strongest</span>
</h1>
"""

html2 = """
<h1 epub:type="fulltitle">Just a Simple Title</h1>
"""

html3 = """
<div epub:type="fulltitle">
  <span epub:type="title">My Hero Academia</span>
  <span epub:type="subtitle">Vol. 1</span>
</div>
"""

print(f"Test 1: {extract_title_logic(html1)}")
print(f"Test 2: {extract_title_logic(html2)}")
print(f"Test 3: {extract_title_logic(html3)}")
