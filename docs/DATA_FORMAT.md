# Input format for Project Halo (for teammates feeding articles in)

Drex takes plain text plus typed questions, so anything you produce only needs to become **one JSON object per article**. Send a JSON array of these, or one object per line (JSONL).

```json
{
  "id": "nvda-cnbc-2026-11-12",
  "url": "https://example.com/article",
  "title": "Headline as published",
  "published_at": "2026-11-12",
  "retrieved_at": "2026-11-14T21:00:00Z",
  "outlet": "CNBC",
  "source_type": "news",
  "text": "Full article text, plain text or Markdown. No HTML, no navigation or ads.",
  "facts": {
    "claims": [
      {
        "claim": "One short sentence stating what is reported.",
        "attributed_to": "Who says it (reporter, named person, the company, a filing)",
        "status": "alleged | confirmed_by_subject | officially_stated | reported | opinion",
        "supporting_passage": "An exact sentence copied word for word from text."
      }
    ],
    "entities": [{ "name": "Jensen Huang", "kind": "person", "role": "CEO" }],
    "event_dates": [{ "date": "2026-11-12", "event": "Stock fell 4%" }]
  }
}
```

## Rules
- **Required:** `id` (unique, stable), `url`, `title`, `text`. Everything else is optional.
- **`published_at`:** `YYYY-MM-DD` or ISO 8601. Leave it out if unknown. Do not guess.
- **`text`:** the article itself, as complete as possible. This is what Drex reads and what evidence is checked against.
- **`source_type`:** one of `news`, `review`, `forum`, `ad_coverage`, `market`, `official`, `other`.
- **`facts`:** optional. If you leave it out, Halo runs NDI to extract it. If you include it, use the field names above.
- **`supporting_passage`:** must appear word for word in `text`. Halo drops any passage that does not match.
- **Do not send conclusions** such as "this is bad for the company" or a sentiment label as the only content. Drex makes those judgments itself from `text` and `facts`. Your own labels are welcome as extra fields (for example `"analyst_sentiment": "negative"`), and we can compare them with Drex later.
- One article per object. Do not merge several articles into one summary.

## How it is used
Each object is the `doc` (with `facts`) that `POST /api/decide` already accepts:

```json
{ "profile": { "name": "Nvidia", "description": "..." }, "doc": { ...article... }, "facts": { ...facts... }, "prior": [] }
```

Drex then answers, per article: right subject, risk category, report type, new or repeat, action, urgency, improvement area and sentiment.
