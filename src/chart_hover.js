(() => {
  const version = "2.0.98";
  const versionKey = "__fowStableHover_2_0_98";
  const boundKey = "fowStableHoverV2098Bound";
  if (window[versionKey]) return;
  window.__fowChartHoverCleanup?.();
  window[versionKey] = true;

  const blockedEvents = ["pointermove", "pointerover", "pointerout", "pointerdown", "pointerup",
    "mousemove", "mouseover", "mouseout", "mousedown", "mouseup", "click"];
  const stop = event => event.stopImmediatePropagation();
  const bindings = [];
  let observer;

  function bind(plot) {
    if (plot.dataset[boundKey] === "true" || typeof plot.on !== "function") return;
    plot.dataset[boundKey] = "true";
    let retained;
    const clear = () => { retained?.remove(); retained = undefined; };
    const onKey = event => { if (event.key === "Escape") clear(); };
    const show = () => requestAnimationFrame(() => {
      if (!plot.isConnected || !plot.matches(":hover")) return;
      const source = plot.querySelector(`.hoverlayer:not([data-fow-retained-hover])`);
      if (!source?.querySelector(".hovertext") || !source.parentNode) return;
      const copy = source.cloneNode(true);
      copy.removeAttribute("id");
      copy.dataset.fowRetainedHover = version;
      copy.style.pointerEvents = "all";
      Array.from(copy.children).forEach(child => {
        if (!child.classList.contains("hovertext")) child.remove();
      });
      copy.querySelectorAll(".hovertext").forEach(label => {
        label.style.pointerEvents = "all";
        blockedEvents.forEach(type => label.addEventListener(type, stop, true));
      });
      clear();
      source.parentNode.insertBefore(copy, source.nextSibling);
      retained = copy;
    });
    plot.on("plotly_hover", show);
    plot.addEventListener("mouseleave", clear);
    plot.addEventListener("keydown", onKey);
    bindings.push({plot, show, clear, onKey});
  }

  let pending = false;
  const scan = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      document.querySelectorAll(
        '[data-testid="stPlotlyChart"] svg[data-fow-sticky-tooltip="true"]'
      ).forEach(overlay => overlay.remove());
      document.querySelectorAll('[data-testid="stPlotlyChart"] .js-plotly-plot').forEach(bind);
    });
  };

  observer = new MutationObserver(scan);
  observer.observe(document.body, {childList: true, subtree: true});
  window.__fowChartHoverCleanup = () => {
    observer.disconnect();
    bindings.forEach(({plot, show, clear, onKey}) => {
      clear();
      plot.off?.("plotly_hover", show);
      plot.removeEventListener("mouseleave", clear);
      plot.removeEventListener("keydown", onKey);
      delete plot.dataset[boundKey];
    });
    delete window[versionKey];
  };
  scan();
})();
