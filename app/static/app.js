const state = {
  mode: "note",
  method: "ic",
  hpoMapper: "dictionary",
  resultMethod: "ic",
  mapperCapabilities: [],
  mapperOptions: {},
  rankingCapabilities: [],
  rankingOptions: {},
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
  loadMapperCapabilities();
  loadRankingCapabilities();
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
    renderRankingOptions();
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
  const rankingMethod = state.method;
  button.disabled = true;
  button.querySelector("span").textContent = "Running";
  hideError();

  try {
    let rankingResponse;
    if (state.mode === "note") {
      const note = $("#clinical-note").value.trim();
      if (!note) throw new Error("Clinical note를 입력하세요.");
      rankingResponse = await postJson(`/api/retrieval/note/${rankingMethod}`, {
        clinical_note: note,
        top_k: Number($("#top-k").value),
        hpo_mapper: state.hpoMapper,
        hpo_mapper_options: state.mapperOptions[state.hpoMapper] || {},
        ranking_options: state.rankingOptions[rankingMethod] || {},
      });
      runMapperCompare(note);
      state.terms = new Map(rankingResponse.extracted_phenotypes.map((item) => [item.hpo_id, item.name]));
      renderTerms();
    } else {
      if (state.terms.size === 0) throw new Error("HPO term을 하나 이상 선택하세요.");
      rankingResponse = await postJson(`/api/retrieval/${rankingMethod}`, requestPayload(rankingMethod));
    }

    state.resultMethod = rankingMethod;
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

async function runMapperCompare(note) {
  const mappers = state.mapperCapabilities
    .filter((mapper) => ["dictionary", "doc2hpo", "original_hpo_mapper"].includes(mapper.id))
    .map((mapper) => mapper.id);
  if (!mappers.length) return;
  try {
    const response = await postJson("/api/hpo-mappers/compare", {
      clinical_note: note,
      mappers,
      top_k: Number($("#top-k").value),
      max_hpo_terms: 30,
      ranking_method: state.method,
      mapper_options: state.mapperOptions,
      ranking_options: state.rankingOptions[state.method] || {},
    });
    renderMapperCompare(response.results);
  } catch (error) {
    $("#mapper-compare").hidden = true;
  }
}

function renderMapperCompare(results) {
  const box = $("#mapper-compare");
  if (!results?.length) {
    box.hidden = true;
    return;
  }
  const readyCount = results.filter((result) => !result.error).length;
  const blockedCount = results.length - readyCount;
  box.innerHTML = `
    <details class="mapper-compare-details">
      <summary>
        <span>Mapper comparison</span>
        <strong>${readyCount} ready · ${blockedCount} unavailable</strong>
      </summary>
      <div class="mapper-compare-grid">
        ${results.map((result) => {
          const topDisease = result.candidates?.[0];
          const rankLabel = topDisease ? `${topDisease.disease_name} (${Number(topDisease.score).toFixed(2)})` : "—";
          const status = result.error ? result.error : `${result.extracted_phenotypes.length} HPO · ${rankLabel}`;
          return `
            <div class="mapper-compare-row ${result.error ? "has-error" : ""}">
              <strong>${escapeHtml(result.label)}</strong>
              <span>${escapeHtml(status)}</span>
            </div>
          `;
        }).join("")}
      </div>
    </details>
  `;
  box.hidden = false;
}

async function loadRankingCapabilities() {
  try {
    const response = await fetch("/api/retrieval/ranking-methods");
    if (!response.ok) throw new Error("Disease ranking 목록을 불러오지 못했습니다.");
    state.rankingCapabilities = await response.json();
  } catch (error) {
    state.rankingCapabilities = [
      { id: "ic", label: "IC", configured: true, options: [] },
      { id: "embedding", label: "Embedding", configured: true, options: [] },
      { id: "hybrid", label: "Hybrid", configured: true, options: [] },
    ];
  }
  renderRankingControls();
}

function renderRankingControls() {
  const container = $("#ranking-method");
  if (!container) return;
  if (!state.rankingCapabilities.some((method) => method.id === state.method)) state.method = "ic";
  container.innerHTML = state.rankingCapabilities.map((method) => `
    <button class="${method.id === state.method ? "active" : ""}" data-method="${escapeHtml(method.id)}" title="${escapeHtml(method.description || "")}">
      ${escapeHtml(method.label)}
    </button>
  `).join("");
  container.style.gridTemplateColumns = `repeat(${Math.max(state.rankingCapabilities.length, 1)}, 1fr)`;
  $$("#ranking-method button").forEach((button) => button.addEventListener("click", () => {
    state.method = button.dataset.method;
    renderRankingControls();
    $("#method-label").textContent = methodLabel(state.method);
  }));
  $("#method-label").textContent = methodLabel(state.method);
  renderRankingOptions();
}

function renderRankingOptions() {
  const method = state.rankingCapabilities.find((item) => item.id === state.method);
  const container = $("#ranking-options");
  if (!container) return;
  if (!method || !method.options?.length) {
    container.innerHTML = "";
    return;
  }
  if (!state.rankingOptions[state.method]) state.rankingOptions[state.method] = {};
  container.innerHTML = `
    <div class="option-grid">
      ${method.options.map((option) => optionField("ranking-option", state.method, option, state.rankingOptions)).join("")}
    </div>
  `;
  bindOptionControls("ranking-option", state.rankingOptions);
  if (window.lucide) window.lucide.createIcons();
}

async function loadMapperCapabilities() {
  try {
    const response = await fetch("/api/hpo-mappers");
    if (!response.ok) throw new Error("HPO mapper 목록을 불러오지 못했습니다.");
    state.mapperCapabilities = await response.json();
  } catch (error) {
    state.mapperCapabilities = [
      { id: "dictionary", label: "Dictionary", configured: true, options: [] },
      { id: "doc2hpo", label: "Doc2HPO", configured: false, options: [] },
    ];
  }
  renderMapperControls();
}

function renderMapperControls() {
  const container = $("#hpo-mapper-mode");
  const visible = state.mapperCapabilities.filter((mapper) => ["dictionary", "doc2hpo", "original_hpo_mapper"].includes(mapper.id));
  if (!visible.some((mapper) => mapper.id === state.hpoMapper)) state.hpoMapper = "dictionary";
  container.style.gridTemplateColumns = `repeat(${Math.max(visible.length, 1)}, 1fr)`;
  container.innerHTML = visible.map((mapper) => `
    <button
      class="${mapper.id === state.hpoMapper ? "active" : ""}"
      data-mapper="${escapeHtml(mapper.id)}"
      data-tooltip="${escapeHtml(mapper.description || "")}"
      aria-label="${escapeHtml(`${mapper.label}: ${mapper.description || ""}`)}"
    >
      ${escapeHtml(mapper.label)}
    </button>
  `).join("");
  $$("#hpo-mapper-mode button").forEach((button) => button.addEventListener("click", () => {
    state.hpoMapper = button.dataset.mapper;
    renderMapperControls();
  }));
  renderMapperOptions();
}

function renderMapperOptions() {
  const mapper = state.mapperCapabilities.find((item) => item.id === state.hpoMapper);
  const container = $("#hpo-mapper-options");
  if (!mapper || !mapper.options?.length) {
    container.innerHTML = mapper && !mapper.configured && state.hpoMapper !== "off"
      ? `<div class="mapper-warning">${escapeHtml(mapper.label)} endpoint is not configured.</div>`
      : "";
    return;
  }
  if (!state.mapperOptions[state.hpoMapper]) state.mapperOptions[state.hpoMapper] = {};
  container.innerHTML = `
    ${!mapper.configured ? `<div class="mapper-warning">${escapeHtml(mapper.label)} endpoint is not configured.</div>` : ""}
    <div class="option-grid">
      ${mapper.options.map((option) => optionField("mapper-option", mapper.id, option, state.mapperOptions)).join("")}
    </div>
  `;
  bindOptionControls("mapper-option", state.mapperOptions);
  if (window.lucide) window.lucide.createIcons();
}

function optionField(className, ownerId, option, optionStore) {
  const current = optionStore[ownerId]?.[option.key] ?? option.default;
  const dataAttrs = `data-owner="${escapeHtml(ownerId)}" data-key="${escapeHtml(option.key)}"`;
  const attrs = `class="${escapeHtml(className)}" ${dataAttrs}`;
  if (option.key === "max_genes") {
    return `
      <div class="option-wide gene-preview-option">
        <span class="option-label-text">${escapeHtml(option.label)}</span>
        <div class="button-choice-group" role="group" aria-label="${escapeHtml(option.label)}">
          ${option.choices.map((choice) => `
            <button
              type="button"
              class="${escapeHtml(className)} button-choice ${String(choice) === String(current) ? "active" : ""}"
              ${dataAttrs}
              data-value="${escapeHtml(choice)}"
            >${choice === "all" ? "All" : escapeHtml(choice)}</button>
          `).join("")}
        </div>
      </div>
    `;
  }
  if (option.type === "boolean") {
    const disabled = option.key === "use_ancestor_terms";
    return `
      <div class="option-boolean">
        <span class="option-label-spacer" aria-hidden="true">&nbsp;</span>
        <button type="button" class="${escapeHtml(className)} option-toggle ${current ? "active" : ""}" ${dataAttrs} data-value="${current ? "true" : "false"}" ${disabled ? "disabled" : ""}>
          <i data-lucide="${current ? "check" : "plus"}"></i>
          <span>${escapeHtml(option.label)}</span>
          ${disabled ? '<em>Soon</em>' : ""}
        </button>
      </div>
    `;
  }
  if (option.type === "select") {
    return `<label class="${optionLabelClass(option.key)}"><span class="option-label-text">${escapeHtml(option.label)}</span><select ${attrs}>${option.choices.map((choice) => `<option value="${escapeHtml(choice)}" ${choice === current ? "selected" : ""}>${escapeHtml(optionChoiceLabel(option.key, choice))}</option>`).join("")}</select></label>`;
  }
  if (option.key === "embedding_model") {
    const backend = optionStore[ownerId]?.embedding_backend || "sapbert_faiss";
    if (backend === "sapbert_faiss") {
      return `<label class="${optionLabelClass(option.key)}"><span class="option-label-text">${escapeHtml(option.label)}</span><input type="text" value="SapBERT PubMedBERT" disabled></label>`;
    }
    if (backend === "hpo_deepwalk_faiss" || backend === "hpo_graph_embedding_faiss") {
      return `<label class="${optionLabelClass(option.key)}"><span class="option-label-text">${escapeHtml(option.label)}</span><input type="text" value="HPO DeepWalk random-walk" disabled></label>`;
    }
    if (backend === "hpo_node2vec_faiss") {
      return `<label class="${optionLabelClass(option.key)}"><span class="option-label-text">${escapeHtml(option.label)}</span><input type="text" value="HPO Node2Vec biased walk" disabled></label>`;
    }
  }
  const inputType = option.type === "number" ? "number" : "text";
  return `<label class="${optionLabelClass(option.key)}"><span class="option-label-text">${escapeHtml(option.label)}</span><input ${attrs} type="${inputType}" value="${escapeHtml(current)}"></label>`;
}

function optionLabelClass(key) {
  return ["embedding_model", "ic_weight"].includes(key) ? "option-label-pad" : "";
}

function optionChoiceLabel(key, value) {
  const labels = {
    embedding_backend: {
      sapbert_faiss: "SapBERT · FAISS",
      custom_sentence_transformer_faiss: "Custom ST · FAISS",
      hpo_deepwalk_faiss: "HPO DeepWalk · FAISS",
      hpo_node2vec_faiss: "HPO Node2Vec · FAISS",
      hpo_graph_embedding_faiss: "HPO DeepWalk · FAISS",
    },
    graph_evidence_mode: {
      local_overlap: "Local overlap",
      frequency_weighted_graph: "Frequency weighted",
      gene_path: "Gene path",
      source_confidence_graph: "Source confidence",
    },
  };
  return labels[key]?.[value] || value;
}

function bindOptionControls(className, optionStore) {
  $$(`.${className}`).forEach((control) => {
    const eventName = control.classList.contains("option-toggle") || control.classList.contains("button-choice") ? "click" : "change";
    control.addEventListener(eventName, () => {
      if (control.disabled) return;
      const ownerOptions = optionStore[control.dataset.owner] || {};
      ownerOptions[control.dataset.key] = readOptionValue(control);
      optionStore[control.dataset.owner] = ownerOptions;
      if (control.dataset.key === "embedding_backend") {
        renderRankingOptions();
        return;
      }
      if (control.classList.contains("button-choice")) {
        $$(`.${className}.button-choice`).forEach((button) => {
          const sameGroup = button.dataset.owner === control.dataset.owner && button.dataset.key === control.dataset.key;
          if (sameGroup) button.classList.toggle("active", button === control);
        });
      }
      if (control.classList.contains("option-toggle")) {
        control.classList.toggle("active", ownerOptions[control.dataset.key]);
        control.dataset.value = ownerOptions[control.dataset.key] ? "true" : "false";
        const icon = control.querySelector("i");
        if (icon) icon.setAttribute("data-lucide", ownerOptions[control.dataset.key] ? "check" : "plus");
        if (window.lucide) window.lucide.createIcons();
      }
    });
  });
}

function readOptionValue(control) {
  if (control.classList.contains("option-toggle")) return control.dataset.value !== "true";
  if (control.classList.contains("button-choice")) return control.dataset.value;
  if (control.type === "number") return Number(control.value);
  return control.value;
}

function requestPayload(method = state.method) {
  return {
    hpo_terms: [...state.terms.keys()],
    top_k: Number($("#top-k").value),
    ranking_options: state.rankingOptions[method] || {},
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
  $("#score-bars").innerHTML = scoreRows(candidate.score_components, state.resultMethod);
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

function scoreRows(scoreComponents, method) {
  const orderedKeys = ["ic_score", "embedding_score", "graph_score"];
  const components = scoreComponents || {};
  return orderedKeys
    .map((key) => {
      const label = key.replace("_score", "");
      if (!isScoreComponentUsed(key, method)) {
        return `
          <div class="score-row score-row-muted">
            <span>${escapeHtml(label)}</span>
            <div class="score-track is-unused"><div class="score-fill" style="width:0%"></div></div>
            <strong>Not used</strong>
          </div>
        `;
      }
      const score = Math.max(0, Math.min(1, Number(components[key] || 0)));
      return `
        <div class="score-row">
          <span>${escapeHtml(label)}</span>
          <div class="score-track"><div class="score-fill" style="width:${score * 100}%"></div></div>
          <strong>${score.toFixed(2)}</strong>
        </div>
      `;
    }).join("");
}

function isScoreComponentUsed(key, method) {
  if (method === "hybrid") return true;
  if (method === "ic") return key === "ic_score";
  if (method === "embedding") return key === "embedding_score";
  if (method === "graph") return key === "graph_score";
  return true;
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
  const configured = state.rankingCapabilities.find((item) => item.id === method);
  if (configured?.label) return configured.label;
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
