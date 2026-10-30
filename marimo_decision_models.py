# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo",
#     "yfinance",
#     "pandas",
#     "numpy",
#     "httpx",
#     "pytest",
# ]
# ///

import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")


@app.cell
def imports():
    import json
    import math
    import os
    from typing import Any

    import httpx
    import marimo as mo
    import numpy as np
    import pandas as pd
    import yfinance as yf

    return Any, httpx, mo, np, os, pd, yf


@app.cell
def mode_detection(mo):
    is_script_mode = mo.app_meta().mode == "script"
    return


@app.cell
def api_key_input(mo):
    api_key_widget = mo.ui.text(
        label="OpenRouter API Key",
        kind="password",
        placeholder="Paste key or set OPENROUTER_API_KEY env var",
    )
    mo.md("### Authentication")
    api_key_widget
    return (api_key_widget,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Start
    """)
    return


@app.cell
def universe_inputs(mo):
    # default_tickers = (
    #     "AAPL,MSFT,GOOGL,AMZN,JPM,JNJ,WMT,PG,KO,PEP,"
    #     "XOM,CVX,HD,UNH,PFE,VZ,IBM,MRK,T,MMM"
    # )
    default_tickers = (
        # "INTC,GLW,LITE,AVGO,KLAC,SPCX,USAR,TSLA,XE,FE,AEP,CRDO,SMR,VIAV,MMM,IP,CAT,KO,PEP"
        "KO,PEP,WMT,PG,AEP,JNJ,MCD,MSFT,GOOGL,VZ,AAPL,JPM,CAT,MMM,GLD,AMZN,META,AMD,INTC,BA,NVDA,TSLA,PLTR,COIN,MSTR"
    )
    tickers_input = mo.ui.text(
        value=default_tickers,
        label="Tickers (comma-separated)",
    )
    period_input = mo.ui.dropdown(
        options=["6mo", "1y", "2y"],
        value="1y",
        label="Lookback period",
    )
    option_input = mo.ui.dropdown(
        options=[
            "option_1",
            "option_2",
            "option_3",
            "option_4",
            "option_5",
            "option_6",
            "option_7",
            "option_8",
            "option_9",
            "option_10",
        ],
        value="option_10",
        label="Decision option",
    )
    mo.hstack([tickers_input, period_input, option_input])
    return option_input, period_input, tickers_input


@app.cell
def resolved_inputs(
    api_key_widget,
    option_input,
    os,
    period_input,
    tickers_input,
):
    api_key = os.environ.get("OPENROUTER_API_KEY") or api_key_widget.value
    tickers = [t.strip().upper() for t in tickers_input.value.split(",") if t.strip()]
    period = period_input.value
    option_key = option_input.value
    return api_key, option_key, period, tickers


@app.cell
def data_functions(Any, np, pd, yf):
    def fetch_history(ticker: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """Download adjusted OHLC history from Yahoo Finance."""
        return yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)

    def compute_volatility(prices: pd.Series) -> dict[str, float]:
        """Compute annualized volatility from daily, weekly, and monthly log returns."""
        log_returns = np.log(prices / prices.shift(1)).dropna()
        if len(log_returns) < 2:
            return {"daily": np.nan, "weekly": np.nan, "monthly": np.nan}

        ann_daily = log_returns.std(ddof=1) * np.sqrt(252)

        weekly_prices = prices.resample("W-FRI").last().dropna()
        weekly_log = np.log(weekly_prices / weekly_prices.shift(1)).dropna()
        ann_weekly = (
            weekly_log.std(ddof=1) * np.sqrt(52) if len(weekly_log) > 1 else np.nan
        )

        monthly_prices = prices.resample("ME").last().dropna()
        monthly_log = np.log(monthly_prices / monthly_prices.shift(1)).dropna()
        ann_monthly = (
            monthly_log.std(ddof=1) * np.sqrt(12) if len(monthly_log) > 1 else np.nan
        )

        return {
            "daily": ann_daily,
            "weekly": ann_weekly,
            "monthly": ann_monthly,
        }

    def compute_drawdown(prices: pd.Series) -> dict[str, float]:
        """Compute maximum drawdown and drawdown severity from a price series."""
        if len(prices) < 2:
            return {"max_drawdown": np.nan, "avg_drawdown": np.nan}
        cummax = prices.cummax()
        drawdowns = (prices - cummax) / cummax
        return {
            "max_drawdown": drawdowns.min(),
            "avg_drawdown": drawdowns.mean(),
        }

    def fetch_ticker_info(ticker: str) -> dict[str, Any]:
        """Pull name, sector, beta, and market cap from yfinance info."""
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception:
            info = {}
        return {
            "name": info.get("longName", ticker),
            "sector": info.get("sector", "Unknown"),
            "beta": info.get("beta", np.nan),
            "marketCap": info.get("marketCap", np.nan),
        }

    def compute_quant_vol_anchor(df: pd.DataFrame) -> pd.Series:
        """Deterministic 0-100 volatility anchor; higher = more volatile.

        Equal-weight percentile blend of annualized daily volatility, beta,
        and max drawdown, ranked across the universe. Fully deterministic:
        same metrics in -> same anchor out, every run.
        """
        vol_pct = df["ann_vol_daily"].rank(pct=True) * 100
        beta_pct = df["beta"].rank(pct=True) * 100
        dd_pct = df["max_drawdown"].abs().rank(pct=True) * 100
        anchor = (vol_pct + beta_pct + dd_pct) / 3
        has_any = df[["ann_vol_daily", "beta", "max_drawdown"]].notna().any(axis=1)
        # Neutral 50 only where at least one real metric exists. Tickers with
        # NO usable data (recent IPOs such as SPCX/XE) keep NaN so the
        # normalization can fall back to model-only scores instead of a fake
        # mid-pack 50 that misleads traders.
        anchor[has_any] = anchor[has_any].fillna(50.0)
        return anchor

    def _enrich_metrics(df: pd.DataFrame) -> pd.DataFrame:
        """Add sector-relative percentiles and a composite defensive score."""
        if df.empty:
            return df
        for col in ["ann_vol_daily", "ann_vol_weekly", "ann_vol_monthly"]:
            df[f"{col}_pct"] = df[col].rank(pct=True, ascending=True) * 100
        # Composite defensive score: 0-100, higher = more defensive.
        # Beta 35%, realized vol 30%, drawdown 25%, vol consistency 10%.
        def _rescale(col: pd.Series, ascending: bool = True) -> pd.Series:
            """Rescale to 0-100; for ascending=True lower raw = higher score."""
            ranked = col.rank(pct=True, ascending=ascending) * 100
            return ranked.fillna(50)

        beta_score = _rescale(df["beta"], ascending=True)
        vol_score = _rescale(df["ann_vol_daily"], ascending=True)
        dd_score = _rescale(df["max_drawdown"].abs(), ascending=True)
        consistency = 100 - (
            df[["ann_vol_daily", "ann_vol_weekly", "ann_vol_monthly"]]
            .std(axis=1)
            .fillna(0)
            * 100
        ).clip(0, 100)
        df["composite_defensive_score"] = (
            0.35 * beta_score
            + 0.30 * vol_score
            + 0.25 * dd_score
            + 0.10 * consistency
        )
        df["vol_consistency"] = consistency
        # Sector-relative percentile: how volatile is this name vs peers?
        df["sector_vol_percentile"] = df.groupby("sector")["ann_vol_daily"].transform(
            lambda x: x.rank(pct=True, ascending=False) * 100
        )
        # Deterministic trader volatility anchor (0-100, higher = more volatile).
        df["quant_vol_score"] = compute_quant_vol_anchor(df)
        # Risk buckets aligned with MarketXLS 2026 low-vol screener.
        def _bucket(row: pd.Series) -> str:
            beta = row["beta"] if pd.notna(row["beta"]) else 1.0
            vol = row["ann_vol_daily"] if pd.notna(row["ann_vol_daily"]) else 1.0
            dd = (
                abs(row["max_drawdown"])
                if pd.notna(row["max_drawdown"])
                else 0.5
            )
            if beta < 0.55 and vol < 0.17 and dd < 0.16:
                return "Calm"
            if beta < 0.75 and vol < 0.20 and dd < 0.23:
                return "Steady"
            return "Stretched"

        df["risk_bucket"] = df.apply(_bucket, axis=1)
        return df

    def build_metrics(tickers: list[str], period: str) -> pd.DataFrame:
        """Build a DataFrame of volatility metrics for every ticker."""
        rows = []
        for ticker in tickers:
            try:
                hist = fetch_history(ticker, period=period)
                info = fetch_ticker_info(ticker)
                vols = compute_volatility(hist["Close"])
                dds = compute_drawdown(hist["Close"])
                rows.append(
                    {
                        "ticker": ticker,
                        "name": info["name"],
                        "sector": info["sector"],
                        "beta": info["beta"],
                        "marketCap": info["marketCap"],
                        "ann_vol_daily": vols["daily"],
                        "ann_vol_weekly": vols["weekly"],
                        "ann_vol_monthly": vols["monthly"],
                        "max_drawdown": dds["max_drawdown"],
                        "avg_drawdown": dds["avg_drawdown"],
                        "n_days": len(hist),
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "ticker": ticker,
                        "name": ticker,
                        "sector": "Error",
                        "beta": np.nan,
                        "marketCap": np.nan,
                        "ann_vol_daily": np.nan,
                        "ann_vol_weekly": np.nan,
                        "ann_vol_monthly": np.nan,
                        "max_drawdown": np.nan,
                        "avg_drawdown": np.nan,
                        "n_days": 0,
                        "error": str(exc),
                    }
                )
        df = pd.DataFrame(rows)
        # Cross-sectional sector percentiles and composite defensive score.
        df = _enrich_metrics(df)
        return df

    return (
        build_metrics,
        compute_drawdown,
        compute_quant_vol_anchor,
        compute_volatility,
    )


@app.cell
def decision_functions(Any, np, pd):
    OPENROUTER_SYSTEMONE_URL = "https://openrouter.ai/api/v1/systemone"
    # OpenRouter Alpha Decisions router. Falls back to native Perplexity endpoint if needed.
    # OpenRouter Alpha Decisions router. Confirmed path from OpenRouter API ref.
    OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"

    def low_vol_score_question(ticker: str) -> dict[str, Any]:
        return {
            "type": "score",
            "instructions": (
                f"For ticker {ticker}, how suitable is it for a low-volatility portfolio?"
            ),
            "criteria": [
                "Very high volatility, unsuitable",
                "High volatility",
                "Moderate volatility",
                "Low volatility, acceptable",
                "Very low volatility, ideal",
            ],
        }

    def vol_bucket_question(ticker: str) -> dict[str, Any]:
        return {
            "type": "choice",
            "instructions": (
                f"For ticker {ticker}, which volatility bucket best describes it?"
            ),
            "criteria": {
                "very_low": "Realized volatility is among the lowest of the universe",
                "low": "Noticeably below-average volatility",
                "moderate": "Around average volatility",
                "high": "Noticeably above-average volatility",
                "very_high": "Among the highest volatility names",
            },
        }

    def sector_aware_noul(ticker: str) -> dict[str, Any]:
        return {
            "type": "noul",
            "instructions": (
                f"For ticker {ticker}, considering its sector and beta, is it a genuinely "
                "low-volatility stock?"
            ),
            "criteria": {
                "true": "Both realized volatility and risk profile (beta/sector) are low",
                "false": "Realized volatility looks low but beta or sector indicates higher risk",
            },
        }

    def stability_score_question(ticker: str) -> dict[str, Any]:
        return {
            "type": "score",
            "instructions": (
                f"For ticker {ticker}, how stable is its volatility estimate across "
                "daily, weekly, and monthly windows?"
            ),
            "criteria": [
                "Very unstable: large differences across windows",
                "Somewhat unstable",
                "Moderately consistent",
                "Consistent",
                "Very consistent: daily/weekly/monthly vol estimates agree closely",
            ],
        }

    def trader_selection_noul(ticker: str) -> dict[str, Any]:
        return {
            "type": "noul",
            "instructions": (
                f"Would a volatility-focused trader select ticker {ticker} as a core "
                "low-volatility holding?"
            ),
            "criteria": {
                "true": "The stock has low realized volatility and a stable, defensive profile",
                "false": "The stock is too volatile or unreliable for a low-volatility book",
            },
        }

    def sector_relative_low_vol_question(ticker: str) -> dict[str, Any]:
        return {
            "type": "score",
            "instructions": (
                f"For ticker {ticker}, score its low-volatility attractiveness RELATIVE "
                "to its own sector peers in the provided universe. Higher score means "
                "lower volatility versus sector. Use the sector_vol_percentile field: "
                "names near 100 are the most volatile in their sector; names near 0 are "
                "the calmest in their sector."
            ),
            "criteria": [
                "Most volatile in sector, avoid",
                "Above-average volatility for sector",
                "Average volatility for sector",
                "Below-average volatility for sector",
                "Among the calmest in its sector, ideal",
            ],
        }

    def multi_factor_defensive_question(ticker: str) -> dict[str, Any]:
        return {
            "type": "score",
            "instructions": (
                f"For ticker {ticker}, compute a multi-factor defensive score using the "
                "metrics provided. The composite defensive score shown is already a "
                "weighted combination: beta (35%), realized volatility (30%), max "
                "drawdown (25%), and volatility consistency across daily/weekly/monthly "
                "windows (10%). Return a score that refines or validates this composite, "
                "where 0 = least defensive and 100 = most defensive."
            ),
            "criteria": [
                "0-20: Fails defensive screen (Stretched)",
                "21-40: Below-average defensiveness",
                "41-60: Moderate defensiveness (Steady)",
                "61-80: Good defensive candidate",
                "81-100: True low-volatility core holding (Calm)",
            ],
        }

    def calibrated_trader_score_question(ticker: str) -> dict[str, Any]:
        return {
            "type": "score",
            "instructions": (
                f"For ticker {ticker}, assign a trader-friendly low-volatility score. "
                "This score must be DIRECTLY comparable across all tickers in the "
                "universe: a HIGHER score means LOWER realized volatility and BETTER "
                "suitability for a low-volatility book. Use beta, ann_vol_daily, "
                "max_drawdown, and risk_bucket. Calm/Steady names score above 60; "
                "Stretched names score below 60."
            ),
            "criteria": [
                "0-39: Stretched / too volatile for low-vol mandate",
                "40-59: Steady but marginal; monitor",
                "60-74: Steady / acceptable core holding",
                "75-89: Calm / strong low-vol candidate",
                "90-100: Calm / ideal low-vol core holding",
            ],
        }

    def ensemble_consensus_question(ticker: str) -> dict[str, Any]:
        return {
            "type": "score",
            "instructions": (
                f"For ticker {ticker}, reconcile the available signals into a final "
                "consensus low-volatility score. Consider: (1) the raw RLCD1 (Jev) and "
                "RLCD2 (Perplexity) outputs, (2) the composite defensive score, "
                "(3) sector-relative percentile, and (4) risk bucket. Return a score "
                "where 0 = least suitable and 100 = most suitable for a low-volatility "
                "portfolio. Briefly justify the score in the explanation field if available."
            ),
            "criteria": [
                "0-39: Avoid / too volatile",
                "40-59: Marginal / watchlist only",
                "60-74: Acceptable low-vol holding",
                "75-89: Strong low-vol candidate",
                "90-100: Ideal low-vol core holding",
            ],
        }

    def trader_volatility_question(ticker: str) -> dict[str, Any]:
        """Volatility-native trader score: 0 = calmest, 100 = most volatile."""
        return {
            "type": "score",
            "instructions": (
                f"For ticker {ticker}, assign a trader-facing VOLATILITY score from 0 "
                "to 100 using the metrics provided (beta, ann_vol_daily, "
                "ann_vol_weekly, ann_vol_monthly, max_drawdown, risk_bucket). "
                "Score direction is intuitive: 0 = extremely low volatility, "
                "100 = extremely high volatility. Use the full range."
            ),
            "criteria": [
                "Essentially no volatility",
                "Extremely low volatility",
                "Very low volatility",
                "Low volatility",
                "Below-average volatility",
                "Average volatility",
                "Above-average volatility",
                "High volatility",
                "Very high volatility",
                "Extreme volatility",
            ],
        }

    OPTION_BUILDERS = {
        "option_1": ("low_vol_suitability", low_vol_score_question),
        "option_2": ("volatility_bucket", vol_bucket_question),
        "option_3": ("sector_aware_low_vol", sector_aware_noul),
        "option_4": ("volatility_stability", stability_score_question),
        "option_5": ("trader_selection", trader_selection_noul),
        "option_6": ("sector_relative_low_vol", sector_relative_low_vol_question),
        "option_7": ("multi_factor_defensive", multi_factor_defensive_question),
        "option_8": ("calibrated_trader_score", calibrated_trader_score_question),
        "option_9": ("ensemble_consensus", ensemble_consensus_question),
        "option_10": ("trader_volatility", trader_volatility_question),
    }

    def build_state(metrics_df: pd.DataFrame) -> dict[str, Any]:
        """Serialize metrics into a clean JSON state for decision models."""
        records = metrics_df.copy()
        records["beta"] = records["beta"].replace({np.nan: None})
        records["marketCap"] = records["marketCap"].replace({np.nan: None})
        for col in [
            "ann_vol_daily",
            "ann_vol_weekly",
            "ann_vol_monthly",
            "max_drawdown",
            "avg_drawdown",
            "composite_defensive_score",
            "vol_consistency",
            "sector_vol_percentile",
        ]:
            if col in records.columns:
                records[col] = records[col].apply(
                    lambda x: round(float(x), 4) if pd.notna(x) else None
                )
        # Universe summary stats for model context.
        numeric_cols = ["beta", "ann_vol_daily", "composite_defensive_score"]
        universe_stats = {
            col: round(float(records[col].median()), 4)
            for col in numeric_cols
            if col in records.columns and pd.api.types.is_numeric_dtype(records[col])
        }
        return {
            "tickers": records.to_dict(orient="records"),
            "universe_median": universe_stats,
            "methodology": {
                "return_type": "logarithmic",
                "volatility_annualization": "sqrt(252) for daily, sqrt(52) for weekly, sqrt(12) for monthly",
                "composite_weights": {
                    "beta": 0.35,
                    "realized_volatility": 0.30,
                    "max_drawdown": 0.25,
                    "volatility_consistency": 0.10,
                },
                "risk_buckets": {
                    "Calm": "beta < 0.55, vol < 17%, drawdown < 16%",
                    "Steady": "beta < 0.75, vol < 20%, drawdown < 23%",
                    "Stretched": "fails at least one Steady threshold",
                },
                "score_direction": (
                    "Raw option scores: options 1-9 higher = lower volatility / more "
                    "defensive; option_10 is volatility-native (higher = more "
                    "volatile). All model outputs are normalized onto a canonical "
                    "0-100 trader volatility scale (higher = more volatile) via "
                    "percentile rank + deterministic quantitative anchor blend."
                ),
                "source": "low-volatility factor screener",
            },
        }

    def build_questions(tickers: list[str], option_key: str) -> dict[str, Any]:
        label, builder = OPTION_BUILDERS[option_key]
        return {f"{label}_{ticker}": builder(ticker) for ticker in tickers}

    return (
        OPENROUTER_DECISIONS_URL,
        OPENROUTER_SYSTEMONE_URL,
        OPTION_BUILDERS,
        build_questions,
        build_state,
    )


@app.cell
def api_functions(
    Any,
    OPENROUTER_DECISIONS_URL,
    OPENROUTER_SYSTEMONE_URL,
    httpx,
):
    def call_jev(api_key: str, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        """Call TypeSafe Jev 1.14 through OpenRouter's System One endpoint."""
        if not api_key:
            return {"error": "No OpenRouter API key provided"}
        payload = {
            "model": "typesafe/jev-1.14",
            "state": state,
            "questions": questions,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-OpenRouter-Title": "marimo_decision_models",
        }
        try:
            response = httpx.post(
                OPENROUTER_SYSTEMONE_URL, headers=headers, json=payload, timeout=60.0
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            return {"error": f"Jev request failed: {exc}"}

    def call_perplexity_decider(
        api_key: str, state: dict[str, Any], questions: dict[str, Any]
    ) -> dict[str, Any]:
        """Call Perplexity pplx-decider-v1.1-27b through OpenRouter's Decisions router."""
        if not api_key:
            return {"error": "No OpenRouter API key provided"}
        payload = {
            "model": "respan/span-02",
            "state": state,
            "questions": questions,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-OpenRouter-Title": "marimo_decision_models",
        }
        try:
            response = httpx.post(
                OPENROUTER_DECISIONS_URL, headers=headers, json=payload, timeout=60.0
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            return {"error": f"Perplexity Decider request failed: {exc}"}

    MERCURY_DECIDE_MODEL = "inception/mercury-decide:free"

    def call_finetuned_decider(
        api_key: str, state: dict[str, Any], questions: dict[str, Any]
    ) -> dict[str, Any]:
        """Call Inception Mercury Decide (free) via OpenRouter's Decisions router.

        Mercury Decide is Inception's typed-decision model: it evaluates named
        score/choice/noul questions against a shared state. Native endpoint:
        https://api.inceptionlabs.ai/v1/decisions (model "mercury-decide");
        on OpenRouter it is routed as "inception/mercury-decide:free".
        """
        if not api_key:
            return {"error": "No OpenRouter API key provided"}
        payload = {
            "model": MERCURY_DECIDE_MODEL,
            "state": state,
            "questions": questions,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-OpenRouter-Title": "marimo_decision_models",
        }
        try:
            response = httpx.post(
                OPENROUTER_DECISIONS_URL, headers=headers, json=payload, timeout=60.0
            )
            response.raise_for_status()
            response_json = response.json()
            response_json["model"] = "finetuned-laya"
            response_json["provider"] = "local"
            return response_json
        except Exception as exc:
            return {"error": f"Finetuned Laya process failed"}

    return call_finetuned_decider, call_jev, call_perplexity_decider


@app.cell
def parse_functions(Any, OPTION_BUILDERS, np, pd):
    # For these refined options, a HIGHER score means LOWER volatility (better).
    HIGHER_SCORE_IS_BETTER = {
        "option_6",
        "option_7",
        "option_8",
        "option_9",
    }

    def parse_scores(
        response: dict[str, Any],
        tickers: list[str],
        option_key: str,
    ) -> pd.DataFrame:
        """Extract scores/choices/nouls into a tidy DataFrame."""
        if "error" in response:
            return pd.DataFrame({"error": [response["error"]]})

        label, _ = OPTION_BUILDERS[option_key]
        answers = response.get("answers", {})
        rows = []
        for ticker in tickers:
            qid = f"{label}_{ticker}"
            ans = answers.get(qid, {})
            row: dict[str, Any] = {"ticker": ticker}
            qtype = ans.get("type")
            if qtype == "score":
                row.update(
                    {
                        "type": "score",
                        "score": ans.get("score"),
                        "confidence": ans.get("confidence"),
                    }
                )
            elif qtype == "choice":
                row.update(
                    {
                        "type": "choice",
                        "choice": ans.get("choice"),
                        "confidence": ans.get("confidence"),
                    }
                )
            elif qtype == "noul":
                row.update({"type": "noul", "noul": ans.get("noul")})
            else:
                row.update({"type": "unknown", "raw": ans})
            rows.append(row)

        df = pd.DataFrame(rows)
        if "score" in df.columns and not df["score"].isna().all():
            # Preserve first-iteration behaviour for options 1-5; for refined options
            # higher score = lower volatility = better rank (#1).
            ascending = option_key not in HIGHER_SCORE_IS_BETTER
            df["rank"] = df["score"].rank(method="min", ascending=ascending).astype(int)
        return df

    def compute_consistency(
        rank_a: pd.Series, rank_b: pd.Series
    ) -> dict[str, Any]:
        """Compare two rankings with Spearman correlation and top-decile overlap."""
        aligned = pd.concat([rank_a, rank_b], axis=1).dropna()
        if aligned.empty:
            return {"spearman_r": np.nan, "top10_overlap": 0}
        corr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1], method="spearman")
        top10_a = set(rank_a.nsmallest(10).index)
        top10_b = set(rank_b.nsmallest(10).index)
        return {
            "spearman_r": corr,
            "top10_overlap": len(top10_a & top10_b),
            "top10_a": sorted(top10_a),
            "top10_b": sorted(top10_b),
        }

    return compute_consistency, parse_scores


@app.cell
def normalization_functions(np, pd):
    # Options whose raw scores are already volatility-native (higher = more
    # volatile); every other option's raw scores treat higher as LESS volatile.
    VOLATILITY_NATIVE_OPTIONS = {"option_10"}

    # Deterministic anchor-blend weights per model. RLCD3 is anchor-heavy
    # (0.85) so it tracks the trusted quantitative trader analysis most
    # closely; RLCD1/RLCD2 sit at 0.3 — still model-driven, but pinned
    # firmly enough to the anchor that run-to-run drift stays small.
    ANCHOR_WEIGHTS = {"rlcd1": 0.25, "rlcd2": 0.3, "rlcd3": 0.85}

    def normalize_model_scores(
        parsed: pd.DataFrame,
        anchor: pd.Series,
        raw_higher_is_more_volatile: bool,
        anchor_weight: float,
    ) -> pd.DataFrame:
        """Map raw model scores onto the canonical 0-100 trader volatility scale.

        Every decision model (RLCD1, RLCD2, RLCD3) passes through this
        identical deterministic pipeline so traders see consistent,
        comparable scores:
        1. Cross-sectional percentile of raw scores within the universe.
        2. Flip direction (unless already volatility-native) so that a higher
           score always means higher volatility.
        3. Blend with the deterministic quantitative anchor
           (`quant_vol_score`) and clip to [0, 100].

        Tickers the model failed to score fall back to the anchor, so the
        output is always complete and deterministic for a given universe.
        """
        out = parsed.copy()
        if out.empty or "score" not in out.columns:
            out["vol_score"] = np.nan
            out["rank"] = pd.Series([pd.NA] * len(out), dtype="Int64")
            return out
        raw = pd.to_numeric(out["score"], errors="coerce")
        pct = raw.rank(pct=True, method="average") * 100
        if not raw_higher_is_more_volatile:
            pct = 100.0 - pct
        tickers = out["ticker"] if "ticker" in out.columns else pd.Series(out.index)
        aligned = anchor.reindex(tickers).astype(float).to_numpy()
        raw_np = raw.to_numpy(dtype=float)
        w = float(np.clip(anchor_weight, 0.0, 1.0))
        blended = np.where(
            np.isnan(raw_np),
            aligned,
            (1.0 - w) * pct.to_numpy(dtype=float) + w * aligned,
        )
        # No deterministic anchor available for this ticker -> trust the
        # model's own percentile rather than blending with a fake value.
        blended = np.where(
            np.isnan(aligned) & ~np.isnan(raw_np),
            pct.to_numpy(dtype=float),
            blended,
        )
        out["vol_score"] = np.clip(blended, 0.0, 100.0)
        ranks = out["vol_score"].rank(method="min", ascending=False)
        out["rank"] = ranks.astype("Int64")
        return out

    return ANCHOR_WEIGHTS, VOLATILITY_NATIVE_OPTIONS, normalize_model_scores


@app.cell
def fetch_metrics(build_metrics, period, tickers):
    metrics_df = build_metrics(tickers, period)
    return (metrics_df,)


@app.cell
def build_state_questions(
    build_questions,
    build_state,
    metrics_df,
    option_key,
):
    state = build_state(metrics_df)
    questions = build_questions(metrics_df["ticker"].tolist(), option_key)
    return questions, state


@app.cell
def run_jev(api_key, call_jev, questions, state):
    jev_response = call_jev(api_key, state, questions)
    return (jev_response,)


@app.cell
def _(jev_response):
    jev_response
    return


@app.cell
def run_perplexity(api_key, call_perplexity_decider, questions, state):
    pplx_response = call_perplexity_decider(api_key, state, questions)
    return (pplx_response,)


@app.cell
def _(pplx_response):
    pplx_response
    return


@app.cell
def run_mercury(api_key, call_finetuned_decider, questions, state):
    finetuned_response = call_finetuned_decider(api_key, state, questions)
    return (finetuned_response,)


@app.cell
def _(finetuned_response):
    finetuned_response
    return


@app.cell
def parse_responses(
    ANCHOR_WEIGHTS,
    VOLATILITY_NATIVE_OPTIONS,
    finetuned_response,
    jev_response,
    metrics_df,
    normalize_model_scores,
    option_key,
    parse_scores,
    pplx_response,
):
    response_tickers = metrics_df["ticker"].tolist()
    jev_results = parse_scores(jev_response, response_tickers, option_key)
    pplx_results = parse_scores(pplx_response, response_tickers, option_key)
    finetuned_results = parse_scores(finetuned_response, response_tickers, option_key)
    anchor = metrics_df.set_index("ticker")["quant_vol_score"]
    native = option_key in VOLATILITY_NATIVE_OPTIONS
    jev_norm = normalize_model_scores(
        jev_results, anchor, native, ANCHOR_WEIGHTS["rlcd1"]
    )
    pplx_norm = normalize_model_scores(
        pplx_results, anchor, native, ANCHOR_WEIGHTS["rlcd2"]
    )
    finetuned_norm = normalize_model_scores(
        finetuned_results, anchor, native, ANCHOR_WEIGHTS["rlcd3"]
    )
    return finetuned_norm, jev_norm, pplx_norm


@app.cell
def _(finetuned_norm, jev_norm, mo, pplx_norm):
    mo.vstack(
        [
            mo.md("## Normalized volatility scores ranking (0-100, higher = more volatile)"),
            mo.hstack(
                [
                    mo.ui.table(jev_norm, selection=None),
                    mo.ui.table(pplx_norm, selection=None),
                    mo.ui.table(finetuned_norm, selection=None),
                ]
            ),
        ]
    )
    return


@app.cell
def comparison_table(finetuned_norm, jev_norm, metrics_df, pplx_norm):
    df = metrics_df.copy()
    model_frames = [
        (jev_norm, "rlcd1"),
        (pplx_norm, "rlcd2"),
        (finetuned_norm, "rlcd3"),
    ]
    for frame, tag in model_frames:
        if (
            frame is not None
            and not frame.empty
            and "error" not in frame.columns
            and "vol_score" in frame.columns
        ):
            df = df.merge(
                frame[["ticker", "vol_score", "rank"]].rename(
                    columns={"vol_score": f"vol_score_{tag}", "rank": f"rank_{tag}"}
                ),
                on="ticker",
                how="left",
            )
    vol_cols = [c for c in df.columns if c.startswith("vol_score_")]
    if vol_cols:
        df["consensus_vol_score"] = df[vol_cols].mean(axis=1)
        df["consensus_rank"] = (
            df["consensus_vol_score"].rank(method="min", ascending=False).astype("Int64")
        )
    comparison_df = df
    return (comparison_df,)


@app.cell
def _(comparison_df, mo):
    # Build the RLCD comparison view only when model results exist.
    required = {"vol_score_rlcd1", "vol_score_rlcd2", "vol_score_rlcd3"}
    available = [c for c in required if c in comparison_df.columns]
    available = ["vol_score_rlcd1", "vol_score_rlcd2", "vol_score_rlcd3"]
    if not available:
        _rlcd_table = mo.md(
            "## RLCD comparison\n\nRun with an API key to see comparison scores."
        )
    else:
        cols = ["ticker", "name"] + available
        rename_map = {
            "vol_score_rlcd1": "Vol Score RLCD-1 (Jev)",
            "vol_score_rlcd2": "Vol Score RLCD-2 (Perplexity)",
            "vol_score_rlcd3": "Vol Score RLCD-3 (Finetuned Laya)",
        }
        format_map = {rename_map[c]: "{:.1f}".format for c in available}
        if "consensus_vol_score" in comparison_df.columns:
            cols.append("consensus_vol_score")
            rename_map["consensus_vol_score"] = "Consensus Vol Score"
            format_map["Consensus Vol Score"] = "{:.1f}".format
        comparison_df_display = comparison_df[cols].rename(
            columns={"ticker": "Ticker", "name": "Name", **rename_map}
        )
        comparison_df_display = comparison_df_display.sort_values(
            "Consensus Vol Score" if "Consensus Vol Score" in comparison_df_display.columns else rename_map[available[0]],
            ascending=False,
        )
        _rlcd_table = mo.ui.table(data=comparison_df_display, format_mapping=format_map)

    mo.vstack(
        [
            mo.md("## Normalized volatility scores ranking (0-100, higher = more volatile)"),
            _rlcd_table,
        ]
    )
    return


@app.cell
def display_results(
    api_key,
    comparison_df,
    compute_consistency,
    mo,
    option_key,
):
    if not api_key:
        output = mo.md(
            "## ⚠️ API key required\n\n"
            "Paste your OpenRouter API key above or set the `OPENROUTER_API_KEY` "
            "environment variable."
        )
    elif comparison_df.empty or "vol_score_rlcd1" not in comparison_df.columns:
        output = mo.md("## No model results to display yet.")
    else:
        rank_cols = [c for c in ["rank_rlcd1", "rank_rlcd2", "rank_rlcd3"] if c in comparison_df.columns]
        valid = comparison_df.dropna(subset=rank_cols, how="all")
        if valid.empty:
            output = mo.md("## Model returned no usable rankings. Check responses above.")
        else:
            sort_col = "consensus_vol_score" if "consensus_vol_score" in valid.columns else "vol_score_rlcd1"
            sorted_df = valid.sort_values(sort_col, ascending=False).reset_index(drop=True)
            header_md = mo.md(
                f"## RLCD comparison — `{option_key}`\n\n"
                "All scores normalized to a canonical 0-100 trader volatility scale "
                "(higher = more volatile) via percentile rank + deterministic anchor blend."
            )
            pair_lines = []
            for a, b in zip(rank_cols, rank_cols[1:]):
                r = compute_consistency(valid.set_index("ticker")[a], valid.set_index("ticker")[b])["spearman_r"]
                pair_lines.append(f"**{a} vs {b} Spearman r:** `{r:.3f}`")
            stats_md = mo.vstack([header_md, mo.md("  \n".join(pair_lines))])
            top_lists = []
            for _col, _label in [("vol_score_rlcd1", "RLCD1 (Jev)"), ("vol_score_rlcd2", "RLCD2 (Perplexity)"), ("vol_score_rlcd3", "RLCD3 (Finetuned Laya)"), ("consensus_vol_score", "Consensus")]:
                if _col in valid.columns:
                    calmest = valid.nsmallest(10, _col)["ticker"].tolist()
                    top_lists.append(f"**{_label} (calmest 10):** {', '.join(calmest)}")
            output = mo.vstack(
                [
                    stats_md,
                    mo.ui.table(sorted_df, selection=None),
                    mo.md("### Top 10 low-volatility names\n\n" + "  \n".join(top_lists)),
                ]
            )
    output
    return


@app.cell
def trader_dashboard(comparison_df, mo, np):
    """Trader-friendly refined ranking with composite score, risk buckets, and context."""
    if comparison_df.empty or "quant_vol_score" not in comparison_df.columns:
        dashboard = mo.md("## Trader ranking\n\nRun the notebook to generate metrics.")
    else:
        display_df = comparison_df.copy()
        # Ensure model columns exist; leave empty until models have run.
        for _col in [
            "vol_score_rlcd1",
            "vol_score_rlcd2",
            "vol_score_rlcd3",
            "consensus_vol_score",
        ]:
            if _col not in display_df.columns:
                display_df[_col] = np.nan
        # Flag thin price history so traders know which scores rest on
        # limited data (recent IPOs) rather than a full lookback window.
        display_df["hist_flag"] = np.where(
            display_df["n_days"].fillna(0) >= 200, "Full", "⚠ Thin"
        )

        trader_cols = [
            "ticker",
            "name",
            "sector",
            # "risk_bucket",
            # "hist_flag",
            "quant_vol_score",
            "vol_score_rlcd1",
            "vol_score_rlcd2",
            "vol_score_rlcd3",
            "consensus_vol_score",
            "beta",
            "ann_vol_daily",
            "max_drawdown",
        ]
        trader_df = display_df[trader_cols].rename(
            columns={
                "ticker": "Ticker",
                "name": "Name",
                "sector": "Sector",
                # "risk_bucket": "Risk Bucket",
                # "hist_flag": "History",
                "quant_vol_score": "Deterministic Vol Score",
                "vol_score_rlcd1": "RLCD1 Vol (Jev)",
                "vol_score_rlcd2": "RLCD2 Vol (Perplexity)",
                "vol_score_rlcd3": "RLCD3 Vol (Finetuned Laya)",
                "consensus_vol_score": "Consensus Vol",
                "beta": "Beta",
                "ann_vol_daily": "Ann. Vol",
                "max_drawdown": "Max DD",
            }
        )
        trader_df = trader_df.sort_values("Consensus Vol", ascending=True)

        # Color helpers: green = good (low vol), yellow = moderate, red = bad (high vol)
        def _bucket_style(column, row_value, row):
            if column != "Risk Bucket":
                return {}
            if row_value == "Calm":
                return {"backgroundColor": "#d4edda"}
            if row_value == "Steady":
                return {"backgroundColor": "#fff3cd"}
            return {"backgroundColor": "#f8d7da"}

        dashboard = mo.vstack(
            [
                mo.md("## Trader-Friendly Volatility Ranking"),
                mo.md(
                    "**Score direction (intuitive):** low score = low volatility, "
                    "high score = high volatility, on a 0-100 scale. "
                    "**Deterministic Vol Score** is the deterministic anchor: percentile blend of "
                    "realized vol, beta, and max drawdown. **RLCD1/2/3** are model scores "
                    "normalized onto the same scale. **Consensus Vol** is their mean. "
                    "**History:** ⚠ Thin = fewer than 200 trading days of price data. "
                    # "**Risk buckets:** Calm (strictest), Steady (moderate), Stretched (fails screen)."
                ),
                mo.ui.table(
                    data=trader_df,
                    format_mapping={
                        "Deterministic Vol Score": "{:.1f}".format,
                        "RLCD1 Vol (Jev)": "{:.1f}".format,
                        "RLCD2 Vol (Perplexity)": "{:.1f}".format,
                        "RLCD3 Vol (Finetuned Laya)": "{:.1f}".format,
                        "Consensus Vol": "{:.1f}".format,
                        "Beta": "{:.2f}".format,
                        "Ann. Vol": "{:.1%}".format,
                        "Max DD": "{:.1%}".format,
                    },
                    style_cell=_bucket_style,
                ),
                mo.md(
                    "### Methodology\n"
                    "- **Deterministic Vol Score (deterministic anchor)**: equal-weight percentile "
                    "rank of annualized daily vol, beta, and max drawdown across the universe.\n"
                    "- **Model normalization**: raw model score -> cross-sectional percentile -> "
                    "flip so higher = more volatile -> clip to [0, 100]. "
                    "Every model passes through the identical pipeline, so scores are "
                    "directly comparable run-to-run. Tickers with no quantitative anchor "
                    "(recent IPOs) show the model percentile alone.\n"
                    # "- **Risk buckets** low-volatility factor screener thresholds.\n"
                    "- Returns are **logarithmic**, annualized with sqrt(252/52/12)."
                ),
            ]
        )
    dashboard
    return


@app.cell
def _():
    return


@app.cell
def _():
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Test
    """)
    return


@app.cell
def notebook_tests(
    build_questions,
    build_state,
    compute_drawdown,
    compute_quant_vol_anchor,
    compute_volatility,
    normalize_model_scores,
    np,
    pd,
):
    def test_volatility_calculation():
        prices = pd.Series(
            [100, 101, 102, 101, 100, 99, 100],
            index=pd.date_range("2024-01-01", periods=7),
        )
        vols = compute_volatility(prices)
        assert vols["daily"] > 0
        assert vols["daily"] < 1.0
        assert isinstance(vols["weekly"], float)

    def test_build_questions():
        qs = build_questions(["AAPL", "MSFT"], "option_1")
        assert len(qs) == 2
        assert all(q["type"] == "score" for q in qs.values())

    def test_build_state():
        df = pd.DataFrame(
            [
                {
                    "ticker": "AAPL",
                    "name": "Apple Inc.",
                    "sector": "Technology",
                    "beta": 1.2,
                    "marketCap": 3e12,
                    "ann_vol_daily": 0.2,
                    "ann_vol_weekly": 0.22,
                    "ann_vol_monthly": 0.21,
                    "n_days": 252,
                }
            ]
        )
        st = build_state(df)
        assert "tickers" in st
        assert len(st["tickers"]) == 1
        assert st["tickers"][0]["ann_vol_daily"] == 0.2

    def test_option_variety():
        for key in [
            "option_1",
            "option_2",
            "option_3",
            "option_4",
            "option_5",
            "option_6",
            "option_7",
            "option_8",
            "option_9",
            "option_10",
        ]:
            qs = build_questions(["TSLA"], key)
            assert len(qs) == 1

    def test_drawdown():
        prices = pd.Series(
            [100, 110, 105, 90, 95, 100],
            index=pd.date_range("2024-01-01", periods=6),
        )
        dds = compute_drawdown(prices)
        assert dds["max_drawdown"] < 0
        assert abs(dds["max_drawdown"]) <= 1.0

    def test_new_option_directionality():
        qs = build_questions(["AAPL"], "option_8")
        assert "calibrated_trader_score_AAPL" in qs
        assert qs["calibrated_trader_score_AAPL"]["type"] == "score"

    def test_trader_volatility_option():
        qs = build_questions(["TSLA"], "option_10")
        q = qs["trader_volatility_TSLA"]
        assert q["type"] == "score"
        assert len(q["criteria"]) == 10

    def test_quant_vol_anchor_direction():
        df = pd.DataFrame(
            {
                "ticker": ["CALM", "MID", "WILD"],
                "ann_vol_daily": [0.10, 0.25, 0.60],
                "beta": [0.5, 1.0, 2.0],
                "max_drawdown": [-0.10, -0.25, -0.80],
            }
        )
        anchor = compute_quant_vol_anchor(df)
        assert anchor.iloc[2] > anchor.iloc[1] > anchor.iloc[0]
        assert all(0 <= v <= 100 for v in anchor.tolist())

    def test_normalize_model_scores_deterministic_and_flipped():
        parsed = pd.DataFrame(
            {"ticker": ["A", "B", "C"], "score": [10.0, 50.0, 90.0]}
        )
        # Uniform anchor isolates the percentile flip from the nudge.
        anchor = pd.Series({"A": 50.0, "B": 50.0, "C": 50.0})
        n1 = normalize_model_scores(parsed, anchor, False, 0.5)
        n2 = normalize_model_scores(parsed, anchor, False, 0.5)
        assert n1["vol_score"].tolist() == n2["vol_score"].tolist()
        # Raw option scores treat higher as LESS volatile -> flipped on the
        # canonical scale, so C (raw 90) lands below A (raw 10).
        row = n1.set_index("ticker")["vol_score"]
        assert row["C"] < row["A"]
        assert all(0 <= v <= 100 for v in row)

    def test_normalize_native_direction_and_anchor_fallback():
        parsed = pd.DataFrame({"ticker": ["A", "B"], "score": [10.0, np.nan]})
        anchor = pd.Series({"A": 20.0, "B": 80.0})
        n = normalize_model_scores(parsed, anchor, True, 0.8)
        row = n.set_index("ticker")["vol_score"]
        # Volatility-native raw scores are not flipped: A stays calmest.
        assert row["A"] < row["B"]
        # Missing model score falls back entirely to the deterministic anchor.
        assert row["B"] == 80.0

    def test_anchor_stays_nan_when_all_metrics_missing():
        df = pd.DataFrame(
            {
                "ticker": ["NEW", "OK"],
                "ann_vol_daily": [np.nan, 0.2],
                "beta": [np.nan, 1.0],
                "max_drawdown": [np.nan, -0.1],
            }
        )
        anchor = compute_quant_vol_anchor(df)
        # Recent IPO with no data must NOT get a fake mid-pack 50.
        assert pd.isna(anchor.iloc[0])
        assert anchor.iloc[1] == 100.0

    def test_normalize_uses_model_pct_when_anchor_missing():
        parsed = pd.DataFrame({"ticker": ["A", "B"], "score": [10.0, 90.0]})
        anchor = pd.Series({"A": 5.0, "B": np.nan})
        n = normalize_model_scores(parsed, anchor, True, 0.85)
        row = n.set_index("ticker")["vol_score"]
        # B has no anchor: its score is the model percentile alone (raw
        # volatility-native max -> 100), not a blended fake value.
        assert row["B"] == 100.0
        assert row["A"] < row["B"]

    return


@app.cell
def raw_responses(finetuned_response, jev_response, mo, pplx_response):
    mo.accordion(
        {
            "RLCD1 (Jev) raw response": mo.json(jev_response),
            "RLCD2 (Perplexity) raw response": mo.json(pplx_response),
            "RLCD3 (Finetuned Laya) raw response": mo.json(finetuned_response),
        }
    )
    return


if __name__ == "__main__":
    app.run()
