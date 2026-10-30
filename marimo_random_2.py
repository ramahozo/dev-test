import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return


@app.cell
def _():
    # pip install selenium pandas  (selenium >= 4.6 auto-downloads geckodriver)
    import time
    import random
    import pandas as pd
    from pathlib import Path
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.support.ui import WebDriverWait

    BASE_URL = "https://musaffa.com/stock-screener/?country=US&page={page}"
    START_PAGE, END_PAGE = 1, 438
    CHECKPOINT = Path("musaffa_crawled.csv")
    DELAY = (3, 6)
    LIBREWOLF_PATH = r"C:\Program Files\LibreWolf\librewolf.exe"

    EXTRACT_JS = """() => {
        const rows = [];
        document.querySelectorAll('table tbody tr').forEach(tr => {
            const tds = [...tr.querySelectorAll('td')];
            if (tds.length < 3) return;
            const ticker = tds[1]?.querySelector('.stock-ticker-chip')?.innerText?.trim()
                        || tds[1]?.innerText?.trim() || '';
            const name   = tds[1]?.querySelector('.stock-name-text')?.innerText?.trim() || '';
            rows.push([ticker, name, ...tds.slice(2).map(td => td.innerText.trim().replace(/\\s+/g, ' '))]);
        });
        return rows;
    }"""


    def crawl():
        done_pages = set()
        if CHECKPOINT.exists():
            done_pages = set(pd.read_csv(CHECKPOINT)["page"])

        opts = Options()
        opts.binary_location = LIBREWOLF_PATH
        # opts.add_argument("-headless")  # uncomment to hide the window
        driver = webdriver.Firefox(options=opts)
        driver.set_page_load_timeout(60)
        table_ready = WebDriverWait(driver, 30).until

        try:
            for n in range(START_PAGE, END_PAGE + 1):
                if n in done_pages:
                    continue
                for attempt in range(3):
                    try:
                        driver.get(BASE_URL.format(page=n))
                        table_ready(lambda d: d.execute_script(
                            "return document.querySelectorAll('table tbody tr').length") > 0)
                        time.sleep(1.5)

                        rows = driver.execute_script("return (" + EXTRACT_JS + ")()")
                        if not rows:
                            raise RuntimeError("no rows found")

                        df = pd.DataFrame(rows, columns=[
                            "Ticker", "Name", "Compliance", "Halal Rating", "Country",
                            "Sector", "Industry", "Market Cap", "Price", "Price Change",
                            "Price Change (%)", "52-Week High", "52-Week Low", "Analyst Rating",
                        ])
                        df.insert(0, "page", n)
                        df.to_csv(CHECKPOINT, mode="a", header=not CHECKPOINT.exists(), index=False)
                        print(f"page {n}: {len(df)} rows")
                        break
                    except Exception as e:
                        print(f"page {n} attempt {attempt+1} failed: {e}")
                        time.sleep(10 * (attempt + 1))
                time.sleep(random.uniform(*DELAY))
        finally:
            driver.quit()

    return (crawl,)


@app.cell
async def _(crawl):
    import asyncio
    await asyncio.to_thread(crawl)
    return


@app.cell
def _():
    return


@app.cell
def _():
    return


@app.cell
def _():
    from bs4 import BeautifulSoup
    import pandas as pd

    def html_table_to_df(html: str) -> pd.DataFrame:
        """Parse an Angular-rendered <table> outer HTML into a clean DataFrame.
        Ignores all links, images, and watchlist/star columns."""
        soup = BeautifulSoup(html, "html.parser")

        # Headers — drop the empty star/watchlist column
        headers = [h for h in (th.get_text(strip=True) for th in soup.select("thead th")) if h]

        rows = []
        for tr in soup.select("tbody tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            cells = tds[1:]  # first td is the watchlist star button

            row = []
            for i, td in enumerate(cells):
                if i == 0:  # name cell: ticker chip + company name (logo/link ignored)
                    ticker = td.select_one(".stock-ticker-chip")
                    name = td.select_one(".stock-name-text")
                    ticker_txt = ticker.get_text(strip=True) if ticker else td.get_text(strip=True)
                    name_txt = name.get_text(strip=True) if name else ""
                    row.append(f"{ticker_txt} - {name_txt}" if name_txt else ticker_txt)
                else:
                    row.append(" ".join(td.get_text(" ", strip=True).split()))
            rows.append(row)

        df = pd.DataFrame(rows, columns=headers[: len(rows[0])] if rows else headers)
        return df.replace("", "-")


    # ── Paste one or more HTML snippets here ──
    html_snippets = [
        '''PASTE_FIRST_TABLE_HTML_HERE''',
        # '''PASTE_SECOND_TABLE_HTML_HERE''',
    ]

    tables = [html_table_to_df(h) for h in html_snippets]
    combined_df = pd.concat(tables, ignore_index=True)
    combined_df  # display in Marimo
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
