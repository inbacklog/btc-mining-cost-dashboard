"use strict";

const byId = (id) => document.getElementById(id);
const dollars = new Intl.NumberFormat("en-US", {
  style: "currency", currency: "USD", maximumFractionDigits: 0
});
const colors = ["#ffbe66", "#60d5ca", "#c19bff", "#9bc77c", "#ff96a9", "#82bffa"];
const defaultModel = {rate: .05, pue: 1.10, share: 60, fees: true, efficiency: null};
let model = defaultModel;
let historyRows = [];
let days = 365;

function applyModel(row) {
  const efficiencyFactor = model.efficiency === null ? 1 : model.efficiency / row.efficiency_j_per_th;
  const feeFactor = 1 + row.fees_btc / row.btc_issued_per_day;
  const cost = row.total_production_cost_per_btc * (model.rate / .05) * (model.pue / 1.10)
    * (60 / model.share) * efficiencyFactor * (model.fees ? 1 : feeFactor);
  const ratio = row.close / cost;
  const costScore = Math.min(1, Math.max(0, (1.5 - ratio) / .8));
  return {...row, cost, ratio, electrical: cost * model.share / 100, miner: row.close * feeFactor,
    score: row.scoreLow + costScore * (row.scoreHigh - row.scoreLow), hash: row.hashrate_th_s / 1e6};
}

// Each chart has one vertical unit, shared by all its series.
const views = {
  cost:  {axis: "USD per BTC", format: "$,.0f", log: true, lines: [
    ["close", "Market price"], ["cost", "Production cost"], ["electrical", "Electricity cost"],
    ["miner", "Miner revenue / BTC", "legendonly"]]},
  trend: {axis: "USD per BTC", format: "$,.0f", log: true, lines: [
    ["close", "Market price"], ["MA20", "20-day MA"], ["MA50", "50-day MA"], ["MA200W", "200-week MA"],
    ["MA200", "200-day MA", "legendonly"], ["BB_upper", "Upper band", "legendonly"],
    ["BB_lower", "Lower band", "legendonly"]]},
  ratio: {axis: "Price / cost", format: ".2f", reference: [1], lines: [["ratio", "Price / cost"]]},
  score: {axis: "Score (0-100)", format: ".1f", range: [0, 100], reference: [55, 75],
    lines: [["score", "Opportunity score"]]},
  rsi:   {axis: "RSI (0-100)", format: ".1f", range: [0, 100], reference: [30, 70], lines: [["RSI14", "14-day RSI"]]},
  volume:{axis: "USD per day", format: "$,.0f", bar: true, lines: [["volume", "Reported spot volume"]]},
  hash:  {axis: "EH/s", format: ",.1f", lines: [["hash", "Network hash rate"]]}
};

function render() {
  const last = historyRows[historyRows.length - 1];
  const cutoff = days ? new Date(Date.parse(last.time) - (days - 1) * 86400000).toISOString().slice(0, 10) : "";
  const rows = historyRows.filter((row) => row.time >= cutoff).map(applyModel);
  const latest = rows[rows.length - 1];
  byId("market").textContent = dollars.format(latest.close);
  byId("production").textContent = dollars.format(latest.cost);
  byId("multiple").textContent = latest.ratio.toFixed(2) + "x";
  byId("opportunity").textContent = latest.score.toFixed(1) + " / 100";
  byId("period-label").textContent = rows[0].time + " to " + last.time + " (UTC)";
  const view = views[byId("view").value];
  byId("log").disabled = !view.log;
  byId("log").parentElement.hidden = !view.log;
  document.querySelectorAll("[data-days]").forEach((button) =>
    button.setAttribute("aria-pressed", String(Number(button.dataset.days) === days)));
  const x = rows.map((r) => r.time);
  const traces = view.lines.map(([field, name, visible = true], i) => ({
    x, y: rows.map((r) => r[field]), name, visible,
    type: view.bar ? "bar" : "scatter", ...(view.bar ? {} : {mode: "lines"}),
    marker: {color: colors[i % colors.length]},
    line: {color: colors[i % colors.length], width: i === 0 ? 2.3 : 1.7},
    hovertemplate: "%{y:" + view.format + "}<extra>" + name + "</extra>"
  }));
  const axis = {gridcolor: "#324043", zeroline: false, automargin: true};
  return Plotly.react("chart", traces, {
    paper_bgcolor: "#182225", plot_bgcolor: "#182225", font: {color: "#dce7e6", family: "Segoe UI, sans-serif"},
    margin: {l: 46, r: 14, t: 20, b: 38}, hovermode: "x unified", dragmode: "zoom",
    legend: {orientation: "h", yanchor: "top", y: -.17, font: {size: 11}}, showlegend: traces.length > 1,
    xaxis: {...axis, type: "date", nticks: 6, range: [x[0], last.time]},
    yaxis: {...axis, title: {text: view.axis}, type: view.log && byId("log").checked ? "log" : "linear",
      ...(view.range ? {range: view.range} : {autorange: true})},
    shapes: (view.reference || []).map((y) => ({
      type: "line", xref: "paper", x0: 0, x1: 1, y0: y, y1: y, line: {dash: "dot", width: 1, color: "#b4c5c1"}
    }))
  }, {responsive: true, displaylogo: false, displayModeBar: false, scrollZoom: false});
}

function syncEfficiency() {
  const constant = byId("mode").value === "constant";
  byId("eff-label").hidden = !constant;
  byId("eff").disabled = !constant;
}

async function start() {
  const response = await fetch("generated/daily.json");
  if (!response.ok) throw Error("Snapshot unavailable");
  const {columns, data} = await response.json();
  historyRows = data.map((values) => Object.fromEntries(columns.map((key, index) => [key, values[index]])));
  const date = historyRows[historyRows.length - 1].time;
  const delayed = Date.now() - Date.parse(date) > 3 * 86400000;
  byId("asof").textContent = "Daily USD observations through " + date + " UTC" + (delayed ? " (refresh delayed)" : "");
  byId("workspace").hidden = false;
  await render();
  byId("view").addEventListener("change", render);
  byId("log").addEventListener("change", render);
  document.querySelectorAll("[data-days]").forEach((button) => button.addEventListener("click", () => {
    days = Number(button.dataset.days);
    render();
  }));
  byId("mode").addEventListener("change", syncEfficiency);
  byId("model").addEventListener("submit", (event) => {
    event.preventDefault();
    model = {rate: byId("rate").valueAsNumber, pue: byId("pue").valueAsNumber,
      share: byId("share").valueAsNumber, fees: byId("fees").checked,
      efficiency: byId("eff").disabled ? null : byId("eff").valueAsNumber};
    render();
  });
  byId("model").addEventListener("reset", () => {
    model = defaultModel;
    requestAnimationFrame(() => { syncEfficiency(); render(); });
  });
}

start().catch(() => {
  byId("workspace").hidden = true;
  byId("asof").textContent = "The dashboard could not load. Reload this page or use the local version under Downloads.";
});
