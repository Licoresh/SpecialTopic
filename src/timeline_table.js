export function rowsAt(data, index) {
  return data.series.map(series => ({
    title: series.title,
    count: series.counts === null ? null : series.counts[index],
    total: series.counts === null ? null : series.counts.slice(0, index + 1).reduce((a, b) => a + b, 0),
    trend: series.counts === null ? null : series.counts.slice(0, index + 1)
  }));
}

export function createPlayback(length, render, schedule = setInterval, cancel = clearInterval) {
  let index = length - 1, timer;
  const pause = () => { cancel(timer); timer = undefined; render(index, false); };
  return {
    pause,
    play() {
      pause();
      if (length < 2) return;
      if (index === length - 1) index = 0;
      render(index, true);
      timer = schedule(() => { index++; render(index, true); if (index === length - 1) pause(); }, 650);
    },
    seek(value) { pause(); index = Math.min(length - 1, Math.max(0, value)); render(index, false); },
    dispose() { cancel(timer); timer = undefined; }
  };
}

export default function ({data, parentElement}) {
  const root = parentElement;
  const play = root.querySelector("#play"), pause = root.querySelector("#pause");
  const slider = root.querySelector("#position"), month = root.querySelector("#month");
  const period = root.querySelector("#period"), body = root.querySelector("tbody");
  let index = data.months.length - 1;
  slider.max = String(index);
  const maximum = Math.max(1, ...data.series.flatMap(series => series.counts || []));
  const cells = data.series.map(series => {
    const row = document.createElement("tr");
    const values = Array.from({length: 4}, () => row.appendChild(document.createElement("td")));
    values[0].textContent = series.title;
    if (series.counts === null) values[3].textContent = "No usable posting dates";
    body.appendChild(row);
    return values;
  });
  function draw(position = index, playing = false) {
    index = position;
    play.disabled = playing || data.months.length < 2;
    pause.disabled = !playing;
    slider.value = String(index);
    slider.setAttribute("aria-valuetext", data.months[index]);
    month.textContent = data.months[index];
    period.textContent = `Monthly counts from ${data.months[0]} through ${data.months[index]}.`;
    rowsAt(data, index).forEach((row, i) => {
      cells[i][1].textContent = row.count === null ? "Not available" : row.count;
      cells[i][2].textContent = row.total === null ? "Not available" : row.total;
      if (row.trend === null) return;
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 180 38");
      svg.setAttribute("role", "img");
      svg.setAttribute("aria-label", `${row.title}: monthly counts ${row.trend.join(", ")}`);
      const line = document.createElementNS(svg.namespaceURI, "polyline");
      line.setAttribute("points", row.trend.map((value, n) => `${4 + n * 172 / Math.max(1, data.months.length - 1)},${34 - value / maximum * 30}`).join(" "));
      line.setAttribute("fill", "none"); line.setAttribute("stroke", "currentColor"); line.setAttribute("stroke-width", "2");
      svg.appendChild(line);
      const dot = document.createElementNS(svg.namespaceURI, "circle");
      dot.setAttribute("cx", String(4 + index * 172 / Math.max(1, data.months.length - 1)));
      dot.setAttribute("cy", String(34 - row.count / maximum * 30));
      dot.setAttribute("r", "2.5"); dot.setAttribute("fill", "currentColor"); svg.appendChild(dot);
      cells[i][3].replaceChildren(svg);
    });
  }
  const playback = createPlayback(data.months.length, draw);
  play.onclick = playback.play;
  pause.onclick = playback.pause;
  slider.oninput = () => playback.seek(Number(slider.value));
  const visibility = () => { if (document.hidden) playback.pause(); };
  document.addEventListener("visibilitychange", visibility);
  draw();
  return () => { playback.dispose(); document.removeEventListener("visibilitychange", visibility); body.replaceChildren(); };
}
