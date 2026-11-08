import { csvRow } from "./csv.js";

const NS = "http://www.w3.org/2000/svg";
const accent = "#78182b";
const ink = "#24303d";
const soft = "#e6d9d7";
const format = new Intl.NumberFormat("en-PH");
const monthFormat = new Intl.DateTimeFormat("en-PH", { month: "short", year: "numeric", timeZone: "UTC" });

export function html(tag, value, className) {
  const node = document.createElement(tag);
  if (value !== undefined) node.textContent = value;
  if (className) node.className = className;
  return node;
}

function svg(tag, attrs = {}, value) {
  const node = document.createElementNS(NS, tag);
  for (const [key, attr] of Object.entries(attrs)) node.setAttribute(key, attr);
  if (value !== undefined) node.textContent = value;
  return node;
}

export function icon(name) {
  const node = svg("svg", { class: "icon", "aria-hidden": "true" });
  node.append(svg("use", { href: "#i-" + name }));
  return node;
}

export function download(data, filename, type) {
  const url = URL.createObjectURL(data instanceof Blob ? data : new Blob([data], { type }));
  const link = html("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export function csv(rows) {
  return "\ufeff" + rows.map(csvRow).join("");
}

export function table(headers, rows) {
  const element = html("table");
  const head = element.createTHead().insertRow();
  for (const header of headers) {
    const cell = html("th", header);
    cell.scope = "col";
    head.append(cell);
  }
  const body = element.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    for (const value of row) {
      const td = tr.insertCell();
      if (value instanceof Node) td.append(value);
      else td.textContent = value ?? "";
    }
  }
  return element;
}

function figure(title, width, height, exported) {
  const node = svg("svg", {
    xmlns: NS, viewBox: `0 0 ${width} ${height}`, width, height,
    role: "img", "aria-label": title, "font-family": "Segoe UI, sans-serif", fill: ink,
  });
  node.append(svg("title", {}, title));
  if (exported) {
    node.append(svg("rect", { width, height, fill: "#fffcfa" }));
    node.append(svg("text", { x: 18, y: 30, fill: accent, "font-size": 19, "font-weight": 700 }, title));
  }
  return node;
}

function axis(max) {
  const target = Math.max(1, max / 5);
  const unit = 10 ** Math.floor(Math.log10(target));
  const step = [1, 2, 5, 10].map(value => value * unit).find(value => value >= target);
  return { step, upper: Math.ceil(max / step) * step || 1 };
}

function wrap(label, max) {
  const lines = [];
  let line = "";
  for (const word of label.split(/\s+/)) {
    if (line && line.length + word.length >= max) { lines.push(line); line = ""; }
    line += (line ? " " : "") + word;
  }
  if (line) lines.push(line);
  return lines.length > 2 ? [lines[0], lines[1].slice(0, max - 1) + "…"] : lines.map(text => text.length > max + 2 ? text.slice(0, max - 1) + "…" : text);
}

function bars(title, rows, width, exported) {
  const top = exported ? 52 : 12;
  const left = Math.max(106, Math.min(225, Math.round(width * .31)));
  const plotWidth = width - left - 45;
  const rowHeight = 36;
  const height = top + rowHeight * rows.length + 49;
  const node = figure(title, width, height, exported);
  const max = Math.max(...rows.map(row => row.count));
  const { step, upper } = axis(max);
  for (let value = 0; value <= upper; value += step) {
    const x = left + value / upper * plotWidth;
    node.append(svg("line", { x1: x, x2: x, y1: top, y2: height - 46, stroke: soft }));
    node.append(svg("text", { x, y: height - 27, "text-anchor": "middle", "font-size": 11 }, format.format(value)));
  }
  rows.forEach(({ label, count }, index) => {
    const y = top + rowHeight * index + rowHeight / 2;
    const text = svg("text", { x: left - 8, y, "text-anchor": "end", "font-size": 12 });
    const lines = wrap(label, Math.max(13, Math.floor((left - 12) / 6.7)));
    lines.forEach((line, i) => text.append(svg("tspan", { x: left - 8, dy: i ? 13 : lines.length > 1 ? -2 : 4 }, line)));
    const length = count / upper * plotWidth;
    const row = svg("g");
    row.append(svg("title", {}, `${label} · ${format.format(count)} job ads`), text);
    row.append(svg("rect", { x: left, y: y - 10, width: length, height: 20, rx: 2, fill: count === max ? accent : "#9b8b7e" }));
    row.append(svg("text", { x: left + length + 6, y: y + 4, "font-size": 12, "font-weight": 650 }, format.format(count)));
    node.append(row);
  });
  node.append(svg("text", { x: left + plotWidth / 2, y: height - 7, "text-anchor": "middle", "font-size": 11 }, "Job advertisements"));
  return node;
}

function timeline(title, rows, width, exported, through) {
  const height = 260;
  const top = exported ? 55 : 16;
  const bottom = height - 37;
  const node = figure(title, width, height, exported);
  const { step, upper } = axis(Math.max(...rows.map(row => row.count)));
  const x = index => 37 + index / Math.max(1, rows.length - 1) * (width - 66);
  const y = count => bottom - count / upper * (bottom - top);
  for (let value = 0; value <= upper; value += step) {
    node.append(svg("line", { x1: 37, x2: width - 29, y1: y(value), y2: y(value), stroke: soft }));
    node.append(svg("text", { x: 28, y: y(value) + 4, "text-anchor": "end", "font-size": 11 }, format.format(value)));
  }
  const labels = Math.max(1, Math.ceil(rows.length / Math.max(2, Math.floor(width / 100))));
  rows.forEach((row, i) => {
    if (i === 0 || i === rows.length - 1 || i % labels === 0 && rows.length - 1 - i > labels / 2) {
      node.append(svg("text", { x: x(i), y: bottom + 22, "text-anchor": i === 0 ? "start" : i === rows.length - 1 ? "end" : "middle", "font-size": 11 }, monthFormat.format(new Date(row.label + "-01T00:00:00Z"))));
    }
  });
  const visible = rows.slice(0, through + 1);
  node.append(svg("polyline", { class: "time-series", points: visible.map((row, i) => `${x(i)},${y(row.count)}`).join(" "), stroke: accent, "stroke-width": 2.5, fill: "none" }));
  visible.forEach((row, i) => {
    if (!row.count && rows.length > 60 && i !== through) return;
    const point = svg("circle", { cx: x(i), cy: y(row.count), r: 3.5, fill: accent, stroke: "#fffcfa" });
    point.append(svg("title", {}, `${row.label} · ${format.format(row.count)} job ads`));
    node.append(point);
  });
  return node;
}

const seriesPalette = [accent, "#d6a33d", "#4f7e73", "#687f9d", "#b56b5d", "#6f5a87", "#8b7a63", "#495c5b"];

function multiLine(title, rows, width, exported, through) {
  const months = [...new Set(rows.map(row => row.label))].sort();
  const names = [...new Set(rows.map(row => row.series))].sort((a, b) => a.localeCompare(b));
  const height = Math.max(280, 190 + names.length * 18);
  const top = exported ? 56 : 20;
  const bottom = height - 40;
  const left = 44;
  const legendWidth = Math.min(170, Math.max(100, Math.round(width * .26)));
  const plotWidth = width - left - legendWidth - 28;
  const node = figure(title, width, height, exported);
  const max = Math.max(1, ...rows.map(row => row.count));
  const { step, upper } = axis(max);
  const x = index => left + index / Math.max(1, months.length - 1) * plotWidth;
  const y = count => bottom - count / upper * (bottom - top);
  for (let value = 0; value <= upper; value += step) {
    node.append(svg("line", { x1: left, x2: left + plotWidth, y1: y(value), y2: y(value), stroke: soft }));
    node.append(svg("text", { x: left - 8, y: y(value) + 4, "text-anchor": "end", "font-size": 11 }, format.format(value)));
  }
  const interval = Math.max(1, Math.ceil(months.length / Math.max(2, Math.floor(plotWidth / 80))));
  months.forEach((month, index) => {
    if (index === 0 || index === months.length - 1 || index % interval === 0) {
      node.append(svg("text", { x: x(index), y: bottom + 22, "text-anchor": index === 0 ? "start" : index === months.length - 1 ? "end" : "middle", "font-size": 10 }, monthFormat.format(new Date(month + "-01T00:00:00Z"))));
    }
  });
  const bySeries = new Map(names.map(name => [name, new Map()]));
  rows.forEach(row => bySeries.get(row.series).set(row.label, row.count));
  names.forEach((name, index) => {
    const color = seriesPalette[index % seriesPalette.length];
    const values = months.slice(0, through + 1).map(month => bySeries.get(name).get(month) ?? 0);
    node.append(svg("polyline", { class: "time-series", points: values.map((value, month) => `${x(month)},${y(value)}`).join(" "), stroke: color, "stroke-width": 2.5, fill: "none" }));
    values.forEach((value, month) => {
      const point = svg("circle", { cx: x(month), cy: y(value), r: 3.2, fill: color, stroke: "#fffcfa" });
      point.append(svg("title", {}, `${name} · ${months[month]} · ${format.format(value)} job ads`));
      node.append(point);
    });
    const legendY = top + 6 + index * 18;
    node.append(svg("line", { x1: left + plotWidth + 16, x2: left + plotWidth + 34, y1: legendY, y2: legendY, stroke: color, "stroke-width": 3 }));
    const text = svg("text", { x: left + plotWidth + 40, y: legendY + 4, "font-size": 10 });
    wrap(name, Math.max(12, Math.floor(legendWidth / 6))).slice(0, 2).forEach((part, line) => text.append(svg("tspan", { x: left + plotWidth + 40, dy: line ? 12 : 0 }, part)));
    node.append(text);
  });
  return node;
}

function heatmap(title, matrix, width, exported) {
  const rowHeight = 34;
  const colWidth = 66;
  const left = Math.max(150, Math.min(250, Math.round(width * .27)));
  const top = exported ? 56 : 20;
  const height = top + rowHeight * matrix.rows.length + 48;
  const plotWidth = colWidth * matrix.columns.length;
  const svgWidth = Math.max(width, left + plotWidth + 24);
  const node = figure(title, svgWidth, height, exported);
  const cells = new Map(matrix.cells.map(cell => [`${cell.row}\u0000${cell.column}`, cell]));
  matrix.rows.forEach((row, rowIndex) => {
    const y = top + rowIndex * rowHeight;
    const label = svg("text", { x: left - 10, y: y + rowHeight / 2 + 4, "text-anchor": "end", "font-size": 11 }, wrap(row, Math.max(14, Math.floor(left / 7))).join(" "));
    node.append(label);
    matrix.columns.forEach((column, columnIndex) => {
      const x = left + columnIndex * colWidth;
      const cell = cells.get(`${row}\u0000${column}`) || { count: 0, share: 0, denominator: 0 };
      const share = Math.max(0, Math.min(1, Number(cell.share) || 0));
      const opacity = .08 + share * .88;
      const color = `rgba(120, 24, 43, ${opacity.toFixed(2)})`;
      const rect = svg("rect", { x: x + 2, y: y + 2, width: colWidth - 4, height: rowHeight - 4, rx: 3, fill: color, stroke: "#e6d9d7" });
      rect.append(svg("title", {}, `${row} · ${column} · ${format.format(cell.count)} ads · ${(share * 100).toFixed(1)}% of ${format.format(cell.denominator)} ads in this group`));
      node.append(rect);
      node.append(svg("text", { x: x + colWidth / 2, y: y + rowHeight / 2 + 4, "text-anchor": "middle", "font-size": 11, "font-weight": 650, fill: share > .52 ? "#fff" : ink }, format.format(cell.count)));
      if (rowIndex === 0) {
        const label = svg("text", { x: x + colWidth / 2, y: top - 6, "text-anchor": "middle", "font-size": 10 });
        wrap(column, 11).forEach((part, line) => label.append(svg("tspan", { x: x + colWidth / 2, dy: line ? 11 : 0 }, part)));
        node.append(label);
      }
    });
  });
  node.append(svg("text", { x: left + plotWidth / 2, y: height - 7, "text-anchor": "middle", "font-size": 10 }, "Darker cells indicate a larger share within the row group"));
  return node;
}

async function downloadPng(node, filename) {
  const serialized = new XMLSerializer().serializeToString(node);
  const url = URL.createObjectURL(new Blob([serialized], { type: "image/svg+xml;charset=utf-8" }));
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    const canvas = html("canvas");
    canvas.width = img.width * 2;
    canvas.height = img.height * 2;
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    const png = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
    if (!png) throw new Error("PNG export unavailable");
    download(png, filename + ".png");
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function chartCard(title, rows, { note, total, type = "bars", single = false, fullRows = rows,
  insight: insightText, insightTitle = "Key Insight", topRows = [], matrix, listTitle = "Top Displayed Categories" } = {}) {
  const card = html("article", undefined, "card chart-card");
  const head = html("div", undefined, "section-head");
  const heading = html("h3");
  heading.append(icon(type.includes("line") ? "pin" : type === "heatmap" ? "layer" : "chart"), document.createTextNode(title));
  head.append(heading);
  card.append(head);
  if (!rows.length) {
    card.append(html("p", note || "No classifiable evidence in this dataset.", "chart-note"));
    return { card, destroy() {} };
  }
  const insightBox = html("aside", undefined, "insight");
  const insightHeading = html("h4");
  insightHeading.append(icon("light"), document.createTextNode(insightTitle));
  let summary = insightText;
  if (!summary) {
    const peak = Math.max(...rows.map(row => row.count));
    const leaders = rows.filter(row => row.count === peak);
    const names = new Intl.ListFormat("en").format(leaders.slice(0, 3).map(row => row.label));
    const suffix = leaders.length > 3 ? ` and ${leaders.length - 3} more` : "";
    const share = total ? ` (${(peak / total * 100).toFixed(1)}% of ${format.format(total)} ads)` : "";
    summary = `${names}${suffix} ${leaders.length === 1 ? "has the highest displayed count" : "share the highest displayed count"} at ${format.format(peak)} ${peak === 1 ? "ad" : "ads"}${leaders.length > 1 ? " each" : ""}${share}.`;
  }
  insightBox.append(insightHeading, html("p", summary));
  if (topRows.length) {
    insightBox.append(html("h5", listTitle));
    const list = html("ol");
    topRows.slice(0, 3).forEach(({ label, count }) => {
      const item = html("li");
      item.append(html("span", label), html("strong", `${format.format(count)} ${count === 1 ? "ad" : "ads"}`));
      list.append(item);
    });
    insightBox.append(list);
  }
  const graphic = html("div", undefined, "chart-graphic");
  if (type === "heatmap") graphic.classList.add("chart-heatmap");
  const layout = html("div", undefined, "chart-layout");
  layout.append(graphic, insightBox);
  card.append(layout);
  let cursor = type === "multi-line" ? Math.max(0, new Set(rows.map(row => row.label)).size - 1) : rows.length - 1;
  let timer;
  let observer;
  const numericOnly = single && rows.length === 1;
  const draw = (width, exported = false) => type === "line" ? timeline(title, rows, width, exported, cursor)
    : type === "multi-line" ? multiLine(title, rows, width, exported, cursor)
      : type === "heatmap" ? heatmap(title, matrix, width, exported) : bars(title, rows, width, exported);
  const render = () => graphic.replaceChildren(draw(Math.max(290, graphic.clientWidth)));
  if (numericOnly) {
    graphic.append(html("p", rows[0].label), html("p", format.format(rows[0].count), "single-value"));
  } else {
    observer = new ResizeObserver(render);
    observer.observe(graphic);
  }
  const stepCount = type === "multi-line" ? new Set(rows.map(row => row.label)).size : rows.length;
  if ((type === "line" && rows.length > 1) || (type === "multi-line" && stepCount > 1)) {
    const controls = html("div", undefined, "timeline-controls");
    const play = html("button", "Play timeline", "button secondary");
    play.type = "button";
    const range = html("input");
    range.type = "range";
    range.min = 0;
    range.max = stepCount - 1;
    range.setAttribute("aria-label", "Through posting month");
    const month = html("output");
    const labels = type === "multi-line" ? [...new Set(rows.map(row => row.label))].sort() : rows.map(row => row.label);
    const update = () => { range.value = cursor; month.textContent = labels[cursor]; render(); };
    const pause = () => { clearInterval(timer); timer = undefined; play.textContent = "Play timeline"; };
    play.addEventListener("click", () => {
      if (timer) { pause(); return; }
      if (cursor === stepCount - 1) cursor = 0;
      update();
      play.textContent = "Pause timeline";
      timer = setInterval(() => {
        cursor = Math.min(stepCount - 1, cursor + Math.max(1, Math.ceil(stepCount / 35)));
        update();
        if (cursor === stepCount - 1) pause();
      }, 550);
    });
    range.addEventListener("input", () => { pause(); cursor = Number(range.value); update(); });
    range.value = cursor;
    month.textContent = labels[cursor];
    controls.append(play, range, month);
    card.append(controls);
  }
  const menu = html("details", undefined, "export-menu");
  const label = html("summary");
  label.append(icon("download"), document.createTextNode(numericOnly ? "Download data" : "Download graph"));
  const choices = html("div", undefined, "export-options");
  const filename = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/-$/, "");
  const exportCsv = html("button", "CSV data", "button quiet");
  exportCsv.addEventListener("click", () => {
    const rows = type === "heatmap" ? [["Row", "Column", "Job ads", "Share", "Group ads"], ...fullRows.map(row => [row.row, row.column, row.count, `${(row.share * 100).toFixed(1)}%`, row.denominator])]
      : type === "multi-line" ? [["Series", "Month", "Job ads"], ...fullRows.map(row => [row.series, row.label, row.count])]
        : [["Label", "Job ads"], ...fullRows.map(row => [row.label, row.count])];
    download(csv(rows), filename + ".csv", "text/csv;charset=utf-8");
    menu.open = false;
  });
  choices.append(exportCsv);
  if (!numericOnly) {
    const png = html("button", "PNG image", "button quiet");
    png.addEventListener("click", async () => {
      png.disabled = true;
      try { await downloadPng(draw(900, true), filename); menu.open = false; }
      catch { png.textContent = "Try PNG again"; }
      finally { png.disabled = false; }
    });
    choices.append(png);
  }
  menu.append(label, choices);
  head.append(menu);
  if (note) card.append(html("p", note, "chart-note"));
  const detail = html("details", undefined, "chart-data");
  const body = html("div", undefined, "table-wrap detail-body");
  detail.append(html("summary", "View data table"), body);
  detail.addEventListener("toggle", () => {
    if (detail.open && !body.firstChild) {
      if (type === "heatmap") body.append(table(["Row", "Column", "Job ads", "Share", "Group ads"], fullRows.map(row => [row.row, row.column, format.format(row.count), `${(row.share * 100).toFixed(1)}%`, format.format(row.denominator)])));
      else if (type === "multi-line") body.append(table(["Series", "Month", "Job ads"], fullRows.map(row => [row.series, row.label, format.format(row.count)])));
      else body.append(table(["Label", "Job ads"], rows.map(row => [row.label, format.format(row.count)])));
    }
  });
  card.append(detail);
  return { card, destroy() { observer?.disconnect(); clearInterval(timer); } };
}
