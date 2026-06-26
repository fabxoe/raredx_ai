const state = {
  mode: "note",
  method: "ic",
  hpoMapper: "dictionary",
  terms: new Map([
    ["HP:0001250", "Seizure"],
    ["HP:0001263", "Global developmental delay"],
    ["HP:0000252", "Microcephaly"],
  ]),
  candidates: [],
  graph: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) window.lucide.createIcons();
  bindControls();
  renderTerms();
  initializeGraph();
  runAnalysis();
});

function bindControls() {
  $$("#input-mode button").forEach((button) => button.addEventListener("click", () => {
    $$("#input-mode button").forEach((item) => item.classList.toggle("active", item === button));
    state.mode = button.dataset.mode;
    $("#hpo-input-section").hidden = state.mode !== "hpo";
    $("#note-input-section").hidden = state.mode !== "note";
  }));

  $$("#ranking-method button").forEach((button) => button.addEventListener("click", () => {
    $$("#ranking-method button").forEach((item) => item.classList.toggle("active", item === button));
    state.method = button.dataset.method;
    $("#method-label").textContent = methodLabel(state.method);
  }));

  $$("#hpo-mapper-mode button").forEach((button) => button.addEventListener("click", () => {
    $$("#hpo-mapper-mode button").forEach((item) => item.classList.toggle("active", item === button));
    state.hpoMapper = button.dataset.mapper;
  }));

  $("#hpo-search").addEventListener("input", debounce(searchPhenotypes, 220));
  $("#hpo-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      const first = $(".suggestion-item");
      if (first) first.click();
    }
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest("#hpo-input-section")) $("#hpo-suggestions").hidden = true;
  });

  $("#run-analysis").addEventListener("click", runAnalysis);
  $("#reset-query").addEventListener("click", () => {
    state.terms.clear();
    $("#clinical-note").value = "";
    renderTerms();
  });
  $("#fit-graph").addEventListener("click", () => state.graph?.fit(undefined, 36));
  $("#reset-graph").addEventListener("click", runGraphLayout);
}

async function searchPhenotypes(event) {
  const query = event.target.value.trim();
  const container = $("#hpo-suggestions");
  if (query.length < 2) {
    container.hidden = true;
    return;
  }
  try {
    const response = await fetch(`/api/retrieval/phenotypes?q=${encodeURIComponent(query)}&limit=8`);
    if (!response.ok) throw new Error("HPO search failed");
    const matches = await response.json();
    container.innerHTML = matches.map((item) => `
      <button class="suggestion-item" data-id="${escapeHtml(item.hpo_id)}" data-name="${escapeHtml(item.name)}">
        <strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.hpo_id)}</span>
      </button>`).join("");
    container.hidden = matches.length === 0;
    $$(".suggestion-item").forEach((button) => button.addEventListener("click", () => {
      state.terms.set(button.dataset.id, button.dataset.name);
      $("#hpo-search").value = "";
      container.hidden = true;
      renderTerms();
    }));
  } catch (error) {
    showError(error.message);
  }
}

function renderTerms() {
  const container = $("#selected-terms");
  container.innerHTML = [...state.terms.entries()].map(([id, name]) => `
    <span class="term-chip" title="${escapeHtml(id)}">
      <span>${escapeHtml(name)}</span>
      <button data-remove="${escapeHtml(id)}" aria-label="${escapeHtml(name)} 제거"><i data-lucide="x"></i></button>
    </span>`).join("");
  $$('[data-remove]').forEach((button) => button.addEventListener("click", () => {
    state.terms.delete(button.dataset.remove);
    renderTerms();
  }));
  $("#phenotype-count").textContent = state.terms.size;
  if (window.lucide) window.lucide.createIcons();
}

async function runAnalysis() {
  const button = $("#run-analysis");
  const started = performance.now();
  button.disabled = true;
  button.querySelector("span").textContent = "Running";
  hideError();

  try {
    let rankingResponse;
    if (state.mode === "note") {
      const note = $("#clinical-note").value.trim();
      if (!note) throw new Error("Clinical note를 입력하세요.");
      const noteMethod = state.method === "hybrid" ? "hybrid" : "ic";
      rankingResponse = await postJson(`/api/retrieval/note/${noteMethod}`, {
        clinical_note: note,
        top_k: Number($("#top-k").value),
        hpo_mapper: state.hpoMapper,
      });
      state.terms = new Map(rankingResponse.extracted_phenotypes.map((item) => [item.hpo_id, item.name]));
      renderTerms();
    } else {
      if (state.terms.size === 0) throw new Error("HPO term을 하나 이상 선택하세요.");
      rankingResponse = await postJson(`/api/retrieval/${state.method}`, requestPayload());
    }

    state.candidates = rankingResponse.candidates;
    renderRanking(state.candidates);
    $("#result-count").textContent = `${state.candidates.length} candidates`;
    if (state.candidates[0]) selectCandidate(state.candidates[0], 0);
    try {
      const graphResponse = await postJson("/api/graph/subgraph", requestPayload());
      renderGraph(graphResponse);
    } catch (graphError) {
      clearGraph("Graph unavailable");
      showError("Disease ranking은 완료됐지만 Neo4j graph를 불러오지 못했습니다.");
    }
    $("#latency").textContent = `${Math.round(performance.now() - started)} ms`;
  } catch (error) {
    showError(error.message);
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "Run analysis";
  }
}

function requestPayload() {
  return {
    hpo_terms: [...state.terms.keys()],
    top_k: Number($("#top-k").value),
  };
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `${url} request failed`);
  return data;
}

function renderRanking(candidates) {
  const body = $("#ranking-body");
  if (!candidates.length) {
    body.innerHTML = '<tr class="empty-row"><td colspan="4">No candidates</td></tr>';
    return;
  }
  body.innerHTML = candidates.map((candidate, index) => `
    <tr class="disease-row" data-index="${index}" data-id="${escapeHtml(candidate.disease_id)}">
      <td>${index + 1}</td>
      <td><span class="disease-name">${escapeHtml(candidate.disease_name)}</span><span class="disease-id">${escapeHtml(candidate.disease_id)}</span></td>
      <td class="gene-cell" title="${escapeHtml(candidate.associated_genes.join(", "))}">${escapeHtml(candidate.associated_genes.slice(0, 2).join(", ") || "—")}</td>
      <td>${Number(candidate.score).toFixed(3)}</td>
    </tr>`).join("");
  $$(".disease-row").forEach((row) => row.addEventListener("click", () => {
    selectCandidate(candidates[Number(row.dataset.index)], Number(row.dataset.index));
  }));
}

function selectCandidate(candidate, index) {
  $$(".disease-row").forEach((row) => row.classList.toggle("active", Number(row.dataset.index) === index));
  $("#selected-disease-id").textContent = candidate.disease_id;
  $("#score-bars").innerHTML = Object.entries(candidate.score_components).map(([key, value]) => {
    const score = Math.max(0, Math.min(1, Number(value)));
    return `<div class="score-row"><span>${escapeHtml(key.replace("_score", ""))}</span><div class="score-track"><div class="score-fill" style="width:${score * 100}%"></div></div><strong>${score.toFixed(2)}</strong></div>`;
  }).join("");
  $("#matched-list").innerHTML = listItems(candidate.matched_phenotypes.map((item) => `${item.name || item.hpo_id} · ${item.hpo_id}`));
  $("#gene-list").innerHTML = listItems(candidate.associated_genes);
  if (state.graph) {
    state.graph.elements().removeClass("focused faded");
    const node = state.graph.getElementById(candidate.disease_id);
    if (node.length) {
      state.graph.elements().addClass("faded");
      node.closedNeighborhood().removeClass("faded").addClass("focused");
      state.graph.animate({ center: { eles: node }, zoom: Math.max(state.graph.zoom(), 1.2) }, { duration: 350 });
    }
  }
}

function initializeGraph() {
  state.graph = cytoscape({
    container: $("#graph"),
    elements: [],
    minZoom: 0.35,
    maxZoom: 2.3,
    wheelSensitivity: 0.18,
    style: graphStyles(),
  });
  state.graph.on("tap", "node", (event) => inspectNode(event.target));
  state.graph.on("tap", (event) => {
    if (event.target === state.graph) state.graph.elements().removeClass("focused faded");
  });
}

function renderGraph(payload) {
  const elements = [
    ...payload.nodes.map((node) => ({ data: node })),
    ...payload.edges.map((edge) => ({ data: edge })),
  ];
  state.graph.elements().remove();
  state.graph.add(elements);
  runGraphLayout();
  $("#graph-count").textContent = `${payload.nodes.length} nodes · ${payload.edges.length} edges`;
}

function clearGraph(label = "0 nodes · 0 edges") {
  state.graph?.elements().remove();
  $("#graph-count").textContent = label;
}

function runGraphLayout() {
  if (!state.graph || state.graph.elements().length === 0) return;
  state.graph.elements().removeClass("focused faded");
  state.graph.layout({
    name: "cose",
    animate: true,
    animationDuration: 420,
    fit: true,
    padding: 36,
    nodeRepulsion: 7000,
    idealEdgeLength: 90,
    gravity: 0.35,
  }).run();
}

function inspectNode(node) {
  const data = node.data();
  $("#inspector-label").textContent = data.label;
  const properties = { Type: data.type, ID: data.id, ...(data.properties || {}) };
  $("#inspector-properties").innerHTML = Object.entries(properties).map(([key, value]) => `
    <div><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(String(value ?? "—"))}</dd></div>`).join("");
  state.graph.elements().addClass("faded");
  node.closedNeighborhood().removeClass("faded").addClass("focused");
}

function graphStyles() {
  const color = { Patient: "#17201c", Phenotype: "#16784a", Disease: "#2766b0", Gene: "#a95e13" };
  const size = { Patient: 38, Phenotype: 28, Disease: 36, Gene: 25 };
  return [
    { selector: "node", style: {
      "background-color": (node) => color[node.data("type")] || "#66716b",
      width: (node) => size[node.data("type")] || 28,
      height: (node) => size[node.data("type")] || 28,
      label: "data(label)",
      color: "#26312b",
      "font-size": 9,
      "font-weight": 600,
      "text-wrap": "wrap",
      "text-max-width": 104,
      "text-valign": "bottom",
      "text-margin-y": 7,
      "border-width": 2,
      "border-color": "#ffffff",
      "overlay-opacity": 0,
    }},
    { selector: "edge", style: {
      width: 1.2,
      "line-color": "#bfc8c3",
      "target-arrow-color": "#9eaaa4",
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.7,
      "curve-style": "bezier",
      opacity: 0.75,
    }},
    { selector: ".faded", style: { opacity: 0.12 } },
    { selector: "node.focused", style: { "border-color": "#f0b44c", "border-width": 4, opacity: 1 } },
    { selector: "edge.focused", style: { "line-color": "#f0b44c", "target-arrow-color": "#f0b44c", width: 2.5, opacity: 1 } },
  ];
}

function methodLabel(method) {
  return { ic: "IC baseline", embedding: "SapBERT · FAISS", hybrid: "Hybrid re-ranking" }[method];
}

function listItems(items) {
  if (!items?.length) return "<li>—</li>";
  return items.slice(0, 8).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function showError(message) {
  const box = $("#query-error");
  box.textContent = message;
  box.hidden = false;
}

function hideError() { $("#query-error").hidden = true; }

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

function debounce(callback, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => callback(...args), delay);
  };
}
