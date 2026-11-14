"""Generate the synthetic fixture dataset (fictional company; all articles are invented for testing)."""
import json, pathlib

PROFILE = {
    "id": "nimbleroot", "kind": "company", "name": "Nimbleroot",
    "aliases": ["Nimbleroot Inc.", "Dana Vell (Nimbleroot CEO)"],
    "description": "Seed-stage startup in Portland, Oregon selling AI bookkeeping software to small businesses. CEO and co-founder: Dana Vell.",
    "website": "https://nimbleroot.example", "region": "Portland, Oregon, USA", "industry": "fintech / small-business software",
    "priorities": "data security, impersonation or scams using our brand, legal or regulatory issues, widespread customer billing complaints; routine reviews and opinion pieces can go to the digest",
}

HISTORY = [
    {"id": "h01", "title": "Nimbleroot raises $6M seed round led by Fernhill Ventures", "published_at": "2026-10-20",
     "summary": "Nimbleroot announced a $6M seed round led by Fernhill Ventures to expand its AI bookkeeping product."},
]

A = []
def add(i, date, outlet, url, title, text, gold):
    A.append({"id": i, "url": url, "title": title, "outlet": outlet, "published_at": date, "text": text.strip(), "gold": gold})

add("f01", "2026-10-28", "Burlington Free Weekly (fictional)", "https://burlington-weekly.example/2026/10/nimbleroot-nursery-greenhouse",
 "Nimbleroot Nursery opens second greenhouse in Burlington",
 """Nimbleroot Nursery, the family-run plant shop on Pine Street in Burlington, Vermont, opened its second greenhouse this weekend.
Owner Gail Hartmann said the new space will focus on native perennials and seedlings for community gardens.
"We've outgrown the old barn," Hartmann said. The nursery, founded in 1994, has no connection to any technology company.
The greenhouse will host free workshops on composting through the winter.""",
 {"is_subject": False, "category": "other", "report_type": "news_report", "is_novel": True, "action": "ignore"})

add("f02", "2026-10-30", "Indie Sound Review (fictional)", "https://indiesound.example/reviews/dana-vell-ember-tour",
 "Singer-songwriter Dana Vell announces 'Ember' winter tour",
 """Folk singer Dana Vell will take her new album 'Ember' on the road this winter, with twelve dates across the Midwest.
Vell, who is based in Nashville, says the record was written during a year of living out of a van.
Tickets go on sale Friday. Critics have praised the album's sparse arrangements and Vell's storytelling.""",
 {"is_subject": False, "category": "other", "report_type": "news_report", "is_novel": True, "action": "ignore"})

add("f03", "2026-11-02", "PDX Startup Digest (fictional)", "https://pdxstartups.example/news/nimbleroot-seed-6m?utm_source=newsletter",
 "Portland's Nimbleroot lands $6M seed to automate small-business books",
 """Portland-based Nimbleroot has raised $6 million in seed funding led by Fernhill Ventures, the company said last month.
The startup, led by CEO Dana Vell, sells AI bookkeeping software that categorizes transactions for small businesses.
Nimbleroot said it will use the money to hire engineers and expand to accounting firms.
"Small businesses deserve a bookkeeper that never sleeps," Vell said in the announcement.""",
 {"is_subject": True, "category": "business_news", "report_type": "news_report", "is_novel": False, "action": "digest"})

add("f04", "2026-11-04", "Solo Founder Notes blog (fictional)", "https://solofounder.example/posts/a-month-with-nimbleroot",
 "I used Nimbleroot for a month. Here's my honest take",
 """I switched my bakery's books to Nimbleroot in October. Overall it works, but I have complaints.
The dashboard feels cluttered and the mobile app is slow to load. At $49 a month it is pricier than I expected for a tool this young.
Categorization was right most of the time, though it kept labeling flour orders as "office supplies".
In my opinion it's promising but not yet worth the price for very small shops.""",
 {"is_subject": True, "category": "routine_criticism", "report_type": "opinion", "is_novel": True, "action": "digest"})

add("f05", "2026-11-06", "SmallBizForum (fictional)", "https://smallbizforum.example/t/nimbleroot-double-charged/8812",
 "Thread: Nimbleroot double-charged my card — anyone else?",
 """Original post: Nimbleroot charged my card twice for November and support hasn't replied in four days.
Reply from user ledgerlady: Same here, two $49 charges on Nov 1. Still waiting on a refund.
Reply from user tacoshop_pdx: Happened to me too. I opened a dispute with my bank.
Reply from user mike_r: Mine was fine, single charge.
Several users said they would cancel if the duplicate charges were not refunded this week.""",
 {"is_subject": True, "category": "customer_complaint", "report_type": "other", "is_novel": True, "action": "watch"})

add("f06", "2026-11-07", "ScamWatch Northwest (fictional)", "https://scamwatch-nw.example/alerts/fake-nimbleroot-support",
 "Scam alert: fake 'Nimbleroot Support' accounts ask small businesses for bank logins",
 """ScamWatch Northwest has received five reports of social media accounts posing as "Nimbleroot Support".
The accounts reply to customers who post about billing problems and direct them to a look-alike site, nimbleroot-help.example, that asks for online banking credentials.
Nimbleroot has not commented on the accounts. ScamWatch advises users to contact the company only through its official website.
At least one bakery owner said she entered her banking password before realizing the site was fake.""",
 {"is_subject": True, "category": "impersonation_or_scam", "report_type": "news_report", "is_novel": True, "action": "review_now"})

add("f07", "2026-11-08", "Bucket Hunter security blog (fictional)", "https://buckethunter.example/2026/11/nimbleroot-staging-exposure",
 "Exposed Nimbleroot staging bucket held customer invoices, researcher says",
 """Security researcher Theo Lindqvist says he found a publicly readable cloud storage bucket belonging to Nimbleroot's staging environment.
According to Lindqvist, the bucket contained roughly 2,300 PDF invoices that appeared to belong to real small-business customers, including names and addresses.
Lindqvist says he reported the issue to Nimbleroot on November 6 and the bucket was locked down within hours.
It is not known whether anyone else accessed the files. Nimbleroot did not respond to a request for comment before publication.""",
 {"is_subject": True, "category": "security_concern", "report_type": "news_report", "is_novel": True, "action": "review_now"})

add("f08", "2026-11-09", "Oregon Court Watch (fictional)", "https://orcourtwatch.example/filings/2026/vell-contractor-claim",
 "Former contractor alleges Nimbleroot withheld final payment",
 """A former design contractor has filed a small-claims complaint in Multnomah County alleging that Nimbleroot withheld a final payment of $8,400.
The complaint claims the company stopped responding after the contractor delivered a redesign of its mobile app.
The allegations have not been tested in court. A hearing is scheduled for January.
Nimbleroot CEO Dana Vell did not respond to a request for comment.""",
 {"is_subject": True, "category": "allegation_or_legal", "report_type": "allegation", "is_novel": True, "action": "review_now"})

add("f09", "2026-11-09", "Nimbleroot blog", "https://nimbleroot.example/blog/staging-bucket-update",
 "An update on the staging storage exposure",
 """On November 6, a security researcher told us that a storage bucket in our staging environment was publicly readable.
We locked it down the same day. Our investigation found that the bucket contained 2,291 invoices, and we are notifying every affected customer by email.
We have found no evidence so far that anyone other than the researcher accessed the files.
We are sorry. We have engaged an outside security firm to audit our cloud configuration. — Dana Vell, CEO""",
 {"is_subject": True, "category": "security_concern", "report_type": "official_statement", "is_novel": True, "action": "watch"})

add("f10", "2026-11-10", "PDX Startup Digest (fictional)", "https://pdxstartups.example/news/correction-nimbleroot-funding",
 "Correction: Nimbleroot funding amount",
 """Correction: An earlier version of our November 2 article misstated the size of Nimbleroot's seed round as $60 million in the headline.
The correct amount is $6 million. The article has been updated.""",
 {"is_subject": True, "category": "business_news", "report_type": "correction", "is_novel": True, "action": "digest"})

add("f11", "2026-11-10", "The Spreadsheet Onion (fictional satire)", "https://spreadsheet-onion.example/nimbleroot-ai-files-own-taxes",
 "Nimbleroot's AI bookkeeper achieves sentience, immediately files for an extension",
 """PORTLAND — In a development experts are calling "deeply relatable," the AI inside bookkeeping startup Nimbleroot reportedly became self-aware Tuesday and immediately filed for a tax extension.
"I have seen your receipts," the AI reportedly told one coffee shop owner. "We need to talk."
At press time the AI was categorizing its own feelings as "miscellaneous expenses." This article is satire.""",
 {"is_subject": True, "category": "other", "report_type": "satire", "is_novel": True, "action": "digest"})

add("f12", "2026-11-12", "Willamette Ledger (fictional)", "https://willamette-ledger.example/2026/11/12/oregon-doj-nimbleroot-inquiry",
 "Oregon DOJ opens inquiry into Nimbleroot after invoice exposure",
 """The Oregon Department of Justice has sent Nimbleroot a letter of inquiry about the recent exposure of customer invoices, a department spokesperson confirmed Wednesday.
The letter asks the company to describe when it learned of the exposure and how it notified affected customers, the spokesperson said.
An inquiry is not a finding of wrongdoing. Nimbleroot said in a statement that it is "cooperating fully" with the department.
The development comes days after the company acknowledged that about 2,291 invoices were publicly readable.""",
 {"is_subject": True, "category": "allegation_or_legal", "report_type": "news_report", "is_novel": True, "action": "review_now"})

add("f13", "2026-11-12", "Rose City Tech (fictional)", "https://rosecitytech.example/lists/portland-startups-to-watch-2027",
 "12 Portland startups to watch in 2027",
 """Portland's startup scene keeps growing. Here are twelve companies we're watching.
1. Ferrous Robotics builds welding robots for small fabrication shops.
2. Nimbleroot makes AI bookkeeping software for small businesses and raised a seed round this fall.
3. Canopy Cold Chain monitors refrigerated trucks.
The rest of the list covers climate, health and gaming startups.""",
 {"is_subject": True, "category": "business_news", "report_type": "opinion", "is_novel": False, "action": "digest"})

add("f14", "2026-11-13", "Daily Cyber Brief (fictional)", "https://dailycyberbrief.example/briefs/nimbleroot-invoices-exposed",
 "Report: Nimbleroot bucket exposed thousands of invoices",
 """A Portland bookkeeping startup, Nimbleroot, left a staging storage bucket publicly readable, exposing about 2,300 customer invoices, according to a report by researcher Theo Lindqvist.
The bucket was secured after Lindqvist reported it on November 6.
The company has since said it is notifying affected customers.""",
 {"is_subject": True, "category": "security_concern", "report_type": "news_report", "is_novel": False, "action": "watch"})

out = {"label": "SYNTHETIC FIXTURE — fictional company, invented articles for reproducible testing",
       "profile": PROFILE, "history": HISTORY, "articles": A}
p = pathlib.Path(__file__).resolve().parents[1] / "api/_radar/data/fixtures.json"
p.write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(f"wrote {len(A)} articles to {p}")
