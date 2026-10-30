import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _():
    import yfinance as yf

    ticker = yf.Ticker("AMD")

    # Current and last 5 historical periods
    valuation = ticker.get_valuation_measures(
        freq="quarterly",
        periods=10,
    )

    print(valuation)
    return


@app.cell
def _():
    return


@app.cell
def _():
    return


@app.cell
def _():
    import os
    import sys
    import time
    import random
    import logging
    from datetime import datetime, timedelta
    from typing import Optional, List
    from dataclasses import dataclass

    import pandas as pd

    # gdeltdoc - official GDELT DOC 2.0 API client
    # Install: pip install gdeltdoc (or add to pixi.toml)
    try:
        from gdeltdoc import GdeltDoc, Filters, near, repeat, multi_near, multi_repeat
        GDELTDOC_AVAILABLE = True
    except ImportError:
        GdeltDoc = None
        Filters = None
        near = repeat = multi_near = multi_repeat = None
        GDELTDOC_AVAILABLE = False
    return (
        Filters,
        GDELTDOC_AVAILABLE,
        GdeltDoc,
        List,
        Optional,
        dataclass,
        logging,
        multi_near,
        multi_repeat,
        pd,
        random,
        time,
    )


@app.cell
def _(GDELTDOC_AVAILABLE, mo):
    if not GDELTDOC_AVAILABLE:
        _mo_md = """
        ⚠️ **gdeltdoc not installed**

        Install the official GDELT DOC 2.0 client:
        ```bash
        pip install gdeltdoc
        ```
        Or add to `pixi.toml`:
        ```toml
        [tool.pixi.dependencies]
        gdeltdoc = ">=1.12.0"
        ```
        Then run `pixi install`.
        """
    else:
        _mo_md = "✅ **gdeltdoc available** — using official GDELT DOC 2.0 API client v1.12+"
    mo.md(_mo_md)
    return


@app.cell
def _(dataclass):
    """
    Financial news collection using gdeltdoc (official GDELT DOC 2.0 Python client).

    Features:
    - Filters with keyword, theme, country, language, tone
    - Proximity search (near/multi_near) for financial term co-occurrence
    - Repetition search (repeat/multi_repeat) for emphasis detection
    - DateTime support (v1.11+) for sub-day granularity
    - Returns pandas DataFrame with: url, url_mobile, title, seendate, socialimage, domain, language, sourcecountry

    Note: GDELT DOC API only guarantees last 3 months of coverage.
    Historical queries (e.g., 2020) may return limited/no results.
    Rate limit: ~1 request per 5 seconds (undocumented, inconsistent).
    """

    @dataclass
    class GDELTConfig:
        num_records: int = 2  # Per request (max 250)
        max_retries: int = 3
        base_backoff: float = 6.0  # Respect ~5s rate limit
        max_backoff: float = 60.0
        jitter: float = 0.25

    # Financial GKG Themes (from GDELT GKG theme taxonomy)
    FINANCIAL_THEMES = [
        "ECONOMY",
        "BUSINESS",
        "FINANCIAL_MARKETS",
        "STOCK_MARKET",
        "BANKING",
        "INVESTMENT",
        "TRADE",
        "COMMERCE",
        "CURRENCY",
        "COMMODITIES",
        "CRYPTOCURRENCY",
        "CENTRAL_BANK",
        "FEDERAL_RESERVE",
        "INFLATION",
        "RECESSION",
        "GDP",
        "EARNINGS",
        "CORPORATE_EARNINGS",
    ]

    # Financial keywords for proximity search
    FINANCIAL_KEYWORDS = [
        "stock market", "federal reserve", "central bank", "interest rate",
        "inflation", "recession", "gdp growth", "corporate earnings",
        "quarterly results", "dividend yield", "bond yield", "currency exchange",
        "cryptocurrency", "bitcoin", "ethereum", "monetary policy"
    ]
    return FINANCIAL_KEYWORDS, FINANCIAL_THEMES, GDELTConfig


@app.cell
def _(
    FINANCIAL_KEYWORDS,
    FINANCIAL_THEMES,
    Filters,
    List,
    Optional,
    multi_near,
    multi_repeat,
):
    def build_financial_filters(
        start_date: str,
        end_date: str,
        num_records: int = 2,
        themes: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
    ) -> Filters:
        """Build Filters object for financial news with advanced gdeltdoc features."""
        if themes is None:
            themes = FINANCIAL_THEMES[:8]  # Top 8 themes to avoid overly broad query

        # Use multi_near for co-occurrence of financial terms (within 10 words)
        proximity_filters = []
        for i in range(0, min(len(keywords or FINANCIAL_KEYWORDS), 6), 2):
            if i + 1 < len(keywords or FINANCIAL_KEYWORDS):
                proximity_filters.append((
                    10,
                    (keywords or FINANCIAL_KEYWORDS)[i],
                    (keywords or FINANCIAL_KEYWORDS)[i + 1]
                ))

        # Use repeat for emphasis on key financial terms
        repeat_filters = [
            (3, "stock"),
            (2, "market"),
            (2, "fed"),
            (2, "inflation"),
        ]

        return Filters(
            start_date=start_date,
            end_date=end_date,
            num_records=num_records,
            theme=themes,
            language="en",
            country=["US", "UK", "CN", "JP", "DE", "FR"],  # Major financial centers
            near=multi_near(proximity_filters, method="OR") if proximity_filters else None,
            repeat=multi_repeat(repeat_filters, method="OR") if repeat_filters else None,
            tone=">-10",  # Exclude extremely negative tone (noise filter)
        )

    return (build_financial_filters,)


@app.cell
def _(GDELTConfig):
    config = GDELTConfig()
    return (config,)


@app.cell
def _(build_financial_filters, config):
    # August 2026 - within 3-month rolling window (if running in late 2026)
    filters_aug_2026 = build_financial_filters(
        start_date="2026-08-01",
        end_date="2026-08-31",
        num_records=config.num_records,
    )

    # February 2020 - historical, outside guaranteed 3-month window
    filters_feb_2020 = build_financial_filters(
        start_date="2020-02-01",
        end_date="2020-02-28",
        num_records=config.num_records,
    )
    return filters_aug_2026, filters_feb_2020


@app.cell
def _(
    Filters,
    GDELTDOC_AVAILABLE,
    GdeltDoc,
    config,
    logging,
    pd,
    random,
    time,
):
    def fetch_with_retry(gd: GdeltDoc, filters: Filters, label: str) -> pd.DataFrame:
        """Fetch articles with exponential backoff for 429 handling."""
        if not GDELTDOC_AVAILABLE:
            return pd.DataFrame()

        last_error = None
        for attempt in range(config.max_retries + 1):
            try:
                articles = gd.article_search(filters)
                if articles is not None and not articles.empty:
                    logging.info(f"{label}: fetched {len(articles)} articles")
                    return articles
                else:
                    logging.info(f"{label}: no articles returned")
                    return pd.DataFrame()

            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if "429" in err_str or "rate" in err_str or "too many" in err_str:
                    wait = min(
                        config.base_backoff * (2 ** attempt) + random.uniform(-config.jitter, config.jitter),
                        config.max_backoff
                    )
                    logging.warning(f"{label}: rate limited (attempt {attempt + 1}), waiting {wait:.1f}s")
                    time.sleep(wait)
                else:
                    logging.error(f"{label}: error - {e}")
                    break

        logging.error(f"{label}: failed after {config.max_retries} retries - {last_error}")
        return pd.DataFrame()

    return (fetch_with_retry,)


@app.cell
def _(
    GDELTDOC_AVAILABLE,
    GdeltDoc,
    config,
    fetch_with_retry,
    filters_aug_2026,
    filters_feb_2020,
    pd,
    time,
):
    if not GDELTDOC_AVAILABLE:
        articles_aug_2026 = pd.DataFrame()
        articles_feb_2020 = pd.DataFrame()
    else:
        gd = GdeltDoc()  # Default json_parsing_max_depth=100

        articles_aug_2026 = fetch_with_retry(gd, filters_aug_2026, "August 2026")
        time.sleep(config.base_backoff)  # Pace requests
        articles_feb_2020 = fetch_with_retry(gd, filters_feb_2020, "February 2020")
    return articles_aug_2026, articles_feb_2020


@app.cell
def _(articles_aug_2026, articles_feb_2020, pd):
    def clean_articles(df: pd.DataFrame, period: str) -> pd.DataFrame:
        """Clean and standardize gdeltdoc DataFrame output."""
        if df.empty:
            return pd.DataFrame(columns=[
                "title", "url", "domain", "language", "source_country",
                "seendate", "period"
            ])

        # gdeltdoc returns: url, url_mobile, title, seendate, socialimage, domain, language, sourcecountry
        cleaned = df.copy()
        cleaned = cleaned.rename(columns={
            "sourcecountry": "source_country",
            "seendate": "seendate",
        })

        # Add period label
        cleaned["period"] = period

        # Select and order columns
        cols = ["title", "url", "domain", "language", "source_country", "seendate", "period"]
        available = [c for c in cols if c in cleaned.columns]
        return cleaned[available]

    df_aug_2026 = clean_articles(articles_aug_2026, "2026-08")
    df_feb_2020 = clean_articles(articles_feb_2020, "2020-02")
    return df_aug_2026, df_feb_2020


@app.cell
def _(mo):
    mo.md("""
    ## Financial News Articles — August 2026 (2026-08-01 to 2026-08-31)
    """)
    return


@app.cell
def _(df_aug_2026, mo):
    if df_aug_2026.empty:
        mo.md("""
        *No articles returned for August 2026.*

        **Possible reasons:**
        - Outside GDELT's 3-month rolling coverage window
        - Rate limited (429) — API allows ~1 req/5s
        - Query too restrictive (theme + country + language + near + repeat)
        - No matching financial news in period
        """)
    else:
        mo.ui.table(df_aug_2026)
    return


@app.cell
def _(mo):
    mo.md("""
    ## Financial News Articles — February 2020 (2020-02-01 to 2020-02-28)
    """)
    return


@app.cell
def _(df_feb_2020, mo):
    if df_feb_2020.empty:
        mo.md("""
        *No articles returned for February 2020.*

        **Expected:** GDELT DOC API only guarantees the most recent 3 months.
        Historical queries may return data but it's not guaranteed.
        """)
    else:
        mo.ui.table(df_feb_2020)
    return


@app.cell
def _(df_aug_2026, df_feb_2020, mo):
    total = len(df_aug_2026) + len(df_feb_2020)
    mo.md(f"**Total articles fetched:** {total} (Target: 4)")
    mo.md(f"- August 2026: {len(df_aug_2026)} articles")
    mo.md(f"- February 2020: {len(df_feb_2020)} articles")
    mo.md("""
    ---
    **Implementation Notes:**
    - Uses `gdeltdoc` v1.12+ (official GDELT DOC 2.0 client)
    - `Filters` with `theme`, `country`, `language`, `near`, `repeat`, `tone`
    - `multi_near`/`multi_repeat` for compound proximity/repetition
    - DateTime support for sub-day granularity (v1.11+)
    - Exponential backoff with jitter for 429 handling
    - Returns pandas DataFrame with standard GDELT columns
    """)
    return


if __name__ == "__main__":
    app.run()
