"""Build api/_radar/data/influencers.json by running the real evaluation on a seed list of creator names.
Every record comes from live search results; nothing is typed in by hand.
Usage: .venv/bin/python scripts/seed_influencers.py [extra names...]"""
import json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
from _radar import influencers  # noqa: E402

SEED = """Marques Brownlee|Linus Tech Tips|Two Minute Papers|Fireship|Matt Wolfe|Dave2D|NetworkChuck|Lex Fridman|Yannic Kilcher|AI Explained|Matthew Berman|ThePrimeagen|Peter McKinnon|JerryRigEverything|Gamers Nexus|Ali Abdaal|3Blue1Brown|Theo t3.gg|Colin and Samir|Mrwhosetheboss
Unbox Therapy|Austin Evans|iJustine|MrMobile|Snazzy Labs|Hardware Unboxed|JayzTwoCents|Optimum Tech|The Coding Train|freeCodeCamp|Traversy Media|Web Dev Simplified|Kevin Powell|Tech With Tim|Corey Schafer|sentdex|Andrej Karpathy|StatQuest|Computerphile
Tom Scott|Veritasium|Kurzgesagt|Vsauce|SmarterEveryDay|Mark Rober|MinutePhysics|CGP Grey|Numberphile|SciShow|CrashCourse|Khan Academy|Real Engineering|Wendover Productions|Johnny Harris
PewDiePie|Markiplier|Jacksepticeye|Ninja|Pokimane|Shroud|Dream|DanTDM|Ludwig|Valkyrae|xQc|Asmongold|penguinz0|videogamedunkey
Dude Perfect|Jeff Nippard|Athlean-X|Chloe Ting|Pamela Reif|Joe Wicks|Jesser|Deestroying|F2Freestylers|House of Highlights|Cristiano Ronaldo|LeBron James|Tifo Football|JxmyHighroller|Nick Bare|Blogilates|Yoga With Adriene
Babish Culinary Universe|Joshua Weissman|Gordon Ramsay|Tasty|Bon Appetit|Nick DiGiovanni|Maangchi|J. Kenji Lopez-Alt|Adam Ragusea|Mark Wiens|Sorted Food|Ethan Chlebowski|Pro Home Cooks|Rosanna Pansino|Uncle Roger|Best Ever Food Review Show|Emmymade|Tabitha Brown
James Charles|NikkieTutorials|Huda Kattan|Michelle Phan|Jackie Aina|Hyram Yarbro|Emma Chamberlain|Bretman Rock|Safiya Nygaard|Patrick Starrr|Wisdom Kaye|Zoella
Kara and Nate|Drew Binsky|Yes Theory|Nas Daily|Lost LeBlanc|Eva zu Beck|Sailing La Vagabonde|Rick Steves
Graham Stephan|Andrei Jikh|Humphrey Yang|The Plain Bagel|Ben Felix|Patrick Boyle|Gary Vaynerchuk|Alex Hormozi|Codie Sanchez|Thomas Frank|Matt D'Avella
Rick Beato|Adam Neely|Jacob Collier|Andrew Huang|Davie504|Casey Neistat|Corridor Crew|Film Riot|Jazza|Proko|The Futur|PiXimperfect
MrBeast|Khaby Lame|Charli D'Amelio|Addison Rae|Zach King|Lilly Singh|Liza Koshy|Good Mythical Morning|Smosh|The Try Guys|Airrack|Ryan Trahan|Michelle Khare|First We Feast|Sidemen|KSI
Doug DeMuro|Donut Media|ChrisFix|Supercar Blondie|Scotty Kilmer
I Like To Make Stuff|Stuff Made Here|Colin Furze|Simone Giertz|Adam Savage's Tested|This Old House|Laura Kampf
Doctor Mike|Andrew Huberman|Ms Rachel""".replace("\n", "|").split("|") + sys.argv[1:]
OUT = ROOT / "api/_radar/data/influencers.json"
done: list = []

def run(n):
    try:
        r = influencers.evaluate(n)
    except Exception as e:
        print(n, "FAILED", str(e)[:100], flush=True); return
    print(n, "->", r["followers_total"], r["p_authentic"] and round(r["p_authentic"], 2), flush=True)
    if r["found"] and r["engine"] == "drex":
        done.append(r)
        if len(done) % 15 == 0:
            OUT.write_text(json.dumps(done, indent=1, ensure_ascii=False))

with ThreadPoolExecutor(max_workers=6) as ex:
    list(ex.map(run, SEED))
OUT.write_text(json.dumps(done, indent=1, ensure_ascii=False))
print("wrote", len(done), "of", len(SEED))
