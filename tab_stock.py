"""Stock & Valuation tab: yfinance price/volume (prices.csv) and yearly valuation ratios."""
import pandas as pd
import streamlit as st
from plotly.subplots import make_subplots

from ui import table
from ui import rgba as _rgba
from ui import (SERIES, THEME, TTM, XLSX, arrow, bars, base_layout, card, inr, kv, kv_card, lines, load, mult, pct,
                show, source, src)

YF = "yfinance POLYCAB.NS daily (prices.csv)"
WINDOWS = {"1M": 30, "3M": 91, "6M": 182, "1Y": 365, "3Y": 3 * 365, "5Y": 5 * 365}
PRESETS = {"6M": 182, "1Y": 365, "3Y": 3 * 365, "5Y": 5 * 365, "Max": None}


def _prices():
    p = load("prices").copy()
    p["date"] = pd.to_datetime(p["date"])
    p = p.sort_values("date").reset_index(drop=True)
    p["dma50"] = p.close.rolling(50).mean()  # on full history, so the averages are valid at any range start
    p["dma200"] = p.close.rolling(200).mean()
    return p


def _base(p, days, col):
    """Close on or before (last date − days); None if before the first date."""
    target = p.date.iloc[-1] - pd.Timedelta(days=days)
    prior = p[p.date <= target]
    return None if prior.empty else float(prior[col].iloc[-1])


def _returns(p, meta):
    rows = []
    for label, d in WINDOWS.items():
        b, ba = _base(p, d, "close"), _base(p, d, "adj_close")
        pr = None if b is None else (p.close.iloc[-1] / b - 1) * 100
        tr = None if ba is None else (p.adj_close.iloc[-1] / ba - 1) * 100
        yrs = d / 365
        cagr = None if tr is None or yrs < 1 else ((1 + tr / 100) ** (1 / yrs) - 1) * 100
        rows.append({"Period": label, "Price return": pct(pr), "Total return (adj. close)": pct(tr),
                     "Annualised (total)": pct(cagr) if yrs >= 1 else "",
                     "Reported (undated)": pct(meta.get(f"Returns {label}"))})
    return pd.DataFrame(rows)


def _price_chart(d):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.04)
    for col, name, color, w in [("close", "Close", SERIES[0], 1.6), ("dma50", "50-day average", SERIES[1], 2),
                                ("dma200", "200-day average", SERIES[2], 2)]:
        fig.add_scatter(x=d.date, y=d[col], name=name, mode="lines", line=dict(color=color, width=w),
                        customdata=[f"₹{inr(v)}" if pd.notna(v) else "n/a" for v in d[col]],
                        hovertemplate=f"{name}: %{{customdata}}<extra></extra>", row=1, col=1)
    fig.add_bar(x=d.date, y=d.volume, name="Volume", marker_color=SERIES[0], opacity=0.45, marker_line_width=0,
                customdata=[inr(v, 0) for v in d.volume], hovertemplate="Volume: %{customdata}<extra></extra>",
                row=2, col=1, showlegend=False)
    fig = base_layout(fig, "Share price with 50- and 200-day averages; daily volume", None, height=520)
    fig.update_xaxes(type="date", showgrid=False)
    fig.update_yaxes(title="₹ per share", tickformat=",.0f", ticksuffix="", row=1, col=1)
    fig.update_yaxes(title="shares", tickformat="~s", row=2, col=1)
    fig.update_layout(bargap=0, barcornerradius=0)
    return fig


def _drawdown_chart(d):
    dd = (d.close / d.close.cummax() - 1) * 100
    x = pd.DataFrame({"date": d.date, "dd": dd})
    fig = lines(x, "date", ["dd"], ["Drawdown"], [THEME["down"]], title="Drawdown from peak (%)", fmt=pct)
    fig.update_traces(mode="lines", fill="tozeroy", line=dict(width=1.5), fillcolor=_rgba(THEME["down"], 0.15))
    fig.update_xaxes(type="date")
    fig.update_layout(showlegend=False, height=300)
    return fig, float(dd.min()), d.date[dd.idxmin()]


def _valuation(sel):
    r = load("ratios_file")
    fy = r[~r.is_ttm.astype(bool)].set_index("period")
    last5, last3 = fy.index[-5:], fy.index[-3:]
    keep = [p for p in sel if pd.notna(fy.p_to_e.get(p))]
    d = fy.loc[keep].reset_index() if keep else None
    specs = [("p_to_e", "P/E"), ("p_to_b", "P/B"), ("ev_to_ebitda", "EV/EBITDA")]
    med = {c: (fy.loc[last3, c].median(), fy.loc[last5, c].median()) for c, _ in specs + [("p_to_s", "P/S")]}
    return d, specs, med, (f"{last3[0]}–{last3[-1]}", f"{last5[0]}–{last5[-1]}")


def _current(p, meta):
    """Ratios at the latest yfinance close, from TTM Sep-26 fundamentals."""
    a = load("annual").set_index("period")
    b = load("balance_sheet").set_index("period")
    mcap = p.close.iloc[-1] * float(meta["Equity Shares (Cr)"])
    eq = b.equity_capital[TTM] + b.reserves[TTM]
    ev = mcap + b.borrowings[TTM] - b.cash_and_equivalents[TTM] - b.investments.fillna(0)[TTM]
    return {"p_to_e": mcap / a.pat[TTM], "p_to_b": mcap / eq, "ev_to_ebitda": ev / a.operating_profit[TTM],
            "p_to_s": mcap / a.revenue[TTM], "ev": ev}, mcap


def render_returns(p, d):
    """Drawdown over the chart's window and the returns table (shown under the main price chart)."""
    meta = dict(zip(load("meta").key, pd.to_numeric(load("meta").value, errors="coerce")))
    c1, c2 = st.columns([3, 2])
    with c1:
        fig, mdd, mdd_d = _drawdown_chart(d)
        show(fig)
        source(f"{YF}. Close vs its running peak within the selected range. Deepest: {mdd:.1f}% on {mdd_d:%d %b %Y}.")
    with c2:
        st.markdown("**Returns to last close**")
        table(_returns(p, meta), hide_index=True, width="stretch")
        source(f"{YF}; total return uses yfinance adjusted close (dividends). 'Reported (undated)' values: {XLSX}, "
               "at an undated price, shown for reference only.")


def render_valuation(sel):
    """Yearly valuation ratios with 3Y/5Y medians, and ratios at the last close (Ratios tab)."""
    p = _prices()
    meta = dict(zip(load("meta").key, pd.to_numeric(load("meta").value, errors="coerce")))
    st.subheader(":material/sell: Valuation")
    d, specs, med, (w3, w5) = _valuation(sel)
    cur, mcap = _current(p, meta)
    kv_card(f"Valuation at last close ({p.date.iloc[-1]:%d %b %Y})", [
        kv("Market capitalisation", f"₹{inr(mcap, 0)}<small>cr</small>"),
        kv("Enterprise value", f"₹{inr(cur['ev'], 0)}<small>cr</small>", "market cap + debt − cash − investments"),
        kv("P/E", mult(cur["p_to_e"], 1), f"{TTM} PAT"), kv("P/B", mult(cur["p_to_b"], 1), "Sep-26 equity"),
        kv("P/S", mult(cur["p_to_s"], 1), f"{TTM} revenue"), kv("EV/EBITDA", mult(cur["ev_to_ebitda"], 1), f"{TTM} EBITDA"),
    ], f"{YF} for the price; fundamentals: {TTM} figures (Sep'26 quarter and Sep-26 investments: Polycab investor "
       f"presentation Q2 FY27, slides 14–15; other inputs: {XLSX}).")
    if d is None or d.empty:
        st.info("Valuation ratios start in FY20 (listed April 2019). Widen the year range.")
    else:
        cols = st.columns(3)
        for box, (c, name) in zip(cols, specs):
            with box:
                fig = lines(d, "period", [c], [name], [SERIES[0]], title=f"{name} (x)", ysuffix="x",
                            yaxis_title="times", fmt=mult)
                m3, m5 = med[c]
                fig.add_hline(y=m5, line=dict(color=THEME["text2"], width=1, dash="dash"),
                              annotation_text=f"5Y median {m5:.1f}x", annotation_position="top right",
                              annotation_font=dict(size=11, color=THEME["text2"]))
                fig.add_hline(y=m3, line=dict(color=THEME["text2"], width=1, dash="dot"),
                              annotation_text=f"3Y median {m3:.1f}x", annotation_position="bottom right",
                              annotation_font=dict(size=11, color=THEME["text2"]))
                fig.update_layout(showlegend=False, height=320)
                show(fig)
                source(f"{XLSX} (yearly ratio at year-end price); medians of the yearly values, 3Y = {w3}, 5Y = {w5}.")

    t = pd.DataFrame({
        "Ratio": ["P/E", "P/B", "P/S", "EV/EBITDA"],
        f"3Y median ({w3})": [mult(med[c][0], 1) for c in ("p_to_e", "p_to_b", "p_to_s", "ev_to_ebitda")],
        f"5Y median ({w5})": [mult(med[c][1], 1) for c in ("p_to_e", "p_to_b", "p_to_s", "ev_to_ebitda")],
        f"At last close, on {TTM}": [mult(cur[c], 1) for c in ("p_to_e", "p_to_b", "p_to_s", "ev_to_ebitda")],
        "Reported (undated price)": [mult(meta.get(k), 2) for k in ("Price To Earnings", "Price To Book Value",
                                                                    "Price To Sales", "EV To EBITDA")],
    })
    table(t, hide_index=True, width="stretch")
    st.caption(f"Reported 5Y P/E median {mult(meta.get('Price To Earnings Median 5 Years'), 2)}; industry P/E median "
               f"{mult(meta.get('Industry PE Median'), 2)} (method not stated, so they can differ from the medians above).")
    source(f"At last close: market cap ₹{inr(mcap, 0)} cr (close × {inr(float(meta['Equity Shares (Cr)']), 2)} cr "
           f"shares) over {TTM} PAT, equity, revenue and EBITDA. EV = market cap + borrowings − cash − current "
           f"investments (Sep-26 investments: Polycab investor presentation Q2 FY27, slide 15). Reported medians and "
           f"yearly ratios: {XLSX}.", "Valuation table")
    with st.expander("Yearly valuation table"):
        r = load("ratios_file")
        r = r[~r.is_ttm.astype(bool) & r.p_to_e.notna()].set_index("period")
        table(r[["p_to_e", "p_to_b", "p_to_s", "ev_to_ebitda"]].rename(
            columns={"p_to_e": "P/E", "p_to_b": "P/B", "p_to_s": "P/S", "ev_to_ebitda": "EV/EBITDA"}).T.map(
            lambda v: mult(v, 2)), width="stretch")
        st.caption("FY18–FY19 are n/a (before listing).")
        source(f"{XLSX} (yearly valuation ratios at year-end prices).", "Yearly valuation table")
    _calculator(p, meta)


def _calculator(p, meta):
    """What-if valuation: grow TTM revenue, apply a net margin and an exit P/E, discount back. Illustrative only."""
    a = load("annual").set_index("period")
    r = load("ratios_file").set_index("period")
    fy = [x for x in a.index if x != TTM]
    base_rev, last = float(a.revenue[TTM]), float(p.close.iloc[-1])
    shares = float(meta["Equity Shares (Cr)"])
    y0, y5 = fy[-6], fy[-1]
    cagr = ((a.revenue[y5] / a.revenue[y0]) ** (1 / 5) - 1) * 100
    npm = a.pat[y5] / a.revenue[y5] * 100
    pe_hist = r.loc[[x for x in fy[-5:] if x in r.index], "p_to_e"].dropna()
    pe_med = float(pe_hist.median())

    st.subheader(":material/calculate: Valuation calculator (illustrative)")
    st.caption("Move the sliders to see what a set of assumptions would imply. Defaults come from the company's own "
               f"history: revenue growth = {y0}–{y5} CAGR, net margin = {y5}, exit P/E = median of {pe_hist.index[0]}–"
               f"{pe_hist.index[-1]}. This is arithmetic on your assumptions, not a forecast, a valuation opinion or "
               "investment advice.")
    with card("calc"):
        c = st.columns(5, gap="medium")
        g = c[0].slider("Revenue growth (% a year)", 0.0, 35.0, round(cagr, 1), 0.5, format="%.1f%%", key="calc_g")
        m = c[1].slider("Net margin (%)", 3.0, 16.0, round(npm, 1), 0.1, format="%.1f%%", key="calc_m")
        pe = c[2].slider("Exit P/E (x)", 10.0, 80.0, round(pe_med, 1), 0.5, format="%.1fx", key="calc_pe")
        n = c[3].select_slider("Years ahead", [3, 4, 5, 6, 7], value=5, key="calc_n")
        k = c[4].slider("Required return (% a year)", 6.0, 20.0, 12.0, 0.5, format="%.1f%%", key="calc_k",
                        help="The yearly return you would want; used to discount the exit value to today.")
        yrs = list(range(1, n + 1))
        rev = [base_rev * (1 + g / 100) ** t for t in yrs]
        pat = [v * m / 100 for v in rev]
        exit_mcap = pat[-1] * pe
        exit_px = exit_mcap / shares
        pv_px = exit_px / (1 + k / 100) ** n
        ret = ((exit_px / last) ** (1 / n) - 1) * 100
        gap = (pv_px / last - 1) * 100
        kv_card("Under these assumptions", [
            kv(f"Revenue in year {n}", f"₹{inr(rev[-1], 0)}<small>cr</small>", f"from {TTM} ₹{inr(base_rev, 0)} cr"),
            kv(f"Net profit in year {n}", f"₹{inr(pat[-1], 0)}<small>cr</small>", f"{m:.1f}% of revenue"),
            kv(f"Market cap in year {n}", f"₹{inr(exit_mcap, 0)}<small>cr</small>", f"profit × {pe:.1f}x"),
            kv(f"Share price in year {n}", f"₹{inr(exit_px, 0)}", f"÷ {inr(shares, 2)} cr shares"),
            kv("Value today at your return", f"₹{inr(pv_px, 0)}", f"{arrow(gap, 1)} vs last close ₹{inr(last, 0)}"),
            kv("Implied yearly price return", arrow(ret, 1), f"from ₹{inr(last, 0)} to ₹{inr(exit_px, 0)} over {n} years"),
        ], cols=3)
        d = pd.DataFrame({"period": [f"Year {t}" for t in yrs], "revenue": rev, "pat": pat})
        fig = bars(d, "period", ["revenue", "pat"], ["Revenue", "Net profit"],
                   [SERIES[0], SERIES[2]], title="Projected path under your assumptions")
        fig.update_layout(height=300)
        show(fig, key="calc_bars")
        source(f"Base: {TTM} revenue ({src('annual', ['revenue'], [TTM])}); last close: {YF}; shares: {XLSX}. "
               f"Defaults: revenue {y0}–{y5} ({src('annual', ['revenue'], [y0, y5])}), {y5} net margin, P/E: {XLSX}. "
               "Constant share count; dividends, dilution and net cash ignored. Not investment advice.",
               "Valuation calculator")
