// Keep Plotly's formatting, but place its hover details in one HTML tooltip.
(() => {
  const version = "__FOW_APP_VERSION__";
  if (window.__fowHtmlHoverVersion === version) return;
  const chartSelector = '[data-testid="stPlotlyChart"]';
  const plotSelector = `${chartSelector} .js-plotly-plot`;
  const plots = [...document.querySelectorAll(plotSelector)];
  // The retired cleanup used off(); Plotly exposes removeListener() instead.
  const bridges = plots.filter(plot => !plot.off && typeof plot.removeListener === "function");
  bridges.forEach(plot => { plot.off = plot.removeListener; });
  try {
    window.__fowChartHoverCleanup?.();
  } finally {
    bridges.forEach(plot => { delete plot.off; });
    delete window.__fowChartHoverCleanup;
  }
  // A scan queued by the retired handler must not bind itself again.
  plots.forEach(plot => { plot.dataset.fowStableHoverV2098Bound = "true"; });
  document.querySelectorAll(
    '[data-testid="stPlotlyChart"] [data-fow-retained-hover], ' +
    '[data-testid="stPlotlyChart"] svg[data-fow-sticky-tooltip="true"]'
  ).forEach(overlay => overlay.remove());

  const tooltip = document.createElement("div");
  tooltip.className = "fow-chart-tooltip";
  tooltip.setAttribute("role", "tooltip");
  tooltip.hidden = true;
  document.body.appendChild(tooltip);
  const bindings = new Map();
  let active, content = "", width = 0, height = 0;
  const hide = () => { active = undefined; tooltip.hidden = true; };
  const position = event => {
    const x = Math.max(12, Math.min(event.clientX + 14, window.innerWidth - width - 12));
    const y = Math.max(12, event.clientY + 14 + height <= window.innerHeight - 12
      ? event.clientY + 14 : event.clientY - height - 14);
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
  };
  const textLines = text => {
    if (!text) return [];
    const lines = [...text.querySelectorAll("tspan.line")];
    return (lines.length ? lines.map(line => line.textContent) : [text.textContent])
      .map(line => line.trim()).filter(Boolean);
  };
  function bind(plot) {
    const previous = bindings.get(plot);
    if (previous && previous.on === plot.on) return;
    if (previous) unbind(plot, previous);
    if (typeof plot.on !== "function" || typeof plot.removeListener !== "function") return;
    plot.dataset.fowStableHoverV2098Bound = "true";
    const leave = () => { if (active === plot) hide(); };
    const move = event => { if (active === plot) position(event); };
    const hover = data => {
      const event = data?.event?.touches?.[0] || data?.event;
      const groups = plot.querySelectorAll('.hoverlayer:not([data-fow-retained-hover]) g.hovertext');
      const lines = [...groups].flatMap(group => [
        ...textLines(group.querySelector("text.nums")), ...textLines(group.querySelector("text.name"))
      ]);
      if (!lines.length || !Number.isFinite(event?.clientX) || !Number.isFinite(event?.clientY)) {
        delete plot.dataset.fowHtmlHover;
        hide();
        return;
      }
      const next = lines.join("\n");
      const changed = next !== content;
      if (changed) {
        tooltip.replaceChildren(...lines.map(line => {
          const row = document.createElement("div");
          row.textContent = line;
          return row;
        }));
        content = next;
      }
      tooltip.hidden = false;
      if (active !== plot || changed) {
        const bounds = tooltip.getBoundingClientRect();
        width = bounds.width;
        height = bounds.height;
      }
      active = plot;
      plot.dataset.fowHtmlHover = "true";
      position(event);
    };
    plot.on("plotly_hover", hover);
    plot.on("plotly_unhover", leave);
    plot.addEventListener("pointermove", move, {passive: true});
    plot.addEventListener("mouseleave", leave);
    // Plotly.purge deletes its public event methods before the DOM is removed.
    bindings.set(plot, {hover, leave, move, on: plot.on, removeListener: plot.removeListener.bind(plot)});
  }
  function unbind(plot, handlers) {
    handlers.removeListener("plotly_hover", handlers.hover);
    handlers.removeListener("plotly_unhover", handlers.leave);
    plot.removeEventListener("pointermove", handlers.move);
    plot.removeEventListener("mouseleave", handlers.leave);
    delete plot.dataset.fowHtmlHover;
    if (active === plot) hide();
    bindings.delete(plot);
  }
  plots.forEach(bind);
  // Discover new chart roots; SVG hover mutations never trigger chart scans.
  const svgNamespace = "http://www.w3.org/2000/svg";
  const observer = new MutationObserver(records => {
    const candidates = new Set();
    let removed = false;
    for (const record of records) {
      if (record.target.namespaceURI === svgNamespace || tooltip.contains(record.target)) continue;
      const chart = record.target.closest?.(chartSelector);
      if (chart) chart.querySelectorAll(".js-plotly-plot").forEach(plot => candidates.add(plot));
      for (const node of record.addedNodes) {
        if (node.nodeType !== 1 || node.namespaceURI === svgNamespace) continue;
        if (node.matches(plotSelector)) candidates.add(node);
        else node.querySelectorAll(plotSelector).forEach(plot => candidates.add(plot));
      }
      removed ||= [...record.removedNodes].some(node => node.nodeType === 1 && node.namespaceURI !== svgNamespace);
    }
    candidates.forEach(bind);
    if (removed) for (const [plot, handlers] of bindings) if (!plot.isConnected) unbind(plot, handlers);
  });
  observer.observe(document.body, {childList: true, subtree: true});
  const escape = event => { if (event.key === "Escape") hide(); };
  window.addEventListener("scroll", hide, {capture: true, passive: true});
  window.addEventListener("resize", hide);
  document.addEventListener("keydown", escape);
  window.__fowHtmlHoverVersion = version;
  window.__fowChartHoverCleanup = () => {
    observer.disconnect();
    for (const [plot, handlers] of bindings) unbind(plot, handlers);
    window.removeEventListener("scroll", hide, true);
    window.removeEventListener("resize", hide);
    document.removeEventListener("keydown", escape);
    tooltip.remove();
    delete window.__fowHtmlHoverVersion;
    delete window.__fowChartHoverCleanup;
  };
})();
