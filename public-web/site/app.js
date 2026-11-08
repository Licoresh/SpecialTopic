import { chartCard, csv, download, html, icon, table } from "./charts.js";
import { forget, remember, restore } from "./session.js";

const $ = id => document.getElementById(id);
const integer = new Intl.NumberFormat("en-PH");
const CSV = "text/csv;charset=utf-8";
const MB = 1024 * 1024;
const required = [
  ["job_title", "Job title"],
  ["job_description", "Job description"],
  ["required_skills", "Required skills"],
  ["preferred_skills", "Preferred skills"],
  ["qualifications", "Qualifications"],
];
const optional = [
  ["job_id", "Job ID"], ["job_family", "Job family"], ["company", "Employer"],
  ["industry", "Industry"], ["location", "Location"], ["education_requirement", "Education"],
  ["experience_requirement", "Experience"], ["posting_date", "Posting date"],
  ["source", "Source"], ["url", "Source URL"], ["source_id", "Source record ID"],
  ["employment_type", "Employment type"], ["salary", "Salary"], ["employment_size", "Employer size"],
  ["search_term", "Search term"], ["collected_at_utc", "Collection date"],
];
const views = {
  skills: [["skills", "Employer-requested skills"], ["technicalSkills", "Technical skills"], ["enablingSkills", "Enabling and interpersonal skills"], ["broadAreas", "Broad competency areas"]],
  roles: [["titles", "Job-title overview"], ["familyHeatmap", "Skills by occupational family"], ["selectedTitleSkills", "Skills for selected titles"], ["locations", "Geographical distribution"], ["locationSkills", "Skills by selected location"], ["timeline", "Job-title posting timeline"]],
  qualifications: [["education", "Stated education requirements by level"], ["experience", "Experience requirements"]],
  psf: [["psf", "PSF-AAI competencies linked to employer demand"], ["psfRoles", "Related PSF-AAI reference roles"], ["psfHeatmap", "Role–competency demand"]],
  alignment: [["alignment", "Status of phrase–competency evidence groups"]],
  unmapped: [["unmapped", "Unmapped skill labels"], ["recurring", "Recurring labels for review"]],
};
const tabs = [...document.querySelectorAll("[role=tab]")];
let result;
let savedFile;
let candidate;
let worker;
let requestController;
let job;
let engineHealth;
let uploadLimit = 4 * MB;
let activeView = "skills";
let titleFilter = "";
let timelineData;
let displayed = [];
let cacheWrite = Promise.resolve();
let flowStep = 1;
let titleViewMode = "common";
let explorationFamily = "All";
let explorationTitle = "All";
let selectedRegion = "All";
let selectedCity = "All";
let timelineTitles;
let familySelection;
let psfRoleFilter = "All";
let psfHeatmapRoles;
let psfHeatmapCompetencies;
const openPickers = new Set();
const pickerQueries = new Map();
const pageCopy = {
  upload: {
    title: "Upload your job advertisements",
    intro: "Start by selecting a CSV dataset. We’ll guide you through the rest.",
  },
  processing: {
    title: "Preparing your file",
    intro: "Your file is being analyzed by the shared research engine.",
  },
  results: {
    title: "Analysis results",
    intro: "Explore the complete public analysis: skills, roles, qualifications, PSF-AAI evidence, alignment methods, and emerging candidates.",
  },
  methodology: {
    title: "Methodology",
    intro: "See how the public analyzer uses the shared research pipeline to compare job-ad evidence.",
  },
};

function showPage(page = location.hash.slice(1)) {
  if (!pageCopy[page]) page = "upload";
  if (page === "processing" && !worker && !requestController) {
    page = result ? "results" : "upload";
    if (location.hash === "#processing") location.hash = `#${page}`;
  }
  if (page === "results" && result) flowStep = 3;
  if (page === "upload" && !candidate && !worker && !requestController) flowStep = 1;
  const reviewing = page === "upload" && Boolean(candidate) && !$("confirm").hidden;
  document.querySelectorAll("[data-page-view]").forEach(view => {
    view.hidden = view.dataset.pageView !== page;
  });
  document.body.dataset.page = page;
  $("upload-guide").hidden = Boolean(reviewing);
  $("review-guide").hidden = !reviewing;
  $("workflow-rail").hidden = page !== "upload" || Boolean(reviewing);
  setFlowStep(flowStep);
  const copy = reviewing ? {title: "Review your dataset", intro: "Check the detected columns before beginning the analysis."} : pageCopy[page];
  $("page-title").textContent = copy.title;
  $("page-intro").textContent = copy.intro;
  for (const item of $("navigation").querySelectorAll("a")) {
    if (item.hash === `#${page}`) item.setAttribute("aria-current", "location");
    else item.removeAttribute("aria-current");
  }
  document.title = `${copy.title} · Future of Work`;
}

function navigate(page) {
  if (location.hash === `#${page}`) showPage(page);
  else location.hash = `#${page}`;
}

function setFlowStep(step) {
  flowStep = step;
  for (const item of document.querySelectorAll("[data-process-step]")) {
    const itemStep = Number(item.dataset.processStep);
    const state = itemStep < step ? "complete" : itemStep === step ? "current" : "upcoming";
    item.dataset.state = state;
    if (state === "current") item.setAttribute("aria-current", "step");
    else item.removeAttribute("aria-current");
  }
}

function notify(message, isError = false) {
  const notice = $("notice");
  notice.hidden = !message;
  notice.textContent = message;
  notice.classList.toggle("error", isError);
  notice.setAttribute("role", isError ? "alert" : "status");
}

function engineStatus(health) {
  engineHealth = health;
  uploadLimit = Number(health.maxUploadBytes) || 4 * MB;
  const available = health.classifierAvailable === true;
  const badge = $("engine-badge");
  badge.dataset.state = available ? "complete" : "error";
  badge.replaceChildren(icon(available ? "check" : "info"), document.createTextNode(available ? "Analysis ready" : "Research classifier unavailable"));
  $("upload-limit").textContent = `CSV files up to ${Math.floor(uploadLimit / MB)} MB are processed by the analysis server and not retained.`;
  refreshMappingStatuses();
  busy(job ? "Processing…" : "");
  if (!available) notify("A public classifier is not available on this server yet. You can review column mapping, but analysis is disabled until a classifier is published.", true);
}

async function connectEngine() {
  try {
    const response = await fetch("/api/health", { cache: "no-store", credentials: "same-origin" });
    if (!response.ok) throw new Error("Research engine is unavailable.");
    engineStatus(await response.json());
  } catch {
    engineHealth = { classifierAvailable: false };
    $("engine-badge").dataset.state = "error";
    $("engine-badge").replaceChildren(icon("info"), document.createTextNode("Research engine offline"));
    refreshMappingStatuses();
    notify("The public analysis server could not be reached. Start the local research engine or try again later.", true);
  }
}

function busy(message = "") {
  $("progress-text").textContent = message;
  $("file").disabled = Boolean(message);
  $("clear").disabled = Boolean(message);
  $("cleaned").disabled = Boolean(message) || !savedFile;
  $("analyze-again").disabled = Boolean(message) || engineHealth?.classifierAvailable !== true;
  if (message) {
    $("progress").removeAttribute("value");
    $("progress-value").textContent = "0%";
  }
}

function stop() {
  worker?.terminate();
  worker = undefined;
  requestController?.abort();
  requestController = undefined;
  job = undefined;
  busy();
}

function fileDisplay(file, filename, fallback = "") {
  $("file-label").textContent = filename || "Drop your CSV file here";
  $("dropzone").dataset.ready = String(Boolean(file));
  $("dropzone-icon").firstElementChild.setAttribute("href", file ? "#i-file" : "#i-upload");
  $("file-ready").hidden = !file;
  $("dropzone-action-text").textContent = file ? "Replace CSV file" : "Select CSV file";
  const size = file?.size ?? 0;
  const [quantity, unit] = size >= MB ? [size / MB, "MB"] : size >= 1024 ? [size / 1024, "KB"] : [size, "bytes"];
  $("file-detail").textContent = file ? `${quantity.toLocaleString("en-PH", { maximumFractionDigits: 2 })} ${unit} · inspected in your browser; sent only when you analyze` : fallback || "or select a file from your device";
}

function fillMapping(target, fields, { columns, mapping }) {
  const table = document.createElement("table");
  table.className = "mapping-table";
  const head = document.createElement("thead");
  const header = document.createElement("tr");
  for (const name of ["CSV column", "Used as", "Status"]) {
    const cell = html("th", name);
    cell.scope = "col";
    header.append(cell);
  }
  head.append(header);
  const body = document.createElement("tbody");
  for (const [key, label] of fields) {
    const row = document.createElement("tr");
    const select = html("select");
    select.name = key;
    select.setAttribute("aria-label", `CSV column used as ${label}`);
    select.append(new Option("Choose a column", ""));
    columns.forEach(column => select.append(new Option(column, column)));
    select.value = mapping[key] || "";
    const source = document.createElement("td");
    source.append(select);
    const usedAs = html("th", label);
    usedAs.scope = "row";
    const status = html("span", "Optional", "mapping-status");
    const statusCell = document.createElement("td");
    statusCell.append(status);
    row.append(source, usedAs, statusCell);
    body.append(row);
  }
  table.append(head, body);
  $(target).replaceChildren(table);
}

function refreshMappingStatuses() {
  const selects = [...$("confirm").querySelectorAll(".mapping-table select")];
  const counts = new Map();
  for (const select of selects) if (select.value) counts.set(select.value, (counts.get(select.value) ?? 0) + 1);
  const mapping = Object.fromEntries(new FormData($("confirm")));
  const hasTitle = Boolean(mapping.job_title);
  const hasContent = required.slice(1).some(([key]) => Boolean(mapping[key]));
  const unique = [...counts.values()].every(count => count === 1);
  for (const select of selects) {
    const row = select.closest("tr");
    const status = row.querySelector(".mapping-status");
    const duplicate = select.value && counts.get(select.value) > 1;
    const requiredField = select.name === "job_title";
    const contentField = required.slice(1).some(([key]) => key === select.name);
    const needsSelection = requiredField || (contentField && !hasContent);
    status.textContent = duplicate ? "Duplicate" : select.value ? "Matched" : requiredField ? "Required" : needsSelection ? "Choose one" : "Optional";
    status.dataset.state = duplicate ? "error" : select.value ? "complete" : needsSelection ? "pending" : "optional";
  }
  const ready = hasTitle && hasContent && unique;
  const completion = Math.round(((Number(hasTitle) + Number(hasContent) + Number(unique)) / 3) * 100);
  $("column-check").dataset.state = ready ? "complete" : "pending";
  $("column-check-title").textContent = ready ? "Column mapping is complete" : "Complete the column mapping";
  $("column-check-copy").textContent = ready ? "Job title and job details are ready." : "Select Job title and at least one job detail field.";
  const engineReady = engineHealth?.classifierAvailable === true;
  $("readiness-title").textContent = ready ? engineReady ? "Ready to analyze" : "Research classifier unavailable" : "Review column matches";
  $("column-check-copy").textContent = ready
    ? engineReady ? "Job title and job details are ready." : "The analysis server needs the approved research classifier."
    : "Select Job title and at least one job detail field.";
  $("mapping-progress").value = completion;
  $("mapping-percent").textContent = `${completion}%`;
  $("analyze-submit").disabled = !ready || !engineReady;
}

function showInspection(inspection) {
  fillMapping("required-fields", required, inspection);
  fillMapping("optional-fields", optional, inspection);
  const columns = inspection.columns.slice(0, 12);
  const rows = inspection.preview.map(row => columns.map(col => String(row[col] ?? "").slice(0, 180)));
  $("preview").replaceChildren(table(columns, rows));
  $("confirm").hidden = false;
  $("clear").hidden = false;
  setFlowStep(1);
  refreshMappingStatuses();
  navigate("upload");
}

function metric(name, value, glyph) {
  const block = html("div", undefined, "card metric");
  const image = html("span", undefined, "tile");
  image.append(icon(glyph));
  const copy = html("div");
  copy.append(html("b", typeof value === "number" ? integer.format(value) : String(value)), html("small", name));
  block.append(image, copy);
  return block;
}

function sorted(rows) {
  const order = $("order").value;
  return [...rows].sort((a, b) => (
    order === "high" ? b.count - a.count : order === "low" ? a.count - b.count : 0
  ) || a.label.localeCompare(b.label));
}

function selectControl(labelText, options, value, onChange, key) {
  const label = html("label", labelText, "chart-filter");
  const select = html("select");
  select.id = `control-${key}`;
  for (const option of options) {
    const item = typeof option === "string" ? { label: option, value: option } : option;
    select.append(new Option(item.label, item.value));
  }
  select.value = value;
  select.addEventListener("change", () => { onChange(select.value); section(); });
  label.append(select);
  return label;
}

function multiPicker(labelText, key, options, selected, onChange, maximum = 8) {
  const box = html("details", undefined, "multi-picker");
  box.open = openPickers.has(key);
  box.addEventListener("toggle", () => box.open ? openPickers.add(key) : openPickers.delete(key));
  const summary = html("summary", `${labelText} · ${selected.length} selected`);
  const search = html("input");
  search.type = "search";
  search.id = `picker-${key}-search`;
  search.placeholder = `Search ${labelText.toLowerCase()}`;
  search.setAttribute("aria-label", `Search ${labelText.toLowerCase()}`);
  search.value = pickerQueries.get(key) || "";
  const count = html("small", "", "picker-count");
  const list = html("div", undefined, "picker-list");
  const renderOptions = () => {
    const query = search.value.trim().toLowerCase();
    const matches = options.filter(name => name.toLowerCase().includes(query));
    const visible = matches.slice(0, 80);
    for (const current of selected) if (!visible.includes(current) && options.includes(current)) visible.unshift(current);
    count.textContent = matches.length > 80 ? `Showing 80 of ${integer.format(matches.length)} · refine your search` : `${integer.format(matches.length)} available`;
    list.replaceChildren(...visible.map(name => {
      const label = html("label", undefined, "picker-option");
      const checkbox = html("input");
      checkbox.type = "checkbox";
      checkbox.checked = selected.includes(name);
      checkbox.disabled = !checkbox.checked && selected.length >= maximum;
      checkbox.addEventListener("change", () => {
        const next = checkbox.checked ? [...selected, name] : selected.filter(value => value !== name);
        pickerQueries.set(key, search.value);
        openPickers.add(key);
        onChange(next.slice(0, maximum));
        section();
        document.getElementById(`picker-${key}-search`)?.focus({ preventScroll: true });
      });
      label.append(checkbox, document.createTextNode(name));
      return label;
    }));
  };
  search.addEventListener("input", () => { pickerQueries.set(key, search.value); renderOptions(); });
  renderOptions();
  box.append(summary, search, count, list);
  return box;
}

function rankedRows(rows) {
  return [...rows].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

function rankedInsight(rows, total, concept = "category") {
  if (!rows.length) return "No reportable evidence in this selection.";
  const data = rankedRows(rows);
  const maximum = data[0].count;
  const leaders = data.filter(row => row.count === maximum).map(row => row.label);
  const share = total ? ` (${(maximum / total * 100).toFixed(1)}% of ${integer.format(total)} selected ads)` : "";
  if (data.length === 1) return `${leaders[0]} appears in ${integer.format(maximum)} ${maximum === 1 ? "ad" : "ads"}${share}. Only one ${concept} is displayed.`;
  if (leaders.length > 1) return `${integer.format(leaders.length)} ${concept.endsWith("y") ? `${concept.slice(0, -1)}ies` : `${concept}s`} tie for the highest displayed count at ${integer.format(maximum)} ${maximum === 1 ? "ad" : "ads"} each${share}.`;
  return `${leaders[0]} has the highest displayed ${concept} count, appearing in ${integer.format(maximum)} ${maximum === 1 ? "ad" : "ads"}${share}.`;
}

function topRows(rows) { return rankedRows(rows).slice(0, 3); }

function makeBar(title, rows, { key, total, concept = "category", note = "One advertisement may appear in more than one bar.", insightTitle = "Key Insight", listTitle = "Top Displayed Categories", single = false, orderOverride, limitOverride } = {}) {
  const order = orderOverride || $("order").value;
  const ordered = order === "alpha" ? [...rows].sort((a, b) => a.label.localeCompare(b.label)) : [...rows].sort((a, b) => (order === "low" ? a.count - b.count : b.count - a.count) || a.label.localeCompare(b.label));
  const limit = Math.min(30, Number(limitOverride || $("limit").value));
  const shown = ordered.slice(0, limit);
  let displayTitle = title;
  if (order === "low") displayTitle = title.replace(/^Top\b/, "Least frequent").replace(/^Most common\b/, "Least common");
  const chart = chartCard(displayTitle, shown, {
    total, note, single, fullRows: rows, insight: rankedInsight(shown, total, concept),
    insightTitle, topRows: topRows(shown), listTitle,
  });
  if (key) chart.card.dataset.chart = key;
  displayed.push(chart);
  $("panel").append(chart.card);
  return chart;
}

function matrixCells(rows, rowKey, columnKey, rowLabels, columnLabels, denominatorByRow, valueKey = "count") {
  const values = new Map(rows.map(row => [`${row[rowKey]}\u0000${row[columnKey]}`, Number(row[valueKey]) || 0]));
  return rowLabels.flatMap(row => columnLabels.map(column => {
    const denominator = Number(denominatorByRow.get(row)) || 0;
    const count = values.get(`${row}\u0000${column}`) || 0;
    return { row, column, count, denominator, share: denominator ? count / denominator : 0 };
  }));
}

function matrixInsight(cells, rowTitle, columnTitle) {
  const ranked = [...cells].sort((a, b) => b.share - a.share || b.count - a.count || a.column.localeCompare(b.column) || a.row.localeCompare(b.row));
  if (!ranked.length || !ranked[0].count) return "No chartable evidence is available for this comparison.";
  const best = ranked[0];
  const tied = ranked.filter(cell => cell.share === best.share);
  const text = tied.length > 1
    ? `${integer.format(tied.length)} displayed ${columnTitle}–${rowTitle} pairs tie for the highest within-group share (${(best.share * 100).toFixed(1)}%).`
    : `${best.column} has the highest displayed within-group share in ${best.row}: ${integer.format(best.count)} of ${integer.format(best.denominator)} ads (${(best.share * 100).toFixed(1)}%).`;
  return { text, top: ranked.slice(0, 3).map(cell => ({ label: `${cell.column} · ${cell.row}`, count: cell.count })) };
}

function makeHeatmap(title, rowLabels, columnLabels, cells, { note, insightTitle = "Heatmap Insight", listTitle = "Top Skill × Group", transpose = false, rowTitle = "group", columnTitle = "skill" } = {}) {
  const matrix = { rows: transpose ? columnLabels : rowLabels, columns: transpose ? rowLabels : columnLabels, cells: transpose
    ? cells.map(cell => ({ ...cell, row: cell.column, column: cell.row })) : cells };
  const rows = cells.map(cell => ({ label: `${cell.column} · ${cell.row}`, count: cell.count }));
  const summary = matrixInsight(cells, rowTitle, columnTitle);
  const chart = chartCard(title, rows, { type: "heatmap", matrix, total: undefined, note,
    fullRows: cells, insight: summary.text, insightTitle, topRows: summary.top, listTitle });
  displayed.push(chart);
  $("panel").append(chart.card);
}

function roleDistribution(rows) {
  const bands = new Map();
  rows.forEach(row => bands.set(row.count, (bands.get(row.count) || 0) + 1));
  const sortedBands = [...bands].sort((a, b) => b[0] - a[0]);
  if (!sortedBands.length) return;
  const groups = sortedBands.slice(0, 3).map(([ads, count]) => ({ label: `${integer.format(ads)} ads each`, count, ads }));
  if (sortedBands.length > 3) groups.push({ label: "Other ad counts", count: sortedBands.slice(3).reduce((sum, item) => sum + item[1], 0) });
  const colors = ["#86142d", "#a99b92", "#d6a33d", "#d9c7be"];
  const total = groups.reduce((sum, row) => sum + row.count, 0);
  let offset = 0;
  const stops = groups.map((row, index) => {
    const end = offset + row.count / total * 100;
    const stop = `${colors[index]} ${offset.toFixed(2)}% ${end.toFixed(2)}%`;
    offset = end;
    return stop;
  });
  const card = html("article", undefined, "card role-distribution");
  card.append(html("h3", "Distribution Summary"));
  card.append(html("p", `${integer.format(total)} displayed reference roles have competency links to the selected advertisements. An advertisement may link to several roles.`, "chart-note"));
  const donut = html("div", undefined, "role-donut");
  donut.setAttribute("role", "img");
  donut.setAttribute("aria-label", `${total} linked reference roles grouped by advertisement count`);
  donut.style.background = `conic-gradient(${stops.join(",")})`;
  donut.append(html("strong", integer.format(total)), html("small", "Linked roles"));
  const legend = html("ul", undefined, "role-legend");
  groups.forEach((row, index) => {
    const item = html("li");
    const swatch = html("i");
    swatch.style.background = colors[index];
    item.append(swatch, html("span", `${row.label} · ${integer.format(row.count)} roles`));
    legend.append(item);
  });
  card.append(donut, legend);
  $("panel").append(card);
}

function referenceEvidence(rows) {
  const disclosure = html("details", undefined, "card evidence");
  const summary = html("summary");
  summary.append(icon("layer"), document.createTextNode("PSF-AAI reference evidence"));
  const body = html("div", undefined, "table-wrap");
  const credit = html("p", "Bundled TESDA PSF-AAI framework");
  const link = safeLink(result.reference.sourceUrl, "Open the official framework");
  if (link) credit.append(document.createTextNode(" · "), link);
  disclosure.append(summary, credit, body);
  disclosure.addEventListener("toggle", () => {
    if (!disclosure.open || body.firstChild) return;
    body.append(table(["Competency", "Job ads", "Basis", "Description", "Range of application", "Source page"], rows.map(row => [
      row.label, row.count, [].concat(row.methods || []).join(", "), row.description, row.range,
      safeLink(row.sourceUrl, row.sourcePage || "Open source") || row.sourcePage,
    ])));
  });
  return disclosure;
}

function sectionHeading(title, copy) {
  const block = html("div", undefined, "result-section-intro");
  block.append(html("h3", title), html("p", copy));
  $("panel").append(block);
}

function renderSkills() {
  const { charts, summary } = result;
  sectionHeading("Skills overview", "The same chart-eligible, grouped skill evidence used by the research results.");
  makeBar("Employer-requested skills", charts.skills, { total: summary.ads, concept: "skill", insightTitle: "Key Insight", listTitle: "Top Displayed Skills", note: "Each advertisement counts once per grouped skill, including equivalent wording. Percentages use all selected ads; skills overlap." });
  makeBar("Technical skills", charts.technicalSkills, { total: summary.ads, concept: "technical skill", listTitle: "Top Displayed Skills", note: "Distinct advertisements per detected technical skill. Ads may appear in multiple bars." });
  makeBar("Enabling and interpersonal skills", charts.enablingSkills, { total: summary.ads, concept: "enabling skill", listTitle: "Top Displayed Skills", note: "Distinct advertisements per detected enabling skill. Ads may appear in multiple bars." });
  makeBar("Broad competency areas", charts.broadAreas, { total: summary.ads, concept: "competency area", note: "An advertisement may contribute to several broad areas; these overlapping counts do not sum to the sample size." });

}

function renderRoles() {
  const { charts, summary } = result;
  sectionHeading("Roles and locations", "Explore normalized titles, source families, regional demand, and the recorded posting timeline.");
  const titleModes = [
    { label: "Most common job titles", value: "common" },
    { label: "Related role groups", value: "groups" },
    { label: "Specific titles (alphabetical)", value: "specific" },
  ];
  $("panel").append(selectControl("Job-title overview", titleModes, titleViewMode, value => { titleViewMode = value; }, "title-view"));
  const titleData = titleViewMode === "groups" ? charts.roleGroups : titleViewMode === "specific" ? charts.sourceTitles : charts.titles;
  const titleHeading = titleViewMode === "groups" ? "Related role groups" : titleViewMode === "specific" ? "Specific job titles" : "Most common job titles";
  const titleNote = titleViewMode === "groups"
    ? "Source-provided families and explicit title rules group related roles. Counts are distinct advertisements."
    : titleViewMode === "specific"
      ? "Specific titles retain normalized source wording and are displayed alphabetically."
      : "Clear seniority and branch variants are consolidated when one recognized occupation is stated; composite and unrecognized titles remain distinct.";
  makeBar(titleHeading, titleData, { total: summary.ads, concept: titleViewMode === "groups" ? "role group" : "job title", insightTitle: "Title Insight", listTitle: "Top Displayed Titles", note: titleNote, orderOverride: titleViewMode === "specific" ? "alpha" : undefined });

  const familyAds = charts.familyAdCounts || [];
  const familyOptions = familyAds.filter(row => row.job_family !== "not stated").map(row => row.job_family);
  const skillOptions = sorted(charts.skills).slice(0, Math.min(15, Number($("limit").value))).map(row => row.label);
  if (familyOptions.length && skillOptions.length) {
    const sizes = new Map(familyAds.map(row => [row.job_family, Number(row.family_ads)]));
    familySelection ??= familyOptions.slice(0, 8);
    familySelection = familySelection.filter(name => familyOptions.includes(name));
    $("panel").append(multiPicker("Occupational families in the heatmap", "skill-families", familyOptions, familySelection, value => { familySelection = value; }, 8));
    const selection = familySelection;
    if (selection.length) {
      const rows = charts.familySkillDemand.filter(row => selection.includes(row.job_family) && skillOptions.includes(row.skill_label));
      const cells = matrixCells(rows, "job_family", "skill_label", selection, skillOptions, sizes, "job_ads");
      makeHeatmap($("order").value === "low" ? "Least frequent requested skills by occupational family" : "Top requested skills by occupational family", selection, skillOptions, cells, {
        transpose: true, rowTitle: "occupational family", columnTitle: "skill", listTitle: "Top Skill × Family",
        note: "Color compares each skill’s share of ads in that family. Denominators include ads with no chartable skill; categories overlap.",
      });
    }
  }

  sectionHeading("Explore a selected title", "Compare requested skills for a source family or a specific normalized job title.");
  const titleFamilies = charts.titleFamilies || [];
  const familyNames = [...new Set(titleFamilies.map(row => row.job_family))].filter(Boolean).sort((a, b) => a.localeCompare(b));
  if (!familyNames.includes("All")) familyNames.unshift("All");
  if (!familyNames.includes(explorationFamily)) explorationFamily = "All";
  $("panel").append(selectControl("Occupational family", familyNames, explorationFamily, value => { explorationFamily = value; explorationTitle = "All"; }, "exploration-family"));
  const familyTitles = titleFamilies.filter(row => explorationFamily === "All" || row.job_family === explorationFamily);
  const titleNames = [...new Set(familyTitles.map(row => row.job_title).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  titleNames.unshift("All");
  if (!titleNames.includes(explorationTitle)) explorationTitle = "All";
  $("panel").append(selectControl("Specific job title", titleNames, explorationTitle, value => { explorationTitle = value; }, "exploration-title"));
  let scopedSkills;
  let titleDenominator = summary.ads;
  if (explorationFamily === "All" && explorationTitle === "All") scopedSkills = charts.skills;
  else {
    const selectedTitles = familyTitles.filter(row => explorationTitle === "All" || row.job_title === explorationTitle);
    titleDenominator = explorationTitle === "All"
      ? Number(familyAds.find(row => row.job_family === explorationFamily)?.family_ads || 0)
      : selectedTitles.reduce((sum, row) => sum + Number(row.job_ads), 0);
    const selectedFamilyNames = new Set(selectedTitles.map(row => row.job_family));
    const selectedExactTitles = new Set(selectedTitles.map(row => row.job_title));
    const skillCounts = new Map();
    charts.titleSkillDemand.filter(row => selectedFamilyNames.has(row.job_family) && selectedExactTitles.has(row.job_title))
      .forEach(row => skillCounts.set(row.skill_label, (skillCounts.get(row.skill_label) || 0) + Number(row.job_ads)));
    scopedSkills = [...skillCounts].map(([label, count]) => ({ label, count }));
  }
  const selectedTitleLabel = explorationTitle !== "All" ? explorationTitle : explorationFamily !== "All" ? explorationFamily : "all selected advertisements";
  makeBar(`Top skills for ${selectedTitleLabel}`, scopedSkills, { total: titleDenominator, concept: "skill", insightTitle: "Selection Insight", listTitle: "Top Displayed Skills", note: `Selected group: ${selectedTitleLabel} · ${integer.format(titleDenominator)} advertisements. Counts are distinct ads per skill.`, limitOverride: 10 });

  sectionHeading("Geographical distribution", "Counts describe collected advertisements, not population- or labor-force-adjusted employment rates.");
  const regionNames = [...new Set(charts.locations.map(row => row.label))].sort((a, b) => a.localeCompare(b));
  regionNames.unshift("All");
  if (!regionNames.includes(selectedRegion)) selectedRegion = "All";
  $("panel").append(selectControl("Region", regionNames, selectedRegion, value => { selectedRegion = value; selectedCity = "All"; }, "geography-region"));
  const regionCities = charts.cities.filter(row => row.region === selectedRegion);
  const cityNames = [...new Set(regionCities.map(row => row.label))].sort((a, b) => a.localeCompare(b));
  cityNames.unshift("All");
  if (!cityNames.includes(selectedCity)) selectedCity = "All";
  if (selectedRegion !== "All") $("panel").append(selectControl("City or municipality", cityNames, selectedCity, value => { selectedCity = value; }, "geography-city"));
  const locationRows = selectedRegion === "All" ? charts.locations : regionCities.map(row => ({ label: row.label, count: row.count }));
  const locationDenominator = selectedRegion === "All" ? summary.ads : Number(charts.locations.find(row => row.label === selectedRegion)?.count || 0);
  const locationHeading = selectedRegion === "All" ? "Advertisements by Philippine region" : `Cities and municipalities in ${selectedRegion}`;
  makeBar(locationHeading, locationRows, { total: locationDenominator, concept: selectedRegion === "All" ? "region" : "location", insightTitle: "Location Insight", listTitle: "Top Displayed Locations", note: `${integer.format(locationDenominator)} advertisements form the comparison denominator. Locations can overlap across advertisements.` });
  const selectedArea = selectedRegion === "All" ? "All regions" : selectedCity === "All" ? selectedRegion : selectedCity;
  const skillSource = selectedRegion === "All" ? charts.regionSkillDemand : charts.citySkillDemand.filter(row => row.region === selectedRegion && (selectedCity === "All" || row.locality === selectedCity));
  const skillTotals = new Map();
  skillSource.forEach(row => skillTotals.set(row.skill_label, (skillTotals.get(row.skill_label) || 0) + Number(row.job_ads)));
  const geographicSkills = [...skillTotals].map(([label, count]) => ({ label, count }));
  const skillDenominator = selectedRegion === "All" ? summary.withLocation : selectedCity === "All" ? locationDenominator : Number(regionCities.find(row => row.label === selectedCity)?.count || 0);
  makeBar(`Skills in ${selectedArea}`, geographicSkills, { total: skillDenominator, concept: "skill", insightTitle: "Key Insight", listTitle: "Top Displayed Skills", note: "Each bar counts distinct advertisements in this area. An advertisement can request several skills.", limitOverride: 10 });
  $("panel").append(html("p", `Location not stated: ${integer.format(summary.notStatedLocation || 0)} ads. Broad, remote, or unresolved location: ${integer.format(summary.unresolvedLocation || 0)} ads.`, "chart-note"));

  sectionHeading("Job-title posting timeline", "Monthly counts describe the collected dataset. Zero means no dated ad was recorded in that month, not zero jobs in the market.");
  const monthly = charts.timelineByTitle || [];
  const coverage = charts.timelineCoverage || [];
  const options = coverage.map(row => row.label).filter(Boolean).sort((a, b) => a.localeCompare(b));
  const totals = new Map();
  monthly.forEach(row => totals.set(row.label, (totals.get(row.label) || 0) + row.count));
  const defaults = [...totals].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 5).map(row => row[0]);
  if (!timelineTitles) timelineTitles = defaults.length ? defaults : options.slice(0, 5);
  timelineTitles = timelineTitles.filter(name => options.includes(name));
  $("panel").append(multiPicker("Job titles to compare", "timeline-titles", options, timelineTitles, value => { timelineTitles = value; }, 8));
  if (timelineTitles.length) {
    const months = [...new Set((charts.timeline || []).map(row => row.label))].sort();
    const series = monthly.filter(row => timelineTitles.includes(row.label));
    const counts = new Map(series.map(row => [`${row.label}\u0000${row.month}`, Number(row.count)]));
    const timelineRows = timelineTitles.flatMap(label => months.map(month => ({ series: label, label: month, count: counts.get(`${label}\u0000${month}`) || 0 })));
    const statusByTitle = new Map(coverage.map(row => [row.label, row]));
    const dated = timelineTitles.reduce((sum, label) => sum + Number(statusByTitle.get(label)?.dated || 0), 0);
    const undated = timelineTitles.reduce((sum, label) => sum + Number(statusByTitle.get(label)?.undated || 0), 0);
    const byMonth = new Map();
    timelineRows.forEach(row => byMonth.set(row.label, (byMonth.get(row.label) || 0) + row.count));
    const peak = Math.max(0, ...byMonth.values());
    const peakMonths = [...byMonth].filter(([, count]) => count === peak).map(([month]) => month);
    const timelineInsight = timelineRows.length
      ? `The chosen titles appear in ${integer.format(dated)} dated ads. The highest recorded monthly count is ${integer.format(peak)}, in ${peakMonths.slice(0, 3).join(", ")}${peakMonths.length > 3 ? ` and ${peakMonths.length - 3} other months` : ""}.`
      : "No usable posting dates are available for the selected titles.";
    const topTitles = [...new Set(timelineTitles)].map(label => ({ label, count: totals.get(label) || 0 })).sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
    const timelineCard = chartCard("Job-title posting timeline", timelineRows, { type: "multi-line", total: dated, insight: timelineInsight, insightTitle: "Timeline Insight", topRows: topTitles, listTitle: "Dated ads by selected title", note: `${integer.format(dated)} dated ads for the chosen titles; ${integer.format(undated)} ads with missing or invalid posting dates are excluded. Play reveals the monthly points from the beginning; Pause stops playback.` });
    displayed.push(timelineCard);
    $("panel").append(timelineCard.card);
  } else {
    $("panel").append(html("p", "Choose at least one title with dated records to explore posting trends.", "chart-note"));
  }
}

function renderQualifications() {
  const { charts, summary } = result;
  sectionHeading("What qualifications are stated?", `Education is stated in ${integer.format(summary.withEducation)} of ${integer.format(summary.ads)} ads. Experience is identified in ${integer.format(summary.withExperience)} ads from source fields or advertisement text.`);
  const education = (charts.education || []).map(row => ({ label: row.education_level, count: Number(row.job_ads), order: Number(row.level_order) }));
  education.sort((a, b) => a.order - b.order);
  const missing = Number(summary.notStatedEducation || 0);
  const needsReview = Number(summary.educationNeedsReview || 0);
  const educationSummary = !education.length
    ? "No single education level could be classified from the stated requirements."
    : education.length === 1
      ? `Only one classifiable stated level appears in this selection: ${education[0].label} (${integer.format(education[0].count)} ads).`
      : (() => {
        const maximum = Math.max(...education.map(row => row.count));
        const leaders = education.filter(row => row.count === maximum).map(row => row.label);
        const classified = education.reduce((sum, row) => sum + row.count, 0);
        return leaders.length > 1
          ? `${integer.format(leaders.length)} displayed levels share the highest count (${integer.format(maximum)} ads each): ${leaders.join(", ")}. There are ${integer.format(classified)} ads with one recognized level.`
          : `${leaders[0]} has the highest classified count (${integer.format(maximum)} of ${integer.format(classified)} ads with one recognized level).`;
      })();
  const educationChart = chartCard("Stated education requirements by level", education, {
    single: education.length === 1, total: summary.ads, insight: educationSummary, insightTitle: "Education Insight",
    topRows: education.length > 1 ? topRows(education) : [], listTitle: "Classified levels",
    note: `Not stated: ${integer.format(missing)} of ${integer.format(summary.ads)} ads. ${integer.format(summary.withEducation)} ads state education, including ${integer.format(needsReview)} that could not be assigned one unambiguous level. Not stated does not mean education was not required.`,
  });
  displayed.push(educationChart);
  $("panel").append(educationChart.card);
  const experience = sorted(charts.experience || []).slice(0, Number($("limit").value));
  const durationSummary = !experience.length ? "No experience durations could be compared in this selection." : (() => {
    const maximum = experience[0].count;
    const ties = experience.filter(row => row.count === maximum).length;
    return ties > 1 ? `${integer.format(ties)} displayed durations share the highest count (${integer.format(maximum)} ads each).`
      : `${experience[0].label.charAt(0).toUpperCase()}${experience[0].label.slice(1)} is the most frequent duration shown (${integer.format(maximum)} of ${integer.format(summary.ads)} selected ads).`;
  })();
  const count = Number(summary.experienceExactCount || 0);
  const exactNote = count >= 2
    ? `Single-value numeric requirements: median ${Number(summary.experienceExactMedian).toLocaleString("en-PH", {maximumFractionDigits: 2})} years (observed range ${summary.experienceExactMin}–${summary.experienceExactMax}), from ${integer.format(count)} ads. Ranges and open-ended wording are excluded.`
    : count === 1 ? `One advertisement states exactly ${summary.experienceExactMedian} years; one observation is not summarized as a distribution. Ranges and open-ended wording remain separate.` : "";
  const experienceChart = chartCard("Experience requirements", experience, {
    total: summary.ads, insight: durationSummary, insightTitle: "Experience Insight", topRows: topRows(experience), listTitle: "Displayed durations",
    note: `No experience duration was identified in ${integer.format(summary.ads - summary.withExperience)} ads. Parsed from source fields and ad text; one ad can contribute to more than one duration, and ranges keep their stated bounds.${exactNote ? ` ${exactNote}` : ""}`,
  });
  displayed.push(experienceChart);
  $("panel").append(experienceChart.card);
}

function renderPsf() {
  const { charts, summary } = result;
  sectionHeading("How does observed demand relate to PSF-AAI?", "An advertisement counts once per competency. Public links are automated candidates for inspection and do not include researcher-only reviews.");
  const roles = charts.psfRoles || [];
  const roleOptions = [...new Set(roles.map(row => row.label))].sort((a, b) => a.localeCompare(b));
  if (!roleOptions.includes("All")) roleOptions.unshift("All");
  if (!roleOptions.includes(psfRoleFilter)) psfRoleFilter = "All";
  $("panel").append(selectControl("PSF-AAI reference role", roleOptions, psfRoleFilter, value => { psfRoleFilter = value; }, "psf-role"));
  let competencies = charts.psf || [];
  let denominator = summary.ads;
  if (psfRoleFilter !== "All") {
    competencies = (charts.psfHeatmap || []).filter(row => row.role === psfRoleFilter)
      .map(row => ({ label: row.competency, count: Number(row.count) }));
    denominator = Number(roles.find(row => row.label === psfRoleFilter)?.count || 0);
  }
  makeBar("PSF-AAI competencies linked to employer demand", competencies, {
    total: denominator, concept: "PSF-AAI competency", insightTitle: "Key Insight", listTitle: "Top Displayed Competencies",
    note: "Automated candidate references from competency terms, descriptions, and verified Range of Application evidence. Inspect source wording before treating a link as confirmed.",
  });
  makeBar("Related PSF-AAI reference roles", roles, {
    total: undefined, concept: "PSF-AAI reference role", insightTitle: "Key Insight", listTitle: "Top Displayed Roles",
    note: "Role links can overlap; one advertisement may be associated with multiple reference roles.",
  });
  roleDistribution(sorted(roles).slice(0, Number($("limit").value)));

  const cells = charts.psfHeatmap || [];
  const roleCounts = new Map(roles.map(row => [row.label, row.count]));
  const roleChoices = [...new Set(cells.map(row => row.role))].sort((a, b) => (roleCounts.get(b) || 0) - (roleCounts.get(a) || 0) || a.localeCompare(b));
  const competencyCounts = new Map((charts.psf || []).map(row => [row.label, row.count]));
  const competencyChoices = [...new Set(cells.map(row => row.competency))].sort((a, b) => (competencyCounts.get(b) || 0) - (competencyCounts.get(a) || 0) || a.localeCompare(b));
  psfHeatmapRoles ??= roleChoices.slice(0, 8);
  psfHeatmapCompetencies ??= competencyChoices.slice(0, Math.min(15, Number($("limit").value)));
  psfHeatmapRoles = psfHeatmapRoles.filter(name => roleChoices.includes(name));
  psfHeatmapCompetencies = psfHeatmapCompetencies.filter(name => competencyChoices.includes(name));
  $("panel").append(multiPicker("Reference roles in the heatmap", "psf-roles", roleChoices, psfHeatmapRoles, value => { psfHeatmapRoles = value; }, 8));
  $("panel").append(multiPicker("PSF-AAI competencies in the heatmap", "psf-competencies", competencyChoices, psfHeatmapCompetencies, value => { psfHeatmapCompetencies = value; }, 15));
  if (psfHeatmapRoles.length && psfHeatmapCompetencies.length) {
    const selectedCells = cells.filter(row => psfHeatmapRoles.includes(row.role) && psfHeatmapCompetencies.includes(row.competency));
    const matrixValues = matrixCells(selectedCells, "role", "competency", psfHeatmapRoles, psfHeatmapCompetencies, roleCounts, "count");
    makeHeatmap("PSF-AAI competencies across reference roles", psfHeatmapRoles, psfHeatmapCompetencies, matrixValues, {
      transpose: true, rowTitle: "reference role", columnTitle: "competency", listTitle: "Top Competency × Role",
      note: "Cells count distinct ads with automated ALIGNED or PARTIALLY ALIGNED candidate links. Color shows share of ads linked to each role. A single ad may support multiple competencies and roles.",
    });
  }
  if (charts.psfEvidence?.length) $("panel").append(referenceEvidence(charts.psfEvidence));
}

function renderAlignment() {
  const { charts, summary, alignmentRates } = result;
  sectionHeading("Automated alignment evidence", "Threshold-based candidates mirror the research alignment functions. They do not confirm equivalence or apply researcher review decisions.");
  const rates = alignmentRates || {};
  const rateMetric = (label, value, glyph) => metric(label, value == null ? "—" : `${Number(value).toFixed(1)}%`, glyph);
  const metrics = html("div", undefined, "metric-grid");
  metrics.append(rateMetric("Alignment rate", rates.alignment_rate, "chart"),
    rateMetric("Partially aligned rate", rates.partially_aligned_rate, "layer"),
    rateMetric("Unmapped rate", rates.unmapped_rate, "info"));
  $("panel").append(metrics);
  const rows = charts.alignment || [];
  const ordered = sorted(rows).slice(0, Number($("limit").value));
  const count = rows.reduce((sum, row) => sum + row.count, 0);
  const breakdown = rows.map(row => `${row.label}: ${integer.format(row.count)} (${count ? (row.count / count * 100).toFixed(1) : "0.0"}%)`).join(" · ");
  const highest = rankedRows(ordered)[0];
  const leaders = highest ? ordered.filter(row => row.count === highest.count) : [];
  let insight = "No alignment evidence groups are available for an insight.";
  if (ordered.length === 1) insight = `Only one status is displayed: ${leaders[0].label} (${integer.format(highest.count)} ${highest.count === 1 ? "evidence group" : "evidence groups"}).`;
  else if (ordered.length && leaders.length === ordered.length) insight = `All ${integer.format(leaders.length)} displayed statuses are tied at ${integer.format(highest.count)} evidence groups each.`;
  else if (highest) insight = `${leaders.map(row => row.label).join(", ")} ${leaders.length === 1 ? "has" : "share"} the highest displayed count: ${integer.format(highest.count)} evidence groups${leaders.length > 1 ? " each" : ""} (${count ? (highest.count / count * 100).toFixed(1) : "0.0"}%${leaders.length > 1 ? " each" : ""}).`;
  const chart = chartCard("Status of Phrase–Competency Evidence Groups", ordered, {
    total: undefined, insight, insightTitle: "Alignment Insight", topRows: topRows(ordered), listTitle: "Status breakdown",
    note: `${breakdown || "No recorded groups."} These percentages use phrase–competency evidence groups, not distinct advertisements. The heuristic thresholds are ≥0.80 aligned and ≥0.60 partially aligned; missing reference evidence is unclassified.`,
  });
  displayed.push(chart);
  $("panel").append(chart.card);
  $("panel").append(html("p", `${integer.format(summary.alignmentGroups)} phrase–competency evidence groups were evaluated. Automated statuses do not establish competency equivalence or model accuracy.`, "chart-note"));
}

function renderUnmapped() {
  const { charts, summary } = result;
  const unmapped = sorted(charts.unmapped || []).slice(0, Number($("limit").value));
  const recurring = sorted(charts.recurring || []).slice(0, Number($("limit").value));
  const metrics = html("div", undefined, "metric-grid");
  metrics.append(metric("Unmapped labels shown", unmapped.length, "layer"), metric("Recurring labels shown", recurring.length, "chart"));
  $("panel").append(metrics);
  $("panel").append(html("p", charts.unmapped?.length ? "Researcher review required. A missing PSF-AAI match does not establish a framework gap or an emerging skill." : "No unmapped labels were found in this selection.", "chart-note"));
  makeBar("Unmapped skill evidence", charts.unmapped || [], { total: summary.ads, concept: "unmapped skill", insightTitle: "Evidence Insight", listTitle: "Top Displayed Skills", note: "A missing framework match does not establish a framework gap." });
  makeBar("Recurring unmapped phrases for review", charts.recurring || [], { total: summary.ads, concept: "recurring unmapped skill", insightTitle: "Review Insight", listTitle: "Top Displayed Candidates", note: "Candidates appear in at least two distinct advertisements. Recurrence alone does not establish emergence." });
}

function section() {
  displayed.forEach(chart => chart.destroy());
  displayed = [];
  $("panel").replaceChildren();
  if (!result) return;
  if (activeView === "skills") renderSkills();
  else if (activeView === "roles") renderRoles();
  else if (activeView === "qualifications") renderQualifications();
  else if (activeView === "psf") renderPsf();
  else if (activeView === "alignment") renderAlignment();
  else if (activeView === "unmapped") renderUnmapped();
}

function safeLink(value, label = "Open source") {
  try {
    const url = new URL(value);
    if (url.protocol === "https:" || url.protocol === "http:") {
      const link = html("a", label);
      link.href = url.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      return link;
    }
  } catch {}
  return "";
}

function showResults() {
  $("empty").hidden = Boolean(result);
  $("result-content").hidden = !result;
  $("exports").hidden = !result;
  $("analysis-ready").hidden = !result;
  if (result) $("analysis-ready-copy").textContent = `${integer.format(result.summary.ads)} job ads analyzed. Open Explore results when you’re ready.`;
  $("clear").hidden = !result && !candidate;
  $("restore-actions").hidden = !savedFile || Boolean(candidate);
  if (!result) {
    $("evidence-table").replaceChildren();
    $("evidence").open = false;
    section();
    return;
  }
  const { summary, charts, filename, model, evidence } = result;
  const source = $("result-source");
  const file = document.createElement("div");
  file.className = "dataset-file";
  const filenameNode = document.createElement("strong");
  filenameNode.textContent = filename;
  const rowsNode = document.createElement("small");
  rowsNode.textContent = `${integer.format(summary.rows)} rows analyzed`;
  file.append(filenameNode, rowsNode);
  const facts = document.createElement("div");
  facts.className = "dataset-facts";
  for (const [label, value] of [["Classifier", model?.name || "Unavailable"], ["Model ID", model?.version || "—"], ["Dataset ID", result.datasetHash.slice(0, 16)]]) {
    const fact = document.createElement("span");
    fact.className = "dataset-fact";
    const title = document.createElement("span");
    title.textContent = label;
    const detail = document.createElement("strong");
    detail.textContent = value;
    fact.append(title, detail);
    facts.append(fact);
  }
  source.replaceChildren(file, facts);
  $("metrics").replaceChildren(
    metric("Job ads", summary.ads, "work"),
    metric("Distinct chart skills", summary.chartSkills ?? charts.skills.length, "chart"),
    metric("Distinct phrases withheld", summary.withheldPhrases, "info"),
    metric("PSF-AAI reference roles", summary.referenceRoles, "layer"),
  );
  $("evidence-note").textContent = `Showing ${integer.format(evidence.rows.length)} of ${integer.format(evidence.total)} analyzed ads. Download the cleaned CSV for the complete source rows.`;
  $("evidence-table").replaceChildren();
  if ($("evidence").open) showEvidence();
  section();
}

function showEvidence() {
  if (!result || $("evidence-table").firstChild) return;
  $("evidence-table").append(table(["CSV record", "Source ID", "Job title", "Employer", "Location", "Posting month", "Detected skills", "PSF-AAI candidates", "Description excerpt", "Source"], result.evidence.rows.map(row => [
    row.sourceRow, row.sourceId || row.jobId, row.title, row.company, row.location, row.postingMonth, row.skills.join(", "), row.psf.join(", "), row.descriptionExcerpt, safeLink(row.url) || row.source,
  ])));
}

function recover(type) {
  if (type === "inspect") {
    candidate = undefined;
    fileDisplay(savedFile, result?.filename);
    showResults();
    setFlowStep(result ? 3 : 1);
    navigate(result ? "results" : "upload");
  } else if (type === "analyze") {
    $("confirm").hidden = false;
    $("analysis-ready").hidden = !result;
    setFlowStep(1);
    refreshMappingStatuses();
    navigate("upload");
  } else navigate("results");
}

function finishAnalysis(analysis, file) {
  result = analysis;
  savedFile = file;
  candidate = undefined;
  titleFilter = "";
  timelineData = undefined;
  titleViewMode = "common";
  explorationFamily = "All";
  explorationTitle = "All";
  selectedRegion = "All";
  selectedCity = "All";
  timelineTitles = undefined;
  familySelection = undefined;
  psfRoleFilter = "All";
  psfHeatmapRoles = undefined;
  psfHeatmapCompetencies = undefined;
  openPickers.clear();
  pickerQueries.clear();
  setFlowStep(3);
  fileDisplay(file, result.filename);
  showResults();
  busy();
  navigate("results");
  const completed = result;
  cacheWrite = cacheWrite.then(async () => {
    try { await remember(completed, file); }
    catch {
      try { await remember(completed, null); }
      catch { await forget().catch(() => {}); }
      if (result === completed) notify("Analysis finished. Browser storage could not retain the full CSV after refresh.");
    }
  });
  notify(`Analyzed ${integer.format(result.summary.ads)} job ads with the research classifier.`);
}

async function analyzeOnServer(file, mapping) {
  if (engineHealth?.classifierAvailable !== true) {
    notify("The research classifier is unavailable on this analysis server.", true);
    recover("analyze");
    return;
  }
  const controller = new AbortController();
  requestController = controller;
  job = "analyze";
  $("processing-title").textContent = "Analyzing job advertisements";
  $("processing-copy").textContent = "Applying the shared research classifier and analysis pipeline.";
  $("progress").removeAttribute("value");
  $("progress-value").textContent = "—";
  $("progress-text").textContent = "Sending the CSV securely to the analysis server…";
  busy("Research engine is analyzing job advertisements…");
  notify("");
  navigate("processing");
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      body: file,
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
      headers: {
        "Content-Type": "text/csv",
        "X-Filename": encodeURIComponent(file.name),
        "X-Column-Mapping": encodeURIComponent(JSON.stringify(mapping)),
      },
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "The research engine could not analyze this CSV.");
    if (requestController !== controller) return;
    stop();
    finishAnalysis(payload.result, file);
  } catch (error) {
    if (requestController !== controller) return;
    stop();
    recover("analyze");
    notify(error.name === "AbortError" ? "Processing cancelled." : error.message || "The research engine could not complete this file.", true);
  }
}

function run(type, file, extras = {}) {
  if (worker || requestController) return;
  job = type;
  if (type === "analyze") {
    analyzeOnServer(file, extras.mapping || {});
    return;
  }
  const stages = {
    inspect: ["Checking your file", "Reading CSV headers and sample rows."],
    export: ["Preparing your download", "Building the cleaned CSV from your dataset."],
  };
  const [title, copy] = stages[type];
  $("processing-title").textContent = title;
  $("processing-copy").textContent = copy;
  $("progress").value = 0;
  $("progress-value").textContent = "0%";
  busy(type === "inspect" ? "Reading CSV columns…" : "Preparing cleaned CSV…");
  notify("");
  try {
    worker = new Worker(new URL("./analysis-worker.js", import.meta.url), { type: "module" });
    navigate("processing");
    worker.onmessage = ({ data }) => {
      if (data.type === "progress") {
        $("progress").value = data.percent;
        $("progress-value").textContent = `${data.percent}%`;
        $("progress-text").textContent = data.message;
        return;
      }
      stop();
      if (data.type === "inspection") showInspection(data);
      else if (data.type === "error") {
        recover(type);
        notify(data.message, true);
      } else if (data.type === "exported") {
        if (data.blob) download(data.blob, data.filename);
        navigate("results");
        notify(`Cleaned CSV prepared with ${integer.format(data.rows)} job ads.`);
      }
    };
    worker.onerror = () => {
      stop();
      recover(type);
      notify("The browser could not complete the task. Try a smaller CSV or reload this page.", true);
    };
    worker.postMessage({ type, file, ...extras });
  } catch {
    stop();
    recover(type);
    notify("The file reader could not start. Reload this page and try again.", true);
  }
}

function choose(file) {
  if (!file || worker || requestController) return;
  if (!/\.csv$/i.test(file.name) || file.size < 1 || file.size > uploadLimit) {
    notify(`Choose a nonempty .csv file up to ${Math.floor(uploadLimit / MB)} MB.`, true);
    return;
  }
  candidate = file;
  setFlowStep(1);
  $("analysis-ready").hidden = true;
  fileDisplay(file, file.name);
  $("confirm").hidden = true;
  $("restore-actions").hidden = true;
  run("inspect", file);
}

$("file").addEventListener("change", event => { choose(event.target.files[0]); event.target.value = ""; });
const drop = $("dropzone");
drop.addEventListener("dragover", event => { event.preventDefault(); if (!worker && !requestController) drop.classList.add("dragover"); });
drop.addEventListener("dragleave", () => drop.classList.remove("dragover"));
drop.addEventListener("drop", event => {
  event.preventDefault();
  drop.classList.remove("dragover");
  if (event.dataTransfer.files.length > 1) notify("Choose one CSV file at a time.", true);
  else choose(event.dataTransfer.files[0]);
});
$("confirm").addEventListener("submit", event => {
  event.preventDefault();
  if (!candidate || worker || requestController) return;
  const mapping = Object.fromEntries(new FormData(event.target));
  if (!mapping.job_title || !required.slice(1).some(([key]) => mapping[key])) {
    notify("Match Job title and at least one field containing job description, skills, or qualifications.", true);
    return;
  }
  if (new Set(Object.values(mapping).filter(Boolean)).size !== Object.values(mapping).filter(Boolean).length) {
    notify("Use each source column once so evidence stays traceable.", true);
    return;
  }
  setFlowStep(2);
  $("confirm").hidden = true;
  run("analyze", candidate, { mapping });
});
$("confirm").addEventListener("change", refreshMappingStatuses);
$("cancel").addEventListener("click", () => {
  const cancelled = job;
  stop();
  recover(cancelled);
  notify("Processing cancelled.");
});
$("clear").addEventListener("click", async () => {
  if (worker || requestController) return;
  result = savedFile = candidate = undefined;
  setFlowStep(1);
  timelineData = undefined;
  $("confirm").hidden = true;
  fileDisplay();
  showResults();
  await cacheWrite;
  try { await forget(); notify("Session cleared from this browser."); }
  catch { notify("The view was cleared. Browser storage could not confirm removal. Clear this site’s data in your browser settings.", true); }
});
$("view-results").addEventListener("click", () => { location.hash = "#results"; });
$("upload-another").addEventListener("click", () => { candidate = undefined; $("analysis-ready").hidden = true; $("confirm").hidden = true; setFlowStep(1); navigate("upload"); });
$("empty-upload").addEventListener("click", () => { setFlowStep(1); navigate("upload"); });
$("analyze-again").addEventListener("click", () => choose(savedFile));
$("cleaned").addEventListener("click", async () => {
  if (!savedFile || worker || requestController) return;
  let handle;
  if (savedFile.size > 32 * MB) {
    if (!window.showSaveFilePicker) {
      notify("This browser cannot save a large cleaned file directly. Use desktop Chrome or Edge, or download the results CSV.", true);
      return;
    }
    try { handle = await window.showSaveFilePicker({ suggestedName: "cleaned-job-ads.csv", types: [{ description: "CSV", accept: { "text/csv": [".csv"] } }] }); }
    catch (error) { if (error.name !== "AbortError") notify("Could not open the file save dialog.", true); return; }
  }
  if (!savedFile || !result) return;
  run("export", savedFile, { mapping: result.mapping, handle });
});
$("report").addEventListener("click", () => {
  if (!result) return;
  const rows = Object.entries(result.charts).flatMap(([chart, entries]) => (entries || []).map(row => {
    const label = row.label || row.skill_label || row.psf_competency || row.job_family || row.role || row.month || "";
    const value = row.count ?? row.job_ads ?? row.family_ads ?? "";
    return [chart, label, value, JSON.stringify(row)];
  }));
  rows.push(...Object.entries(result.summary).map(([field, value]) => ["coverage", field, value]));
  rows.push(["dataset", result.filename, ""], ["classifier", result.model?.version || "No released classifier", ""]);
  rows.push(["reference", result.reference.sourceUrl, ""], ["reference hash", result.reference.sourceHash, ""]);
  download(csv([["Section", "Label", "Job ads or count", "Details"], ...rows]), "job-market-results.csv", CSV);
});
$("evidence").addEventListener("toggle", () => { if ($("evidence").open) showEvidence(); });
$("order").addEventListener("change", section);
$("limit").addEventListener("change", section);

function activateTab(tab) {
  for (const other of tabs) {
    other.setAttribute("aria-selected", other === tab);
    other.tabIndex = other === tab ? 0 : -1;
  }
  activeView = tab.dataset.view;
  $("panel").setAttribute("aria-labelledby", tab.id);
  section();
}
tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => { if (activeView !== tab.dataset.view) activateTab(tab); });
  tab.addEventListener("keydown", event => {
    const next = { ArrowLeft: (index + tabs.length - 1) % tabs.length, ArrowRight: (index + 1) % tabs.length, Home: 0, End: tabs.length - 1 }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    activateTab(tabs[next]);
    tabs[next].focus();
  });
});

window.addEventListener("hashchange", () => showPage());
showPage();
connectEngine();

try {
  const stored = await restore();
  if (stored && stored.result?.schemaVersion === 4 && !candidate && !result) {
    result = stored.result;
    savedFile = stored.file;
    setFlowStep(3);
    fileDisplay(savedFile, result.filename, "Results restored · Choose the original CSV to analyze again");
    showResults();
    busy();
  } else if (stored?.file && !result) {
    savedFile = stored.file;
    fileDisplay(savedFile, stored.result?.filename || savedFile.name, "Previous results use an older analysis. Reanalyze this file with the research engine.");
    $("restore-actions").hidden = false;
    notify("The saved result used the earlier browser analyzer. Reanalyze the original CSV to get the shared research-engine results.");
  }
} catch {
  if (!worker && !requestController) notify("Browser storage is unavailable. You can still analyze and download results while this tab is open.");
}
