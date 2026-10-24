import { api } from "../api.js";
import { esc, icon } from "../ui.js";

const PREVIEW_ICONS = ["calendar", "trending", "target"];
const PREVIEW_TINTS = ["tint-violet", "tint-cyan", "tint-green"];

export async function render(container) {
  const info = await api.insights();
  container.innerHTML = `
    <div class="card insights-hero">
      <div class="big-icon">${icon("sparkles")}</div>
      <span class="chip soon">Coming soon</span>
      <h2>Weekly insights, powered by Claude</h2>
      <p>${esc(info.message)} Each week you'll get a short, personal read on your focus:
         what went well, where your time went, and one thing to try next.</p>
    </div>
    <div class="grid cards-grid section">
      ${info.planned.map((text, i) => `
        <div class="card hoverable preview-card ${PREVIEW_TINTS[i % 3]}">
          <span class="stat-icon">${icon(PREVIEW_ICONS[i % 3])}</span>
          <p>${esc(text)}</p>
          <div class="skeleton-lines"><span></span><span></span><span></span></div>
        </div>`).join("")}
    </div>`;
}
