/* 个股 Deep Research — presentation only; never mutates judgment. */

const state = {
  snapshot: null,
  studies: [],
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 4200);
}

function showView(name) {
  $$(".view").forEach((v) => v.classList.remove("active"));
  $(`#view-${name}`).classList.add("active");
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function typeLabel(t) {
  return (
    {
      FACT: "Fact",
      DERIVED: "Derived",
      EVENT: "Event",
      EXPECTATION: "Expectation",
    }[t] || t || "—"
  );
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function loadStudies() {
  const res = await fetch("/api/studies");
  const data = await res.json();
  state.studies = data.studies || [];
  const list = $("#study-list");
  const chips = $("#example-chips");
  if (!state.studies.length) {
    list.innerHTML = `<p class="muted">暂无完整研究产物。</p>`;
    return;
  }
  list.innerHTML = state.studies
    .map(
      (s) => `
      <div class="study-item" data-symbol="${escapeHtml(s.symbol)}">
        <div>
          <strong>${escapeHtml(s.symbol)} · ${escapeHtml(s.name)}</strong>
          <span>artifacts · grounded replay</span>
        </div>
        <span>打开 →</span>
      </div>`
    )
    .join("");
  chips.innerHTML = state.studies
    .map(
      (s) =>
        `<button type="button" class="chip" data-symbol="${escapeHtml(s.symbol)}">${escapeHtml(s.symbol)} ${escapeHtml(s.name)}</button>`
    )
    .join("");

  list.querySelectorAll(".study-item").forEach((el) => {
    el.addEventListener("click", () => startResearch(el.dataset.symbol));
  });
  chips.querySelectorAll(".chip").forEach((el) => {
    el.addEventListener("click", () => {
      $("#query").value = el.dataset.symbol;
      startResearch(el.dataset.symbol);
    });
  });
}

function renderPipelineRail(snapshot, activeKey = null) {
  const stages = snapshot.pipeline_stages || [];
  const counts = snapshot.counts || {};
  const tips = {
    evidence: `${counts.evidence || 0} 条证据`,
    fundamental: `${counts.fundamental_findings || 0} 个命题`,
    market: `${counts.market_findings || 0} 个命题`,
    bull_bear: `B ${counts.bull_claims || 0} / S ${counts.bear_claims || 0}`,
    challenge: `${counts.challenges || 0} 条质询`,
    rebuttal: `${counts.rebuttals || 0} 条回应`,
    final_analyst: (snapshot.judgment || {}).assessment_strength || "done",
    report: "Brief ready",
  };
  const tabFor = {
    evidence: "evidence",
    fundamental: "details",
    market: "details",
    bull_bear: "debate",
    challenge: "debate",
    rebuttal: "debate",
    final_analyst: "judgment",
    report: "brief",
  };

  $("#pipeline-rail").innerHTML = `
    <div class="rail-head">Agent Pipeline</div>
    <ul class="pipeline-list">
      ${stages
        .map((s) => {
          const done = activeKey == null || stages.findIndex((x) => x.key === activeKey) >= stages.findIndex((x) => x.key === s.key);
          const active = s.key === activeKey;
          return `
        <li class="${done ? "done" : ""} ${active ? "active" : ""}">
          <button type="button" class="pipeline-btn" data-tab="${tabFor[s.key] || "brief"}">
            <span class="pipe-check">${done && !active ? "✓" : active ? "●" : "○"}</span>
            <span>
              <strong>${escapeHtml(s.title)}</strong>
              <em>${escapeHtml(tips[s.key] || s.note || "")}</em>
            </span>
          </button>
        </li>`;
        })
        .join("")}
    </ul>
    <p class="rail-note">点击任一阶段查看结果。Agent 是一支研究团队，不是黑盒。</p>`;

  $$("#pipeline-rail .pipeline-btn").forEach((btn) => {
    btn.addEventListener("click", () => setTab(btn.dataset.tab));
  });
}

async function animatePipeline(snapshot) {
  showView("progress");
  const stages = snapshot.pipeline_stages || [];
  const list = $("#stage-list");
  const timeline = $("#timeline");
  const counts = snapshot.counts || {};

  $("#progress-title").textContent = `${snapshot.symbol} · ${snapshot.name}`;
  $("#progress-lede").textContent = `截至 ${snapshot.as_of} · 回放研究团队工作流（不调用模型）`;

  list.innerHTML = stages
    .map(
      (s) => `
      <li data-key="${escapeHtml(s.key)}">
        <span class="stage-dot"></span>
        <div>
          <div>${escapeHtml(s.title)}</div>
          <div class="muted" style="font-size:0.78rem">${escapeHtml(s.note)}</div>
        </div>
      </li>`
    )
    .join("");

  timeline.innerHTML = stages
    .map(
      (s) => `
      <li data-key="${escapeHtml(s.key)}">
        <div class="t-title">${escapeHtml(s.title)}</div>
        <div class="t-note">${escapeHtml(s.note)}</div>
      </li>`
    )
    .join("");

  const agentNames = {
    evidence: "Evidence",
    fundamental: "Fundamental Research",
    market: "Market Research",
    bull_bear: "Bull / Bear",
    challenge: "Challenge",
    rebuttal: "Rebuttal",
    final_analyst: "Final Analyst",
    report: "Research Brief",
  };

  for (let i = 0; i < stages.length; i++) {
    const key = stages[i].key;
    $$("#stage-list li").forEach((li, idx) => {
      li.classList.toggle("done", idx < i);
      li.classList.toggle("active", idx === i);
    });
    const tl = timeline.querySelector(`li[data-key="${key}"]`);
    if (tl) tl.classList.add("visible");
    $("#status-agent").textContent = agentNames[key] || stages[i].title;
    $("#status-note").textContent = stages[i].note;

    if (key === "evidence") {
      $("#mini-stats").innerHTML = `
        <div class="mini-stat"><div class="k">Evidence</div><div class="v">${counts.evidence || 0}</div></div>
        <div class="mini-stat"><div class="k">Cited</div><div class="v">—</div></div>`;
    } else if (key === "fundamental" || key === "market") {
      $("#mini-stats").innerHTML = `
        <div class="mini-stat"><div class="k">Fundamental</div><div class="v">${counts.fundamental_findings || 0}</div></div>
        <div class="mini-stat"><div class="k">Market</div><div class="v">${counts.market_findings || 0}</div></div>`;
    } else if (["bull_bear", "challenge", "rebuttal"].includes(key)) {
      $("#mini-stats").innerHTML = `
        <div class="mini-stat"><div class="k">Bull / Bear</div><div class="v">${counts.bull_claims || 0}/${counts.bear_claims || 0}</div></div>
        <div class="mini-stat"><div class="k">Challenge</div><div class="v">${counts.challenges || 0}</div></div>`;
    } else {
      const j = snapshot.judgment || {};
      $("#mini-stats").innerHTML = `
        <div class="mini-stat"><div class="k">Debate</div><div class="v">${escapeHtml(j.debate_state || "—")}</div></div>
        <div class="mini-stat"><div class="k">Strength</div><div class="v">${escapeHtml(j.assessment_strength || "—")}</div></div>`;
    }
    await sleep(i === 0 ? 380 : 420);
  }

  $$("#stage-list li").forEach((li) => {
    li.classList.add("done");
    li.classList.remove("active");
  });
  $("#status-agent").textContent = "Research Complete";
  $("#status-note").textContent = "研究完成。进入 Workspace 查看 Brief、证据与争议。";
  await sleep(350);
  renderReport(snapshot);
  showView("report");
}

function renderEvidenceCard(e, supportHint = "") {
  const value = e.display_value || e.value_preview;
  const showValue = value != null && String(value).trim() !== "";
  return `
    <button type="button" class="ev-card eid" data-eid="${escapeHtml(e.evidence_id)}">
      <div class="ev-card-top">
        <span class="type-badge">${escapeHtml(typeLabel(e.type || e.evidence_type))}</span>
        <span class="muted">${escapeHtml(e.period || e.date || "")}</span>
      </div>
      ${showValue ? `<div class="ev-num">${escapeHtml(String(value))}</div>` : ""}
      <div class="ev-metric">${escapeHtml(e.metric_label || e.subtype || "证据")}</div>
      ${supportHint ? `<div class="ev-support">支持：${escapeHtml(supportHint)}</div>` : ""}
      <div class="ev-claim">${escapeHtml(e.claim || "")}</div>
      <div class="ev-source">${escapeHtml(e.source_label || e.source || "—")}</div>
    </button>`;
}

function renderSignalCard(sig, idx) {
  const kindLabel = sig.kind === "external" ? "External" : "Fundamental";
  const keyData = (sig.key_data || [])
    .map(
      (d) => `
      <span class="signal-kpi">
        <em>${escapeHtml(d.label)}</em>${escapeHtml(d.value)}${d.period ? ` <small>${escapeHtml(d.period)}</small>` : ""}
      </span>`
    )
    .join("");
  const eids = (sig.evidence_ids || []).slice(0, 2);
  const evidenceBtns = eids
    .map((id) => `<button type="button" class="btn-link eid" data-eid="${escapeHtml(id)}">查看证据</button>`)
    .join(" ");

  return `
    <article class="signal-card ${sig.kind === "external" ? "external" : "fundamental"}">
      <header>
        <span class="signal-rank">#${idx + 1}</span>
        <span class="signal-kind">${kindLabel}</span>
        ${sig.link_strength_label ? `<span class="signal-link">${escapeHtml(sig.link_strength_label)}</span>` : ""}
      </header>
      <h3>${escapeHtml(sig.headline || sig.event || "")}</h3>
      <p class="signal-insight"><strong>Agent Insight</strong> ${escapeHtml(sig.agent_insight || "")}</p>
      ${sig.company_link ? `<p class="signal-link-text"><strong>可能关联</strong> ${escapeHtml(sig.company_link)}</p>` : ""}
      ${(sig.impact_channels || []).length ? `<p class="signal-channels"><strong>影响渠道</strong> ${escapeHtml((sig.impact_channels || []).join(" · "))}</p>` : ""}
      ${keyData ? `<div class="signal-kpis">${keyData}</div>` : ""}
      <p class="signal-rq"><strong>下一步研究</strong> ${escapeHtml(sig.research_question || "")}</p>
      ${evidenceBtns ? `<div class="signal-actions">${evidenceBtns}</div>` : ""}
    </article>`;
}

function renderBriefTab(snapshot) {
  const r = snapshot.report || {};
  const brief = r.research_brief || (r.executive || {}).research_brief || {};
  const v = r.verdict || {};
  const signals = r.research_signals || (r.insights || {}).research_signals || [];
  const extSignals = r.external_signals || (r.insights || {}).external_signals || [];
  const picture = r.fundamental_picture || (r.insights || {}).fundamental_picture || {};
  const connections = r.connections || (r.insights || {}).connections || [];
  const changers = brief.what_changes_view || r.view_changers || [];

  const whyLines = (brief.insight_why || [])
    .map((line) => `<li>${escapeHtml(line)}</li>`)
    .join("");

  const signalCards = signals.map((s, i) => renderSignalCard(s, i)).join("");
  const extCards = extSignals.slice(0, 3).map((s, i) => renderSignalCard(s, i)).join("");

  const relationLines = (picture.relations || [])
    .map((line) => `<div class="relation-chip">${escapeHtml(line)}</div>`)
    .join("");

  const connRows = connections
    .map(
      (c) => `
      <div class="connection-row">
        <div class="conn-ext">${escapeHtml(c.external_headline || "")}</div>
        <div class="conn-arrow">→ ${escapeHtml(c.external_channel || "")} →</div>
        <div class="conn-fund">${escapeHtml(c.fundamental_headline || "")}</div>
        <div class="conn-meta">${escapeHtml(c.exposure || "")} · ${escapeHtml(c.link_strength_label || "")}</div>
        <div class="conn-rq">${escapeHtml(c.research_question || "")}</div>
      </div>`
    )
    .join("");

  const changeItems = changers
    .map(
      (c) => `
      <div class="brief-change">
        <p>${escapeHtml(c.trigger)}</p>
        <span class="pill">${escapeHtml(c.direction_label || "")}</span>
      </div>`
    )
    .join("");

  return `
    <div class="brief-hero">
      <div class="brief-id">
        <span class="eyebrow">个股 Deep Research</span>
        <h1>${escapeHtml(r.name || snapshot.name)} <span class="code">${escapeHtml(r.symbol || snapshot.symbol)}</span></h1>
        <p class="muted">截至 ${escapeHtml(r.as_of || snapshot.as_of)} · 研究方向组织，非交易建议</p>
      </div>
      <div class="pill-row">
        <span class="pill"><em>判断强度</em>${escapeHtml(brief.assessment_label || v.assessment_label || "—")}</span>
        <span class="pill"><em>主轴</em>${escapeHtml(brief.axis_label || v.axis_label || "—")}</span>
        <span class="pill"><em>辩论</em>${escapeHtml(brief.debate_label || v.debate_label || "—")}</span>
      </div>
    </div>

    <article class="insight-hero">
      <div class="brief-label">当前最值得研究的变化</div>
      <h2>${escapeHtml(brief.insight_change || brief.core_judgment || r.cover_title || "")}</h2>
      ${whyLines ? `<div class="insight-block"><strong>为什么</strong><ul class="clean-list">${whyLines}</ul></div>` : ""}
      ${brief.insight_meaning ? `<div class="insight-block"><strong>这意味着什么</strong><p>${escapeHtml(brief.insight_meaning)}</p></div>` : ""}
      ${brief.insight_next_research ? `<div class="insight-block highlight"><strong>下一步值得查</strong><p>${escapeHtml(brief.insight_next_research)}</p></div>` : ""}
    </article>

    <div class="section-title">Research Signals <span class="muted">AI 筛出的 Top ${signals.length || 0} 变化</span></div>
    <div class="signal-grid">${signalCards || `<p class="muted">暂无排序洞察</p>`}</div>

    <div class="section-title">Fundamental Picture <span class="muted">看关系，不是看指标表</span></div>
    <div class="fundamental-picture">
      <p class="picture-summary">${escapeHtml(picture.summary || "")}</p>
      <div class="relation-row">${relationLines || `<span class="muted">—</span>`}</div>
    </div>

    <div class="section-title">External Signals <span class="muted">宏观 · 行业 · 政策 · 新闻</span></div>
    <div class="signal-grid external-grid">${extCards || `<p class="muted">暂无外部信号</p>`}</div>

    ${connections.length ? `<div class="section-title">Where They Might Connect</div><div class="connections-panel">${connRows}</div>` : ""}

    <details class="brief-more">
      <summary>展开：Bull / Bear / Final Judgment 上下文</summary>
      <div class="brief-grid compact">
        <article class="brief-card">
          <div class="brief-label">核心矛盾（FA 主轴）</div>
          <h3>${escapeHtml(brief.core_tension || v.core_tension || "")}</h3>
        </article>
        <article class="brief-card bull">
          <div class="brief-label">Bull Case</div>
          <p>${escapeHtml(brief.bull_case || "")}</p>
        </article>
        <article class="brief-card bear">
          <div class="brief-label">Bear Case</div>
          <p>${escapeHtml(brief.bear_case || "")}</p>
        </article>
        <article class="brief-card span-2">
          <div class="brief-label">Key Unknown</div>
          <p>${escapeHtml(brief.key_unknown || "")}</p>
        </article>
        <article class="brief-card span-2">
          <div class="brief-label">什么证据会改变判断</div>
          <div class="brief-changes">${changeItems || `<p class="muted">无</p>`}</div>
        </article>
      </div>
    </details>

    <div class="jump-row">
      <button type="button" class="btn-primary" data-jump="judgment">查看 Final Judgment</button>
      <button type="button" class="btn-ghost" data-jump="evidence">Evidence Explorer</button>
      <button type="button" class="btn-ghost" data-jump="debate">打开 Debate</button>
    </div>`;
}

function renderJudgmentTab(snapshot) {
  const r = snapshot.report || {};
  const v = r.verdict || {};
  const judg = r.judgment || {};
  const brief = r.research_brief || {};
  const confirmed = (judg.confirmed || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("");
  const unconfirmed = (judg.unconfirmed || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("");
  const risks = (r.risks || []).map((x) => `<li>${escapeHtml(x.text || x)}</li>`).join("");
  const changers = (r.view_changers || [])
    .map(
      (c) => `
      <div class="changer">
        <div>
          <p>${escapeHtml(c.trigger)}</p>
          <div class="meta-line">${escapeHtml(c.why || c.effect || "")}</div>
        </div>
        <span class="pill">${escapeHtml(c.direction_label)}</span>
      </div>`
    )
    .join("");

  return `
    <div class="judgment-hero">
      <div class="label">AI Final Judgment</div>
      <div class="assessment">${escapeHtml(brief.core_judgment || r.cover_title || v.headline || "")}</div>
      <div class="pill-row" style="margin-top:0.9rem">
        <span class="pill"><em>状态</em>${escapeHtml(judg.strength_label || v.assessment_label)} · ${escapeHtml(v.debate_label || "")}</span>
        <span class="pill"><em>主轴</em>${escapeHtml(v.axis_label || "")}</span>
      </div>
      <p class="disclaimer">${escapeHtml(r.disclaimer || "")}</p>
    </div>

    <div class="grid-2">
      <div class="card">
        <h3>支持因素</h3>
        <ul class="clean-list">${confirmed || `<li class="muted">—</li>`}</ul>
      </div>
      <div class="card">
        <h3>主要风险 / 未确认</h3>
        <ul class="clean-list">${unconfirmed || risks || `<li class="muted">—</li>`}</ul>
      </div>
    </div>

    <div class="card">
      <h3>当前证据最支持什么</h3>
      <p>${escapeHtml(judg.current_supports || "")}</p>
      <p class="finding-interp" style="margin-top:0.55rem">${escapeHtml(judg.strength_reason || "")}</p>
    </div>

    <div class="section-title">什么会改变判断</div>
    <div class="card">${changers || `<p class="muted">无</p>`}</div>

    <div class="jump-row">
      <button type="button" class="btn-ghost" data-jump="evidence">展开 Evidence</button>
      <button type="button" class="btn-ghost" data-jump="debate">展开 Debate</button>
      <button type="button" class="btn-ghost" data-jump="details">展开 Research Details</button>
    </div>`;
}

function renderEvidenceTab(snapshot) {
  const r = snapshot.report || {};
  const briefSupport = (r.research_brief || {}).core_judgment || r.cover_title || "";
  const cards = (r.key_evidence || []).map((e) => renderEvidenceCard(e, briefSupport)).join("");
  const rows = snapshot.evidence || [];
  const types = [...new Set(rows.map((x) => x.evidence_type))].sort();

  return `
    <div class="section-title">支撑终判的证据卡片</div>
    <div class="ev-grid">${cards || `<p class="muted">无关键证据</p>`}</div>

    <div class="section-title">Evidence Explorer</div>
    <div class="evidence-toolbar">
      <input id="ev-filter" type="search" placeholder="搜索事实、来源或关键词" style="flex:1;min-width:200px" />
      <select id="ev-type">
        <option value="">全部类型</option>
        ${types.map((t) => `<option value="${escapeHtml(t)}">${escapeHtml(typeLabel(t))}</option>`).join("")}
      </select>
      <label class="muted" style="display:flex;gap:0.35rem;align-items:center">
        <input type="checkbox" id="ev-cited" checked /> 仅显示被引用
      </label>
    </div>
    <div id="evidence-list" class="ev-explorer">
      ${rows.map(renderEvidenceItem).join("")}
    </div>`;
}

function renderEvidenceItem(e) {
  const used = e.used_by || {};
  const val = (e.value || {}).value;
  let display = "";
  if (typeof val === "number") {
    const st = e.subtype || "";
    const asPct = ["roe", "margin", "yoy", "ratio"].some((k) => st.includes(k)) && Math.abs(val) <= 2;
    display = asPct ? `${(val * 100).toFixed(2)}%` : String(Number(val.toFixed ? val.toFixed(2) : val));
  }
  return `
    <details class="evidence-item" data-eid="${escapeHtml(e.evidence_id)}" data-type="${escapeHtml(e.evidence_type)}" data-cited="${e.cited ? "1" : "0"}" data-text="${escapeHtml((e.claim || "") + " " + (e.subtype || "") + " " + e.evidence_id)}">
      <summary>
        <span class="type-badge">${escapeHtml(typeLabel(e.evidence_type))}</span>
        <div>
          ${display ? `<div class="ev-inline-num">${escapeHtml(display)}</div>` : ""}
          <strong style="font-size:0.92rem">${escapeHtml(e.claim)}</strong>
          <div class="meta-line">${escapeHtml(e.subtype)} · ${escapeHtml((e.source || {}).provider || "")}</div>
        </div>
        <span class="muted">${e.cited ? "已引用" : "未引用"}</span>
      </summary>
      <div class="evidence-body">
        <div class="kv">
          <div class="k">原始事实</div><div class="v">${escapeHtml(e.claim)}</div>
          <div class="k">来源</div><div class="v">${escapeHtml(e.source?.provider || "")}</div>
          <div class="k">时间</div><div class="v">${escapeHtml(e.time?.data_date || e.time?.report_date || "—")}</div>
          <div class="k">研究 / 辩论 / 终判</div>
          <div class="v">${(used.research || []).length ? "研究" : "—"} · ${(used.debate || []).length ? "辩论" : "—"} · ${(used.final_analyst || []).length ? "终判" : "—"}</div>
          <div class="k">支持环节</div><div class="v">${(e.supports || []).map(escapeHtml).join(" · ") || "未被引用"}</div>
        </div>
      </div>
    </details>`;
}

function renderDebateTab(snapshot) {
  const dv = snapshot.report?.debate_view;
  const brief = snapshot.report?.research_brief || {};
  if (!dv) return `<div class="card"><p class="muted">暂无多空辩论产物。</p></div>`;

  const primary = (dv.comparisons || [])[0] || {};
  const chains = (dv.chains || [])
    .slice(0, 4)
    .map(
      (ch) => `
    <div class="chain">
      <div class="chain-step">
        <div class="who">被质疑 · ${escapeHtml(ch.target_side)}</div>
        <p>${escapeHtml(ch.target)}</p>
      </div>
      <div class="chain-step challenge">
        <div class="who">Challenge · ${escapeHtml(ch.challenger)} · ${escapeHtml(ch.challenge_type)}</div>
        <p>${escapeHtml(ch.challenge)}</p>
      </div>
      ${(ch.rebuttals || [])
        .map(
          (r) => `
        <div class="chain-step rebuttal">
          <div class="who">Response · ${escapeHtml(r.author)} · ${escapeHtml(r.response)}</div>
          <p>${escapeHtml(r.argument)}</p>
        </div>`
        )
        .join("") || `<div class="chain-step"><span class="muted">尚无回应</span></div>`}
    </div>`
    )
    .join("");

  return `
    <div class="debate-arena">
      <div class="side-card bull">
        <div class="brief-label">BULL CASE</div>
        <h3>${escapeHtml(brief.bull_case || dv.bull_thesis || "")}</h3>
        <p>${escapeHtml(primary.bull || "")}</p>
      </div>
      <div class="debate-core">
        <div class="brief-label">CORE DISAGREEMENT</div>
        <h2>${escapeHtml(brief.core_tension || primary.question || "")}</h2>
        <div class="pill">${escapeHtml(primary.winner || "未决")}</div>
        <p class="muted">${escapeHtml(primary.reason || "")}</p>
      </div>
      <div class="side-card bear">
        <div class="brief-label">BEAR CASE</div>
        <h3>${escapeHtml(brief.bear_case || dv.bear_thesis || "")}</h3>
        <p>${escapeHtml(primary.bear || "")}</p>
      </div>
    </div>

    <div class="section-title">Challenge · Response · Evidence</div>
    ${chains || `<p class="muted">暂无质询链</p>`}

    <details class="card raw-toggle">
      <summary>更多争议对照（次级）</summary>
      ${(dv.comparisons || [])
        .slice(1)
        .map(
          (t) => `
        <div style="margin-top:0.9rem">
          <h3 class="finding-title">${escapeHtml(t.question)}</h3>
          <div class="grid-2">
            <p><span class="pill bull">Bull</span> ${escapeHtml(t.bull || "")}</p>
            <p><span class="pill bear">Bear</span> ${escapeHtml(t.bear || "")}</p>
          </div>
        </div>`
        )
        .join("") || `<p class="muted">无更多争议</p>`}
    </details>`;
}

function renderDetailsTab(snapshot) {
  const r = snapshot.report || {};
  const sections = r.sections || [];
  const findings = r.findings || [];
  const profile = r.company_profile || [];

  return `
    <div class="section-title">研究报告细节（折叠默认关闭）</div>
    <details class="card raw-toggle" open>
      <summary>▍分节正文</summary>
      <div class="prose" style="margin-top:0.8rem">
        ${sections
          .map(
            (s) => `
          <section class="memo-section">
            <h3 class="memo-kicker">${escapeHtml(s.kicker)}${s.thesis ? "：" + escapeHtml(s.thesis) : ""}</h3>
            ${s.body ? `<p>${escapeHtml(s.body)}</p>` : ""}
          </section>`
          )
          .join("")}
      </div>
    </details>
    <details class="card raw-toggle">
      <summary>研究命题</summary>
      ${findings
        .map((f) => `<p style="margin-top:0.7rem"><strong>${escapeHtml(f.title)}</strong> ${escapeHtml(f.claim)}</p>`)
        .join("")}
    </details>
    <details class="card raw-toggle">
      <summary>公司速览</summary>
      <div class="profile-grid" style="margin-top:0.8rem">
        ${profile
          .map(
            (p) => `
          <div class="profile-cell">
            <div class="k">${escapeHtml(p.label)}</div>
            <div class="v">${escapeHtml(p.value ?? "")}</div>
          </div>`
          )
          .join("")}
      </div>
    </details>`;
}

function bindEvidenceFilters() {
  const apply = () => {
    const q = ($("#ev-filter")?.value || "").trim().toLowerCase();
    const type = $("#ev-type")?.value || "";
    const citedOnly = $("#ev-cited")?.checked;
    $$("#evidence-list .evidence-item").forEach((el) => {
      const text = (el.dataset.text || "").toLowerCase();
      const okType = !type || el.dataset.type === type;
      const okCited = !citedOnly || el.dataset.cited === "1";
      const okQ = !q || text.includes(q) || (el.dataset.eid || "").toLowerCase().includes(q);
      el.style.display = okType && okCited && okQ ? "" : "none";
    });
  };
  $("#ev-filter")?.addEventListener("input", apply);
  $("#ev-type")?.addEventListener("change", apply);
  $("#ev-cited")?.addEventListener("change", apply);
  apply();
}

function bindEidClicks() {
  $$(".eid").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.eid;
      setTab("evidence");
      const box = $("#ev-cited");
      if (box) box.checked = false;
      const filter = $("#ev-filter");
      if (filter) {
        filter.value = id;
        filter.dispatchEvent(new Event("input"));
      }
      requestAnimationFrame(() => {
        const item = document.querySelector(`.evidence-item[data-eid="${CSS.escape(id)}"]`);
        if (item) {
          item.open = true;
          item.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      });
    });
  });
}

function bindJumpButtons() {
  $$("[data-jump]").forEach((btn) => {
    btn.addEventListener("click", () => setTab(btn.dataset.jump));
  });
}

function renderReport(snapshot) {
  state.snapshot = snapshot;
  $("#report-identity").innerHTML = `<strong>${escapeHtml(snapshot.symbol)} · ${escapeHtml(snapshot.name)}</strong>
    <span class="muted"> · 截至 ${escapeHtml(snapshot.as_of)} · Replay</span>`;

  renderPipelineRail(snapshot);
  $("#tab-brief").innerHTML = renderBriefTab(snapshot);
  $("#tab-judgment").innerHTML = renderJudgmentTab(snapshot);
  $("#tab-evidence").innerHTML = renderEvidenceTab(snapshot);
  $("#tab-debate").innerHTML = renderDebateTab(snapshot);
  $("#tab-details").innerHTML = renderDetailsTab(snapshot);

  bindEvidenceFilters();
  bindEidClicks();
  bindJumpButtons();
  setTab("brief");
}

function setTab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $$(".tab-pane").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
}

async function startResearch(query) {
  const q = (query || $("#query").value || "").trim();
  if (!q) {
    toast("请输入股票代码或名称", true);
    return;
  }
  const btn = $("#search-form button[type=submit]");
  btn.disabled = true;
  try {
    const res = await fetch("/api/research/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: q, mode: "replay" }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "启动失败");
    await animatePipeline(data.snapshot);
  } catch (err) {
    toast(String(err.message || err), true);
    showView("home");
  } finally {
    btn.disabled = false;
  }
}

function boot() {
  $("#search-form").addEventListener("submit", (e) => {
    e.preventDefault();
    startResearch();
  });
  $("#btn-home").addEventListener("click", () => showView("home"));
  $$(".tab").forEach((t) => t.addEventListener("click", () => setTab(t.dataset.tab)));
  loadStudies().catch((err) => toast(String(err), true));
}

boot();
