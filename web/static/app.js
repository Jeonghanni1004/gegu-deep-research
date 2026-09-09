/* 深研 · AI 智能投研助手 — 对话工作台 */

const STORAGE_KEY = "shenyan_chats_v1";

const EXAMPLE_PROMPTS = [
  { label: "个股深研", text: "帮我深度研究 601127 赛力斯，梳理当前最值得关注的矛盾。" },
  { label: "财报解读", text: "概括贵州茅台最近一期财报的关键变化，并标出需要验证的假设。" },
  { label: "多空对比", text: "用多空辩论视角对比赛力斯销量叙事与估值压力，给出证据链。" },
  { label: "风险扫描", text: "如果我准备建仓新能源整车，当前最需要警惕的三类风险是什么？" },
];

const SUGGESTION_BANK = [
  "展开核心矛盾的证据来源",
  "对比同业估值与增速",
  "把结论改成更谨慎的口径",
  "补充近期市场信息面变化",
];

const FOLLOWUP_BANK = [
  "这份结论对持仓周期有什么影响？",
  "哪些假设一旦证伪会推翻判断？",
  "能否把关键证据做成一页摘要？",
  "下一步最该跟踪哪些数据？",
];

const state = {
  chats: [],
  activeId: null,
  attachments: [],
  quote: null,
  docOpen: false,
  sidebarCollapsed: false,
  voiceListening: false,
  recognition: null,
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function uid() {
  return `c_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 3200);
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/** 将文本中的 URL / 【引用】 渲染为可点击链接 */
function renderRichText(text) {
  const escaped = escapeHtml(text);
  return escaped
    .replace(
      /(https?:\/\/[^\s<]+)/g,
      '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
    )
    .replace(
      /【([^】]+)】/g,
      '<a class="cite" href="#" data-cite="$1">【$1】</a>'
    );
}

function greetingByTime() {
  const h = new Date().getHours();
  if (h < 5) return "夜深了，今天想研究哪只标的？";
  if (h < 11) return "早上好，今天想研究哪只标的？";
  if (h < 14) return "中午好，今天想研究哪只标的？";
  if (h < 18) return "下午好，今天想研究哪只标的？";
  return "晚上好，今天想研究哪只标的？";
}

function loadStore() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const data = JSON.parse(raw);
    state.chats = data.chats || [];
    state.activeId = data.activeId || null;
  } catch {
    state.chats = [];
  }
}

function saveStore() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ chats: state.chats, activeId: state.activeId })
  );
}

function activeChat() {
  return state.chats.find((c) => c.id === state.activeId) || null;
}

function createChat(title = "新对话") {
  const chat = {
    id: uid(),
    title,
    updatedAt: Date.now(),
    messages: [],
    document: null,
  };
  state.chats.unshift(chat);
  state.activeId = chat.id;
  saveStore();
  return chat;
}

function ensureChat() {
  let chat = activeChat();
  if (!chat) chat = createChat();
  return chat;
}

/* —— UI: sidebar / layout —— */
function setSidebarCollapsed(collapsed) {
  state.sidebarCollapsed = collapsed;
  $("#app").classList.toggle("sidebar-collapsed", collapsed);
  $("#btn-reopen-sidebar").classList.toggle("hidden", !collapsed);
}

function setDocOpen(open) {
  state.docOpen = open;
  $("#app").classList.toggle("doc-open", open);
  $("#doc-panel").classList.toggle("hidden", !open);
  if (!open) {
    hideSelBubble();
    hideDocCtx();
  }
}

function renderHistory() {
  const list = $("#history-list");
  if (!state.chats.length) {
    list.innerHTML = `<div class="history-empty">暂无历史对话<br/>发起一次研究后会出现在这里</div>`;
    return;
  }
  const today = startOfDay(Date.now());
  const groups = { 今天: [], 更早: [] };
  for (const c of state.chats) {
    (c.updatedAt >= today ? groups["今天"] : groups["更早"]).push(c);
  }
  list.innerHTML = Object.entries(groups)
    .filter(([, items]) => items.length)
    .map(
      ([label, items]) => `
      <div class="history-group">${label}</div>
      ${items
        .map(
          (c) => `
        <button type="button" class="history-item ${c.id === state.activeId ? "active" : ""}" data-id="${c.id}">
          <span class="dot"></span>
          <span>${escapeHtml(c.title)}</span>
        </button>`
        )
        .join("")}`
    )
    .join("");

  $$(".history-item", list).forEach((btn) => {
    btn.addEventListener("click", () => {
      state.activeId = btn.dataset.id;
      saveStore();
      renderAll();
      if (window.matchMedia("(max-width: 960px)").matches) setSidebarCollapsed(true);
    });
  });
}

function startOfDay(ts) {
  const d = new Date(ts);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

function renderHomePrompts() {
  $("#prompt-grid").innerHTML = EXAMPLE_PROMPTS.map(
    (p) => `
    <button type="button" class="prompt-card" data-text="${escapeHtml(p.text)}">
      <div class="label">${escapeHtml(p.label)}</div>
      <div class="text">${escapeHtml(p.text)}</div>
    </button>`
  ).join("");
  $$(".prompt-card").forEach((btn) => {
    btn.addEventListener("click", () => sendMessage(btn.dataset.text));
  });
}

function showHomeOrChat() {
  const chat = activeChat();
  const hasMsgs = chat && chat.messages.length > 0;
  $("#view-home").classList.toggle("hidden", hasMsgs);
  $("#view-chat").classList.toggle("hidden", !hasMsgs);
  $("#chat-title").textContent = chat?.title || "新对话";
}

function renderMessages() {
  const chat = activeChat();
  const box = $("#messages");
  if (!chat || !chat.messages.length) {
    box.innerHTML = "";
    return;
  }
  box.innerHTML = chat.messages
    .map((m) => {
      if (m.role === "typing") {
        return `<div class="msg assistant" data-typing="1">
          <div class="msg-avatar">深</div>
          <div class="msg-body"><div class="bubble typing"><span></span><span></span><span></span></div></div>
        </div>`;
      }
      const quote = m.quote
        ? `<div class="msg-quote-ref">${escapeHtml(m.quote)}</div>`
        : "";
      const attaches =
        m.attachments?.length
          ? `<div class="attach-chips">${m.attachments
              .map((a) =>
                a.kind === "image"
                  ? `<span class="attach-chip"><img src="${a.url}" alt="" />${escapeHtml(a.name)}</span>`
                  : `<span class="attach-chip">📎 ${escapeHtml(a.name)}</span>`
              )
              .join("")}</div>`
          : "";
      const follow =
        m.followups?.length
          ? `<div class="followups"><div class="chip-label">追问建议</div>${m.followups
              .map((f) => `<button type="button" class="followup-btn" data-q="${escapeHtml(f)}">${escapeHtml(f)}</button>`)
              .join("")}</div>`
          : "";
      const suggest =
        m.suggestions?.length
          ? `<div class="suggestions"><div class="chip-label">建议回答</div>${m.suggestions
              .map((s) => `<button type="button" class="suggest-btn" data-q="${escapeHtml(s)}">${escapeHtml(s)}</button>`)
              .join("")}</div>`
          : "";
      const docBtn = m.hasDoc
        ? `<button type="button" class="doc-open-btn" data-open-doc="1">📄 打开分析文档 · 划词自动引用提问</button>`
        : "";
      return `<div class="msg ${m.role}">
        <div class="msg-avatar">${m.role === "user" ? "你" : "深"}</div>
        <div class="msg-body">
          ${quote}
          <div class="bubble">${renderRichText(m.content)}${attaches}</div>
          ${docBtn}${follow}${suggest}
        </div>
      </div>`;
    })
    .join("");

  box.querySelectorAll(".followup-btn, .suggest-btn").forEach((btn) => {
    btn.addEventListener("click", () => sendMessage(btn.dataset.q));
  });
  box.querySelectorAll("[data-open-doc]").forEach((btn) => {
    btn.addEventListener("click", () => {
      renderDocument();
      setDocOpen(true);
    });
  });
  box.querySelectorAll("a[data-cite]").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      toast(`引用锚点：${a.dataset.cite}`);
      renderDocument();
      setDocOpen(true);
    });
  });

  const scroller = $("#view-chat");
  scroller.scrollTop = scroller.scrollHeight;
}

function renderDocument() {
  const chat = activeChat();
  const doc = chat?.document;
  if (!doc) {
    $("#doc-title").textContent = "未命名分析";
    $("#doc-meta").textContent = "";
    $("#doc-editor").innerHTML = "";
    return;
  }
  $("#doc-title").textContent = doc.title;
  $("#doc-meta").textContent = `${doc.symbol || "综合"} · 更新于 ${formatTime(doc.updatedAt)} · 划词自动引用到对话框`;
  if ($("#doc-editor").dataset.boundId !== chat.id) {
    $("#doc-editor").innerHTML = doc.html;
    $("#doc-editor").dataset.boundId = chat.id;
  }
}

function formatTime(ts) {
  return new Date(ts).toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderAttachments() {
  const box = $("#attach-preview");
  if (!state.attachments.length) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.classList.remove("hidden");
  box.innerHTML = state.attachments
    .map(
      (a, i) => `
    <span class="item">
      ${a.kind === "image" ? `<img src="${a.url}" alt="" />` : "📎"}
      ${escapeHtml(a.name)}
      <button type="button" class="rm" data-i="${i}" aria-label="移除">×</button>
    </span>`
    )
    .join("");
  $$(".rm", box).forEach((btn) => {
    btn.addEventListener("click", () => {
      const item = state.attachments[+btn.dataset.i];
      if (item?.url?.startsWith("blob:")) URL.revokeObjectURL(item.url);
      state.attachments.splice(+btn.dataset.i, 1);
      renderAttachments();
      syncSendEnabled();
    });
  });
}

function renderQuoteBar() {
  const bar = $("#quote-bar");
  if (!state.quote) {
    bar.classList.add("hidden");
    return;
  }
  bar.classList.remove("hidden");
  $("#quote-text").textContent = state.quote;
}

function syncSendEnabled() {
  const text = $("#composer-input").value.trim();
  $("#btn-send").disabled = !text && !state.attachments.length;
}

function renderAll() {
  renderHistory();
  showHomeOrChat();
  renderMessages();
  renderDocument();
  renderQuoteBar();
  renderAttachments();
  syncSendEnabled();
  if (activeChat()?.document && state.docOpen) setDocOpen(true);
  else if (!activeChat()?.document) setDocOpen(false);
}

/* —— Composer —— */
function autoResizeInput() {
  const el = $("#composer-input");
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
}

function addFiles(fileList, kind) {
  for (const file of fileList) {
    const url = kind === "image" ? URL.createObjectURL(file) : null;
    state.attachments.push({
      id: uid(),
      name: file.name,
      kind,
      url,
      size: file.size,
    });
  }
  renderAttachments();
  syncSendEnabled();
}

function clearQuote() {
  state.quote = null;
  renderQuoteBar();
  const input = $("#composer-input");
  input.placeholder = "输入研究问题，例如：分析赛力斯的核心矛盾…";
}

async function sendMessage(textOverride) {
  const input = $("#composer-input");
  const text = (textOverride ?? input.value).trim();
  if (!text && !state.attachments.length) return;

  const chat = ensureChat();
  const quote = state.quote;
  const attachments = [...state.attachments];

  if (!textOverride) {
    input.value = "";
    autoResizeInput();
  }
  state.attachments = [];
  clearQuote();
  renderAttachments();

  if (chat.title === "新对话" && text) {
    chat.title = text.slice(0, 22) + (text.length > 22 ? "…" : "");
  }

  chat.messages = chat.messages.filter((m) => m.role !== "typing");
  chat.messages.push({
    role: "user",
    content: text || "（已上传附件）",
    quote,
    attachments,
    ts: Date.now(),
  });
  chat.updatedAt = Date.now();
  chat.messages.push({ role: "typing" });
  saveStore();
  renderAll();

  const reply = await generateReply(text, chat, quote, attachments);
  chat.messages = chat.messages.filter((m) => m.role !== "typing");
  chat.messages.push(reply.message);
  if (reply.document) {
    chat.document = reply.document;
    $("#doc-editor").dataset.boundId = "";
  }
  chat.updatedAt = Date.now();
  saveStore();
  renderAll();
  if (reply.document) {
    setDocOpen(true);
    renderDocument();
  }
}

function pick(arr, n) {
  const copy = [...arr].sort(() => Math.random() - 0.5);
  return copy.slice(0, n);
}

function detectSymbol(text) {
  const m = text.match(/\b(60\d{4}|00\d{4}|30\d{4}|68\d{4})\b/);
  if (m) return m[1];
  if (/茅台|600519/.test(text)) return "600519";
  if (/赛力斯|601127/.test(text)) return "601127";
  return null;
}

async function tryFetchStudy(symbol) {
  try {
    const res = await fetch(`/api/research/${symbol}`);
    if (!res.ok) return null;
    const data = await res.json();
    return data.snapshot || data;
  } catch {
    return null;
  }
}

async function generateReply(text, chat, quote, attachments) {
  await sleep(700 + Math.random() * 600);

  const symbol = detectSymbol(text);
  let snapshot = null;
  if (symbol) snapshot = await tryFetchStudy(symbol);

  const attachNote = attachments.length
    ? `\n\n已收到 ${attachments.length} 个附件（${attachments.map((a) => a.name).join("、")}），我会在文档中结合引用。`
    : "";
  const quoteNote = quote
    ? `\n\n针对你引用的段落「${quote.slice(0, 80)}${quote.length > 80 ? "…" : ""}」，我补充如下分析。`
    : "";

  let content;
  let docHtml;
  let title;
  let symLabel = symbol || "综合";

  if (snapshot) {
    const report = snapshot.report || {};
    const judgment = snapshot.judgment || {};
    const fa = snapshot.final_analyst || {};
    const signals = (report.research_signals || []).slice(0, 4);
    const headline =
      report.cover_title ||
      report.verdict?.headline ||
      fa.core_thesis?.text ||
      "见右侧分析文档";
    title = `${snapshot.symbol} · ${snapshot.name} 研究简报`;
    content =
      `已完成对 【${snapshot.symbol} ${snapshot.name}】 的结构化研究整理（截至 ${snapshot.as_of || "最新"}）。` +
      `\n\n当前最值得关注的变化：${headline}` +
      `\n\n我已生成可编辑的分析文档，可在右侧修改，或选中段落后「引用提问」。` +
      `\n相关材料也可参考：https://quote.eastmoney.com/${snapshot.symbol}.html` +
      quoteNote +
      attachNote;
    docHtml = buildDocFromSnapshot(snapshot, signals, judgment, report, fa);
  } else {
    title = `${text.slice(0, 16) || "投研"}分析`;
    symLabel = symbol || "主题研究";
    content =
      `我已围绕你的问题整理了一份分析文档。` +
      `\n\n核心判断会标注证据锚点（如【销量验证】【估值压力】），可点击跳转到文档对应位置。` +
      `\n公开行情可参考：https://quote.eastmoney.com/center/gridlist.html` +
      quoteNote +
      attachNote;
    docHtml = buildMockDoc(text, quote, symbol);
  }

  return {
    message: {
      role: "assistant",
      content,
      hasDoc: true,
      followups: pick(FOLLOWUP_BANK, 3),
      suggestions: pick(SUGGESTION_BANK, 2),
      ts: Date.now(),
    },
    document: {
      title,
      symbol: symLabel,
      html: docHtml,
      updatedAt: Date.now(),
    },
  };
}

function buildDocFromSnapshot(snapshot, signals, judgment, report, fa) {
  const signalHtml = signals
    .map(
      (s) =>
        `<li><strong>${escapeHtml(s.headline || s.title || s.label || "信号")}</strong> — ${escapeHtml(s.agent_insight || s.summary || s.note || "")}</li>`
    )
    .join("");
  const headline =
    report?.cover_title || report?.verdict?.headline || fa?.core_thesis?.text || "—";
  const tension =
    report?.verdict?.core_tension ||
    report?.executive?.core_tension ||
    "见 Final Judgment 细节。";
  const strength =
    report?.judgment?.strength_label ||
    judgment?.assessment_strength ||
    report?.verdict?.assessment_label ||
    "—";
  const thesis = fa?.core_thesis?.text || report?.core_view || "";
  return `
    <h1>${escapeHtml(snapshot.symbol)} ${escapeHtml(snapshot.name)}</h1>
    <p><em>生成自本地 grounded artifacts · 可编辑</em></p>
    <h2>一句话 Insight</h2>
    <blockquote>${escapeHtml(headline)}</blockquote>
    <h2 id="core">核心矛盾</h2>
    <p>${escapeHtml(tension)}</p>
    <h2>Research Signals</h2>
    <ul>${signalHtml || "<li>暂无信号列表</li>"}</ul>
    <h2 id="judgment">判断口径</h2>
    <p>强度：<strong>${escapeHtml(strength)}</strong></p>
    <p>${escapeHtml(thesis)}</p>
    <h2>下一步</h2>
    <ol>
      <li>核验关键证据是否仍成立（【销量验证】）</li>
      <li>跟踪估值与预期差（【估值压力】）</li>
      <li>用引用提问继续追问文档中任意段落</li>
    </ol>
  `;
}

function buildMockDoc(text, quote, symbol) {
  const topic = escapeHtml(text || "投研问题");
  return `
    <h1>${symbol ? escapeHtml(symbol) + " · " : ""}分析文档</h1>
    <p><em>默认输出可编辑分析稿 · 参考豆包文档侧栏交互</em></p>
    <h2>问题重述</h2>
    <p>${topic}</p>
    ${quote ? `<h2>引用上下文</h2><blockquote>${escapeHtml(quote)}</blockquote>` : ""}
    <h2 id="core">核心观点</h2>
    <p>当前叙事的关键在于<strong>基本面验证速度</strong>与<strong>预期定价</strong>是否匹配。建议把研究拆成：事实层 → 推导层 → 可证伪假设。</p>
    <h2>证据框架</h2>
    <ul>
      <li><a href="#core">【销量验证】</a>：量、价、库存是否同向改善</li>
      <li>【估值压力】：隐含增长率是否过高</li>
      <li>【外部冲击】：政策、竞争与资金面噪声</li>
    </ul>
    <h2>情景推演</h2>
    <ol>
      <li><strong>基准</strong>：兑现进度符合一致预期，波动来自交易层面</li>
      <li><strong>乐观</strong>：边际改善超预期，估值扩张有支撑</li>
      <li><strong>谨慎</strong>：验证滞后，预期下修主导定价</li>
    </ol>
    <h2>可执行跟踪清单</h2>
    <p>优先跟踪高频销量/订单、毛利率斜率、以及机构预期修正方向。选中任意段落即可「引用提问」。</p>
  `;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/* —— Voice —— */
function initVoice() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const btn = $("#btn-voice");
  if (!SR) {
    btn.addEventListener("click", () => toast("当前浏览器不支持语音输入", true));
    return;
  }
  const rec = new SR();
  rec.lang = "zh-CN";
  rec.continuous = false;
  rec.interimResults = true;
  state.recognition = rec;

  rec.onresult = (e) => {
    let transcript = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      transcript += e.results[i][0].transcript;
    }
    const input = $("#composer-input");
    input.value = (input.value + transcript).trim();
    autoResizeInput();
    syncSendEnabled();
  };
  rec.onerror = () => {
    stopVoice();
    toast("语音识别已中断", true);
  };
  rec.onend = () => stopVoice();

  btn.addEventListener("click", () => {
    if (state.voiceListening) stopVoice();
    else startVoice();
  });
}

function startVoice() {
  try {
    state.recognition.start();
    state.voiceListening = true;
    $("#btn-voice").classList.add("recording");
    $("#btn-voice").setAttribute("aria-pressed", "true");
    toast("正在聆听…");
  } catch {
    toast("无法启动麦克风", true);
  }
}

function stopVoice() {
  state.voiceListening = false;
  $("#btn-voice").classList.remove("recording");
  $("#btn-voice").setAttribute("aria-pressed", "false");
  try {
    state.recognition?.stop();
  } catch {
    /* ignore */
  }
}

/* —— Doc quote selection：划词自动引用 + 右键复制 —— */
function getDocSelectionText() {
  const editor = $("#doc-editor");
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) return "";
  if (!editor.contains(sel.anchorNode) && !editor.contains(sel.focusNode)) return "";
  return sel.toString().trim();
}

function getSelectionAnchorRect() {
  const sel = window.getSelection();
  if (!sel || !sel.rangeCount) return null;
  const range = sel.getRangeAt(0);
  const rects = range.getClientRects();
  if (rects.length) {
    const first = rects[0];
    const last = rects[rects.length - 1];
    return {
      left: (first.left + last.right) / 2,
      top: first.top,
      bottom: last.bottom,
    };
  }
  const box = range.getBoundingClientRect();
  if (!box.width && !box.height) return null;
  return { left: box.left + box.width / 2, top: box.top, bottom: box.bottom };
}

function hideSelBubble() {
  $("#sel-bubble").classList.add("hidden");
}

function hideDocCtx() {
  $("#doc-ctx").classList.add("hidden");
}

function flashQuoteBar() {
  const bar = $("#quote-bar");
  bar.classList.remove("flash");
  void bar.offsetWidth;
  bar.classList.add("flash");
  clearTimeout(flashQuoteBar._t);
  flashQuoteBar._t = setTimeout(() => bar.classList.remove("flash"), 900);
}

/** 划词即写入底部对话框引用，无需点按钮 */
function autoQuoteSelection() {
  const text = getDocSelectionText();
  if (!state.docOpen || text.length < 2) {
    hideSelBubble();
    return false;
  }
  const changed = state.quote !== text;
  state.quote = text;
  renderQuoteBar();
  if (changed) flashQuoteBar();
  showSelBubble();
  // 焦点回到底部对话框，用户可直接输入
  clearTimeout(autoQuoteSelection._focusT);
  autoQuoteSelection._focusT = setTimeout(() => {
    const input = $("#composer-input");
    input.placeholder = "针对引用内容继续提问…";
    input.focus({ preventScroll: true });
  }, 120);
  return true;
}

function showSelBubble() {
  const text = state.quote || getDocSelectionText();
  const bubble = $("#sel-bubble");
  if (!state.docOpen || text.length < 2) {
    hideSelBubble();
    return;
  }
  const anchor = getSelectionAnchorRect();
  if (!anchor) {
    hideSelBubble();
    return;
  }
  hideDocCtx();
  bubble.dataset.text = text;
  bubble.classList.remove("hidden");

  const pad = 10;
  const bw = bubble.offsetWidth || 140;
  const bh = bubble.offsetHeight || 40;
  let x = anchor.left;
  let y = anchor.top - 10;
  x = Math.max(pad + bw / 2, Math.min(window.innerWidth - pad - bw / 2, x));
  if (y - bh < pad) y = anchor.bottom + bh + 12;
  bubble.style.left = `${x}px`;
  bubble.style.top = `${y}px`;
}

async function copyText(text, okMsg = "已复制") {
  const t = (text || "").trim();
  if (!t) {
    toast("没有可复制的内容", true);
    return;
  }
  try {
    await navigator.clipboard.writeText(t);
    toast(okMsg);
  } catch {
    toast("复制失败", true);
  }
  hideSelBubble();
  hideDocCtx();
}

function initDocSelection() {
  const editor = $("#doc-editor");
  const bubble = $("#sel-bubble");
  const ctx = $("#doc-ctx");
  let selecting = false;

  const finishSelect = () => {
    clearTimeout(finishSelect._t);
    finishSelect._t = setTimeout(() => {
      if (selecting) return;
      autoQuoteSelection();
    }, 60);
  };

  editor.addEventListener("mousedown", () => {
    selecting = true;
    hideSelBubble();
    hideDocCtx();
  });

  document.addEventListener("mouseup", (e) => {
    if (bubble.contains(e.target) || ctx.contains(e.target)) return;
    selecting = false;
    if (state.docOpen && (editor.contains(e.target) || getDocSelectionText())) {
      finishSelect();
    } else if (!getDocSelectionText()) {
      hideSelBubble();
    }
  });

  document.addEventListener("selectionchange", () => {
    if (selecting || !state.docOpen) return;
    if (getDocSelectionText().length >= 2) finishSelect();
    else hideSelBubble();
  });

  editor.addEventListener("scroll", () => {
    if (!bubble.classList.contains("hidden")) showSelBubble();
  }, { passive: true });

  window.addEventListener("resize", hideSelBubble);
  window.addEventListener("scroll", hideSelBubble, true);

  bubble.addEventListener("mousedown", (e) => e.preventDefault());
  ctx.addEventListener("mousedown", (e) => e.preventDefault());

  bubble.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const text = bubble.dataset.text || state.quote || getDocSelectionText();
    if (btn.dataset.action === "copy") await copyText(text);
  });

  editor.addEventListener("contextmenu", (e) => {
    if (!state.docOpen) return;
    e.preventDefault();
    hideSelBubble();
    const selected = getDocSelectionText();
    if (selected.length >= 2) {
      state.quote = selected;
      renderQuoteBar();
      flashQuoteBar();
    }
    ctx.dataset.text = selected || state.quote || "";
    ctx.classList.remove("hidden");
    const pad = 8;
    const cw = 148;
    const ch = 100;
    let x = e.clientX;
    let y = e.clientY;
    if (x + cw > window.innerWidth - pad) x = window.innerWidth - cw - pad;
    if (y + ch > window.innerHeight - pad) y = window.innerHeight - ch - pad;
    ctx.style.left = `${Math.max(pad, x)}px`;
    ctx.style.top = `${Math.max(pad, y)}px`;

    const hasCopyTarget = (ctx.dataset.text || "").length >= 1;
    const copyBtn = ctx.querySelector("[data-action='copy']");
    if (copyBtn) {
      copyBtn.style.opacity = hasCopyTarget ? "1" : "0.4";
      copyBtn.style.pointerEvents = hasCopyTarget ? "auto" : "none";
    }
  });

  ctx.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const selected = ctx.dataset.text || getDocSelectionText();
    if (btn.dataset.action === "copy") await copyText(selected);
    if (btn.dataset.action === "copy-all") await copyText(editor.innerText, "已复制全文");
  });

  document.addEventListener("click", (e) => {
    if (!ctx.contains(e.target)) hideDocCtx();
    if (!bubble.contains(e.target) && !editor.contains(e.target) && !getDocSelectionText()) {
      hideSelBubble();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      hideSelBubble();
      hideDocCtx();
    }
  });

  editor.addEventListener("input", () => {
    const chat = activeChat();
    if (!chat?.document) return;
    chat.document.html = editor.innerHTML;
    chat.document.updatedAt = Date.now();
    saveStore();
    $("#doc-meta").textContent = `${chat.document.symbol || "综合"} · 更新于 ${formatTime(chat.document.updatedAt)} · 划词自动引用到对话框`;
  });
}

/* —— Boot —— */
function bindEvents() {
  $("#btn-toggle-sidebar").addEventListener("click", () => setSidebarCollapsed(true));
  $("#btn-reopen-sidebar").addEventListener("click", () => setSidebarCollapsed(false));
  $("#btn-new-chat").addEventListener("click", () => {
    createChat();
    setDocOpen(false);
    clearQuote();
    state.attachments = [];
    renderAll();
    $("#composer-input").focus();
  });
  $("#btn-toggle-doc").addEventListener("click", () => {
    if (!activeChat()?.document) {
      toast("当前对话尚无分析文档，先提一个研究问题吧");
      return;
    }
    setDocOpen(!state.docOpen);
    if (state.docOpen) renderDocument();
  });
  $("#btn-close-doc").addEventListener("click", () => setDocOpen(false));
  $("#btn-clear-quote").addEventListener("click", clearQuote);

  $("#composer").addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage();
  });
  $("#composer-input").addEventListener("input", () => {
    autoResizeInput();
    syncSendEnabled();
  });
  $("#composer-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  $("#file-attach").addEventListener("change", (e) => {
    addFiles(e.target.files, "file");
    e.target.value = "";
  });
  $("#file-image").addEventListener("change", (e) => {
    addFiles(e.target.files, "image");
    e.target.value = "";
  });
}

function boot() {
  loadStore();
  $("#greeting").textContent = greetingByTime();
  renderHomePrompts();
  bindEvents();
  initVoice();
  initDocSelection();
  if (!state.chats.length) {
    /* empty home */
  } else if (!activeChat()) {
    state.activeId = state.chats[0].id;
  }
  renderAll();
}

boot();
