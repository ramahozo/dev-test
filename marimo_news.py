# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo",
#     "requests",
#     "trafilatura",
#     "warcio",
# ]
# ///

import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md("""
    # CC-NEWS access test

    Exercises the recipe end to end against the real infrastructure:

    1. read the month manifest `crawl-data/CC-NEWS/<yyyy>/<mm>/warc.paths.gz`
    2. filter it to one calendar day
    3. stream the WARC and stop after N records (a full file is ~1 GB, so an early
       `break` keeps this to a few MB of transfer)
    4. extract body text with `trafilatura`
    5. match tickers with word boundaries, not substrings
    6. cross-check against the GDELT DOC API (free, no key)

    Days are selected by the **filename** timestamp (`CC-NEWS-yyyymmddHHMMSS-nnnnn`),
    which marks when the file's first record was created, so a file can span
    midnight.
    """)
    return


@app.cell
def _():
    import gzip
    import json
    import re
    from html import unescape

    import requests
    import trafilatura
    from warcio.archiveiterator import ArchiveIterator

    return ArchiveIterator, gzip, json, re, requests, trafilatura, unescape


@app.cell
def _(mo):
    is_script_mode = mo.app_meta().mode == "script"
    mode_label = "script (auto-run)" if is_script_mode else "interactive"
    mo.md(f"Running in **{mode_label}** mode.")
    return (is_script_mode,)


@app.cell
def _(mo):
    year = mo.ui.number(start=2016, stop=2026, value=2026, label="Year")
    month = mo.ui.dropdown(
        options=[f"{value:02d}" for value in range(1, 13)], value="09", label="Month"
    )
    day = mo.ui.number(start=1, stop=31, value=1, label="Day of month")
    max_files = mo.ui.slider(1, 3, value=1, label="WARC files to stream")
    max_records = mo.ui.slider(3, 60, value=15, label="Records per file")
    tickers = mo.ui.text(value="AAPL,NVDA,TSLA,Fed,earnings", label="Terms to match")
    gdelt_query = mo.ui.text(value="stock market", label="GDELT query")
    mo.vstack(
        [
            mo.hstack([year, month, day]),
            mo.hstack([max_files, max_records]),
            tickers,
            gdelt_query,
        ]
    )
    return day, gdelt_query, max_files, max_records, month, tickers, year


@app.cell
def _(gzip, mo, requests):
    BASE_URL = "https://data.commoncrawl.org"

    @mo.cache
    def load_manifest(year, month):
        """Month listing: one relative WARC path per line, gzip-compressed."""
        url = f"{BASE_URL}/crawl-data/CC-NEWS/{year}/{month}/warc.paths.gz"
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        text = gzip.decompress(response.content).decode("utf-8")
        return [line.strip() for line in text.splitlines() if line.strip()], url

    return BASE_URL, load_manifest


@app.cell
def _(day, load_manifest, max_files, mo, month, year):
    all_paths, manifest_url = load_manifest(year.value, month.value)
    day_prefix = f"CC-NEWS-{year.value}{month.value}{day.value:02d}"
    day_paths = [path for path in all_paths if day_prefix in path]
    selected_paths = day_paths[: max_files.value]

    mo.md(
        f"""
        Manifest: [`{manifest_url}`]({manifest_url})

        | measure | value |
        |---|---|
        | WARCs in {year.value}-{month.value} | {len(all_paths):,} |
        | WARCs on {year.value}-{month.value}-{day.value:02d} | {len(day_paths):,} |
        | selected for streaming | {len(selected_paths)} |
        """
    )
    return day_paths, selected_paths


@app.cell
def _(
    ArchiveIterator,
    BASE_URL,
    max_records,
    mo,
    re,
    requests,
    selected_paths,
    unescape,
):
    @mo.cache
    def read_warc(relative_path, limit):
        """Stream a WARC and stop after `limit` response records."""
        records = []
        with requests.get(f"{BASE_URL}/{relative_path}", stream=True, timeout=180) as response:
            response.raise_for_status()
            for record in ArchiveIterator(response.raw):
                if record.rec_type != "response":
                    continue
                page = record.content_stream().read().decode("utf-8", "replace")
                title_match = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
                records.append(
                    {
                        "warc": relative_path.rsplit("/", 1)[-1],
                        "url": record.rec_headers.get_header("WARC-Target-URI") or "",
                        "captured": record.rec_headers.get_header("WARC-Date") or "",
                        "status": record.http_headers.get_statuscode() if record.http_headers else "",
                        "title": unescape(title_match.group(1)).strip() if title_match else "",
                        "html": page,
                    }
                )
                if len(records) >= limit:
                    break
        return records

    warc_records = [
        record
        for path in selected_paths
        for record in read_warc(path, max_records.value)
    ]
    mo.md(
        f"Streamed **{len(warc_records)}** HTML responses from "
        f"{len(selected_paths)} WARC file(s); stopped early, so only a few MB moved."
    )
    return (warc_records,)


@app.cell
def _(mo, re, trafilatura, unescape, warc_records):
    articles = []
    for record in warc_records:
        text = trafilatura.extract(record["html"], include_comments=False) or ""
        title = record["title"] or (text.splitlines()[0] if text else "")
        articles.append(
            {
                "captured": record["captured"][:19],
                "domain": re.sub(r"^https?://", "", record["url"]).split("/")[0],
                "status": record["status"],
                "title": unescape(title)[:120],
                "chars": len(text),
                "url": record["url"],
                "text": text,
                "warc": record["warc"],
                "tickers": [],
            }
        )

    extracted = sum(1 for article in articles if article["chars"] > 0)
    mo.md(
        f"`trafilatura` recovered body text for **{extracted}/{len(articles)}** records "
        f"({sum(article['chars'] for article in articles):,} chars total)."
    )
    return (articles,)


@app.cell
def _(articles, mo):
    table = mo.ui.table(articles, selection=None) if articles else mo.md("No records streamed.")
    table
    return


@app.cell
def _(articles, mo, re, tickers):
    terms = [term.strip() for term in tickers.value.split(",") if term.strip()]
    pattern = re.compile(r"\b(" + "|".join(re.escape(term) for term in terms) + r")\b", re.I)

    hits = []
    for article in articles:
        haystack = f"{article['title']} {article['url']} {article['text']}"
        found = sorted({match.upper() for match in pattern.findall(haystack)})
        hits.append(
            {
                "captured": article["captured"],
                "domain": article["domain"],
                "terms": ", ".join(found),
                "title": article["title"],
                "url": article["url"],
            }
        )

    matched = [hit for hit in hits if hit["terms"]]
    summary = (
        f"**{len(matched)}/{len(hits)}** records matched {terms}. "
        "Word boundaries keep `A` or `F` from matching every article."
    )
    body = mo.ui.table(matched, selection=None) if matched else mo.md("No matches — widen the terms.")
    mo.vstack([mo.md(summary), body])
    return


@app.cell
def _(gdelt_query, is_script_mode, json, mo, requests):
    params = {
        "query": gdelt_query.value,
        "mode": "artlist",
        "format": "json",
        "maxrecords": 15 if is_script_mode else 25,
        "timespan": "1d",
        "sort": "datedesc",
    }
    response = requests.get(
        "https://api.gdeltproject.org/api/v2/doc/doc", params=params, timeout=60
    )
    try:
        payload = json.loads(response.text)
    except json.JSONDecodeError:
        payload = {}

    gdelt_articles = payload.get("articles", [])
    gdelt_rows = [
        {
            "seendate": article.get("seendate", ""),
            "domain": article.get("domain", ""),
            "language": article.get("language", ""),
            "title": article.get("title", ""),
            "url": article.get("url", ""),
        }
        for article in gdelt_articles
    ]
    mo.vstack(
        [
            mo.md(
                f"### GDELT DOC 2.0 — `{gdelt_query.value}`\n"
                f"HTTP {response.status_code}, **{len(gdelt_rows)}** articles "
                "(an empty body with no `articles` key means zero matches)"
            ),
            mo.ui.table(gdelt_rows, selection=None) if gdelt_rows else mo.md("No GDELT matches."),
        ]
    )
    return (gdelt_rows,)


@app.cell
def _(articles, day_paths, gdelt_rows, json, mo, selected_paths):
    domains = sorted({article["domain"] for article in articles})
    first = articles[0] if articles else None
    sample = (
        {
            "date": first["captured"],
            "text": first["text"][:280],
            "tickers": first["tickers"],
            "source": first["domain"],
            "url": first["url"],
            "extra_fields": {"warc": first["warc"], "license": "publisher-copyright"},
        }
        if first
        else {}
    )

    mo.vstack(
        [
            mo.md(
                f"""
                ### Summary

                | source | measure |
                |---|---|
                | CC-NEWS | {len(day_paths)} WARCs that day, {len(selected_paths)} streamed |
                | CC-NEWS | {len(articles)} articles, {len(domains)} domains |
                | GDELT | {len(gdelt_rows)} articles in the last day |

                Domains seen: {", ".join(domains) if domains else "—"}

                Row shape mapped onto this repo's `financial_news` table:
                """
            ),
            mo.md(f"```json\n{json.dumps(sample, indent=2)}\n```"),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
