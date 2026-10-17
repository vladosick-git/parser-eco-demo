"use strict";

const PAGE = 40;
const FILES = ["news", "waste", "runs", "sources"];
const state = { tab: "news", shown: PAGE, data: null };
const $ = (id) => document.getElementById(id);

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");

function fmtDate(iso) {
  if (!iso) return "без даты";
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  if (isNaN(d)) return iso;
  const opts = { day: "numeric", month: "long", year: "numeric" };
  if (iso.length > 10) Object.assign(opts, { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleString("ru-RU", opts);
}
const fmtShort = (iso) => new Date(iso).toLocaleString("ru-RU",
  { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
const fmtMoney =(v, cur) => v == null ? null :
  new Intl.NumberFormat("ru-RU", { style: "currency", currency: cur || "RUB", maximumFractionDigits: 2 }).format(v);
const roman = (n) => ["", "I", "II", "III", "IV", "V"][n] || n;

// --- загрузка: JSON по http(s), а при открытии файла с диска запасной data/bundle.js ---
async function fetchJson(name) {
  for (const base of ["data/", "../data/"]) {
    try {
      const r = await fetch(base + name + ".json", { cache: "no-store" });
      if (r.ok) return await r.json();
    } catch (e) { /* пробуем следующий путь */ }
  }
  return null;
}

function loadBundle() {
  return new Promise((resolve) => {
    const tryPath = (paths) => {
      if (!paths.length) return resolve(null);
      const s = document.createElement("script");
      s.src = paths[0];
      s.onload = () => resolve(window.ECO_DATA || null);
      s.onerror = () => { s.remove(); tryPath(paths.slice(1)); };
      document.head.appendChild(s);
    };
    tryPath(["data/bundle.js", "../data/bundle.js"]);
  });
}

async function load() {
  const parts = await Promise.all(FILES.map(fetchJson));
  if (parts.every((p) => p !== null)) return Object.fromEntries(FILES.map((f, i) => [f, parts[i]]));
  return loadBundle();
}

// --- фильтры ---
const FILTERS = ["q", "category", "offer", "region", "source", "from", "to"];

function fillSelect(id, label, values) {
  const el = $(id);
  const current = el.value;
  el.innerHTML = `<option value="">${esc(label)}</option>` +
    values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("");
  if (values.includes(current)) el.value = current;
}

const uniq = (arr) => [...new Set(arr.filter(Boolean))].sort((a, b) => a.localeCompare(b, "ru"));

function setupFilters() {
  const items = state.data[state.tab] || [];
  const isList = state.tab === "news" || state.tab === "waste";
  $("filters").hidden = !isList;
  if (!isList) return;
  fillSelect("category", "Все категории", uniq(items.map((i) => i.category)));
  fillSelect("source", "Все источники", uniq(items.map((i) => i.source_name)));
  fillSelect("region", "Все регионы", uniq(items.map((i) => i.region)));
  fillSelect("offer", "Любой тип", uniq(items.map((i) => i.offer_type)));
  $("region").hidden = state.tab !== "waste";
  $("offer").hidden = state.tab !== "waste";
}

function filtered() {
  const f = Object.fromEntries(FILTERS.map((k) => [k, $(k).value.trim()]));
  const q = f.q.toLowerCase();
  return (state.data[state.tab] || []).filter((i) => {
    const day = (i.published || "").slice(0, 10);
    if (f.category && i.category !== f.category) return false;
    if (f.source && i.source_name !== f.source) return false;
    if (state.tab === "waste" && f.region && i.region !== f.region) return false;
    if (state.tab === "waste" && f.offer && i.offer_type !== f.offer) return false;
    if (f.from && (!day || day < f.from)) return false;
    if (f.to && (!day || day > f.to)) return false;
    if (q) {
      const hay = [i.title, i.summary, i.organization, i.region, i.source_name].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

// --- отрисовка ---
function newsCard(i) {
  return `<article class="card">
    <div class="meta"><span>${esc(fmtDate(i.published))}</span><span>${esc(i.source_name)}</span>
      <span class="chip">${esc(i.category)}</span></div>
    <h3><a href="${esc(safeUrl(i.url))}" target="_blank" rel="noopener">${esc(i.title)}</a></h3>
    ${i.summary ? `<p>${esc(i.summary)}</p>` : ""}
  </article>`;
}

function wasteCard(i) {
  const offerClass = { "куплю": "", "продам": "chip--warn", "вывоз": "", "утилизация": "chip--bad" }[i.offer_type] || "";
  const facts = [
    ["Цена", fmtMoney(i.price, i.currency), "price"],
    ["Объём", i.volume != null ? `${i.volume} ${i.volume_unit}` : null],
    ["Регион", i.region],
    ["Организация", i.organization],
    ["Класс опасности", i.hazard_classes && i.hazard_classes.length ? i.hazard_classes.map(roman).join(", ") : null],
    ["ФККО", i.fkko],
  ].filter(([, v]) => v);
  return `<article class="card">
    <div class="meta"><span>${esc(fmtDate(i.published))}</span><span>${esc(i.source_name)}</span>
      ${i.offer_type ? `<span class="chip ${offerClass}">${esc(i.offer_type)}</span>` : ""}
      <span class="chip">${esc(i.category)}</span></div>
    <h3><a href="${esc(safeUrl(i.url))}" target="_blank" rel="noopener">${esc(i.title)}</a></h3>
    ${facts.length ? `<div class="facts">${facts.map(([k, v, cls]) =>
      `<div><span>${esc(k)}:</span> <b class="${cls || ""}">${esc(v)}</b></div>`).join("")}</div>` : ""}
  </article>`;
}

const STATUS = {
  ok: ["ок", ""], not_modified: ["без изменений", ""], partial: ["частично", "chip--warn"],
  failed: ["сбой", "chip--bad"], error: ["ошибка", "chip--bad"],
};
const statusChip = (s) => { const [t, c] = STATUS[s] || [s, ""]; return `<span class="chip ${c}">${esc(t)}</span>`; };

function renderRuns() {
  const runs = state.data.runs || [];
  if (!runs.length) return `<p class="empty">Запусков ещё не было.</p>`;
  return `<div class="table-wrap"><table>
    <thead><tr><th>Запуск</th><th>Статус</th><th class="num">Получено</th><th class="num">Новых</th>
      <th class="num">Дублей</th><th class="num">Ошибок</th><th class="num">Время, с</th></tr></thead>
    <tbody>${runs.map((r) => `<tr>
      <td><details><summary class="nowrap">${esc(fmtShort(r.started_at))}</summary>
        <table>${r.sources.map((s) => `<tr><td>${esc(s.source_name)}</td><td>${statusChip(s.status)}</td>
          <td class="num">${s.fetched}</td><td class="num">+${s.new}</td><td class="num">${s.duplicates} дубл.</td>
          <td class="num">${s.duration_s} с</td></tr>
          ${s.error ? `<tr><td colspan="6" class="err">${esc(s.error)}</td></tr>` : ""}`).join("")}</table>
      </details></td>
      <td>${statusChip(r.status)}</td><td class="num">${r.totals.fetched}</td><td class="num">${r.totals.new}</td>
      <td class="num">${r.totals.duplicates}</td><td class="num">${r.totals.errors}</td><td class="num">${r.duration_s}</td>
    </tr>`).join("")}</tbody></table></div>`;
}

function renderSources() {
  const src = state.data.sources;
  if (!src) return `<p class="empty">Таблица источников не найдена.</p>`;
  const main = ["#", "Источник", "Решение", "Причина"];
  const card = (row, columns) => {
    const v = row["Решение"] || "";
    const cls = v.startsWith("используем с") ? "chip--warn" : v === "используем" ? "" : "chip--bad";
    const rest = columns.filter((c) => !main.includes(c) && row[c] && row[c] !== "-");
    return `<article class="card">
      <div class="meta"><span>${esc(row["#"])}</span><span class="chip ${cls}">${esc(v)}</span></div>
      <h3>${esc(row["Источник"])}</h3>
      <p>${esc(row["Причина"])}</p>
      ${rest.length ? `<details class="more-info"><summary>Подробности проверки</summary><dl>${rest.map((c) =>
        `<dt>${esc(c)}</dt><dd>${esc(row[c])}</dd>`).join("")}</dl></details>` : ""}
    </article>`;
  };
  return `<p class="count">Источники проверены ${esc(fmtDate(src.checked))}, полная версия в docs/AUDIT.md</p>` +
    src.tables.map((t) => `<h2 class="section">${esc(t.title)}</h2>
      <div class="list">${t.rows.map((row) => card(row, t.columns)).join("")}</div>`).join("");
}

function renderStats() {
  const d = state.data;
  const last = (d.runs || [])[0];
  $("stats").innerHTML = [
    `Новостей: <b>${(d.news || []).length}</b>`,
    `Объявлений и закупок: <b>${(d.waste || []).length}</b>`,
    last ? `Последний сбор: <b>${esc(fmtDate(last.started_at))}</b> ${statusChip(last.status)}` : "Сбор ещё не запускался",
  ].map((s) => `<span>${s}</span>`).join("");
}

function render() {
  const view = $("view");
  $("more").hidden = true;
  $("count").textContent = "";
  if (state.tab === "runs") { view.innerHTML = renderRuns(); return; }
  if (state.tab === "sources") { view.innerHTML = renderSources(); return; }
  const items = filtered();
  const total = (state.data[state.tab] || []).length;
  $("count").textContent = `Найдено ${items.length} из ${total}`;
  if (!items.length) {
    view.innerHTML = `<p class="empty">${total ? "Ничего не найдено, попробуйте ослабить фильтры." : "Данных пока нет."}</p>`;
    return;
  }
  const card = state.tab === "news" ? newsCard : wasteCard;
  view.innerHTML = `<div class="list">${items.slice(0, state.shown).map(card).join("")}</div>`;
  $("more").hidden = items.length <= state.shown;
}

function selectTab(tab) {
  state.tab = tab;
  state.shown = PAGE;
  document.querySelectorAll(".tabs button").forEach((b) =>
    b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
  try { history.replaceState(null, "", "#" + tab); } catch (e) { /* file:// */ }
  setupFilters();
  render();
}

function setupTheme() {
  $("theme").addEventListener("click", () => {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch (e) { /* приватный режим */ }
  });
}

async function main() {
  setupTheme();
  state.data = await load();
  if (!state.data) {
    $("view").innerHTML = `<p class="empty">Не удалось загрузить данные. Запустите сбор (python -m collector)
      и откройте витрину через локальный сервер: python -m http.server, затем /site/.</p>`;
    $("filters").hidden = true;
    return;
  }
  renderStats();
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => selectTab(b.dataset.tab)));
  FILTERS.forEach((id) => $(id).addEventListener("input", () => { state.shown = PAGE; render(); }));
  $("reset").addEventListener("click", () => { FILTERS.forEach((id) => { $(id).value = ""; }); state.shown = PAGE; render(); });
  $("more").addEventListener("click", () => { state.shown += PAGE; render(); });
  const tabFromHash = () => {
    const h = location.hash.slice(1);
    return ["news", "waste", "runs", "sources"].includes(h) ? h : "news";
  };
  window.addEventListener("hashchange", () => { if (tabFromHash() !== state.tab) selectTab(tabFromHash()); });
  selectTab(tabFromHash());
}

main();
