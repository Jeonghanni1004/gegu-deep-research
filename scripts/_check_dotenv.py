from pathlib import Path

p = Path(".env")
print("exists", p.exists())
if p.exists():
    lines = [
        l.strip()
        for l in p.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    print("n_lines", len(lines))
    print("keys", [l.split("=", 1)[0] for l in lines])
