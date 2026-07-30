import json
import os

import requests

k = os.environ["KRX_API_KEY"]
for p in ["sto/stk_bydd_trd", "sto/stk_isu_base_info", "sto/ksq_isu_base_info"]:
    r = requests.get(f"https://data-dbg.krx.co.kr/svc/apis/{p}",
                     params={"basDd": "20260728"}, headers={"AUTH_KEY": k}, timeout=90)
    js = r.json()
    rows = js.get("OutBlock_1") or []
    print("==", p, "n=", len(rows))
    if rows:
        print("  fields:", list(rows[0].keys()))
        print("  row0:", json.dumps(rows[0], ensure_ascii=False)[:700])
