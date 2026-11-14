"""Build the fixture-mode Drex replay file from a recorded benchmark run.

The replay holds REAL Drex responses (drex-latest, repeat 0) captured during a benchmark run, so the fixture demo
can still be shown when the Nace API is unreachable. The UI only uses it when the user turns on replay, and every
replayed item is labeled with its recording time.

Usage: python scripts/make_drex_replay.py docs/benchmark_runs/<run>.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = Path(sys.argv[1])
run = json.loads(src.read_text())
recorded_at = run["summary"]["run_at"]
out = {}
for r in run["raw"]["Drex (drex-latest)"]:
    if r["rep"] != 0 or not r["out"] or r["error"]:
        continue
    out[r["id"]] = {**r["out"], "recorded_at": recorded_at, "recorded_from": src.name}
dest = ROOT / "api/_radar/data/drex_replay.json"
dest.write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(f"wrote {len(out)} recorded Drex responses to {dest}")
