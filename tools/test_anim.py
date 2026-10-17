"""Run ghoul_anim.decode over every Anim asset under a directory tree and report failures.
usage: python -I test_anim.py <dir>
"""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghoul_anim  # noqa: E402

root = Path(sys.argv[1])
ok = 0
errs = collections.Counter()
examples = {}
slack = collections.Counter()
for desc in root.rglob("Anim__*/descriptor"):
    try:
        a = ghoul_anim.decode(desc.read_bytes())
        ok += 1
        m = a["main"]
        slack[m["kf_bytes"] * 8 - m["bits"]] += 1
    except Exception as e:  # noqa: BLE001
        key = type(e).__name__ + ": " + str(e).split(":")[0]
        errs[key] += 1
        examples.setdefault(key, (desc.parent.name, str(e)))
print("ok", ok, "fail", sum(errs.values()))
for k, v in errs.most_common():
    print(v, k, examples[k])
print("unused bits per keyframe (should be 0-7):", sorted(slack.items())[:12])
