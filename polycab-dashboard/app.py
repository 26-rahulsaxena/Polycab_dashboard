"""Polycab India Ltd dashboard. Reads only data/processed/*.csv (built by etl.py, pdf_etl.py, prices.py)."""
import pandas as pd
import streamlit as st

import fin_sections
import stock_page
import tab_expansions
import tab_ratios
import tab_segments
import tab_peers
import tab_stock
from ui import table
from ui import begin_tab, count_up_script, filter_bar, glossary, reset_sources, sources_expander, synced
from ui import (C, SERIES, TTM, WARN, XLSX, bars, card, cr, inr, lines, load, load_css, ok_periods, pct, section,
                set_mode, show, source, src, fy_of_quarter)

SEP26 = "Sep'26"

st.set_page_config(page_title="Polycab India Ltd dashboard", page_icon="🔌", layout="wide")
load_css()
LIGHT = bool(st.session_state.get("light", False))  # header toggle; dark is the default
set_mode(LIGHT)
if LIGHT:
    st.html('<div class="pc-light-flag"></div>')

# ---------------------------------------------------------------- data
annual, bs, cf, ratios = load("annual"), load("balance_sheet"), load("cash_flow"), load("ratios_file")
quarterly, meta, prices = load("quarterly"), load("meta"), load("prices")
prices["date"] = pd.to_datetime(prices["date"])
quarterly["fy"] = quarterly.period.map(fy_of_quarter)
META = dict(zip(meta.key, meta.value))
FYS = [p for p in annual.period if p != TTM]

# ---------------------------------------------------------------- sidebar
TTM_LABEL = f"Include latest ({TTM})"


def year_range(where):
    # value= keeps it a range slider; the copy's state is still seeded from the shared value (see ui.synced)
    return synced(st.select_slider, "yr", where, "Year range", ("FY22", "FY26"), options=FYS, value=("FY22", "FY26"))


def frequency(where):
    return synced(st.radio, "freq", where, "Frequency", "Annual", options=["Annual", "Quarterly"], horizontal=True)


def latest(where):
    return synced(st.checkbox, "ttm", where, TTM_LABEL, True,
                  help=f"Adds the {TTM} column (four quarters to Sep'26) and, in quarterly views, the FY27 quarters.")


def period_bar(where, yr=True, fq=False, ttm=True):
    """'Select period' filter bar at the top of a tab; its controls mirror the sidebar ones."""
    with filter_bar(where):
        parts = [(w, fn) for on, w, fn in ((yr, 3, year_range), (fq, 2.2, frequency), (ttm, 2, latest)) if on]
        for col, (_, fn) in zip(st.columns([w for w, _ in parts], gap="medium", vertical_alignment="bottom"), parts):
            with col:
                fn(where)


with st.sidebar:
    st.header("Polycab India Ltd")
    st.caption("NSE: POLYCAB · ₹ crore unless stated")
    st.toggle("Light theme", key="light", help="Dark is the default. Switches the whole page between dark and light.")
    with filter_bar("side"):
        yr0, yr1 = year_range("side")
        freq = frequency("side")
        show_ttm = latest("side")
    st.divider()
    vo = load("verified_overrides")
    st.caption(f"**Data as of**  \nFinancials: FY18–FY26 and {TTM}  \nVerified against reports: "
               f"{int(vo.status.isin(['verified', 'changed']).sum())} figures  \n"
               f"Prices: yfinance POLYCAB.NS, last close {prices.date.max():%d %b %Y}")
    if st.button("Refresh prices"):
        from prices import fetch_prices
        try:
            fetch_prices()
            st.cache_data.clear()
            st.rerun()
        except Exception as e:  # network failure keeps the saved CSV
            st.error(f"Refresh failed, using saved prices: {e}")

sel = FYS[FYS.index(yr0): FYS.index(yr1) + 1]
periods = sel + ([TTM] if show_ttm else [])


def pick(df, col="period", keep=None):
    keep = keep or periods
    return df[df[col].isin(keep)].reset_index(drop=True)


q_sel = quarterly[quarterly.fy.isin(sel) | (show_ttm & (quarterly.fy > FYS[-1]))].reset_index(drop=True)

last_close = float(prices.close.iloc[-1])
shares_cr = float(META["Equity Shares (Cr)"])
yr_ago = prices[prices.date <= prices.date.max() - pd.Timedelta(days=365)]
close_1y = float(yr_ago.close.iloc[-1]) if len(yr_ago) else None

# ---------------------------------------------------------------- header, performance strip, main chart
reset_sources()
px = stock_page.prices()
# Section tabs first: theme.css pins their bar to the top of the page (sticky); the compact price header sits below.
TAB_NAMES = ['Overview', 'Financials', 'Ratios', 'Segments & KPIs', 'Expansions', 'Peers & Ownership']
tabs = st.tabs(TAB_NAMES)


def tab_top(i, **bar):
    """Start a tab: register its sources, show the compact price header and (optionally) the period filter bar."""
    begin_tab(TAB_NAMES[i])
    stock_page.header(px, META, compact=i != 0)  # landing tab (Overview): large name with the logo
    if bar.pop("period", True):
        period_bar(f"t{i}", **bar)


# ---------------------------------------------------------------- Overview
with tabs[0]:
    tab_top(0)
    section("At a glance", f"{sel[-1]} against the year before, with the trend across {sel[0]}–{sel[-1]}"
            if len(sel) > 1 else f"{sel[-1]} against the year before")
    stock_page.kpi_strip(px, META, sel)
    tab_segments.company_overview(beside=lambda: (stock_page.key_stats(px, META, cols=2),
                                                  stock_page.company_info(META, cols=2)))
    fin_sections.latest_quarter()

    begin_tab("Price chart")
    section("Share price", "Daily close, performance and moving averages")
    stock_page.perf_strip(px)
    window = stock_page.price_chart(px)
    with st.expander("Returns and drawdown"):
        tab_stock.render_returns(px, window)

    begin_tab('Overview')
    stock_page.seasonals(px)

    section("Financials", "Revenue and net income by year")
    d = pick(annual)
    with card("ov-revenue"):
        show(bars(d, "period", ["revenue", "pat"], ["Revenue", "Net income"], [C["revenue"], C["pat"]],
                  title="Revenue and net income"))
        source(src("annual", ["revenue", "pat"], [p for p in d.period if p != TTM],
                   f"{TTM} = sum of the four quarters to Sep'26 (Sep'26 quarter: "
                   f"{src('quarterly', ['revenue', 'pat'], [SEP26])})"))

# ---------------------------------------------------------------- Financials
with tabs[1]:
    tab_top(1, fq=True)
    if freq == "Annual":
        d = pick(annual)
        section("Growth and profitability", "Recent performance, margins and how revenue turns into profit")
        c1, c2 = st.columns([3, 2])
        with c1, card("performance"):
            show(bars(d, "period", ["revenue", "operating_profit", "pat"], ["Revenue", "EBITDA", "Net income"],
                      [C["revenue"], C["ebitda"], C["pat"]], title="Performance"))
            source(src("annual", ["revenue", "operating_profit", "pat"], list(d.period),
                       "EBITDA rebuilt from the consolidated P&L lines on the cited page"))
        with c2, card("margins"):
            rm = pick(ratios)
            show(lines(rm, "period", ["opm_pct", "npm_pct"], ["EBITDA margin", "Net margin"],
                       [C["opm"], C["npm"]], title="Margins"))
            source(src("annual", ["revenue", "operating_profit", "pat"], list(rm.period),
                       "margins = EBITDA or PAT / revenue"))
        with card("waterfall"):
            st.subheader(":material/waterfall_chart: Revenue to profit conversion")
            wf_year = fin_sections.waterfall(sel)
        if wf_year:
            with card("profit-flow"):
                st.subheader(f":material/account_tree: Profit flow, {wf_year}")
                st.caption("Where each rupee of revenue goes. Hover a band for its amount and share of revenue; "
                           "the year follows the picker above.")
                fin_sections.profit_flow(wf_year)

        section("Cash flow and financial health", "Cash generation, debt and the balance sheet")
        c = pick(cf)
        c = c.assign(capex=c.capex_fixed_assets_purchased.abs())
        c1, c2 = st.columns([3, 2])
        with c1, card("cashflow"):
            show(bars(c, "period", ["cash_from_operating", "capex", "free_cash_flow"],
                      ["Operating cash flow (CFO)", "Capex", "Free cash flow"],
                      [C["cfo"], C["capex"], C["fcf"]], title="CFO, capex and free cash flow"))
            source(src("cash_flow", ["cash_from_operating", "capex_fixed_assets_purchased"], list(c.period),
                       f"FCF = CFO − capex + fixed-asset sale proceeds. {TTM} CFO = H1 FY27 + FY26 − H1 FY26; "
                       f"{TTM} capex and FCF are n/a"))
        with c2, card("cfo-pat"):
            cp = pick(ratios)[["period", "cfo_to_pat"]]
            show(lines(cp, "period", ["cfo_to_pat"], ["CFO / PAT"], [C["cfo"]], title="CFO / PAT (%)"))
            source(src("cash_flow", ["cash_from_operating"], list(cp.period), "CFO / PAT in percent"))
        if "FY26" in periods:
            acc = load("kpis").set_index(["kpi", "period"]).value
            st.info(
                f"FY26 CFO/PAT of {pct(ratios.set_index('period').cfo_to_pat.get('FY26'))} is real but partly comes from "
                f"supplier finance: acceptances (bank-paid supplier bills, shown within trade payables) rose from "
                f"{cr(acc.get(('Acceptances', 'FY25')), 0)} to {cr(acc.get(('Acceptances', 'FY26')), 0)}."
            )
            source("Polycab Annual Report FY26, p.365 (acceptances note).", "Acceptances note")
        c1, c2 = st.columns(2)
        with c1, card("debt"):
            st.subheader(":material/shield: Debt level and coverage")
            fin_sections.debt_coverage(sel)
        with c2, card("position"):
            st.subheader(":material/account_balance: Financial position")
            fin_sections.financial_position(sel)

        section("Dividends", "Dividend per share, yield and history (verified figures only)")
        fin_sections.dividends(float(px.close.iloc[-1]))

        section("Balance sheet", "Selected items by year")
        b = pick(bs).copy()
        b["equity"] = b.equity_capital + b.reserves
        inv_ok = ok_periods("balance_sheet", "investments")
        b["net_cash"] = (b.cash_and_equivalents + b.investments - b.borrowings).where(b.period.isin(inv_ok))
        items = {  # 6 items max so each keeps a fixed palette slot (net block and CWIP are in the data table)
            "Equity (capital + reserves)": "equity",
            "Inventories": "inventories", "Trade receivables": "trade_receivables",
            "Cash and bank": "cash_and_equivalents", "Trade payables (incl. acceptances)": "trade_payables",
            "Net cash (cash + current investments − borrowings)": "net_cash",
        }
        chosen = st.multiselect("Items", list(items), default=["Equity (capital + reserves)", "Inventories",
                                                               "Trade receivables", "Trade payables (incl. acceptances)"])
        if chosen:
            cols = [items[i] for i in chosen]
            colors = [SERIES[list(items).index(i)] for i in chosen]
            show(bars(b, "period", cols, chosen, colors, title="Balance-sheet items"))
            keys = [c_ for c_ in cols if c_ not in ("equity", "net_cash")] + (["investments"] if "net_cash" in cols else [])
            source(src("balance_sheet", keys, list(b.period),
                       "Trade payables include acceptances (bank-paid supplier bills) in every period. Net cash uses "
                       "the reported current investments and is n/a where they are not verified (FY18–FY20)"))

        with st.expander("Balance-sheet notes"):
            st.caption(
                "Unclassified assets = other current + other non-current assets, less the current investments the "
                "dataset had left inside them. The remaining liability gap is mainly non-controlling interest "
                f"(FY26 {cr(b.set_index('period').get('non_controlling_interest', pd.Series(dtype=float)).get('FY26'))}; "
                "Polycab Annual Report FY26, p.317).")

        with st.expander("Data table (₹ crore)"):
            t = d.set_index("period")[["revenue", "operating_profit", "pat", "eps"]].rename(
                columns={"revenue": "Revenue", "operating_profit": "EBITDA", "pat": "PAT", "eps": "EPS (₹)"})
            t = t.join(c.set_index("period")[["cash_from_operating", "capex", "free_cash_flow"]].rename(
                columns={"cash_from_operating": "CFO", "capex": "Capex", "free_cash_flow": "FCF"}))
            t = t.join(b.set_index("period")[["equity", "borrowings", "cash_and_equivalents", "net_block", "cwip",
                                              "unclassified_assets_derived", "total_assets"]].rename(
                columns={"equity": "Equity", "borrowings": "Borrowings", "cash_and_equivalents": "Cash",
                         "net_block": "Net block", "cwip": "CWIP",
                         "unclassified_assets_derived": "Unclassified assets (derived)",
                         "total_assets": "Total assets"}))
            table(t.T.map(inr), width="stretch")
    elif q_sel.empty:
        st.info(f"Quarterly data starts at {quarterly.period.iloc[0]} (FY22). Widen the year range.")
    else:
        st.subheader(":material/calendar_month: Quarterly results")
        q = q_sel.copy()
        q["opm_pct"] = q.operating_profit / q.revenue * 100
        q["npm_pct"] = q.pat / q.revenue * 100
        pat_ = ["/" if v else "" for v in q.to_verify]
        show(bars(q, "period", ["revenue", "operating_profit", "pat"], ["Revenue", "EBITDA", "PAT"],
                  [C["revenue"], C["ebitda"], C["pat"]], title="Quarterly revenue, EBITDA, PAT", patterns=pat_))
        source(src("quarterly", ["revenue", "operating_profit", "pat"], list(q.period)))
        show(lines(q, "period", ["opm_pct", "npm_pct"], ["Operating margin", "Net margin"], [C["opm"], C["npm"]],
                   title="Quarterly margins"))
        source(src("quarterly", ["revenue", "operating_profit", "pat"], list(q.period),
                   "margins = operating profit or PAT / revenue"))
        st.info("Quarterly balance sheet and cash flow are not in the dataset. Switch to Annual for them.")
        with st.expander("Data table (₹ crore)"):
            t = q.set_index("period")[["revenue", "operating_profit", "pat", "eps"]]
            t.columns = ["Revenue", "EBITDA", "PAT", "EPS (₹)"]
            out = t.T.map(inr)
            out.columns = [f"{p} (to verify)" if v else p for p, v in zip(q.period, q.to_verify)]
            table(out, width="stretch")

# ---------------------------------------------------------------- Ratios
with tabs[2]:
    tab_top(2)
    tab_ratios.render(FYS, (yr0, yr1), show_ttm)
    st.divider()
    tab_stock.render_valuation(sel)

# ---------------------------------------------------------------- Segments & KPIs, Expansions
with tabs[3]:
    tab_top(3, fq=True)
    tab_segments.render(sel, freq, show_ttm)
with tabs[4]:
    tab_top(4, period=False)  # the timeline has its own period filter bar
    tab_expansions.render()

# ---------------------------------------------------------------- Peers & Ownership
with tabs[5]:
    tab_top(5, yr=False, ttm=False, fq=True)
    tab_peers.render(freq)

# ---------------------------------------------------------------- Glossary + Sources & notes, one per tab
TERMS = [
    ["TTM", "EBITDA", "EBITDA margin", "PAT", "ROCE", "YoY / QoQ", "pp", "PBIT margin", "Inter-segment elimination"],
    ["EBITDA", "PAT", "CFO", "FCF", "Acceptances", "TTM", "YoY / QoQ"],
    ["ROE", "ROCE", "DuPont", "EBITDA margin", "Cash conversion cycle", "Acceptances", "P/E", "EV/EBITDA", "pp"],
    ["PBIT margin", "Inter-segment elimination", "YoY / QoQ", "TTM"],
    ["TTM", "YoY / QoQ"],
    ["P/E", "ROE", "ROCE", "Promoter / FII / DII", "pp"],
]
for _i, _n in enumerate(TAB_NAMES):
    with tabs[_i]:
        glossary(TERMS[_i])
        sources_expander(["Price chart"] + TAB_NAMES if _i == 0 else [_n],
                         "Sources & notes (all tabs)" if _i == 0 else "Sources & notes")
count_up_script()

st.divider()
st.caption(
    "Sources: Polycab annual reports and investor presentations (where verified), company results, yfinance prices. "
    "Details in each tab's Sources & notes. ₹ crore unless stated. Independent student project, not affiliated with "
    "or endorsed by Polycab India Ltd. For education only, not investment advice."
)
