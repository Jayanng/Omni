import ast
from pathlib import Path

def check(path: Path):
    src = path.read_text()
    tree = ast.parse(src)
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                name = a.asname or a.name.split('.')[0]
                imported[name] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            # __future__ imports are compiler directives, not names that get
            # referenced, so they are never "unused".
            if (node.module or "") == "__future__":
                continue
            for a in node.names:
                if a.name == '*':
                    continue
                name = a.asname or a.name
                imported[name] = node.lineno
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            pass
    # attribute roots like os.environ -> Name os already counted
    unused = {k: v for k, v in imported.items() if k not in used}
    if unused:
        print(f"{path}: unused imports -> " + ", ".join(f"{k} (line {v})" for k, v in unused.items()))

files = (
    sorted(Path('omni').glob('*.py'))
    + sorted(Path('tests').glob('*.py'))
    + sorted(Path('tools').glob('*.py'))
)
for f in files:
    check(f)
print("scan complete over", len(files), "files")

# also detect long lines and tabs
for f in files:
    for i, line in enumerate(f.read_text().splitlines(), 1):
        if len(line) > 110:
            print(f"{f}:{i}: line length {len(line)}")
        if '\t' in line:
            print(f"{f}:{i}: tab character")
