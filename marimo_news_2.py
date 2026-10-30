# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "altair",
#     "marimo",
#     "pandas",
#     "requests",
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
    # GDELT 2.0 news check

    GDELT exposes the same news corpus through two very different doors, and
    they fail in different ways:

    | door | endpoint | throttling | latency |
    |---|---|---|---|
    | **DOC 2.0 API** | `api.gdeltproject.org/api/v2/doc/doc` | **1 request / 5 s per IP**, then HTTP 429 with a *plain-text* body | live |
    | **15-minute raw files** | `data.gdeltproject.org/gdeltv2/<stamp>.gkg.csv.zip` | none (static files, no key) | ~15 min |

    The limiter penalises bursts: once an IP trips it, every call answers 429
    for minutes even at 1 request / 5 s. So the API is best-effort here and the
    raw slice is the reliable path — the same split a production ingest needs.
    """)
    return


@app.cell
def _():
    import io
    import json
    import re
    import time
    import zipfile
    from collections import Counter

    import altair as alt
    import pandas as pd
    import requests

    return Counter, alt, io, json, pd, re, requests, time, zipfile


@app.cell
def _(mo):
    is_script_mode = mo.app_meta().mode == "script"
    mo.md(f"Running in **{'script (auto-run)' if is_script_mode else 'interactive'}** mode.")
    return


@app.cell
def _(mo):
    query = mo.ui.text(value='"bank of america"', label="Query (GDELT operator syntax)")
    window = mo.ui.dropdown(
        options={"last hour": "1h", "last day": "1d", "last week": "1w", "last month": "1m"},
        value="last day",
        label="Window",
    )
    sort = mo.ui.dropdown(
        options={"newest first": "datedesc", "most relevant": "hybridrel", "most negative": "toneasc"},
        value="newest first",
        label="Sort",
    )
    max_records = mo.ui.slider(10, 250, value=20, step=10, label="Max records (cap 250)")
    gkg_terms = mo.ui.text(value="market, bank", label="Terms to match in the GKG slice")
    include_gkg = mo.ui.checkbox(value=True, label="Download the latest 15-minute GKG slice")
    mo.vstack(
        [
            query,
            mo.hstack([window, sort]),
            max_records,
            mo.hstack([gkg_terms, include_gkg]),
        ]
    )
    return gkg_terms, include_gkg, max_records, query, sort, window


@app.cell
def _(json, requests, time):
    DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
    # GDELT asks for 1 request / 5 s; a shared egress IP gets pushed into a
    # penalty box fast, so leave real headroom.
    MIN_INTERVAL = 10.0
    call_log = []

    def gdelt_doc(params):
        """One paced DOC API call; retries once when the limiter answers 429."""
        for attempt in range(2):
            elapsed = time.monotonic() - (call_log[-1] if call_log else 0.0)
            if elapsed < MIN_INTERVAL:
                time.sleep(MIN_INTERVAL - elapsed)
            response = requests.get(DOC_URL, params=params, timeout=60)
            call_log.append(time.monotonic())
            throttled = response.status_code == 429 and attempt == 0
            if not throttled:
                break
            time.sleep(MIN_INTERVAL * 2)

        is_json = response.headers.get("content-type", "").startswith("application/json")
        payload = json.loads(response.text) if is_json else {}
        return response, payload

    return (gdelt_doc,)


@app.cell
def _(gdelt_doc, max_records, mo, query, sort, window):
    response, payload = gdelt_doc(
        {
            "query": query.value,
            "mode": "artlist",
            "format": "json",
            "maxrecords": max_records.value,
            "timespan": window.value,
            "sort": sort.value,
        }
    )
    articles = payload.get("articles", [])
    rows = [
        {
            "seen (UTC)": article.get("seendate", ""),
            "country": article.get("sourcecountry", ""),
            "language": article.get("language", ""),
            "domain": article.get("domain", ""),
            "title": article.get("title", ""),
            "url": article.get("url", ""),
        }
        for article in articles
    ]

    header = (
        f"### Article list — `{query.value}` ({window.value})\n"
        f"HTTP {response.status_code}, **{len(rows)}** articles"
    )
    body = (
        mo.ui.table(rows, selection=None)
        if rows
        else mo.callout(
            mo.md(f"**HTTP {response.status_code}** — no articles.\n\n{response.text[:300]}"),
            kind="warn",
        )
    )
    mo.vstack([mo.md(header), body])
    return (articles,)


@app.cell
def _(alt, gdelt_doc, mo, pd, query, window):
    timeline_response, timeline_payload = gdelt_doc(
        {
            "query": query.value,
            "mode": "timelinevolraw",
            "format": "json",
            "timespan": window.value,
        }
    )
    timeline_rows = [
        {
            "date": point.get("date", ""),
            "series": series.get("series", ""),
            "value": point.get("value", 0),
            "norm": point.get("norm", 0),
        }
        for series in timeline_payload.get("timeline", [])
        for point in series.get("data", [])
    ]

    timeline_header = (
        f"### Coverage volume — `{query.value}`\n"
        f"HTTP {timeline_response.status_code}, **{len(timeline_rows)}** time steps "
        "(15-minute resolution under 72 h, hourly to a week, daily beyond)"
    )

    frame = pd.DataFrame(timeline_rows)
    if frame.empty:
        view = mo.callout(
            mo.md(f"**HTTP {timeline_response.status_code}** — no timeline.\n\n{timeline_response.text[:300]}"),
            kind="warn",
        )
    else:
        frame["when"] = pd.to_datetime(frame["date"], format="ISO8601", utc=True)
        view = (
            alt.Chart(frame)
            .mark_line(point=False)
            .encode(
                x=alt.X("when:T", title="UTC"),
                y=alt.Y("value:Q", title="matching articles"),
                color=alt.Color("series:N", title=None),
                tooltip=["when:T", "series:N", "value:Q", "norm:Q"],
            )
            .properties(height=240)
        )

    mo.vstack([mo.md(timeline_header), view])
    return


@app.cell
def _(mo, requests):
    lastupdate_text = requests.get(
        "http://data.gdeltproject.org/gdeltv2/lastupdate.txt", timeout=30
    ).text
    feed_rows = []
    feed_urls = {}
    for line in lastupdate_text.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        size, checksum, url = parts
        kind = "gkg" if url.endswith(".gkg.csv.zip") else url.rsplit(".", 3)[-3]
        feed_urls[kind] = url
        feed_rows.append(
            {
                "kind": kind,
                "size (MB)": round(int(size) / 1_048_576, 2),
                "md5": checksum,
                "url": url,
            }
        )

    mo.vstack(
        [
            mo.md(
                "### Latest raw slice\n"
                "`lastupdate.txt` is rewritten every 15 minutes; these are the files "
                "you can download with no key and no rate limit."
            ),
            mo.ui.table(feed_rows, selection=None),
        ]
    )
    return (feed_urls,)


@app.cell
def _(io, mo, requests, zipfile):
    GKG_COLUMNS = [
        "gkg_record_id",
        "date",
        "source_collection",
        "source_common_name",
        "document_identifier",
        "counts",
        "v2_counts",
        "themes",
        "v2_themes",
        "locations",
        "v2_locations",
        "persons",
        "v2_persons",
        "organizations",
        "v2_organizations",
        "v2_tone",
        "dates",
        "gcam",
        "sharing_image",
        "related_images",
        "social_image_embeds",
        "social_video_embeds",
        "quotations",
        "all_names",
        "amounts",
        "translation_info",
        "extras",
    ]

    @mo.cache
    def load_gkg(url):
        """Download + unzip one 15-minute GKG slice (2.1 layout, 27 tab fields)."""
        blob = requests.get(url, timeout=180).content
        archive = zipfile.ZipFile(io.BytesIO(blob))
        name = archive.namelist()[0]
        text = archive.read(name).decode("utf-8", "replace")
        records = []
        for line in text.splitlines():
            fields = line.split("\t")
            if len(fields) != len(GKG_COLUMNS):
                continue
            record = dict(zip(GKG_COLUMNS, fields))
            tone = record["v2_tone"].split(",")
            records.append(
                {
                    **record,
                    "theme_list": [theme for theme in record["themes"].split(";") if theme],
                    "tone": float(tone[0]) if tone and tone[0] else 0.0,
                }
            )
        return name, records

    return (load_gkg,)


@app.cell
def _(feed_urls, include_gkg, load_gkg, mo):
    if include_gkg.value:
        gkg_name, gkg_records = load_gkg(feed_urls["gkg"])
    else:
        gkg_name, gkg_records = "", []

    result = (
        mo.md(f"Loaded **{len(gkg_records):,}** GKG records from `{gkg_name}` (27 fields each).")
        if gkg_records
        else mo.callout(mo.md("GKG slice download is off — tick the checkbox above."), kind="info")
    )
    result
    return (gkg_records,)


@app.cell
def _(Counter, gkg_records, gkg_terms, mo, re):
    terms = [term.strip() for term in gkg_terms.value.split(",") if term.strip()]
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(term) for term in terms) + r")\b", re.IGNORECASE
    )

    matched = [
        record
        for record in gkg_records
        if pattern.search(
            f"{record['document_identifier']} {record['themes']} "
            f"{record['persons']} {record['organizations']}"
        )
    ]
    match_rows = [
        {
            "date": record["date"],
            "source": record["source_common_name"],
            "tone": round(record["tone"], 2),
            "themes": ", ".join(record["theme_list"][:3]),
            "url": record["document_identifier"],
        }
        for record in matched[:40]
    ]
    theme_counts = Counter(
        theme for record in matched for theme in record["theme_list"]
    ).most_common(10)
    theme_rows = [{"theme": theme, "records": count} for theme, count in theme_counts]

    average_tone = sum(record["tone"] for record in matched) / len(matched) if matched else 0.0

    mo.vstack(
        [
            mo.md(
                f"### GKG matches for {terms}\n"
                f"**{len(matched):,}/{len(gkg_records):,}** records · mean tone **{average_tone:+.2f}** "
                "(GDELT tone runs roughly −20 … +20)"
            ),
            mo.hstack(
                [
                    mo.ui.table(match_rows, selection=None)
                    if match_rows
                    else mo.md("No matches in this 15-minute slice."),
                    mo.ui.table(theme_rows, selection=None) if theme_rows else mo.md(""),
                ],
                widths=[3, 1],
                align="start",
            ),
        ]
    )
    return (matched,)


@app.cell
def _(articles, gkg_records, json, matched, mo, query):
    first = articles[0] if articles else {}
    sample = {
        "date": first.get("seendate", ""),
        "text": first.get("title", "")[:200],
        "tickers": [],
        "source": first.get("domain", ""),
        "url": first.get("url", ""),
        "extra_fields": {
            "gdelt_query": query.value,
            "language": first.get("language", ""),
            "source_country": first.get("sourcecountry", ""),
            "license": "gdelt-open",
        },
    }
    gkg_sample = (
        {
            "gkg_record_id": matched[0]["gkg_record_id"],
            "themes": matched[0]["theme_list"][:6],
            "tone": matched[0]["tone"],
            "persons": matched[0]["persons"][:120],
        }
        if matched
        else {}
    )

    mo.vstack(
        [
            mo.md(
                f"""
                ### Summary

                | source | measure |
                |---|---|
                | DOC API | {len(articles)} articles for `{query.value}` |
                | GKG slice | {len(gkg_records):,} records, {len(matched):,} matching |

                Both doors land in the same row shape this repo stores in
                `financial_news`. DOC API article:
                """
            ),
            mo.md(f"```json\n{json.dumps(sample, indent=2)}\n```"),
            mo.md("GKG extras worth keeping in `extra_fields` (themes drive entity linking):"),
            mo.md(f"```json\n{json.dumps(gkg_sample, indent=2)}\n```"),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
