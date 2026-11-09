function waitForResultCharts(expectedPlots) {
  const overlay = document.querySelector(".st-key-public-processing-overlay");
  const sections = document.querySelector(".st-key-public-results-tabs");
  if (!overlay || !sections) return;

  const meter = overlay.querySelector("progress");
  const percent = overlay.querySelector(".public-processing-percent");
  const status = overlay.querySelector(".public-processing-status");
  const continueButton = overlay.querySelector(".public-processing-continue");
  const started = performance.now();
  let readyLastCheck = false;

  function dismiss() {
    overlay.hidden = true;
    sections.inert = false;
  }

  function plotReady(container) {
    const plot = container.querySelector(".js-plotly-plot");
    return plot?._fullLayout?._size?.w > 0 && !plot._promises?.length &&
      plot.querySelector("svg.main-svg");
  }

  function timelineReady() {
    const table = sections.querySelector(".st-key-public-posting-timeline");
    return !table || Array.from(table.querySelectorAll("*")).some(
      node => node.shadowRoot?.querySelector("tbody svg") || node.querySelector("tbody svg")
    );
  }

  function check() {
    if (!overlay.isConnected || overlay.hidden) return;
    const charts = [...sections.querySelectorAll('[data-testid="stPlotlyChart"]')];
    const ready = charts.length === expectedPlots && charts.every(plotReady) && timelineReady();
    if (ready && readyLastCheck) {
      meter.value = 100;
      percent.textContent = "100%";
      status.textContent = "Your results are ready.";
      continueButton.hidden = true;
      window.setTimeout(dismiss, 450);
      return;
    }
    if (performance.now() - started > 30_000 && continueButton.hidden) {
      status.textContent = "Some charts are taking longer to draw.";
      continueButton.hidden = false;
    }
    readyLastCheck = ready;
    window.setTimeout(check, 100);
  }

  sections.inert = true;
  continueButton.addEventListener("click", dismiss);
  check();
}
