from pathlib import Path

for i, raw in enumerate(Path(".env").read_text(encoding="utf-8").splitlines(), 1):
    if "FA_LIVE" in raw or i <= 2:
        # show only FA_LIVE related / first lines structure, mask values except FA_LIVE
        if raw.strip().startswith("FA_LIVE"):
            print(f"line{i}=", repr(raw))
        else:
            k = raw.split("=", 1)[0] if "=" in raw else raw
            print(f"line{i}_key=", repr(k), "len_val=", len(raw.split("=", 1)[1]) if "=" in raw else 0)
