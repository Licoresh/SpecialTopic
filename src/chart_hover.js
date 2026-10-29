(() => {
  if (window.__fowStickyHover) return;
  window.__fowStickyHover = true;

  function bind(plot) {
    if (typeof plot.on !== "function") return;
    plot.dataset.fowHoverBound = "true";
    let overlay;
    const clear = () => { overlay?.remove(); overlay = undefined; };

    plot.on("plotly_hover", () => requestAnimationFrame(() => {
      if (!plot.isConnected || !plot.matches(":hover")) return;
      const layer = plot.querySelector(".hoverlayer:not([data-fow-copy])");
      if (!layer?.querySelector(".hovertext")) return;
      const originalSvg = layer.ownerSVGElement;
      const copy = originalSvg.cloneNode(false);
      copy.removeAttribute("id");
      copy.setAttribute("aria-hidden", "true");
      copy.dataset.fowStickyTooltip = "true";
      Object.assign(copy.style, {
        position: "absolute", top: "0", left: "0", background: "transparent",
        pointerEvents: "none", overflow: "visible", zIndex: "5"
      });
      const contents = layer.cloneNode(true);
      contents.dataset.fowCopy = "true";
      contents.querySelectorAll(".hovertext").forEach(node => {
        node.style.pointerEvents = "all";
      });
      copy.append(contents);
      clear();
      originalSvg.parentElement.append(copy);
      overlay = copy;
    }));
    plot.on("plotly_afterplot", clear);
    plot.addEventListener("mouseleave", clear);
    plot.addEventListener("keydown", event => { if (event.key === "Escape") clear(); });
  }

  let pending = false;
  const scan = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      document.querySelectorAll('[data-testid="stPlotlyChart"] .js-plotly-plot:not([data-fow-hover-bound])').forEach(bind);
    });
  };
  new MutationObserver(scan).observe(document.body, {childList: true, subtree: true});
  scan();
})();
