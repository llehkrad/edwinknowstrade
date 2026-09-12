"""
Generates a self-contained HTML dashboard (equity curve, drawdown, PnL
breakdowns, filterable/sortable trades table) from a backtest run's output
CSVs. Works entirely offline -- no server, opens directly in a browser.

Usage:
    python backtest/build_dashboard.py
    python backtest/build_dashboard.py --results-dir backtest_results --real-data
"""
import argparse
import json
import os

import pandas as pd

DEFAULT_RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "backtest_results")

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1" integrity="sha384-jb8JQMbMoBUzgWatfe6COACi2ljcDdZQ2OxczGA3bGNeWe+6DChMTBJemed7ZnvJ" crossorigin="anonymous"></script>
<style>
:root {
    --bg-primary: #f8f9fa;
    --bg-card: #ffffff;
    --bg-header: #1a1a2e;
    --text-primary: #212529;
    --text-secondary: #6c757d;
    --text-on-dark: #ffffff;
    --positive: #28a745;
    --negative: #dc3545;
    --gap: 16px;
    --radius: 8px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.5;
}
.dashboard-container { max-width: 1400px; margin: 0 auto; padding: var(--gap); }
.banner {
    background: #fff3cd; color: #664d03; border: 1px solid #ffe69c;
    border-radius: var(--radius); padding: 12px 18px; margin-bottom: var(--gap);
    font-size: 14px; font-weight: 500;
}
.dashboard-header {
    background: var(--bg-header); color: var(--text-on-dark);
    padding: 20px 24px; border-radius: var(--radius); margin-bottom: var(--gap);
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;
}
.dashboard-header h1 { font-size: 20px; font-weight: 600; }
.dashboard-header .subtitle { font-size: 13px; color: rgba(255,255,255,0.7); margin-top: 4px; }
.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: var(--gap); margin-bottom: var(--gap); }
.kpi-row.primary { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.kpi-row.secondary { grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); margin-bottom: calc(var(--gap) * 1.5); }
.kpi-card { background: var(--bg-card); border-radius: var(--radius); padding: 18px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.kpi-row.primary .kpi-card { padding: 22px 24px; border-left: 4px solid var(--color-1, #4C72B0); }
.kpi-label { font-size: 12px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.kpi-value { font-size: 24px; font-weight: 700; }
.kpi-row.primary .kpi-value { font-size: 30px; }
.kpi-row.secondary .kpi-value { font-size: 19px; }
.kpi-value.positive { color: var(--positive); }
.kpi-value.negative { color: var(--negative); }
.kpi-subvalue { font-size: 14px; font-weight: 600; margin-top: 2px; }
.kpi-subvalue.positive { color: var(--positive); }
.kpi-subvalue.negative { color: var(--negative); }
.chart-row { display: grid; grid-template-columns: 2fr 1fr; gap: var(--gap); margin-bottom: var(--gap); }
.chart-row.secondary { grid-template-columns: 1fr 1fr; }
.chart-container { background: var(--bg-card); border-radius: var(--radius); padding: 20px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.chart-container h3 { font-size: 14px; font-weight: 600; margin-bottom: 16px; }
.chart-container canvas { max-height: 280px; }
.table-section { background: var(--bg-card); border-radius: var(--radius); padding: 20px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); overflow-x: auto; }
.table-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
.table-header h3 { font-size: 14px; font-weight: 600; }
.filters { display: flex; gap: 12px; flex-wrap: wrap; }
.filter-group { display: flex; align-items: center; gap: 6px; }
.filter-group label { font-size: 12px; color: var(--text-secondary); }
.filter-group select { padding: 6px 10px; border: 1px solid #dee2e6; border-radius: 4px; font-size: 13px; background: white; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table thead th {
    text-align: left; padding: 10px 12px; border-bottom: 2px solid #dee2e6;
    color: var(--text-secondary); font-weight: 600; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.5px; white-space: nowrap; cursor: pointer; user-select: none;
}
.data-table thead th:hover { color: var(--text-primary); background: #f8f9fa; }
.data-table tbody td { padding: 8px 12px; border-bottom: 1px solid #f0f0f0; white-space: nowrap; }
.data-table tbody tr:hover { background: #f8f9fa; }
.pnl-positive { color: var(--positive); font-weight: 600; }
.pnl-negative { color: var(--negative); font-weight: 600; }
.table-footer { font-size: 12px; color: var(--text-secondary); margin-top: 10px; }
.calendar-section { background: var(--bg-card); border-radius: var(--radius); padding: 20px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: var(--gap); }
.calendar-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 4px; }
.calendar-header h3 { font-size: 14px; font-weight: 600; }
.cal-nav { display: flex; align-items: center; gap: 10px; }
.cal-nav-btn {
    width: 30px; height: 30px; border-radius: 6px; border: 1px solid #dee2e6; background: white;
    color: var(--text-primary); font-size: 14px; cursor: pointer; display: flex; align-items: center; justify-content: center;
}
.cal-nav-btn:hover:not(:disabled) { background: #f8f9fa; }
.cal-nav-btn:disabled { opacity: 0.35; cursor: default; }
.cal-month-label { font-size: 14px; font-weight: 600; min-width: 130px; text-align: center; }
.calendar-section .cal-legend { font-size: 12px; color: var(--text-secondary); margin-bottom: 16px; }
.cal-month { margin-bottom: 22px; }
.cal-month h4 { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: var(--text-primary); }
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 5px; }
.cal-dow { text-align: center; font-size: 11px; color: var(--text-secondary); font-weight: 600; padding: 2px 0 6px; }
.cal-cell { min-height: 64px; border-radius: 6px; padding: 6px 8px; font-size: 11px; background: #f8f9fa; border: 1px solid #eee; }
.cal-cell.empty { background: transparent; border: none; }
.cal-day-num { font-weight: 600; color: var(--text-secondary); margin-bottom: 3px; }
.cal-cell.cal-win { background: rgba(40,167,69,0.14); border-color: rgba(40,167,69,0.35); }
.cal-cell.cal-loss { background: rgba(220,53,69,0.14); border-color: rgba(220,53,69,0.35); }
.cal-cell.cal-flat { background: rgba(108,117,125,0.08); }
.cal-pnl { font-weight: 700; font-size: 12px; }
.cal-pnl.positive { color: var(--positive); }
.cal-pnl.negative { color: var(--negative); }
.cal-counts { color: var(--text-secondary); font-size: 10px; margin-top: 3px; }
@media (max-width: 900px) { .chart-row, .chart-row.secondary { grid-template-columns: 1fr; } }
@media (max-width: 700px) { .cal-cell { min-height: 46px; font-size: 10px; } .cal-counts { display: none; } }
</style>
</head>
<body>
<div class="dashboard-container">
    __BANNER__
    <header class="dashboard-header">
        <div>
            <h1>__TITLE__</h1>
            <div class="subtitle">__SUBTITLE__</div>
        </div>
    </header>

    <section class="kpi-row primary">
        <div class="kpi-card">
            <div class="kpi-label">Current Equity</div>
            <div class="kpi-value" id="kpi-current"></div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Total Return</div>
            <div class="kpi-value" id="kpi-return-usd"></div>
            <div class="kpi-subvalue" id="kpi-return-pct"></div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Commission Paid</div>
            <div class="kpi-value" id="kpi-commission"></div>
        </div>
    </section>

    <section class="kpi-row secondary">
        <div class="kpi-card"><div class="kpi-label">Max Drawdown</div><div class="kpi-value negative" id="kpi-dd"></div></div>
        <div class="kpi-card"><div class="kpi-label">Win Rate</div><div class="kpi-value" id="kpi-winrate"></div></div>
        <div class="kpi-card"><div class="kpi-label">Round Trips</div><div class="kpi-value" id="kpi-trips"></div></div>
        <div class="kpi-card"><div class="kpi-label">Open Positions</div><div class="kpi-value" id="kpi-open"></div></div>
    </section>

    <section class="calendar-section">
        <div class="calendar-header">
            <h3>Daily Trading Calendar</h3>
            <div class="cal-nav">
                <button id="cal-prev" class="cal-nav-btn" aria-label="Previous month">&#8592;</button>
                <span id="cal-month-label" class="cal-month-label"></span>
                <button id="cal-next" class="cal-nav-btn" aria-label="Next month">&#8594;</button>
            </div>
        </div>
        <div class="cal-legend">Green = day closed net positive · Red = day closed net negative · Returns counted on the day a trade closes, not when it opened.</div>
        <div id="calendar-container"></div>
    </section>

    <section class="chart-row">
        <div class="chart-container"><h3>Equity Curve</h3><canvas id="equity-chart"></canvas></div>
        <div class="chart-container"><h3>Drawdown from Peak</h3><canvas id="drawdown-chart"></canvas></div>
    </section>

    <section class="chart-row secondary">
        <div class="chart-container"><h3>Realized PnL by Symbol</h3><canvas id="pnl-symbol-chart"></canvas></div>
        <div class="chart-container"><h3>Realized PnL by Strategy / Exit Type</h3><canvas id="pnl-strategy-chart"></canvas></div>
    </section>

    <section class="table-section">
        <div class="table-header">
            <h3>All Fills</h3>
            <div class="filters">
                <div class="filter-group"><label for="filter-symbol">Symbol</label><select id="filter-symbol"><option value="all">All</option></select></div>
                <div class="filter-group"><label for="filter-strategy">Strategy</label><select id="filter-strategy"><option value="all">All</option></select></div>
                <div class="filter-group"><label for="filter-action">Action</label><select id="filter-action"><option value="all">All</option></select></div>
            </div>
        </div>
        <div id="table-container"></div>
        <div class="table-footer" id="table-footer"></div>
    </section>
</div>

<script>
const DATA = __DATA_JSON__;

const COLORS = ['#4C72B0', '#DD8452', '#55A868', '#C44E52', '#8172B3', '#937860'];

function fmtCurrency(v) {
    const sign = v < 0 ? '-' : '';
    return sign + '$' + Math.abs(v).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function fmtPct(v) { return (v * 100).toFixed(2) + '%'; }
function isBlank(v) { return v === null || v === undefined || (typeof v === 'number' && isNaN(v)); }

function renderKPIs() {
    const k = DATA.kpis;
    const sign = k.total_return_usd >= 0 ? 'positive' : 'negative';

    document.getElementById('kpi-current').textContent = fmtCurrency(k.ending_equity);

    const usdEl = document.getElementById('kpi-return-usd');
    usdEl.textContent = fmtCurrency(k.total_return_usd);
    usdEl.className = 'kpi-value ' + sign;

    const pctEl = document.getElementById('kpi-return-pct');
    pctEl.textContent = fmtPct(k.total_return_pct);
    pctEl.className = 'kpi-subvalue ' + sign;

    document.getElementById('kpi-commission').textContent = fmtCurrency(k.total_commission);

    document.getElementById('kpi-dd').textContent = fmtPct(k.max_drawdown_pct);
    document.getElementById('kpi-winrate').textContent = fmtPct(k.win_rate);
    document.getElementById('kpi-trips').textContent = k.num_round_trips.toLocaleString();
    document.getElementById('kpi-open').textContent = k.num_open_positions.toLocaleString();
}

function renderCalendarMonth(year, month, daily) {
    const monthNames = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    const firstDay = new Date(year, month, 1);
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const startWeekday = firstDay.getDay();

    let html = `<div class="cal-month"><h4>${monthNames[month]} ${year}</h4><div class="cal-grid">`;
    ['S','M','T','W','T','F','S'].forEach(d => { html += `<div class="cal-dow">${d}</div>`; });

    for (let i = 0; i < startWeekday; i++) html += '<div class="cal-cell empty"></div>';

    for (let day = 1; day <= daysInMonth; day++) {
        const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const info = daily[dateStr];
        let cls = 'cal-cell';
        let body = `<div class="cal-day-num">${day}</div>`;
        if (info) {
            cls += info.pnl > 0 ? ' cal-win' : (info.pnl < 0 ? ' cal-loss' : ' cal-flat');
            const pnlCls = info.pnl >= 0 ? 'positive' : 'negative';
            body += `<div class="cal-pnl ${pnlCls}">${fmtCurrency(info.pnl)}</div>`;
            body += `<div class="cal-counts">${info.opened} opened / ${info.closed} closed</div>`;
        }
        html += `<div class="${cls}">${body}</div>`;
    }

    const totalCells = startWeekday + daysInMonth;
    const remainder = (7 - (totalCells % 7)) % 7;
    for (let i = 0; i < remainder; i++) html += '<div class="cal-cell empty"></div>';

    html += '</div></div>';
    return html;
}

const calState = { year: null, month: null, minIdx: null, maxIdx: null };

function monthIndex(y, m) { return y * 12 + m; }

function initCalendarState() {
    const dateKeys = Object.keys(DATA.daily);
    if (dateKeys.length === 0) return false;

    const dates = dateKeys.map(d => new Date(d + 'T00:00:00'));
    const minDate = new Date(Math.min(...dates));
    const maxDate = new Date(Math.max(...dates));

    calState.minIdx = monthIndex(minDate.getFullYear(), minDate.getMonth());
    calState.maxIdx = monthIndex(maxDate.getFullYear(), maxDate.getMonth());
    calState.year = maxDate.getFullYear();  // default to the most recent month
    calState.month = maxDate.getMonth();
    return true;
}

function renderCalendars() {
    const container = document.getElementById('calendar-container');
    const monthNames = ['January','February','March','April','May','June','July','August','September','October','November','December'];

    if (calState.year === null) { container.textContent = 'No trades yet.'; return; }

    container.innerHTML = renderCalendarMonth(calState.year, calState.month, DATA.daily);
    document.getElementById('cal-month-label').textContent = `${monthNames[calState.month]} ${calState.year}`;

    const curIdx = monthIndex(calState.year, calState.month);
    document.getElementById('cal-prev').disabled = curIdx <= calState.minIdx;
    document.getElementById('cal-next').disabled = curIdx >= calState.maxIdx;
}

function shiftCalendarMonth(delta) {
    let month = calState.month + delta;
    let year = calState.year;
    if (month < 0) { month = 11; year -= 1; }
    if (month > 11) { month = 0; year += 1; }

    const idx = monthIndex(year, month);
    if (idx < calState.minIdx || idx > calState.maxIdx) return;

    calState.year = year;
    calState.month = month;
    renderCalendars();
}

function renderEquityChart() {
    const ctx = document.getElementById('equity-chart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: { labels: DATA.equity_series.labels, datasets: [{
            label: 'Equity ($)', data: DATA.equity_series.equity,
            borderColor: COLORS[0], backgroundColor: COLORS[0] + '20',
            borderWidth: 2, fill: true, tension: 0.1, pointRadius: 0,
        }]},
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => 'Equity: ' + fmtCurrency(c.parsed.y) } } },
            scales: { x: { ticks: { maxTicksLimit: 10 }, grid: { display: false } }, y: { ticks: { callback: (v) => fmtCurrency(v) } } }
        }
    });
}

function renderDrawdownChart() {
    const ctx = document.getElementById('drawdown-chart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: { labels: DATA.equity_series.labels, datasets: [{
            label: 'Drawdown (%)', data: DATA.equity_series.drawdown_pct.map(v => -v),
            borderColor: COLORS[3], backgroundColor: COLORS[3] + '30',
            borderWidth: 1.5, fill: true, tension: 0.1, pointRadius: 0,
        }]},
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => 'Drawdown: ' + (-c.parsed.y).toFixed(2) + '%' } } },
            scales: { x: { ticks: { maxTicksLimit: 10 }, grid: { display: false } }, y: { ticks: { callback: (v) => v + '%' } } }
        }
    });
}

function renderBreakdownChart(canvasId, dict) {
    const labels = Object.keys(dict);
    const values = Object.values(dict);
    const ctx = document.getElementById(canvasId).getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: { labels: labels, datasets: [{
            data: values,
            backgroundColor: values.map(v => v >= 0 ? 'rgba(40,167,69,0.75)' : 'rgba(220,53,69,0.75)'),
            borderRadius: 4,
        }]},
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => fmtCurrency(c.parsed.y) } } },
            scales: { y: { ticks: { callback: (v) => fmtCurrency(v) } } }
        }
    });
}

function populateFilter(selectId, values) {
    const select = document.getElementById(selectId);
    [...new Set(values)].filter(v => !isBlank(v)).sort().forEach(v => {
        const opt = document.createElement('option');
        opt.value = v; opt.textContent = v;
        select.appendChild(opt);
    });
}

function getFilterValue(id) {
    const v = document.getElementById(id).value;
    return v === 'all' ? null : v;
}

let sortState = { field: 'timestamp', dir: 'desc' };

function applyFilters() {
    const symbol = getFilterValue('filter-symbol');
    const strategy = getFilterValue('filter-strategy');
    const action = getFilterValue('filter-action');

    let rows = DATA.fills.filter(r => {
        if (symbol && r.symbol !== symbol) return false;
        if (strategy && r.strategy !== strategy) return false;
        if (action && r.action !== action) return false;
        return true;
    });

    rows = rows.slice().sort((a, b) => {
        let av = a[sortState.field], bv = b[sortState.field];
        if (isBlank(av)) av = sortState.dir === 'asc' ? Infinity : -Infinity;
        if (isBlank(bv)) bv = sortState.dir === 'asc' ? Infinity : -Infinity;
        const cmp = av < bv ? -1 : av > bv ? 1 : 0;
        return sortState.dir === 'asc' ? cmp : -cmp;
    });

    renderTable(rows);
}

function renderTable(rows) {
    const columns = [
        { field: 'timestamp', label: 'Time' }, { field: 'symbol', label: 'Symbol' },
        { field: 'action', label: 'Action' }, { field: 'quantity', label: 'Qty' },
        { field: 'price', label: 'Price' }, { field: 'commission', label: 'Commission' },
        { field: 'strategy', label: 'Strategy' }, { field: 'regime', label: 'Regime' },
        { field: 'realized_pnl', label: 'Realized PnL' },
    ];

    const pageSize = 100;
    const pageRows = rows.slice(0, pageSize);

    let html = '<table class="data-table"><thead><tr>';
    columns.forEach(col => {
        const arrow = sortState.field === col.field ? (sortState.dir === 'asc' ? ' ▲' : ' ▼') : '';
        html += `<th data-field="${col.field}">${col.label}${arrow}</th>`;
    });
    html += '</tr></thead><tbody>';

    pageRows.forEach(row => {
        html += '<tr>';
        columns.forEach(col => {
            let v = row[col.field];
            if (isBlank(v)) { html += '<td>—</td>'; return; }
            if (col.field === 'price') v = Number(v).toFixed(3);
            if (col.field === 'commission') v = fmtCurrency(v);
            if (col.field === 'realized_pnl') {
                const cls = v >= 0 ? 'pnl-positive' : 'pnl-negative';
                html += `<td class="${cls}">${fmtCurrency(v)}</td>`;
                return;
            }
            html += `<td>${v}</td>`;
        });
        html += '</tr>';
    });
    html += '</tbody></table>';

    document.getElementById('table-container').innerHTML = html;
    document.getElementById('table-footer').textContent =
        `Showing ${pageRows.length.toLocaleString()} of ${rows.length.toLocaleString()} fills` +
        (rows.length > pageSize ? ' (sort or filter to narrow down)' : '');

    document.querySelectorAll('.data-table thead th').forEach(th => {
        th.addEventListener('click', () => {
            const field = th.dataset.field;
            if (sortState.field === field) { sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc'; }
            else { sortState.field = field; sortState.dir = 'desc'; }
            applyFilters();
        });
    });
}

function init() {
    renderKPIs();
    initCalendarState();
    renderCalendars();
    document.getElementById('cal-prev').addEventListener('click', () => shiftCalendarMonth(-1));
    document.getElementById('cal-next').addEventListener('click', () => shiftCalendarMonth(1));
    renderEquityChart();
    renderDrawdownChart();
    renderBreakdownChart('pnl-symbol-chart', DATA.pnl_by_symbol);
    renderBreakdownChart('pnl-strategy-chart', DATA.pnl_by_strategy);

    populateFilter('filter-symbol', DATA.fills.map(f => f.symbol));
    populateFilter('filter-strategy', DATA.fills.map(f => f.strategy));
    populateFilter('filter-action', DATA.fills.map(f => f.action));
    ['filter-symbol', 'filter-strategy', 'filter-action'].forEach(id => {
        document.getElementById(id).addEventListener('change', applyFilters);
    });

    applyFilters();
}

init();
</script>
</body>
</html>
"""


def build_dashboard_data(results_dir: str) -> dict:
    equity = pd.read_csv(os.path.join(results_dir, "equity_curve.csv"), parse_dates=["timestamp"])
    fills = pd.read_csv(os.path.join(results_dir, "fills.csv"), parse_dates=["timestamp"])
    fills["strategy"] = fills["strategy"].str.replace("bot.strategies.", "", regex=False)

    starting_equity = float(equity["equity"].iloc[0])
    ending_equity = float(equity["equity"].iloc[-1])
    peak = equity["equity"].cummax()
    drawdown = (peak - equity["equity"]) / peak

    round_trips = fills[fills["realized_pnl"].notna()].copy()
    wins = round_trips[round_trips["realized_pnl"] > 0]

    # A symbol is "open" if its most recent fill (in time order) is an entry
    # (buy/sell) rather than an exit -- engine.py only ever holds one position
    # per symbol at a time, so last-fill-wins is sufficient here.
    num_open_positions = 0
    for _, group in fills.sort_values("timestamp").groupby("symbol"):
        if group.iloc[-1]["action"] in ("buy", "sell"):
            num_open_positions += 1

    kpis = {
        "starting_equity": starting_equity,
        "ending_equity": ending_equity,
        "total_return_usd": ending_equity - starting_equity,
        "total_return_pct": ending_equity / starting_equity - 1,
        "max_drawdown_pct": float(drawdown.max()),
        "win_rate": len(wins) / len(round_trips) if len(round_trips) else 0.0,
        "num_round_trips": int(len(round_trips)),
        "num_open_positions": num_open_positions,
        "total_commission": float(fills["commission"].sum()),
    }

    # Daily calendar: trades opened/closed and PnL, attributed to the day a
    # trade CLOSES (not when it opened), per how the operator wants this read.
    fills_by_day = fills.copy()
    fills_by_day["date"] = fills_by_day["timestamp"].dt.strftime("%Y-%m-%d")
    opened_counts = fills_by_day[fills_by_day["action"].isin(["buy", "sell"])].groupby("date").size()
    closed_counts = fills_by_day[fills_by_day["action"] == "exit"].groupby("date").size()
    daily_pnl = fills_by_day[fills_by_day["action"] == "exit"].groupby("date")["realized_pnl"].sum()

    all_days = sorted(set(opened_counts.index) | set(closed_counts.index))
    daily = {
        day: {
            "opened": int(opened_counts.get(day, 0)),
            "closed": int(closed_counts.get(day, 0)),
            "pnl": round(float(daily_pnl.get(day, 0.0)), 2),
        }
        for day in all_days
    }

    step = max(1, len(equity) // 750)
    sampled = equity.iloc[::step]
    sampled_dd = drawdown.iloc[::step]
    equity_series = {
        "labels": sampled["timestamp"].dt.strftime("%Y-%m-%d %H:%M").tolist(),
        "equity": sampled["equity"].round(2).tolist(),
        "drawdown_pct": (sampled_dd * 100).round(3).tolist(),
    }

    fills_out = fills.copy()
    fills_out["timestamp"] = fills_out["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
    for col in ("price", "commission", "realized_pnl"):
        fills_out[col] = fills_out[col].round(3)
    fills_out["quantity"] = fills_out["quantity"].round(4)

    return {
        "kpis": kpis,
        "equity_series": equity_series,
        "daily": daily,
        "pnl_by_symbol": {k: round(v, 2) for k, v in round_trips.groupby("symbol")["realized_pnl"].sum().items()},
        "pnl_by_strategy": {k: round(v, 2) for k, v in round_trips.groupby("strategy")["realized_pnl"].sum().items()},
        "fills": fills_out.to_dict(orient="records"),
    }


def build_dashboard(results_dir: str, output_path: str, title: str, subtitle: str, synthetic_data: bool) -> None:
    data = build_dashboard_data(results_dir)

    banner = ""
    if synthetic_data:
        banner = (
            '<div class="banner">⚠️ SYNTHETIC TEST DATA — not a real backtest. '
            "Results say nothing about whether the strategy actually works.</div>"
        )

    html = (
        TEMPLATE.replace("__TITLE__", title)
        .replace("__SUBTITLE__", subtitle)
        .replace("__BANNER__", banner)
        .replace("__DATA_JSON__", json.dumps(data))
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote dashboard to {os.path.abspath(output_path)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--output", default=None, help="Defaults to <results-dir>/dashboard.html")
    parser.add_argument("--title", default="Phase 1 Backtest Dashboard")
    parser.add_argument("--subtitle", default="Regime-filtered mean reversion / trend following — SPY, QQQ, IWM")
    parser.add_argument("--real-data", action="store_true", help="Hides the synthetic-data warning banner")
    args = parser.parse_args()

    output_path = args.output or os.path.join(args.results_dir, "dashboard.html")
    build_dashboard(args.results_dir, output_path, args.title, args.subtitle, synthetic_data=not args.real_data)


if __name__ == "__main__":
    main()
