import json
from pathlib import Path

cls = json.loads(Path("examples/600519_cls_test.json").read_text(encoding="utf-8"))
v1 = cls.get("v1_roll") or {}
print("v1 keys", list(v1.keys()))
print("count", v1.get("count"), "errno", v1.get("errno"), "parse_ok", v1.get("parse_ok"))
print("items len", len(v1.get("items") or []))
print("meta", v1.get("meta"))
print("error", v1.get("error"))
if v1.get("items"):
    print("item0", v1["items"][0])
print("summary", cls.get("summary"))
print("primary", cls.get("primary_api"))
