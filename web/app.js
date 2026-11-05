const form = document.querySelector("#ask-form");
const questionInput = document.querySelector("#question");
const askButton = document.querySelector("#ask-button");
const apiTokenInput = document.querySelector("#api-token");
const emptyState = document.querySelector("#empty-state");
const resultSection = document.querySelector("#result-section");
const resultTitle = document.querySelector("#result-title");
const resultStatus = document.querySelector("#result-status");
const errorBox = document.querySelector("#error-box");
const summaryGrid = document.querySelector("#summary-grid");
const resultHead = document.querySelector("#result-head");
const resultBody = document.querySelector("#result-body");
const traceDetails = document.querySelector("#trace-details");
const sqlText = document.querySelector("#sql-text");
const answerSummary = document.querySelector("#answer-summary");
const chartPanel = document.querySelector("#chart-panel");
const chartCanvas = document.querySelector("#result-chart");
const chartNote = document.querySelector("#chart-note");
const identityPill = document.querySelector("#identity-pill");
const historyList = document.querySelector("#history-list");
const clearHistoryButton = document.querySelector("#clear-history");
const followupRow = document.querySelector("#followup-row");
const usePreviousInput = document.querySelector("#use-previous");
const previousQuestionText = document.querySelector("#previous-question");
const HISTORY_KEY = "vg-analytics-query-history";
let lastSuccessfulQuestion = "";

renderHistory();
apiTokenInput.addEventListener("change", loadIdentity);
clearHistoryButton.addEventListener("click", () => {
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
});

document.querySelectorAll(".example").forEach((button) => {
  button.addEventListener("click", () => {
    questionInput.value = button.dataset.question;
    questionInput.focus();
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (!question) return;

  setLoading(true);
  showResultShell(question);
  try {
    const headers = { "Content-Type": "application/json" };
    if (apiTokenInput.value.trim()) headers["X-API-Key"] = apiTokenInput.value.trim();
    const response = await fetch("/ask", {
      method: "POST",
      headers,
      body: JSON.stringify({
        question,
        previous_question: usePreviousInput.checked ? lastSuccessfulQuestion : null,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "问数服务暂时不可用");
    renderAnswer(payload);
    saveHistory(question, payload.status);
    loadIdentity();
    if (payload.status === "success") {
      lastSuccessfulQuestion = question;
      previousQuestionText.textContent = `上一问：${question}`;
      followupRow.classList.remove("hidden");
      usePreviousInput.checked = false;
    }
  } catch (error) {
    renderError(error.message || "请求失败，请稍后重试");
  } finally {
    setLoading(false);
  }
});

function setLoading(loading) {
  askButton.disabled = loading;
  askButton.innerHTML = loading ? "查询中..." : '查询数据 <span aria-hidden="true">→</span>';
}

function showResultShell(question) {
  emptyState.classList.add("hidden");
  resultSection.classList.remove("hidden");
  resultTitle.textContent = question;
  resultStatus.textContent = "查询中";
  errorBox.classList.add("hidden");
  summaryGrid.innerHTML = "";
  answerSummary.classList.add("hidden");
  chartPanel.classList.add("hidden");
  resultHead.innerHTML = "";
  resultBody.innerHTML = '<tr><td>正在获取数据…</td></tr>';
  traceDetails.classList.add("hidden");
}

function renderAnswer(answer) {
  resultStatus.textContent = answer.status === "success" ? "查询成功" : answer.status;
  if (answer.status !== "success") {
    renderError(answer.message || "这个问题暂时无法回答");
  }
  summaryGrid.innerHTML = [
    ["指标", (answer.metrics || []).join("、") || "-"],
    ["数据集", (answer.datasets || []).join("、") || "-"],
    ["指标口径", answer.metric_definition || "-"],
  ].map(([label, value]) => `<div class="summary-item"><div class="summary-label">${escapeHtml(label)}</div><div class="summary-value">${escapeHtml(value)}</div></div>`).join("");

  const rows = Array.isArray(answer.rows) ? answer.rows : [];
  if (answer.status === "success") {
    answerSummary.textContent = buildSummary(rows);
    answerSummary.classList.remove("hidden");
  }
  if (!rows.length) {
    resultHead.innerHTML = "";
    resultBody.innerHTML = '<tr><td>没有找到符合条件的数据</td></tr>';
  } else {
    const columns = Object.keys(rows[0]);
    resultHead.innerHTML = `<tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>`;
    resultBody.innerHTML = rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(formatValue(row[column]))}</td>`).join("")}</tr>`).join("");
    renderChart(rows, columns);
  }

  if (answer.sql) {
    sqlText.textContent = answer.sql;
    traceDetails.classList.remove("hidden");
  }
}

function buildSummary(rows) {
  if (!rows.length) return "本次查询没有找到符合条件的数据。";
  const first = rows[0];
  const numericKey = Object.keys(first).find((key) => typeof first[key] === "number");
  const labelKey = Object.keys(first).find((key) => typeof first[key] === "string");
  if (numericKey && labelKey) {
    return `共返回 ${rows.length} 条数据。第一项为 ${first[labelKey]}，${numericKey} 为 ${formatValue(first[numericKey])}。`;
  }
  if (numericKey) return `查询结果：${numericKey} 为 ${formatValue(first[numericKey])}。`;
  return `共返回 ${rows.length} 条数据。`;
}

function renderChart(rows, columns) {
  const numericKey = columns.find((key) => rows.some((row) => typeof row[key] === "number"));
  const labelKey = columns.find((key) => key !== numericKey && rows.some((row) => row[key] !== null));
  if (!numericKey || !labelKey || rows.length > 20) return;
  const items = rows.slice(0, 12);
  const context = chartCanvas.getContext("2d");
  const width = chartCanvas.clientWidth || 900;
  const height = 260;
  const ratio = window.devicePixelRatio || 1;
  chartCanvas.width = width * ratio;
  chartCanvas.height = height * ratio;
  context.scale(ratio, ratio);
  context.clearRect(0, 0, width, height);
  const values = items.map((row) => Number(row[numericKey]) || 0);
  const maximum = Math.max(...values, 1);
  const left = 124;
  const barHeight = Math.max(10, Math.min(24, (height - 24) / items.length - 6));
  context.font = "12px -apple-system, BlinkMacSystemFont, sans-serif";
  items.forEach((row, index) => {
    const y = 12 + index * ((height - 20) / items.length);
    const label = String(row[labelKey] ?? "-").slice(0, 16);
    context.fillStyle = "#66737d";
    context.fillText(label, 4, y + barHeight - 3);
    context.fillStyle = "#c9572c";
    context.fillRect(left, y, Math.max(2, (width - left - 72) * values[index] / maximum), barHeight);
    context.fillStyle = "#1e2933";
    context.fillText(formatValue(values[index]), width - 66, y + barHeight - 3);
  });
  chartNote.textContent = `${labelKey} / ${numericKey}`;
  chartPanel.classList.remove("hidden");
}

async function loadIdentity() {
  const token = apiTokenInput.value.trim();
  if (!token) {
    identityPill.textContent = "输入令牌后显示权限";
    return;
  }
  try {
    const response = await fetch("/me", { headers: { "X-API-Key": token } });
    if (!response.ok) throw new Error();
    const user = await response.json();
    const scope = user.role === "admin" ? "全部店铺" : (user.shops.join("、") || "未配置店铺");
    identityPill.textContent = `${user.name} · ${user.role} · ${scope}`;
  } catch {
    identityPill.textContent = "令牌无效";
  }
}

function saveHistory(question, status) {
  const history = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  history.unshift({ question, status, time: new Date().toLocaleString("zh-CN") });
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 10)));
  renderHistory();
}

function renderHistory() {
  const history = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  if (!history.length) {
    historyList.innerHTML = '<p class="history-empty">暂无查询记录</p>';
    return;
  }
  historyList.innerHTML = history.map((item, index) => `
    <div class="history-item">
      <button type="button" class="history-question" data-history-index="${index}">${escapeHtml(item.question)}</button>
      <span class="history-meta">${escapeHtml(item.status)} · ${escapeHtml(item.time)}</span>
    </div>`).join("");
  historyList.querySelectorAll(".history-question").forEach((button) => {
    button.addEventListener("click", () => {
      questionInput.value = history[Number(button.dataset.historyIndex)].question;
      questionInput.focus();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

function renderError(message) {
  errorBox.textContent = message;
  errorBox.classList.remove("hidden");
  resultStatus.textContent = "需要处理";
}

function formatValue(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return value.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  return String(value);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  }[character]));
}
