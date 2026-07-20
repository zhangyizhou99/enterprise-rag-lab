const state = {
  overview: null,
  mode: "keyword",
  searching: false,
  uploading: false,
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
  Object.assign(elements, {
    liveState: document.querySelector("#live-state"),
    refreshButton: document.querySelector("#refresh-button"),
    keywordState: document.querySelector("#keyword-state"),
    hybridState: document.querySelector("#hybrid-state"),
    snapshotLabel: document.querySelector("#snapshot-label"),
    searchForm: document.querySelector("#search-form"),
    queryInput: document.querySelector("#query-input"),
    searchButton: document.querySelector("#search-button"),
    contextToggle: document.querySelector("#context-toggle"),
    limitSelect: document.querySelector("#limit-select"),
    resultsList: document.querySelector("#results-list"),
    resultStatus: document.querySelector("#result-status"),
    retrieverLabel: document.querySelector("#retriever-label"),
    metricRecall: document.querySelector("#metric-recall"),
    metricMrr: document.querySelector("#metric-mrr"),
    metricP95: document.querySelector("#metric-p95"),
    metricLive: document.querySelector("#metric-live"),
    metricScope: document.querySelector("#metric-scope"),
    resultCount: document.querySelector("#result-count"),
    documentTotal: document.querySelector("#document-total"),
    chunkTotal: document.querySelector("#chunk-total"),
    indexedTotal: document.querySelector("#indexed-total"),
    documentTableBody: document.querySelector("#document-table-body"),
    evaluationTableBody: document.querySelector("#evaluation-table-body"),
    uploadForm: document.querySelector("#upload-form"),
    uploadDropzone: document.querySelector("#upload-dropzone"),
    uploadLabel: document.querySelector("#upload-label"),
    fileInput: document.querySelector("#file-input"),
    sourceUriInput: document.querySelector("#source-uri-input"),
    uploadButton: document.querySelector("#upload-button"),
    pipelineReceipt: document.querySelector("#pipeline-receipt"),
    toast: document.querySelector("#toast"),
  });

  bindNavigation();
  bindRetrieval();
  bindUpload();
  elements.refreshButton.addEventListener("click", loadOverview);
  renderIcons();
  loadOverview();
});

function bindNavigation() {
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-view]").forEach((item) => item.classList.remove("is-active"));
      button.classList.add("is-active");
      document.querySelectorAll("[data-view-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.viewPanel !== button.dataset.view;
      });
    });
  });
}

function bindRetrieval() {
  elements.searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    runSearch();
  });
  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.addEventListener("click", () => setMode(button.dataset.mode));
  });
  elements.contextToggle.addEventListener("change", renderSelectedMetrics);
  document.querySelectorAll("[data-query]").forEach((button) => {
    button.addEventListener("click", () => {
      elements.queryInput.value = button.dataset.query;
      elements.queryInput.focus();
    });
  });
}

function bindUpload() {
  elements.fileInput.addEventListener("change", () => {
    const file = elements.fileInput.files[0];
    elements.uploadLabel.textContent = file ? file.name : "选择或拖入文档";
  });
  ["dragenter", "dragover"].forEach((name) => {
    elements.uploadDropzone.addEventListener(name, () => elements.uploadDropzone.classList.add("is-dragging"));
  });
  ["dragleave", "drop"].forEach((name) => {
    elements.uploadDropzone.addEventListener(name, () => elements.uploadDropzone.classList.remove("is-dragging"));
  });
  elements.uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.uploading || !elements.fileInput.files[0]) return;
    state.uploading = true;
    elements.uploadButton.disabled = true;
    elements.uploadButton.querySelector("span").textContent = "处理中...";
    const body = new FormData();
    body.append("file", elements.fileInput.files[0]);
    if (elements.sourceUriInput.value.trim()) body.append("source_uri", elements.sourceUriInput.value.trim());
    try {
      const receipt = await requestJson("/api/documents", { method: "POST", body });
      renderPipelineReceipt(receipt);
      showToast(`接入完成：${receipt.chunk_count} chunks`);
      await loadOverview();
    } catch (error) {
      showToast(error.message, true);
    } finally {
      state.uploading = false;
      elements.uploadButton.disabled = false;
      elements.uploadButton.querySelector("span").textContent = "执行接入流水线";
    }
  });
}

async function loadOverview() {
  elements.refreshButton.disabled = true;
  try {
    state.overview = await requestJson("/api/overview");
    renderOverview();
    elements.liveState.className = "live-state is-ready";
    elements.liveState.querySelector("span:last-child").textContent = "本地服务已连接";
  } catch (error) {
    elements.liveState.className = "live-state is-error";
    elements.liveState.querySelector("span:last-child").textContent = "服务不可用";
    showToast(error.message, true);
  } finally {
    elements.refreshButton.disabled = false;
  }
}

function renderOverview() {
  const { corpus, capabilities, vector_index: vectorIndex, recent_documents: documents } = state.overview;
  setStateTag(elements.keywordState, capabilities.keyword);
  setStateTag(elements.hybridState, capabilities.hybrid);
  elements.snapshotLabel.textContent = vectorIndex ? `snapshot · ${vectorIndex.vector_index_id}` : "snapshot · unavailable";
  elements.documentTotal.textContent = formatInteger(corpus.document_count);
  elements.chunkTotal.textContent = formatInteger(corpus.chunk_count);
  elements.indexedTotal.textContent = `${formatInteger(corpus.keyword_indexed_document_count)} indexed`;
  renderDocuments(documents);
  renderEvaluation();
  renderSelectedMetrics();
  if (!capabilities.hybrid && state.mode === "hybrid") setMode("keyword");
}

function setStateTag(element, ready) {
  element.textContent = ready ? "ready" : "offline";
  element.className = `state-tag ${ready ? "is-ready" : "is-offline"}`;
}

function setMode(mode) {
  if (mode === "hybrid" && state.overview && !state.overview.capabilities.hybrid) {
    showToast("本地向量快照不可用，当前只能运行 BM25", true);
    return;
  }
  state.mode = mode;
  document.querySelectorAll("[data-mode]").forEach((button) => button.classList.toggle("is-selected", button.dataset.mode === mode));
  elements.contextToggle.disabled = mode !== "hybrid";
  if (mode !== "hybrid") elements.contextToggle.checked = false;
  elements.retrieverLabel.textContent = mode === "keyword" ? "BM25 / FTS5 trigram" : "BM25 + E5 / deterministic RRF";
  renderSelectedMetrics();
}

async function runSearch() {
  if (state.searching) return;
  const query = elements.queryInput.value.trim();
  if (query.length < 3) return;
  state.searching = true;
  elements.searchButton.disabled = true;
  elements.searchButton.querySelector("span").textContent = "检索中";
  elements.resultsList.innerHTML = '<div class="loading-card"></div><div class="loading-card"></div><div class="loading-card"></div>';
  elements.resultStatus.textContent = "正在执行检索...";
  try {
    const response = await requestJson("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        mode: state.mode,
        limit: Number(elements.limitSelect.value),
        expand_context: elements.contextToggle.checked,
      }),
    });
    renderResults(response);
  } catch (error) {
    elements.resultsList.innerHTML = emptyMarkup("检索失败", error.message, "triangle-alert");
    elements.resultStatus.textContent = "请求失败";
    showToast(error.message, true);
    renderIcons();
  } finally {
    state.searching = false;
    elements.searchButton.disabled = false;
    elements.searchButton.querySelector("span").textContent = "检索";
  }
}

function renderResults(response) {
  elements.metricLive.textContent = `${response.latency_ms.toFixed(1)} ms`;
  elements.resultCount.textContent = `${response.result_count} results`;
  elements.resultStatus.textContent = response.result_count ? `找到 ${response.result_count} 条候选证据` : "没有命中候选证据";
  elements.retrieverLabel.textContent = response.retriever;
  if (!response.results.length) {
    elements.resultsList.innerHTML = emptyMarkup("没有匹配结果", "尝试更具体的术语或切换检索模式。", "search-x");
    renderIcons();
    return;
  }
  elements.resultsList.innerHTML = response.results.map((result, index) => resultMarkup(result, index)).join("");
  renderIcons();
}

function resultMarkup(result, index) {
  const heading = Array.isArray(result.heading_path) && result.heading_path.length ? result.heading_path.join(" / ") : "无标题路径";
  const pages = result.page_start ? ` · page ${result.page_start}${result.page_end && result.page_end !== result.page_start ? `–${result.page_end}` : ""}` : "";
  const text = result.context_text || result.text || "";
  const source = result.source_uri
    ? `<a class="source-link" href="${escapeAttribute(result.source_uri)}" target="_blank" rel="noreferrer">原文 <i data-lucide="external-link"></i></a>`
    : '<span class="source-link">local source</span>';
  const scores = [];
  if (result.rrf_score !== undefined) scores.push(`<span class="score-chip is-acid">RRF ${formatScore(result.rrf_score)}</span>`);
  if (result.keyword_rank) scores.push(`<span class="score-chip">BM25 #${result.keyword_rank} · ${formatScore(result.keyword_score)}</span>`);
  if (result.vector_rank) scores.push(`<span class="score-chip is-blue">Vector #${result.vector_rank} · ${formatScore(result.vector_score)}</span>`);
  if (result.score !== undefined && result.rrf_score === undefined) scores.push(`<span class="score-chip">BM25 ${formatScore(result.score)}</span>`);
  if (Array.isArray(result.expanded_chunks) && result.expanded_chunks.length) {
    scores.push(`<span class="score-chip is-blue">+${result.expanded_chunks.length} neighbors · ${result.context_character_count} chars</span>`);
  }
  return `
    <article class="result-card" style="animation-delay:${index * 45}ms">
      <div class="rank-cell">${String(result.rank).padStart(2, "0")}</div>
      <div class="result-content">
        <div class="result-head"><h3>${escapeHtml(result.title || "Untitled")}</h3>${source}</div>
        <div class="location-line">${escapeHtml(heading + pages)}</div>
        <p class="evidence-preview">${escapeHtml(result.text || text)}</p>
        <div class="score-row">${scores.join("")}</div>
        <details class="evidence-details"><summary>展开完整${result.context_text ? "上下文" : "证据"}</summary><pre>${escapeHtml(text)}</pre></details>
      </div>
    </article>`;
}

function renderSelectedMetrics() {
  if (!state.overview) return;
  const reportId = state.mode === "keyword" ? "keyword" : (elements.contextToggle.checked ? "rrf-context" : "rrf");
  const report = state.overview.evaluation_reports.find((item) => item.id === reportId);
  if (!report) {
    elements.metricRecall.textContent = "--";
    elements.metricMrr.textContent = "--";
    elements.metricP95.textContent = "--";
    return;
  }
  const expanded = reportId === "rrf-context";
  elements.metricRecall.textContent = formatMetric(expanded ? report.expanded_evidence_recall_at_k : report.recall_at_k);
  elements.metricMrr.textContent = formatMetric(expanded ? report.expanded_evidence_mrr : report.mrr);
  elements.metricP95.textContent = `${report.p95_latency_ms.toFixed(1)} ms`;
  elements.metricScope.textContent = expanded ? "扩展证据" : "锚点检索";
}

function renderDocuments(documents) {
  if (!documents.length) {
    elements.documentTableBody.innerHTML = '<tr><td colspan="5">尚无文档</td></tr>';
    return;
  }
  elements.documentTableBody.innerHTML = documents.map((document) => {
    const source = document.source_uri
      ? `<a class="table-source" href="${escapeAttribute(document.source_uri)}" target="_blank" rel="noreferrer">open</a>`
      : "local";
    return `<tr>
      <td><span class="document-title">${escapeHtml(document.title)}</span><span class="document-id">${escapeHtml(document.document_id)}</span></td>
      <td>${escapeHtml(document.source_format)}</td>
      <td><span class="state-tag is-ready">${escapeHtml(document.index_status)}</span></td>
      <td>${escapeHtml(formatDate(document.updated_at))}</td>
      <td>${source}</td>
    </tr>`;
  }).join("");
}

function renderEvaluation() {
  const reports = state.overview.evaluation_reports;
  if (!reports.length) {
    elements.evaluationTableBody.innerHTML = '<tr><td colspan="7">没有找到评测报告</td></tr>';
    return;
  }
  elements.evaluationTableBody.innerHTML = reports.map((report) => `<tr>
    <td><strong>${escapeHtml(report.label)}</strong></td>
    <td>${formatMetric(report.hit_rate_at_k)}</td>
    <td>${formatMetric(report.recall_at_k)}</td>
    <td>${formatMetric(report.mrr)}</td>
    <td>${formatMetric(report.expanded_evidence_recall_at_k)}</td>
    <td>${formatMetric(report.expanded_evidence_mrr)}</td>
    <td>${report.p95_latency_ms == null ? "--" : `${report.p95_latency_ms.toFixed(1)} ms`}</td>
  </tr>`).join("");
}

function renderPipelineReceipt(receipt) {
  elements.pipelineReceipt.innerHTML = `
    <div class="receipt-header">
      <div><strong>流水线执行完成</strong><code>${escapeHtml(receipt.document_id)}</code></div>
      <span class="success-stamp">SUCCEEDED</span>
    </div>
    <div class="receipt-grid">
      <div class="receipt-stat"><span>Source blocks</span><b>${receipt.source_block_count}</b></div>
      <div class="receipt-stat"><span>Cleaned blocks</span><b>${receipt.cleaned_block_count}</b></div>
      <div class="receipt-stat"><span>Modified</span><b>${receipt.modified_block_count}</b></div>
      <div class="receipt-stat"><span>Removed</span><b>${receipt.removed_block_count}</b></div>
      <div class="receipt-stat"><span>Chunks</span><b>${receipt.chunk_count}</b></div>
      <div class="receipt-stat"><span>Tables</span><b>${receipt.table_count}</b></div>
    </div>
    <div class="table-callout">识别到 <strong>${receipt.table_count}</strong> 张逻辑表；详细页码与 bbox 已保存在解析 metadata。</div>`;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  let payload;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    const detail = payload && payload.detail;
    const message = typeof detail === "string" ? detail : detail && detail.message;
    throw new Error(message || `Request failed with HTTP ${response.status}`);
  }
  return payload;
}

function showToast(message, error = false) {
  elements.toast.textContent = message;
  elements.toast.className = `toast is-visible${error ? " is-error" : ""}`;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => { elements.toast.className = "toast"; }, 3200);
}

function emptyMarkup(title, message, icon) {
  return `<div class="empty-state"><i data-lucide="${icon}"></i><strong>${escapeHtml(title)}</strong><span>${escapeHtml(message)}</span></div>`;
}

function renderIcons() {
  if (window.lucide) window.lucide.createIcons({ attrs: { "stroke-width": 1.8 } });
}

function formatMetric(value) { return value == null ? "--" : Number(value).toFixed(3); }
function formatScore(value) { return value == null ? "--" : Number(value).toFixed(value < 0.1 ? 4 : 3); }
function formatInteger(value) { return new Intl.NumberFormat("zh-CN").format(value || 0); }
function formatDate(value) {
  if (!value) return "--";
  const parsed = new Date(value.endsWith("Z") ? value : `${value}Z`);
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(parsed);
}
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
}
function escapeAttribute(value) { return escapeHtml(value); }