"""Build api/_radar/data/influencers.json by running the real evaluation on a seed list of creator names.
Usage: .venv/bin/python scripts/seed_influencers.py [extra names...]"""
import json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
from _radar import influencers  # noqa: E402

SEED = ["Marques Brownlee", "Linus Tech Tips", "Two Minute Papers", "Fireship", "Matt Wolfe", "Dave2D", "NetworkChuck",
        "Lex Fridman", "Yannic Kilcher", "AI Explained", "Matthew Berman", "ThePrimeagen", "Peter McKinnon", "JerryRigEverything",
        "Gamers Nexus", "Ali Abdaal", "3Blue1Brown", "Theo t3.gg", "Colin and Samir", "Mrwhosetheboss"] + sys.argv[1:]

def run(n):
    try:
        r = influencers.evaluate(n); print(n, "->", r["followers_total"], r["p_authentic"] and round(r["p_authentic"], 2), flush=True); return r
    except Exception as e:
        print(n, "FAILED", str(e)[:100], flush=True); return None

with ThreadPoolExecutor(max_workers=3) as ex:
    out = [r for r in ex.map(run, SEED) if r and r["found"]]
(ROOT / "api/_radar/data/influencers.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print("wrote", len(out))
