import re, sys

with open(sys.argv[1], encoding='utf-8') as f:
    html = f.read()

# Remove wp: block comments
text = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
# Remove HTML tags
text = re.sub(r'<[^>]+>', '', text)
# Remove shortcodes
text = re.sub(r'\[.*?\]', '', text)
# Collapse whitespace
text = re.sub(r'\n{3,}', '\n\n', text)
text = re.sub(r'[ \t]+', ' ', text)

out = sys.argv[2] if len(sys.argv) > 2 else None
if out:
    with open(out, 'w', encoding='utf-8') as f:
        f.write(text.strip())
else:
    sys.stdout.buffer.write(text.strip().encode('utf-8'))
