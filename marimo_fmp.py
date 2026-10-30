# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo",
#     "requests",
#     "pandas",
# ]
# ///

import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import os

    import marimo as mo
    import pandas as pd
    import requests

    return mo, os, pd, requests


@app.cell
def _(mo):
    is_script_mode = mo.app_meta().mode == "script"
    return (is_script_mode,)


@app.cell
def _(mo):
    api_key_input = mo.ui.text(
        label="FMP API Key",
        placeholder="Paste your FMP API key here",
        kind="password",
    )
    api_key_input
    return (api_key_input,)


@app.cell
def _(api_key_input, is_script_mode, os):
    env_key = os.environ.get("FMP_API_KEY", "")
    raw_key = env_key if is_script_mode else api_key_input.value
    effective_key = raw_key.strip() if raw_key else ""
    return (effective_key,)


@app.cell
def _(effective_key, mo):
    key_ok = bool(effective_key) and effective_key.lower() not in {
        "api_key_input",
        "your_api_key",
        "paste your fmp api key here",
        "placeholder",
    }
    if not key_ok and not mo.app_meta().mode == "script":
        key_warning = mo.callout(
            mo.md(
                "Please paste a real FMP API key above. "
                "The field currently looks empty or contains a placeholder."
            ),
            kind="warn",
        )
    else:
        key_warning = None
    key_warning
    return (key_ok,)


@app.cell
def _():
    BASE_URL = "https://financialmodelingprep.com"

    SUBSCRIPTION_ACCESS = {
        "FMP Articles": "Full access",
        "General News": "Limited access",
        "Press Releases": "No access",
        "Stock News": "Limited access",
        "Crypto News": "Limited access",
        "Forex News": "Limited access",
        "Search Press Releases": "No access",
        "Search Stock News": "Limited access",
        "Search Crypto News": "Limited access",
        "Search Forex News": "Limited access",
    }

    ENDPOINTS = {
        "FMP Articles": {
            "path": "/stable/fmp-articles",
            "params": ["page", "limit"],
        },
        "General News": {
            "path": "/stable/news/general-latest",
            "params": ["page", "limit"],
        },
        "Press Releases": {
            "path": "/stable/news/press-releases-latest",
            "params": ["page", "limit"],
        },
        "Stock News": {
            "path": "/stable/news/stock-latest",
            "params": ["page", "limit"],
        },
        "Crypto News": {
            "path": "/stable/news/crypto-latest",
            "params": ["page", "limit"],
        },
        "Forex News": {
            "path": "/stable/news/forex-latest",
            "params": ["page", "limit"],
        },
    }
    return BASE_URL, ENDPOINTS, SUBSCRIPTION_ACCESS


@app.cell
def _(BASE_URL, requests):
    def fetch_fmp_news(api_key, endpoint_name, endpoints, page=0, limit=5):
        if not api_key:
            raise ValueError("API key is required")

        cfg = endpoints[endpoint_name]
        url = f"{BASE_URL}{cfg['path']}"
        params = {"apikey": api_key}

        if "page" in cfg["params"]:
            params["page"] = page
        if "limit" in cfg["params"]:
            params["limit"] = limit

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    return (fetch_fmp_news,)


@app.cell
def _(BASE_URL, requests):
    def count_fmp_articles(api_key, endpoint_name, endpoints, max_pages=100_000):
        """Infer the total number of articles by paginating with limit=1.

        FMP's news endpoints do not expose an official total-count field, so the
        only way to obtain an exact count is to walk pages until the API returns
        an empty list. We first use exponential search to bracket the first empty
        page, then binary search to pin it down. With limit=1, the first empty
        page index equals the total number of articles.
        """
        if not api_key:
            raise ValueError("API key is required")

        cfg = endpoints[endpoint_name]

        def fetch_page(page, limit):
            url = f"{BASE_URL}{cfg['path']}"
            params = {"apikey": api_key, "page": page, "limit": limit}
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []

        # Exponential search to find an empty page bracket.
        page = 0
        step = 1
        while page <= max_pages:
            data = fetch_page(page, limit=1)
            if not data:
                break
            page += step
            step *= 2
        else:
            return {
                "count": None,
                "error": f"Reached max_pages ({max_pages:,}) without finding the end.",
            }

        if page == 0:
            return {"count": 0, "error": None}

        # Binary search: low is known populated, high is known empty.
        low = page // 2
        high = page
        while low + 1 < high:
            mid = (low + high) // 2
            data = fetch_page(mid, limit=1)
            if data:
                low = mid
            else:
                high = mid

        return {"count": high, "error": None, "last_page_index": low}

    return (count_fmp_articles,)


@app.cell
def _(mo):
    endpoint_select = mo.ui.dropdown(
        options=[
            "FMP Articles",
            "General News",
            "Press Releases",
            "Stock News",
            "Crypto News",
            "Forex News",
        ],
        value="FMP Articles",
        label="News endpoint",
    )
    page_slider = mo.ui.slider(
        start=0,
        stop=10,
        step=1,
        value=0,
        label="Page",
    )
    size_slider = mo.ui.slider(
        start=1,
        stop=50,
        step=1,
        value=5,
        label="Limit",
    )

    search_form = (
        mo.md(
            """
            **FMP News search**

            {endpoint}

            {page}

            {limit}
            """
        )
        .batch(
            endpoint=endpoint_select,
            page=page_slider,
            limit=size_slider,
        )
        .form(
            label="",
            bordered=True,
            submit_button_label="Fetch news",
        )
    )
    search_form
    return (search_form,)


@app.function
def make_synthetic_articles(endpoint_name, limit=5):
    return [
        {
            "title": f"Synthetic {endpoint_name} article #{i + 1}",
            "date": "2026-10-28T00:00:00",
            "content": f"This is synthetic placeholder content for {endpoint_name}. "
                       "In script mode we do not call the live FMP API.",
            "tickers": "AAPL",
            "image": "",
            "link": "",
            "author": "demo",
        }
        for i in range(limit)
    ]


@app.cell
def _(
    ENDPOINTS,
    effective_key,
    fetch_fmp_news,
    is_script_mode,
    key_ok,
    requests,
    search_form,
):
    if is_script_mode:
        selected_endpoint = "FMP Articles"
        page = 0
        limit = 5
        raw_news = make_synthetic_articles(selected_endpoint, limit=limit)
        error = None
    elif search_form.value is not None:
        selected_endpoint = search_form.value["endpoint"]
        page = search_form.value["page"]
        limit = search_form.value["limit"]
        if not key_ok:
            raw_news = []
            error = "Invalid or missing FMP API key."
        else:
            try:
                raw_news = fetch_fmp_news(
                    api_key=effective_key,
                    endpoint_name=selected_endpoint,
                    endpoints=ENDPOINTS,
                    page=page,
                    limit=limit,
                )
                error = None
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code
                if status == 401:
                    raw_news = []
                    error = "Unauthorized (401). Please check that your FMP API key is valid."
                elif status == 403:
                    raw_news = []
                    error = (
                        f"Forbidden (403). The '{selected_endpoint}' endpoint may not be "
                        "included in your FMP subscription plan."
                    )
                else:
                    raw_news = []
                    error = f"HTTP {status}: {exc}"
            except Exception as exc:
                raw_news = []
                error = str(exc)
    else:
        selected_endpoint = "FMP Articles"
        page = 0
        limit = 5
        raw_news = []
        error = None

    has_fetched = is_script_mode or search_form.value is not None
    return error, has_fetched, raw_news, selected_endpoint


@app.cell
def _(SUBSCRIPTION_ACCESS, mo, pd, raw_news, selected_endpoint):
    access_level = SUBSCRIPTION_ACCESS.get(selected_endpoint, "Unknown")
    info = mo.md(
        f"### {selected_endpoint}\n"
        f"**Subscription access:** {access_level}"
    )
    info

    if isinstance(raw_news, list) and raw_news:
        df = pd.DataFrame(raw_news)
    elif isinstance(raw_news, dict):
        df = pd.json_normalize(raw_news)
    else:
        df = pd.DataFrame()
    return (df,)


@app.cell
def _(df, error, has_fetched, mo, selected_endpoint):
    if not has_fetched:
        result = mo.md("Submit the **FMP News search** form above to fetch data.")
    elif error:
        result = mo.callout(
            mo.md(f"**Error fetching {selected_endpoint}:** {error}"),
            kind="danger",
        )
    elif df.empty:
        result = mo.md(f"No data returned for **{selected_endpoint}**.")
    else:
        display_cols = [c for c in ["title", "date", "tickers", "author", "content"] if c in df.columns]
        result = mo.vstack(
            [
                mo.md(f"Fetched {len(df)} item(s) from **{selected_endpoint}**."),
                df[display_cols].head(20),
            ]
        )
    result
    return


@app.cell
def _(df):
    df
    return


@app.cell
def _(SUBSCRIPTION_ACCESS, mo, pd):
    access_table = pd.DataFrame(
        [
            {"Endpoint": k, "Starter access": v}
            for k, v in SUBSCRIPTION_ACCESS.items()
        ]
    )
    mo.md("## Subscription access summary")
    access_table
    return


@app.cell
def _(mo):
    count_endpoint_select = mo.ui.dropdown(
        options=[
            "FMP Articles",
            "General News",
            "Press Releases",
            "Stock News",
            "Crypto News",
            "Forex News",
        ],
        value="FMP Articles",
        label="Endpoint to count",
    )
    count_button = mo.ui.run_button(label="Count articles")
    mo.vstack(
        [
            mo.md("## Article count explorer"),
            mo.hstack([count_endpoint_select, count_button]),
        ]
    )
    return count_endpoint_select, count_button


@app.cell
def _(
    BASE_URL,
    ENDPOINTS,
    count_button,
    count_endpoint_select,
    count_fmp_articles,
    effective_key,
    is_script_mode,
    key_ok,
    requests,
):
    if is_script_mode:
        count_result = {
            "endpoint": "FMP Articles",
            "count": 42,
            "error": None,
            "note": "Synthetic count for script-mode demonstration.",
        }
    elif count_button.value:
        endpoint = count_endpoint_select.value
        if not key_ok:
            count_result = {
                "endpoint": endpoint,
                "count": None,
                "error": "Invalid or missing FMP API key.",
            }
        else:
            count_result = count_fmp_articles(
                api_key=effective_key,
                endpoint_name=endpoint,
                endpoints=ENDPOINTS,
                max_pages=100_000,
            )
            count_result["endpoint"] = endpoint
    else:
        count_result = None
    return (count_result,)


@app.cell
def _(count_result, mo):
    if count_result is None:
        output = mo.md(
            "Click **Count articles** above to estimate the total number of articles."
        )
    elif count_result.get("error"):
        output = mo.callout(
            mo.md(
                f"**Error counting {count_result['endpoint']}:** {count_result['error']}"
            ),
            kind="danger",
        )
    else:
        note = count_result.get("note", "")
        count = count_result["count"]
        items = [
            mo.md(f"### Estimated article count for **{count_result['endpoint']}**"),
            mo.md(f"**{count:,}** articles"),
            mo.md(
                "This count is inferred by paginating the endpoint until no more "
                "articles are returned. FMP does not expose an official total-count "
                "field in the news endpoints."
            ),
        ]
        if note:
            items.append(mo.md(f"*{note}*"))
        output = mo.vstack(items)
    output
    return


if __name__ == "__main__":
    app.run()
