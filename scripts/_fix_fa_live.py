from pathlib import Path

p = Path(".env")
lines = p.read_text(encoding="utf-8").splitlines()
out = []
found = False
for line in lines:
    if line.strip().startswith("FA_LIVE="):
        out.append("FA_LIVE=1")
        found = True
    else:
        out.append(line)
if not found:
    out.insert(0, "FA_LIVE=1")
p.write_text("\n".join(out) + "\n", encoding="utf-8")
print("fixed FA_LIVE=1")
for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
    if line.startswith("FA_LIVE"):
        print("now", repr(line))
    else:
        print(f"line{i}_key", line.split("=", 1)[0])
