"""Ratios tab: the file's own ratio rows, each recomputed from the statements as a cross-check."""
import pandas as pd
import streamlit as st

from ui import table
from ui import SERIES, TTM, WARN, XLSX, arrow, bars, days, inr, lines, load, mult, pct, show, source, src
FMT = {"%": pct, "x": mult, "days": days}


def _inputs():
    a = load("annual").set_index("period")
    b = load("balance_sheet").set_index("period")
    c = load("cash_flow").set_index("period")
    q = load("quarterly").set_index("period")
    return a, b, c, q


def _growth(s, q_col, q):
    """FY growth vs prior FY; TTM growth vs the TTM a year earlier (sum of the 4 quarters before the last 4)."""
    fy = s.drop(TTM)
    g = (fy / fy.shift(1) - 1) * 100
    prev_ttm = q[q_col].iloc[-8:-4].sum()
    g[TTM] = (s[TTM] / prev_ttm - 1) * 100 if len(q) >= 8 and pd.notna(s.get(TTM)) else float("nan")
    return g


def ratio_specs():
    """(column, label, unit, formula, recomputed series)."""
    a, b, c, q = _inputs()
    eq = b.equity_capital + b.reserves
    mat = a.material_cost
    return [
        # profitability
        ("opm_pct", "EBITDA margin", "%", "Operating profit / revenue", a.operating_profit / a.revenue * 100),
        ("npm_pct", "Net margin", "%", "PAT / revenue", a.pat / a.revenue * 100),
        ("gpm_pct", "Gross margin", "%", "(Revenue − material − manufacturing cost) / revenue",
         (a.revenue - a.material_cost - a.manufacturing_cost) / a.revenue * 100),
        # returns
        ("roe_pct", "ROE", "%", "PAT / (equity capital + reserves), year-end", a.pat / eq * 100),
        ("roce_pct", "ROCE", "%", "EBIT / (equity capital + reserves + borrowings), year-end",
         a.ebit / (eq + b.borrowings) * 100),
        ("roa_pct", "ROA", "%", "PAT / total assets, year-end", a.pat / b.total_assets * 100),
        # leverage / liquidity
        ("debt_to_equity", "Debt / equity", "x", "Borrowings / (equity capital + reserves)", b.borrowings / eq),
        ("interest_coverage", "Interest cover", "x", "EBIT / interest", a.ebit / a.interest),
        ("current_ratio", "Current ratio", "x", "Current assets / current liabilities",
         b.current_assets / b.current_liabilities),
        ("quick_ratio", "Quick ratio", "x", "(Current assets − inventories) / current liabilities",
         (b.current_assets - b.inventories) / b.current_liabilities),
        # efficiency
        ("receivable_days", "Receivable days", "days", "Trade receivables / revenue × 365",
         b.trade_receivables / a.revenue * 365),
        ("inventory_days", "Inventory days", "days", "Inventories / material cost × 365", b.inventories / mat * 365),
        ("payable_days", "Payable days", "days", "Trade payables / material cost × 365", b.trade_payables / mat * 365),
        ("cash_conversion_cycle", "Cash conversion cycle", "days", "Receivable days + inventory days − payable days",
         (b.trade_receivables / a.revenue + (b.inventories - b.trade_payables) / mat) * 365),
        ("asset_turnover", "Asset turnover", "x", "Revenue / total assets", a.revenue / b.total_assets),
        ("cfo_to_pat", "CFO / PAT", "%", "Cash from operations / PAT", c.cash_from_operating / a.pat * 100),
        ("cfo_to_ebitda", "CFO / EBITDA", "%", "Cash from operations / operating profit",
         c.cash_from_operating / a.operating_profit * 100),
        # growth
        ("revenue_growth_pct", "Revenue growth", "%", "Revenue / prior-year revenue − 1 (TTM: vs TTM Sep-25)",
         _growth(a.revenue, "revenue", q)),
        ("operating_profit_growth_pct", "Operating profit growth", "%", "Same, on operating profit",
         _growth(a.operating_profit, "operating_profit", q)),
        ("pat_growth_pct", "PAT growth", "%", "Same, on PAT", _growth(a.pat, "pat", q)),
        ("eps_growth_pct", "EPS growth", "%", "Same, on EPS", _growth(a.eps, "eps", q)),
    ]


@st.cache_data
def cross_check():
    """Per ratio: max |file − recomputed| over periods where both exist."""
    r = load("ratios_file").set_index("period")
    out = {}
    for col, label, unit, formula, calc in ratio_specs():
        both = pd.concat([r[col], calc], axis=1).dropna()
        diff = (both.iloc[:, 0] - both.iloc[:, 1]).abs().max() if len(both) else None
        tol = 0.01 if unit == "x" else 0.1
        out[col] = (len(both), diff, diff is not None and diff <= tol)
    return out


def _pct_section(title, chart_title, specs, r, note):
    """A section of percent ratios drawn on one chart."""
    st.subheader(title)
    show(lines(r, "period", [s[0] for s in specs], [s[1] for s in specs], SERIES[:len(specs)],
               title=chart_title, fmt=pct))
    source(src("annual", ["revenue", "operating_profit", "pat"], [p for p in r.period if p != TTM], note))


def _dupont(keep, r_file):
    """ROE = net margin × asset turnover × equity multiplier (year-end figures), with the latest change attributed."""
    import math
    a, b, _, _ = _inputs()
    yrs = [y for y in keep if y in a.index and y in b.index]
    eq = b.equity_capital + b.reserves
    d = pd.DataFrame({"period": yrs,
                      "npm": [a.pat[y] / a.revenue[y] * 100 for y in yrs],
                      "at": [a.revenue[y] / b.total_assets[y] for y in yrs],
                      "em": [b.total_assets[y] / eq[y] for y in yrs]})
    d["roe"] = d.npm * d["at"] * d.em
    if d.empty:
        return
    st.subheader(":material/account_tree: ROE breakdown (DuPont)")
    st.caption("ROE = net margin × asset turnover × equity multiplier. Each factor shows what drives returns: "
               "profitability, how hard the assets work, and how much of the balance sheet is funded by equity.")
    cols = st.columns(4)
    for box, (col, title, fmt, ys) in zip(cols, [
            ("roe", "ROE (%)", pct, "%"), ("npm", "Net margin (%)", pct, "%"),
            ("at", "Asset turnover (x)", mult, "x"), ("em", "Equity multiplier (x)", mult, "x")]):
        with box:
            show(lines(d, "period", [col], [title.split(" (")[0]], [SERIES[["roe", "npm", "at", "em"].index(col)]],
                       title=title, ysuffix=ys, yaxis_title=None, fmt=fmt))
    fy = [y for y in yrs if y != TTM]
    x1, x0 = (d.set_index("period").loc[fy[-1]], d.set_index("period").loc[fy[-2]]) if len(fy) >= 2 else (None, None)
    if x1 is not None and min(x1.min(), x0.min()) > 0:  # log split needs positive factors
        dr = x1.roe - x0.roe
        logs = {k: math.log(x1[k] / x0[k]) for k in ("npm", "at", "em")}
        tot = sum(logs.values())
        parts = {k: (dr * v / tot if abs(tot) > 1e-9 else 0.0) for k, v in logs.items()}
        name = {"npm": "net margin", "at": "asset turnover", "em": "leverage (equity multiplier)"}
        lead = max(parts, key=lambda k: abs(parts[k]))
        st.html(f'<div class="pc pc-callout"><span class="pc-ico" aria-hidden="true">insights</span><div>'
                f'<b>{fy[-1]} ROE {x1.roe:.1f}%</b> vs {x0.roe:.1f}% in {fy[-2]} ({arrow(dr, 1, " pp")}). By factor: '
                + "; ".join(f"{name[k]} {arrow(v, 1, ' pp')}" for k, v in parts.items())
                + f". The biggest driver was <b>{name[lead]}</b>.</div></div>")
    chk = [(y, d.set_index("period").roe[y], r_file.set_index("period").roe_pct.get(y)) for y in yrs]
    ok = all(f is None or pd.isna(f) or abs(v - f) < 0.6 for _, v, f in chk)
    source(src("annual", ["revenue", "pat"], fy, f"Total assets, equity capital and reserves: {XLSX}. Year-end "
               f"figures. Change split by log shares of each factor. "
               + ("The product matches the file's ROE in every year shown (within 0.6 pp)." if ok else
                  "Note: the product differs from the file's ROE in some years: "
                  + ", ".join(f"{y} {v:.1f}% vs {f:.1f}%" for y, v, f in chk if f is not None and pd.notna(f)
                              and abs(v - f) >= 0.6))), "ROE breakdown (DuPont)")


def render(fys, default_range, show_ttm):
    r_all = load("ratios_file")
    lo, hi = default_range  # set by the tab's "Select period" bar (mirrors the sidebar)
    keep = fys[fys.index(lo): fys.index(hi) + 1] + ([TTM] if show_ttm else [])
    r = r_all[r_all.period.isin(keep)].reset_index(drop=True)
    specs = {s[0]: s for s in ratio_specs()}
    checks = cross_check()
    S = lambda *k: [specs[x] for x in k]

    c1, c2 = st.columns(2)
    with c1:
        _pct_section(":material/percent: Profitability", "Margins (%)", S("opm_pct", "npm_pct", "gpm_pct"), r,
                     f"Gross-margin cost lines: {XLSX}. GPM is n/a for {TTM}")
    with c2:
        _pct_section(":material/trending_up: Returns", "Returns on capital (%)", S("roe_pct", "roce_pct", "roa_pct"), r,
                     f"Numerators as cited; equity, borrowings and total assets: {XLSX}. Year-end (not average) capital")

    _dupont(keep, r_all)

    st.subheader(":material/balance: Leverage and liquidity")
    c1, c2, c3 = st.columns(3)
    for box, key in zip((c1, c2), ("debt_to_equity", "interest_coverage")):
        with box:
            col, label, unit, *_ = specs[key]
            show(lines(r, "period", [col], [label], [SERIES[0]], title=f"{label} (x)", ysuffix="x",
                       yaxis_title="times", fmt=FMT[unit]))
            source(XLSX)
    with c3:
        show(lines(r, "period", ["current_ratio", "quick_ratio"], ["Current", "Quick"],
                   SERIES[:2], title="Current and quick ratio (x)", ysuffix="x", yaxis_title="times", fmt=mult))
        source(XLSX)

    st.subheader(":material/autorenew: Efficiency and cash conversion")
    c1, c2 = st.columns([3, 2])
    fy_only = [p for p in r.period if p != TTM]
    with c1:
        k = ["receivable_days", "inventory_days", "payable_days", "cash_conversion_cycle"]
        show(lines(r, "period", k, [specs[x][1] for x in k], SERIES[:4], title="Working-capital days",
                   ysuffix="", yaxis_title="days", fmt=days))
        source(src("balance_sheet", ["trade_payables"], list(r.period),
                   f"Trade payables (incl. acceptances) as cited; receivables, inventories and material cost: {XLSX}"))
    with c2:
        show(lines(r, "period", ["asset_turnover"], ["Asset turnover"], [SERIES[0]], title="Asset turnover (x)",
                   ysuffix="x", yaxis_title="times", fmt=mult))
        source(src("annual", ["revenue"], fy_only, f"Total assets: {XLSX}"))
    nwc = load("kpis")
    nwc = nwc[nwc.kpi == "Net working capital days (company, closing)"]
    st.info(
        "Payable days include acceptances (bank-paid supplier bills) in every period, as in the annual reports. "
        "FY26 payables rose because acceptances grew from ₹1,306 cr to ₹4,266 cr. "
        "The company's own closing net working-capital days: "
        + ", ".join(f"{r_.period} {r_.value:g}" for r_ in nwc.itertuples())
        + ". The company uses its own day-count basis, so its values differ from the material-cost days above."
    )
    source("Acceptances: Polycab Annual Report FY26, p.365. Company working-capital days: Polycab investor "
           "presentation Q2 FY27, slide 17.", "Working-capital note")
    show(lines(r, "period", ["cfo_to_pat", "cfo_to_ebitda"], ["CFO / PAT", "CFO / EBITDA"], SERIES[:2],
               title="Cash conversion (%)", fmt=pct))
    source(src("cash_flow", ["cash_from_operating"], list(r.period),
               f"{TTM} CFO = H1 FY27 + FY26 − H1 FY26. PAT and EBITDA as on the Financials tab"))

    st.subheader(":material/trending_up: Growth")
    k = ["revenue_growth_pct", "operating_profit_growth_pct", "pat_growth_pct", "eps_growth_pct"]
    show(bars(r, "period", k, [specs[x][1] for x in k], SERIES[:4], title="Year-on-year growth (%)",
              yaxis_title="%", fmt=pct, ysuffix="%"))
    source(src("annual", ["revenue", "operating_profit", "pat"], fy_only,
               f"EPS: {XLSX}. FY18 has no prior year. {TTM} growth is against TTM Sep-25 (sum of Dec'24–Sep'25 "
               "quarters), not FY25"))

    st.subheader(":material/percent: Dividend payout")
    a = load("annual").set_index("period")
    k = load("kpis")
    co = k[k.kpi == "Dividend payout ratio"].set_index("period").value
    fy = [x for x in keep if x != TTM and x >= "FY22" and pd.notna(a.dividends_paid.get(x))]
    if fy:
        dp = pd.DataFrame({"period": fy,
                           "derived": [abs(a.dividends_paid[x]) / a.pat[x] * 100 for x in fy],
                           "company": [co.get(x) for x in fy]})
        show(lines(dp, "period", ["derived", "company"], ["Cash dividends paid / PAT",
                                                          "Payout ratio reported by the company"],
                   SERIES[:2], title="Dividend payout (%)", fmt=pct))
        source(src("annual", ["dividends_paid", "pat"], fy,
                   "Cash paid in a year is mostly the previous year's dividend. Company payout ratio: Polycab investor "
                   "presentation Q4 FY26, slide 17"))
        st.caption("Shown from FY22. FY19–FY20 cash dividends are not stated (n/a); FY21 was nil.")
        _register_note = ("FY21 cash dividends were nil (Polycab Annual Report FY22, p.86). FY20 dividends were declared "
                          "(final FY19 30%, interim FY20 70%; Annual Report FY22, p.60) but the cash amount is not stated.")
        source(_register_note, "Dividend history note")
    else:
        st.info("Dividend payout is shown from FY22 (FY19–FY20 cash dividends are not available).")

    with st.expander("ℹ️ Formulas and cross-checks"):
        rows = []
        for col, label, unit, formula, _ in ratio_specs():
            n, diff, ok = checks[col]
            status = "n/a" if diff is None else (f"✓ reproduces ({n} periods, max diff {diff:.3f})" if ok
                                                 else f"{WARN} differs (max diff {diff:.2f})")
            rows.append({"Ratio": label, "Formula": formula, "Unit": unit, "Recomputed vs file": status})
        table(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Ratios are recomputed from the statements, using the verified figures where available. CFO/PAT "
                   "and CFO/EBITDA are percent; debt/equity, interest cover, current/quick ratio and asset turnover "
                   "are multiples (x).")

    with st.expander("Ratio table"):
        t = r.set_index("period")
        out = pd.DataFrame({label: [FMT[unit](v) for v in t[col]] for col, label, unit, *_ in ratio_specs()},
                           index=t.index).T
        table(out, width="stretch")
