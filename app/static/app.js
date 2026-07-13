const state = {
  mode: "note",
  method: "ic",
  hpoMapper: "dictionary",
  resultMethod: "ic",
  mapperCapabilities: [],
  mapperOptions: {},
  llmModels: {
    openai: ["gpt-4o-mini"],
    ollama: [],
  },
  rankingCapabilities: [],
  rankingOptions: {},
  terms: new Map([
    ["HP:0001250", "Seizure"],
    ["HP:0001263", "Global developmental delay"],
    ["HP:0000252", "Microcephaly"],
  ]),
  candidates: [],
  graph: null,
  workspace: "ranking",
  cypherMode: "read",
  cypherGraph: null,
  cypherPresets: [],
  cypherResultView: "table",
  cypherLastResponse: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) window.lucide.createIcons();
  bindControls();
  loadMapperCapabilities();
  loadLlmModels("openai");
  loadRankingCapabilities();
  renderTerms();
  initializeGraph();
  initializeCypherGraph();
  loadCypherPresets();
  runAnalysis();
});

function bindControls() {
  $$("#workspace-switch button").forEach((button) => button.addEventListener("click", () => {
    setWorkspace(button.dataset.workspace);
  }));

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
  $("#cypher-schema-refresh").addEventListener("click", loadCypherPresets);
  $("#cypher-run").addEventListener("click", runCypher);
  $("#cypher-lock-toggle").addEventListener("click", toggleCypherLock);
  $("#cypher-unlock-cancel").addEventListener("click", closeCypherUnlockModal);
  $("#cypher-unlock-apply").addEventListener("click", confirmCypherUnlock);
  $("#cypher-unlock-confirm").addEventListener("keydown", (event) => {
    if (event.key === "Enter") confirmCypherUnlock();
    if (event.key === "Escape") closeCypherUnlockModal();
  });
  $$("#cypher-result-tabs button").forEach((button) => button.addEventListener("click", () => {
    setCypherResultView(button.dataset.resultView);
  }));
}

function setWorkspace(workspace) {
  state.workspace = workspace === "cypher" ? "cypher" : "ranking";
  $$("#workspace-switch button").forEach((button) => {
    button.classList.toggle("active", button.dataset.workspace === state.workspace);
  });
  $("#ranking-workspace").hidden = state.workspace !== "ranking";
  $("#cypher-workspace").hidden = state.workspace !== "cypher";
  if (state.workspace === "cypher") {
    setTimeout(() => state.cypherGraph?.resize().fit(undefined, 40), 0);
  }
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
  hideLlmStatus();

  try {
    let rankingResponse;
    if (state.mode === "note") {
      const note = $("#clinical-note").value.trim();
      if (!note) throw new Error("Clinical note를 입력하세요.");
      rankingResponse = await postJson(`/api/retrieval/note/${rankingMethod}`, {
        clinical_note: note,
        top_k: Number($("#top-k").value),
        hpo_mapper: state.hpoMapper,
        hpo_mapper_options: resolvedMapperOptions(state.hpoMapper),
        ranking_options: state.rankingOptions[rankingMethod] || {},
      });
      runMapperCompare(note);
      renderLlmStatusFromResponse(rankingResponse);
      state.terms = new Map(
        rankingResponse.extracted_phenotypes
          .filter(isFinalSelectedPhenotype)
          .map((item) => [item.hpo_id, item.name])
      );
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
    renderLlmStatusFromError(error);
    showError(error.message);
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "Run analysis";
  }
}

async function loadLlmModels(provider) {
  const providerName = provider || "openai";
  try {
    const response = await fetch(`/api/retrieval/llm-models?provider=${encodeURIComponent(providerName)}`);
    if (!response.ok) throw new Error("LLM model list failed");
    const models = await response.json();
    if (Array.isArray(models) && models.length) {
      state.llmModels[providerName] = models;
      renderMapperOptions();
    }
  } catch (error) {
    if (!state.llmModels[providerName]?.length && providerName === "openai") {
      state.llmModels.openai = ["gpt-4o-mini"];
    }
  }
}

async function runMapperCompare(note) {
  const mappers = state.mapperCapabilities
    .filter((mapper) => ["dictionary", "doc2hpo", "original_hpo_mapper"].includes(mapper.id))
    .map((mapper) => mapper.id);
  if (!mappers.length) return;
  try {
    const activeOptions = resolvedMapperOptions(state.hpoMapper);
    const mapperOptions = { ...state.mapperOptions };
    mappers.forEach((mapperId) => {
      mapperOptions[mapperId] = {
        ...resolvedMapperOptions(mapperId),
        negation_mode: resolvedMapperOptions(mapperId).negation_mode || activeOptions.negation_mode || "off",
        negation_llm_provider: resolvedMapperOptions(mapperId).negation_llm_provider || activeOptions.negation_llm_provider || "off",
        negation_chat_model: resolvedMapperOptions(mapperId).negation_chat_model || activeOptions.negation_chat_model || "gpt-4o-mini",
      };
    });
    const response = await postJson("/api/hpo-mappers/compare", {
      clinical_note: note,
      mappers,
      top_k: Number($("#top-k").value),
      max_hpo_terms: 30,
      ranking_method: state.method,
      mapper_options: mapperOptions,
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
          const selectedCount = result.extracted_phenotypes?.filter(isFinalSelectedPhenotype).length || 0;
          const totalCount = result.extracted_phenotypes?.length || 0;
          const excludedCount = Math.max(0, totalCount - selectedCount);
          const status = result.error ? result.error : `${selectedCount}/${totalCount} used · ${excludedCount} excluded · ${rankLabel}`;
          return `
            <div class="mapper-compare-row ${result.error ? "has-error" : ""}">
              <strong>${escapeHtml(result.label)}</strong>
              <span>${escapeHtml(status)}</span>
              ${result.error ? "" : phenotypeContextPreview(result.extracted_phenotypes)}
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
  const disabled = optionDisabled(ownerId, option.key, optionStore);
  const attrs = `class="${escapeHtml(className)}" ${dataAttrs} ${disabled ? "disabled" : ""}`;
  if (option.key === "chat_model" || option.key === "negation_chat_model") {
    const providerKey = option.key === "negation_chat_model" ? "negation_llm_provider" : "llm_provider";
    const provider = optionStore[ownerId]?.[providerKey] || optionDefault(ownerId, providerKey) || "off";
    if (disabled) {
      return `<label class="${optionLabelClass(option.key)}"><span class="option-label-text">${escapeHtml(option.label)}</span><input type="text" value="" disabled></label>`;
    }
    if (provider === "openai") {
      const choices = state.llmModels.openai?.length ? state.llmModels.openai : ["gpt-4o-mini"];
      const selected = choices.includes(String(current)) ? String(current) : choices[0];
      return `<label class="${optionLabelClass(option.key)}"><span class="option-label-text">${escapeHtml(option.label)}</span><select ${attrs}>${choices.map((choice) => `<option value="${escapeHtml(choice)}" ${choice === selected ? "selected" : ""}>${escapeHtml(choice)}</option>`).join("")}</select></label>`;
    }
    if (provider === "ollama") {
      return `<label class="${optionLabelClass(option.key)}"><span class="option-label-text">${escapeHtml(option.label)}</span><input ${attrs} type="text" value="${escapeHtml(current || "phi4-mini")}"></label>`;
    }
    return `<label class="${optionLabelClass(option.key)}"><span class="option-label-text">${escapeHtml(option.label)}</span><input type="text" value="" disabled></label>`;
  }
  if (option.key === "embedding_model") {
    const backend = optionStore[ownerId]?.embedding_backend || "sapbert_faiss";
    const displayName = embeddingModelDisplayName(backend);
    if (displayName) {
      return `<label class="${optionLabelClass(option.key)}"><span class="option-label-text">${escapeHtml(option.label)}</span><input type="text" value="${escapeHtml(displayName)}" disabled></label>`;
    }
  }
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
    const toggleDisabled = option.key === "use_ancestor_terms";
    return `
      <div class="option-boolean">
        <span class="option-label-spacer" aria-hidden="true">&nbsp;</span>
        <button type="button" class="${escapeHtml(className)} option-toggle ${current ? "active" : ""}" ${dataAttrs} data-value="${current ? "true" : "false"}" ${toggleDisabled ? "disabled" : ""}>
          <i data-lucide="${current ? "check" : "plus"}"></i>
          <span>${escapeHtml(option.label)}</span>
          ${toggleDisabled ? '<em>Soon</em>' : ""}
        </button>
      </div>
    `;
  }
  if (option.type === "select") {
    return `<label class="${optionLabelClass(option.key)}"><span class="option-label-text">${escapeHtml(option.label)}</span><select ${attrs}>${option.choices.map((choice) => `<option value="${escapeHtml(choice)}" ${choice === current ? "selected" : ""}>${escapeHtml(optionChoiceLabel(option.key, choice))}</option>`).join("")}</select></label>`;
  }
  const inputType = option.type === "number" ? "number" : "text";
  return `<label class="${optionLabelClass(option.key)}"><span class="option-label-text">${escapeHtml(option.label)}</span><input ${attrs} type="${inputType}" value="${escapeHtml(current)}"></label>`;
}

function optionDisabled(ownerId, key, optionStore) {
  const ownerOptions = optionStore[ownerId] || {};
  if (["negation_llm_provider", "negation_chat_model"].includes(key)) {
    const mode = String(ownerOptions.negation_mode ?? optionDefault(ownerId, "negation_mode") ?? "off").toLowerCase();
    return mode !== "llm_qc";
  }
  if (key === "chat_model") {
    const provider = String(ownerOptions.llm_provider ?? optionDefault(ownerId, "llm_provider") ?? "off").toLowerCase();
    return provider === "off";
  }
  return false;
}

function embeddingModelDisplayName(backend) {
  const labels = {
    sapbert_faiss: "SapBERT",
    pubmedbert_faiss: "PubMedBERT",
    biosentvec_faiss: "BioSentVec external model",
    hpo_deepwalk_faiss: "HPO DeepWalk random-walk",
    hpo_graph_embedding_faiss: "HPO DeepWalk random-walk",
    hpo_node2vec_faiss: "HPO Node2Vec biased walk",
  };
  return labels[backend] || "";
}

function optionLabelClass(key) {
  return ["embedding_model", "ic_weight"].includes(key) ? "option-label-pad" : "";
}

function optionDefault(ownerId, key) {
  const mapper = state.mapperCapabilities.find((item) => item.id === ownerId);
  const ranking = state.rankingCapabilities.find((item) => item.id === ownerId);
  const option = [...(mapper?.options || []), ...(ranking?.options || [])].find((item) => item.key === key);
  return option?.default;
}

function optionChoiceLabel(key, value) {
  const labels = {
    embedding_backend: {
      sapbert_faiss: "SapBERT · FAISS",
      pubmedbert_faiss: "PubMedBERT · FAISS",
      biosentvec_faiss: "BioSentVec · FAISS",
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
    negation_mode: {
      off: "Off",
      simple_trigger: "Simple trigger",
      negex_lite: "NegEx-lite",
      medspacy_context: "medspaCy context",
      status_weight: "Status weight",
      llm_qc: "LLM QC",
    },
    negation_llm_provider: {
      off: "Off",
      openai: "OpenAI",
      ollama: "Ollama",
    },
    llm_provider: {
      off: "Off",
      openai: "OpenAI",
      ollama: "Ollama",
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
      if (control.dataset.key === "llm_provider" || control.dataset.key === "negation_llm_provider") {
        const providerKey = control.dataset.key;
        const modelKey = providerKey === "negation_llm_provider" ? "negation_chat_model" : "chat_model";
        if (ownerOptions[providerKey] === "openai" && !ownerOptions[modelKey]) {
          ownerOptions[modelKey] = state.llmModels.openai?.[0] || "gpt-4o-mini";
        }
        if (ownerOptions[providerKey] === "openai") loadLlmModels("openai");
        renderMapperOptions();
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

function resolvedMapperOptions(mapperId) {
  const mapper = state.mapperCapabilities.find((item) => item.id === mapperId);
  const defaults = Object.fromEntries((mapper?.options || []).map((option) => [option.key, option.default]));
  return { ...defaults, ...(state.mapperOptions[mapperId] || {}) };
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

async function loadCypherPresets() {
  const container = $("#cypher-presets");
  if (!container) return;
  container.innerHTML = '<button class="preset-item" disabled>Loading presets...</button>';
  try {
    const response = await fetch("/api/admin/cypher/presets");
    if (!response.ok) throw new Error("Cypher preset 목록을 불러오지 못했습니다.");
    state.cypherPresets = await response.json();
    renderCypherPresets();
  } catch (error) {
    container.innerHTML = `<button class="preset-item" disabled>${escapeHtml(error.message)}</button>`;
  }
}

function renderCypherPresets() {
  const container = $("#cypher-presets");
  if (!container) return;
  container.innerHTML = state.cypherPresets.map((preset) => `
    <button type="button" class="preset-item" data-preset="${escapeHtml(preset.id)}">
      <strong>${escapeHtml(preset.label)}</strong>
      <span>${escapeHtml(preset.description)}</span>
    </button>
  `).join("");
  $$(".preset-item[data-preset]").forEach((button) => button.addEventListener("click", () => {
    const preset = state.cypherPresets.find((item) => item.id === button.dataset.preset);
    if (!preset) return;
    $("#cypher-query").value = preset.query;
    $("#cypher-params").value = JSON.stringify(preset.params || {}, null, 2);
    hideCypherError();
  }));
}

async function runCypher() {
  const button = $("#cypher-run");
  const label = button?.querySelector("span");
  if (!button || !label) return;
  button.disabled = true;
  label.textContent = "Running";
  hideCypherError();
  renderCypherWarnings([]);
  try {
    const payload = {
      query: $("#cypher-query").value,
      params: parseCypherParams(),
      mode: state.cypherMode,
      result_limit: Number($("#cypher-result-limit").value || 500),
      graph_limit: Number($("#cypher-graph-limit").value || 250),
    };
    const response = await postJson("/api/admin/cypher/run", payload);
    state.cypherLastResponse = response;
    renderCypherResponse(response);
  } catch (error) {
    showCypherError(error.message);
  } finally {
    button.disabled = false;
    label.textContent = "Run Cypher";
  }
}

function parseCypherParams() {
  const raw = $("#cypher-params").value.trim();
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error("params must be an object");
    }
    return parsed;
  } catch (error) {
    throw new Error("Params는 JSON object 형식이어야 합니다.");
  }
}

function renderCypherResponse(response) {
  renderCypherStats(response.stats);
  renderCypherWarnings(response.warnings || []);
  renderCypherTable(response.columns || [], response.rows || []);
  renderCypherGraph(response.graph || { nodes: [], edges: [] });
  $("#cypher-json-panel").textContent = JSON.stringify(response, null, 2);
  setCypherResultView(state.cypherResultView);
}

function renderCypherStats(stats) {
  $("#cypher-stats").textContent = `${stats?.row_count || 0} rows · ${stats?.node_count || 0} nodes · ${stats?.edge_count || 0} edges · ${stats?.elapsed_ms || 0} ms`;
}

function renderCypherWarnings(warnings) {
  const box = $("#cypher-warning");
  if (!box) return;
  if (!warnings?.length) {
    box.hidden = true;
    box.textContent = "";
    return;
  }
  box.textContent = warnings.join(" ");
  box.hidden = false;
}

function renderCypherTable(columns, rows) {
  const head = $("#cypher-table-head");
  const body = $("#cypher-table-body");
  const resolvedColumns = columns.length ? columns : Object.keys(rows[0] || {});
  if (!resolvedColumns.length) {
    head.innerHTML = "";
    body.innerHTML = '<tr class="empty-row"><td>결과 row가 없습니다.</td></tr>';
    return;
  }
  head.innerHTML = `<tr>${resolvedColumns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>`;
  body.innerHTML = rows.map((row) => `
    <tr>${resolvedColumns.map((column) => `<td>${formatCypherCell(row[column])}</td>`).join("")}</tr>
  `).join("") || `<tr class="empty-row"><td colspan="${resolvedColumns.length}">결과 row가 없습니다.</td></tr>`;
}

function formatCypherCell(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return escapeHtml(value);
  }
  return `<code class="cypher-cell-code">${escapeHtml(JSON.stringify(value, null, 2))}</code>`;
}

function initializeCypherGraph() {
  const container = $("#cypher-graph");
  if (!container || !window.cytoscape) return;
  state.cypherGraph = cytoscape({
    container,
    elements: [],
    minZoom: 0.2,
    maxZoom: 2.5,
    wheelSensitivity: 0.18,
    style: cypherGraphStyles(),
  });
  state.cypherGraph.on("tap", "node", (event) => {
    const data = event.target.data();
    $("#cypher-json-panel").textContent = JSON.stringify(data, null, 2);
    setCypherResultView("json");
  });
}

function renderCypherGraph(graph) {
  if (!state.cypherGraph) return;
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  state.cypherGraph.elements().remove();
  state.cypherGraph.add([
    ...nodes.map((node) => ({ data: node })),
    ...edges.map((edge) => ({ data: edge })),
  ]);
  runCypherGraphLayout();
}

function runCypherGraphLayout() {
  if (!state.cypherGraph || state.cypherGraph.elements().length === 0) return;
  state.cypherGraph.layout({
    name: "cose",
    animate: true,
    animationDuration: 360,
    fit: true,
    padding: 34,
    nodeRepulsion: 7500,
    idealEdgeLength: 92,
    gravity: 0.28,
  }).run();
}

function cypherGraphStyles() {
  const color = { Patient: "#17201c", Phenotype: "#16784a", Disease: "#2766b0", Gene: "#a95e13" };
  const size = { Patient: 38, Phenotype: 28, Disease: 34, Gene: 24 };
  return [
    { selector: "node", style: {
      "background-color": (node) => color[node.data("type")] || "#64736b",
      width: (node) => size[node.data("type")] || 28,
      height: (node) => size[node.data("type")] || 28,
      label: "data(label)",
      color: "#26312b",
      "font-size": 9,
      "font-weight": 650,
      "text-wrap": "wrap",
      "text-max-width": 110,
      "text-valign": "bottom",
      "text-margin-y": 7,
      "border-width": 2,
      "border-color": "#ffffff",
      "overlay-opacity": 0,
    }},
    { selector: "edge", style: {
      width: 1.1,
      label: "data(type)",
      "font-size": 7,
      "text-rotation": "autorotate",
      "text-margin-y": -8,
      "line-color": "#c3cbc6",
      "target-arrow-color": "#aab5af",
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.65,
      "curve-style": "bezier",
      opacity: 0.74,
    }},
  ];
}

function setCypherResultView(view) {
  state.cypherResultView = ["table", "graph", "json"].includes(view) ? view : "table";
  $$("#cypher-result-tabs button").forEach((button) => {
    button.classList.toggle("active", button.dataset.resultView === state.cypherResultView);
  });
  $("#cypher-table-panel").hidden = state.cypherResultView !== "table";
  $("#cypher-graph-panel").hidden = state.cypherResultView !== "graph";
  $("#cypher-json-panel").hidden = state.cypherResultView !== "json";
  if (state.cypherResultView === "graph") {
    setTimeout(() => state.cypherGraph?.resize().fit(undefined, 36), 0);
  }
}

function toggleCypherLock() {
  if (state.cypherMode === "write") {
    setCypherMode("read");
    return;
  }
  openCypherUnlockModal();
}

function openCypherUnlockModal() {
  const modal = $("#cypher-unlock-modal");
  modal.hidden = false;
  $("#cypher-unlock-confirm").value = "";
  setTimeout(() => $("#cypher-unlock-confirm").focus(), 0);
}

function closeCypherUnlockModal() {
  $("#cypher-unlock-modal").hidden = true;
  $("#cypher-unlock-confirm").value = "";
}

function confirmCypherUnlock() {
  if ($("#cypher-unlock-confirm").value.trim() !== "UNLOCK") {
    showCypherError('Write mode를 열려면 확인창에 "UNLOCK"을 입력해야 합니다.');
    $("#cypher-unlock-confirm").focus();
    return;
  }
  setCypherMode("write");
  closeCypherUnlockModal();
}

function setCypherMode(mode) {
  state.cypherMode = mode === "write" ? "write" : "read";
  const button = $("#cypher-lock-toggle");
  const icon = button.querySelector("i");
  const text = button.querySelector("span");
  $("#cypher-mode-label").textContent = state.cypherMode === "write" ? "Write unlocked" : "Read-only";
  button.classList.toggle("is-unlocked", state.cypherMode === "write");
  button.classList.toggle("is-locked", state.cypherMode !== "write");
  icon.setAttribute("data-lucide", state.cypherMode === "write" ? "unlock" : "lock");
  text.textContent = state.cypherMode === "write" ? "Write unlocked" : "Read-only lock";
  if (window.lucide) window.lucide.createIcons();
}

function showCypherError(message) {
  const box = $("#cypher-error");
  box.textContent = message;
  box.hidden = false;
}

function hideCypherError() {
  const box = $("#cypher-error");
  if (!box) return;
  box.hidden = true;
  box.textContent = "";
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
  return { ic: "IC baseline", embedding: "Embedding retrieval", graph: "Graph evidence", hybrid: "Hybrid re-ranking" }[method];
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

function renderLlmStatusFromResponse(response) {
  const options = resolvedMapperOptions(state.hpoMapper);
  const statuses = llmRequestStatuses(options, response);
  if (state.mode !== "note" || !statuses.length) {
    hideLlmStatus();
    return;
  }
  const hasError = statuses.some((status) => status.tone === "error");
  showLlmStatus(statuses.map((status) => status.message).join(" · "), hasError ? "error" : "success");
}

function renderLlmStatusFromError(error) {
  const options = resolvedMapperOptions(state.hpoMapper);
  const message = String(error?.message || "");
  if (/llm|openai|api_key|chat model|model/i.test(message)) {
    const extraction = extractionLlmRequested(options);
    const negation = negationLlmRequested(options);
    const labels = [
      extraction ? `Extraction ${providerLabel(String(options.llm_provider || "off"))} LLM 호출실패` : "",
      negation ? `Negation ${providerLabel(String(options.negation_llm_provider || "off"))} LLM 호출실패` : "",
    ].filter(Boolean);
    if (labels.length) showLlmStatus(labels.join(" · "), "error");
  }
}

function llmRequestStatuses(options, response) {
  const phenotypes = response.extracted_phenotypes || [];
  const statuses = [];
  if (extractionLlmRequested(options)) {
    const provider = String(options.llm_provider || "off").toLowerCase();
    const used = phenotypes.some((item) => item.metadata?.llm_used && item.metadata?.context_method !== "llm_qc");
    statuses.push({ message: `Extraction ${providerLabel(provider)} LLM 호출${used ? "성공" : "실패"}`, tone: used ? "success" : "error" });
  }
  if (negationLlmRequested(options)) {
    const provider = String(options.negation_llm_provider || "off").toLowerCase();
    const used = phenotypes.some((item) => item.metadata?.context_method === "llm_qc");
    statuses.push({ message: `Negation ${providerLabel(provider)} LLM 호출${used ? "성공" : "실패"}`, tone: used ? "success" : "error" });
  }
  return statuses;
}

function extractionLlmRequested(options) {
  const provider = String(options.llm_provider || "off").toLowerCase();
  return provider !== "off" && (Boolean(options.use_llm) || String(options.protocol || "").toLowerCase() === "p3_llm_selection");
}

function negationLlmRequested(options) {
  const provider = String(options.negation_llm_provider || "off").toLowerCase();
  return provider !== "off" && String(options.negation_mode || "").toLowerCase() === "llm_qc";
}

function showLlmStatus(message, tone) {
  const box = $("#llm-status");
  box.className = `llm-status ${tone === "success" ? "is-success" : "is-error"}`;
  box.textContent = message;
  box.hidden = false;
}

function hideLlmStatus() { $("#llm-status").hidden = true; }

function providerLabel(provider) {
  return provider === "openai" ? "OpenAI" : provider === "ollama" ? "Ollama" : provider;
}

function isFinalSelectedPhenotype(item) {
  return item?.metadata?.final_selected !== false;
}

function phenotypeContextPreview(phenotypes) {
  if (!phenotypes?.length) return "";
  const rows = phenotypes.slice(0, 4).map((item) => {
    const selected = isFinalSelectedPhenotype(item);
    const label = item.metadata?.context_label || "present";
    const trigger = item.metadata?.context_trigger ? ` · trigger: ${item.metadata.context_trigger}` : "";
    const badge = selected ? "Used" : "Not used";
    return `
      <li class="${selected ? "" : "is-excluded"}">
        <span>${escapeHtml(badge)}</span>
        ${escapeHtml(item.name)} · ${escapeHtml(label)}${escapeHtml(trigger)}
      </li>
    `;
  }).join("");
  return `<ul class="phenotype-context-list">${rows}</ul>`;
}

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
