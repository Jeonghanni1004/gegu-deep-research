import json
from pathlib import Path

d = json.loads(Path("examples/_poc_raw_probes.json").read_text(encoding="utf-8"))
v1 = d["cls"]["v1"]["json"]
rd = v1["data"]["roll_data"]
print("type", type(rd), "len", len(rd) if isinstance(rd, list) else rd)
print("update_num", v1["data"].get("update_num"))
print("first", (rd or [None])[0] if isinstance(rd, list) else rd)
alt = d["cls"]["v1_alt"]["json"]
rd2 = alt["data"]["roll_data"]
print("alt len", len(rd2) if isinstance(rd2, list) else rd2)
print("em np", d["em_news"]["np_listapi"])
print("em 600519 preview", d["em_news"]["600519"]["preview"][:400])
