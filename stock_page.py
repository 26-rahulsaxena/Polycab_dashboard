"""Stock-page layout: header, performance strip, main price chart, key stats, company info and seasonals."""
import base64
import datetime as dt
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from tab_stock import _prices
from ui import (SERIES, THEME, TTM, XLSX, arrow, base_layout, count, indian_ticks, inr, kv_card, load, ok_periods,
                q_label, rgba, show, source, sparkline, src)

YF = "yfinance POLYCAB.NS daily (prices.csv)"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
TIMEFRAMES = ["1M", "6M", "YTD", "1Y", "5Y", "All"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def prices():
    return _prices()


def _cls(v):
    return "flat" if v is None or pd.isna(v) or v == 0 else ("up" if v > 0 else "down")


def _pc(v, dec=2):
    return "n/a" if v is None or pd.isna(v) else f"{v:+.{dec}f}%".replace("-", "−")


def _base_close(p, days=None, trading=None):
    """Close `trading` sessions back, or the last close on/before (last date − days); None if before listing."""
    if trading is not None:
        return float(p.close.iloc[-1 - trading]) if len(p) > trading else None
    prior = p[p.date <= p.date.iloc[-1] - pd.Timedelta(days=days)]
    return None if prior.empty else float(prior.close.iloc[-1])


def market_open(now=None):
    now = now or dt.datetime.now(IST)
    return now.weekday() < 5 and dt.time(9, 15) <= now.time() < dt.time(15, 30)


# ---------------------------------------------------------------- header + performance strip
LOGO = Path(__file__).parent / "assets" / "polycab_logo.png"  # wordmark from the Q2 FY27 investor presentation cover


@st.cache_data
def _logo_img():
    if not LOGO.exists():
        return ""
    b64 = base64.b64encode(LOGO.read_bytes()).decode()
    return f'<img class="pc-logo" src="data:image/png;base64,{b64}" alt="Polycab logo">'


def header(p, meta, compact=False):
    last, prev = float(p.close.iloc[-1]), float(p.close.iloc[-2])
    chg, chg_pct = last - prev, (last / prev - 1) * 100
    sign = "+" if chg > 0 else ("−" if chg < 0 else "")
    is_open = market_open()
    status = ("pc-status-open", "Market open") if is_open else ("pc-status-closed", "Market closed")
    sector = meta.get("Sector")
    lq = load("quarterly").period.iloc[-1]
    badge = (f'<span class="pc-chip pc-data-chip" title="Financials to the {lq} quarter; prices to the last close">'
             f'<span class="pc-ico" aria-hidden="true">update</span>Data to {q_label(lq)} · prices '
             f'{p.date.iloc[-1]:%d %b %Y}</span>')
    if compact:  # one line under the sticky tab bar, repeated on every tab
        st.html(f"""
<div class="pc pc-header pc-header-compact">
  <span class="pc-name">{escape(str(meta.get("Company", "Polycab India Ltd")))}</span>
  <span class="pc-chip"><strong>NSE:POLYCAB</strong></span>
  {f'<span class="pc-chip pc-hide-sm">{escape(str(sector))}</span>' if sector else ''}
  <span class="pc-chip {status[0]}">{status[1]}</span>
  <span class="pc-price">₹{inr(last)}<small>INR</small></span>
  <span class="pc-change {_cls(chg)}">{arrow(chg, 2, "", "₹")} ({_pc(chg_pct)})</span>
  {badge}
</div>""")
        return
    st.html(f"""
<div class="pc pc-header">
  <div class="pc-brand">{_logo_img()}<h1>{escape(str(meta.get("Company", "Polycab India Ltd")))}</h1></div>
  <div class="pc-chips">
    <span class="pc-chip"><strong>NSE:POLYCAB</strong></span>
    {f'<span class="pc-chip">{escape(str(sector))}</span>' if sector else ''}
    <span class="pc-chip {status[0]}">{status[1]}</span>
    {badge}
  </div>
  <div class="pc-price-row">
    <span class="pc-price">₹{inr(last)}<small>INR</small></span>
    <span class="pc-change {_cls(chg)}">{arrow(chg, 2, "", "₹")} ({_pc(chg_pct)})</span>
  </div>
  <div class="pc-asof">Last close as of {p.date.iloc[-1]:%d %b %Y} · daily data from yfinance
    {'· the market is open, so today’s move is not included yet' if is_open else ''}</div>
</div>""")


def perf_strip(p):
    last = float(p.close.iloc[-1])
    last_d = p.date.iloc[-1]
    ytd = p[p.date < pd.Timestamp(year=last_d.year, month=1, day=1)]
    bases = [("1D", _base_close(p, trading=1)), ("5D", _base_close(p, trading=5)), ("1M", _base_close(p, 30)),
             ("6M", _base_close(p, 182)), ("YTD", float(ytd.close.iloc[-1]) if len(ytd) else None),
             ("1Y", _base_close(p, 365)), ("5Y", _base_close(p, 5 * 365)), ("All", float(p.close.iloc[0]))]
    cells = []
    for lab, b in bases:
        v = None if b is None else (last / b - 1) * 100
        cells.append(f'<div class="pc-perf-cell"><div class="lab">{lab}</div>'
                     f'<div class="val {_cls(v)}">{arrow(v)}</div></div>')
    st.html(f'<div class="pc pc-perf">{"".join(cells)}</div>')
    source(f"{YF}. Price return on the daily close. 1D/5D = trading sessions; YTD = from the last close of "
           f"{last_d.year - 1}; All = since listing ({p.date.iloc[0]:%d %b %Y}).")


# ---------------------------------------------------------------- main chart
def _window(p, tf):
    last_d = p.date.iloc[-1]
    start = {"1M": last_d - pd.Timedelta(days=30), "6M": last_d - pd.Timedelta(days=182),
             "YTD": pd.Timestamp(year=last_d.year, month=1, day=1), "1Y": last_d - pd.Timedelta(days=365),
             "5Y": last_d - pd.Timedelta(days=5 * 365)}.get(tf, p.date.iloc[0])
    return p[p.date >= start].reset_index(drop=True)


def _events(fig, d):
    """Mark dated company events on the price line (one colour per Expansions lane; filled = verified)."""
    from tab_expansions import LANE_ORDER, _frame
    e = _frame()
    e = e.assign(when=pd.to_datetime(e.when))
    e = e[e.when.notna() & (e.when >= d.date.iloc[0]) & (e.when <= d.date.iloc[-1])].sort_values("when")
    if e.empty:
        return 0
    # place each event on the close of its date (or the last session before it)
    e = pd.merge_asof(e, d[["date", "close"]].sort_values("date"), left_on="when", right_on="date",
                      suffixes=("", "_px"))
    lane_color = dict(zip(LANE_ORDER, SERIES))
    for lane in LANE_ORDER:
        x = e[e.lane == lane]
        if x.empty:
            continue
        hover = [f"<b>{r.event}</b><br>{r.date} · {r.category}<br>Source: {r.src}" for r in x.itertuples()]
        col = lane_color[lane]
        fig.add_scatter(x=x.date_px, y=x.close, mode="markers", name=lane, legendgroup="events",
                        marker=dict(symbol="diamond", size=11, color=[col if v else THEME["card"] for v in x.verified],
                                    line=dict(color=col, width=2)),
                        customdata=hover, hovertemplate="%{customdata}<extra></extra>", row=1, col=1)
    return len(e)


def price_chart(p):
    c = st.columns([1.2, 2.6, 1.1, 1.1, 0.9], vertical_alignment="center")
    kind = c[0].segmented_control("Chart type", ["Line", "Candles"], default="Line", key="chart_kind",
                                  label_visibility="collapsed") or "Line"
    tf = c[1].segmented_control("Timeframe", TIMEFRAMES, default="1Y", key="chart_tf",
                                label_visibility="collapsed") or "1Y"
    ma50 = c[2].toggle("50-day MA", key="ma50")
    ma200 = c[3].toggle("200-day MA", key="ma200")
    show_ev = c[4].toggle("Events", value=True, key="chart_events",
                          help="Plants, capex programmes, orders, launches and corporate actions (Expansions tab)")
    d = _window(p, tf)
    up, down = THEME["up"], THEME["down"]
    trend = up if d.close.iloc[-1] >= d.close.iloc[0] else down

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.03)
    fmt = [f"₹{inr(v)}" for v in d.close]
    if kind == "Candles":
        fig.add_trace(go.Candlestick(x=d.date, open=d.open, high=d.high, low=d.low, close=d.close, name="Price",
                                     increasing=dict(line=dict(color=up), fillcolor=up),
                                     decreasing=dict(line=dict(color=down), fillcolor=down)), row=1, col=1)
    else:
        lo, hi = float(d.close.min()), float(d.close.max())
        pad = (hi - lo) * 0.06 or hi * 0.02
        fig.add_scatter(x=d.date, y=d.close, name="Close", mode="lines", line=dict(color=trend, width=2),
                        fill="tozeroy", fillcolor=rgba(trend, 0.12), customdata=fmt,
                        hovertemplate="Close %{customdata}<extra></extra>", row=1, col=1)
        fig.update_yaxes(range=[lo - pad, hi + pad], row=1, col=1)
    for on, col, name, color in [(ma50, "dma50", "50-day MA", SERIES[1]), (ma200, "dma200", "200-day MA", SERIES[5])]:
        if on:
            fig.add_scatter(x=d.date, y=d[col], name=name, mode="lines", line=dict(color=color, width=1.6),
                            customdata=[f"₹{inr(v)}" if pd.notna(v) else "n/a" for v in d[col]],
                            hovertemplate=f"{name} %{{customdata}}<extra></extra>", row=1, col=1)
    n_ev = _events(fig, d) if show_ev else 0
    vol_col = [rgba(up if cl >= op else down, 0.55) for op, cl in zip(d.open, d.close)]
    fig.add_bar(x=d.date, y=d.volume, name="Volume", marker_color=vol_col, marker_line_width=0, showlegend=False,
                customdata=[f"{inr(v, 0)} · {'▲ up day' if cl >= op else '▼ down day'}"
                            for v, op, cl in zip(d.volume, d.open, d.close)],
                hovertemplate="Volume %{customdata}<extra></extra>",
                row=2, col=1)

    fig = base_layout(fig, None, None, height=560)
    fig.update_layout(bargap=0, barcornerradius=0, hovermode="x unified", showlegend=bool(ma50 or ma200 or n_ev),
                      legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, traceorder="normal",
                                  groupclick="toggleitem"),
                      xaxis_rangeslider_visible=False,
                      xaxis2_rangeslider=dict(visible=True, thickness=0.06, bgcolor=THEME["card"],
                                              bordercolor=THEME["grid"], borderwidth=1))
    spikes = dict(showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1, spikedash="dot",
                  spikecolor=THEME["text2"])
    fig.update_xaxes(type="date", showgrid=False, rangebreaks=[dict(bounds=["sat", "mon"])], **spikes)
    fig.update_yaxes(showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1, spikedash="dot",
                     spikecolor=THEME["text2"])
    fig.update_yaxes(title=None, tickprefix="₹", tickformat=",.0f", side="right", row=1, col=1)
    tv, _ = indian_ticks(float(d.volume.max()) / 1e5, 0, n=3)
    fig.update_yaxes(title=None, side="right", showgrid=False, row=2, col=1,
                     tickvals=[v * 1e5 for v in tv if v > 0], ticktext=[f"{v:g} L" for v in tv if v > 0])  # lakh
    show(fig, key="main_chart", animate=True)
    source(f"{YF}. Unadjusted daily prices; weekends hidden. Moving averages are simple averages of the close over "
           "50 and 200 trading days, computed on the full history. Drag the slider under the volume panel to zoom."
           + (f" Diamonds: {n_ev} company events from the Expansions tab (filled = verified against an annual report "
              "or presentation; each cites its source on hover), placed on the close of their date; quarter and "
              "year-only dates sit mid-period." if n_ev else ""))
    return d


# ---------------------------------------------------------------- overview: key stats, company info, seasonals
def _kv(label, value, note=""):
    return (f'<div><div class="k">{escape(label)}</div><div class="v">{value}</div>'
            + (f'<div class="n">{escape(note)}</div>' if note else "") + "</div>")


def kpi_strip(p, meta, years):
    """Six headline tiles: latest full year in the selected range vs the year before, with a trend sparkline."""
    a = load("annual").set_index("period")
    r = load("ratios_file").set_index("period")
    fys = [y for y in years if y in a.index and y != TTM]
    if not fys:
        return
    y1 = fys[-1]
    all_fy = [x for x in a.index if x != TTM]
    y0 = all_fy[all_fy.index(y1) - 1] if all_fy.index(y1) > 0 else None
    spark_years = fys if len(fys) >= 2 else all_fy[max(0, all_fy.index(y1) - 4): all_fy.index(y1) + 1]
    tiles = []

    def tile(label, val_html, delta_html, series, color, foot):
        tiles.append(f'<div class="pc-tile"><div class="lab">{label}</div><div class="val">{val_html}</div>'
                     f'<div class="row"><span class="dl">{delta_html}</span>{sparkline(series, color, label=label)}</div>'
                     f'<div class="ft">{foot}</div></div>')

    def money(col, label, color):
        v1, v0 = a[col].get(y1), a[col].get(y0) if y0 else None
        g = (v1 / v0 - 1) * 100 if v0 else None
        d = f'<span class="{_cls(g)}">{arrow(g, 1)}</span> YoY' if g is not None else "n/a"
        tile(label, f"₹{count(inr(v1, 0), v1)}<small>cr</small>", d, [a[col].get(x) for x in spark_years], color,
             f"{y1}{f' vs {y0}' if y0 else ''}")

    def ratio(col, label, color):
        v1, v0 = r[col].get(y1), r[col].get(y0) if y0 else None
        dp = v1 - v0 if v0 is not None and pd.notna(v0) else None
        d = f'<span class="{_cls(dp)}">{arrow(dp, 1, " pp")}</span> YoY' if dp is not None else "n/a"
        tile(label, f"{count(f'{v1:.1f}', v1, 1)}<small>%</small>", d, [r[col].get(x) for x in spark_years], color,
             f"{y1}{f' vs {y0}' if y0 else ''}")

    money("revenue", "Revenue", SERIES[0])
    money("operating_profit", "EBITDA", SERIES[1])
    money("pat", "Net profit (PAT)", SERIES[2])
    ratio("opm_pct", "EBITDA margin", SERIES[3])
    ratio("roce_pct", "ROCE", SERIES[4])
    shares, last = float(meta["Equity Shares (Cr)"]), float(p.close.iloc[-1])
    b = _base_close(p, 365)
    g = (last / b - 1) * 100 if b else None
    me = p.set_index("date").close.resample("ME").last().tail(12) * shares
    tile("Market cap", f"₹{count(inr(last * shares, 0), last * shares)}<small>cr</small>",
         f'<span class="{_cls(g)}">{arrow(g, 1)}</span> 1Y' if g is not None else "n/a", list(me), SERIES[5],
         f"last close {p.date.iloc[-1]:%d %b %Y}")
    st.html(f'<div class="pc pc-tiles">{"".join(tiles)}</div>')
    source(f"{src('annual', ['revenue', 'operating_profit', 'pat'], spark_years)}. EBITDA margin and ROCE: "
           f"{XLSX} (ROCE = EBIT / (equity + borrowings), year-end). Market cap: {YF} close × shares ({XLSX}); "
           f"its sparkline is the month-end market cap over 12 months. Sparklines span {spark_years[0]}–{spark_years[-1]}.",
           "At a glance")


def key_stats(p, meta, cols=4):
    a = load("annual").set_index("period")
    k = load("kpis")
    last, last_d = float(p.close.iloc[-1]), p.date.iloc[-1]
    shares = float(meta["Equity Shares (Cr)"])
    mcap = last * shares
    pat_ttm, eps_ttm = a.pat.get(TTM), a.eps.get(TTM)
    pe = mcap / pat_ttm if pat_ttm else None
    yr = p[p.date > last_d - pd.Timedelta(days=365)]
    dps = k[(k.kpi == "Dividend per share") & (k.period == "FY26") & k.verified].value
    items = [
        _kv("Market capitalisation", f"₹{inr(mcap, 0)}<small>cr</small>", f"close × {inr(shares, 2)} cr shares"),
        _kv("P/E (TTM)", f"{pe:.1f}x" if pe else "n/a", f"market cap / {TTM} PAT"),
        _kv("EPS (TTM)", f"₹{inr(eps_ttm)}" if pd.notna(eps_ttm) else "n/a", TTM),
    ]
    if len(dps):  # only shown when the dividend per share is verified
        items.append(_kv("Dividend yield", f"{dps.iloc[0] / last * 100:.2f}%",
                         f"FY26 dividend ₹{dps.iloc[0]:g} / last close"))
    items += [
        _kv("Revenue (FY26)", f"₹{inr(a.revenue['FY26'], 0)}<small>cr</small>", f"{TTM}: ₹{inr(a.revenue[TTM], 0)} cr"),
        _kv("Net income (FY26)", f"₹{inr(a.pat['FY26'], 0)}<small>cr</small>", f"{TTM}: ₹{inr(pat_ttm, 0)} cr"),
        _kv("52-week range", f"₹{inr(float(yr.low.min()), 0)} – ₹{inr(float(yr.high.max()), 0)}",
            "daily lows and highs"),
    ]
    q_src = src("quarterly", ["pat"], ["Sep'26"])
    srcs = [f"Price, market cap and 52-week range: {YF}, last close {last_d:%d %b %Y}; shares: {XLSX}.",
            f"Revenue and net income FY26: {src('annual', ['revenue', 'pat'], ['FY26'])}.",
            f"{TTM} PAT, EPS and revenue: sum of four quarters (Sep'26: {q_src}; earlier quarters: {XLSX})."]
    if len(dps):
        srcs.append("Dividend: Polycab Annual Report FY26, p.409 (final dividend recommended, subject to approval).")
    kv_card("Key stats", items, " ".join(srcs), cols)


def company_info(meta, cols=4):
    fields = [(lab, meta.get(key)) for lab, key in [("Sector", "Sector"), ("Industry", "Industry")]]
    fields = [(lab, v) for lab, v in fields if isinstance(v, str) and v.strip()]
    if not fields:
        return
    kv_card("Company info", [_kv(lab, escape(v)) for lab, v in fields], f"{XLSX} (classification).", cols)


def seasonals(p):
    s = p.set_index("date").close
    month_end = s.resample("ME").last()
    ret = month_end.pct_change() * 100
    ret.iloc[0] = (month_end.iloc[0] / s.iloc[0] - 1) * 100  # listing month: from the first close
    df = pd.DataFrame({"year": ret.index.year, "month": ret.index.month, "ret": ret.values})
    grid = df.pivot(index="year", columns="month", values="ret").reindex(columns=range(1, 13)).sort_index(ascending=False)
    last_d = p.date.iloc[-1]
    partial = (last_d.year, last_d.month)
    text = [[("" if pd.isna(v) else ("▲" if v > 0 else "▼" if v < 0 else "■") + f"{v:+.1f}".replace("-", "−")
              + ("*" if (y, m) == partial else ""))
             for m, v in zip(grid.columns, row)] for y, row in zip(grid.index, grid.values)]
    lim = float(min(max(abs(grid.min().min()), abs(grid.max().max())), 25))
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=MONTHS, y=[str(y) for y in grid.index], zmid=0, zmin=-lim, zmax=lim,
        colorscale=[[0, THEME["heat_down"]], [0.5, THEME["neutral"]], [1, THEME["heat_up"]]],
        text=text, texttemplate="%{text}", textfont=dict(size=11, color=THEME["text"]), xgap=3, ygap=3,
        hovertemplate="%{x} %{y}: %{text}<extra></extra>", colorbar=dict(ticksuffix="%", thickness=10)))
    st.subheader("Seasonals")
    st.caption("Monthly price return by year")
    fig = base_layout(fig, None, None, height=60 + 42 * len(grid))
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10))
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(type="category", gridcolor="rgba(0,0,0,0)", tickformat=None)
    fig.update_xaxes(side="top")
    show(fig)
    avg = grid.mean()
    best, worst = int(avg.idxmax()), int(avg.idxmin())
    source(f"{YF}. Month-end close vs previous month-end close (listing month from the first close, "
           f"{p.date.iloc[0]:%d %b %Y}). * = month to date ({last_d:%d %b %Y}). Average by month: best "
           f"{MONTHS[best - 1]} ({avg[best]:+.1f}%), worst {MONTHS[worst - 1]} ({avg[worst]:+.1f}%).")
