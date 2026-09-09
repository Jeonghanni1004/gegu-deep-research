/* 华辰 Demo · Agent 工作日志动效（操作日志，非内部 CoT） */
(function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function isHuachenQuestion(text) {
    const t = String(text || "");
    if (/华辰科技/.test(t)) return true;
    if (/600XXX/.test(t)) return true;
    const demo = window.HUACHEN_DEMO?.question || "";
    return demo && t.replace(/\s/g, "") === demo.replace(/\s/g, "");
  }

  function matchFollowup(text) {
    const demo = window.HUACHEN_DEMO;
    if (!demo) return null;
    for (const key of Object.keys(demo.followups)) {
      const item = demo.followups[key];
      if (item.match.test(text.trim())) return { key, ...item };
    }
    return null;
  }

  function el(html) {
    const t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  function scrollChat() {
    const scroller = document.querySelector("#view-chat");
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
  }

  function setRunStatus(root, text, done = false) {
    const s = root.querySelector(".agent-run-status");
    if (!s) return;
    s.textContent = text;
    s.classList.toggle("done", done);
    s.classList.toggle("pulse", !done);
  }

  function addStage(root, title) {
    const log = root.querySelector(".agent-log");
    const stage = el(`
      <div class="agent-stage">
        <button type="button" class="agent-stage-head" aria-expanded="true">
          <span class="stage-dot running"></span>
          <span class="stage-title">${title}</span>
          <span class="stage-chevron">▾</span>
        </button>
        <div class="agent-stage-body"></div>
      </div>`);
    log.appendChild(stage);
    stage.querySelector(".agent-stage-head").addEventListener("click", () => {
      const open = stage.classList.toggle("collapsed");
      stage.querySelector(".agent-stage-head").setAttribute("aria-expanded", String(!open));
    });
    scrollChat();
    return stage;
  }

  function completeStage(stage) {
    const dot = stage.querySelector(".stage-dot");
    dot.classList.remove("running");
    dot.classList.add("done");
    dot.textContent = "✓";
  }

  async function addLine(stage, text, opts = {}) {
    const body = stage.querySelector(".agent-stage-body");
    const line = el(`
      <div class="agent-line ${opts.kind || ""} ${opts.running ? "running" : ""}">
        <span class="line-mark">${opts.check ? "✓" : opts.running ? "●" : "·"}</span>
        <span class="line-text">${text}</span>
        ${opts.tag ? `<span class="fact-tag ${opts.tagClass || ""}">${opts.tag}</span>` : ""}
      </div>`);
    body.appendChild(line);
    scrollChat();
    if (opts.delay) await sleep(opts.delay);
    return line;
  }

  async function addFactCard(board, fact, index, delay = 380) {
    const card = el(`
      <div class="fact-card live ${fact.cls}" data-source-id="${fact.sourceId || ""}">
        <span class="fact-index">F${String(index + 1).padStart(2, "0")}</span>
        <span class="fact-metric">${fact.metric || ""}</span>
        <span class="fact-text">${fact.text}</span>
        <span class="fact-tag ${fact.cls}">${fact.tag}</span>
      </div>`);
    board.appendChild(card);
    scrollChat();
    if (delay) await sleep(delay);
    return card;
  }

  async function finishLine(line) {
    if (!line) return;
    line.classList.remove("running");
    const mark = line.querySelector(".line-mark");
    if (mark) mark.textContent = "✓";
  }

  async function runCounter(stage, values, delay = 450) {
    const body = stage.querySelector(".agent-stage-body");
    const counter = el(`<div class="filter-counter"><span class="n">${values[0]}</span><span class="lbl"> 条相关信息</span></div>`);
    body.appendChild(counter);
    scrollChat();
    for (let i = 1; i < values.length; i++) {
      await sleep(delay);
      counter.querySelector(".n").textContent = values[i];
      counter.classList.add("tick");
      setTimeout(() => counter.classList.remove("tick"), 280);
    }
  }

  /**
   * 在聊天区挂载 Agent Run 卡片并逐步播放工作日志
   * @returns {Promise<{summary:string, document:object}>}
   */
  async function runHuachenResearch(mountEl) {
    const demo = window.HUACHEN_DEMO;
    const root = el(`
      <div class="agent-run" data-demo="huachen">
        <div class="agent-run-head">
          <span class="agent-run-status pulse">● Understanding request</span>
          <span class="agent-run-meta">华辰科技 · 2026.06—2026.09</span>
        </div>
        <div class="agent-log"></div>
      </div>`);
    mountEl.appendChild(root);
    scrollChat();

    // —— Step 1 理解问题 ——
    let stage = addStage(root, "正在理解你的问题");
    setRunStatus(root, "● Understanding request");
    await sleep(500);
    await addLine(stage, "已识别研究对象：华辰科技", { check: true, delay: 420 });
    await addLine(stage, "已确定研究周期：近三个月（2026.06.01 — 2026.09.09）", { check: true, delay: 420 });
    await addLine(stage, "已识别分析重点：看涨因素 / 看跌因素", { check: true, delay: 420 });
    const planHint = await addLine(stage, "正在确定需要查询的信息……", { running: true, delay: 700 });
    await finishLine(planHint);
    await addLine(stage, "研究范围已确定", { check: true, delay: 350 });
    completeStage(stage);

    // —— Step 2 研究计划 ——
    stage = addStage(root, "正在制定研究计划");
    setRunStatus(root, "● Planning research");
    const planItems = [
      "查询近期财务数据",
      "查询公司公告及重大事件",
      "查询行业变化",
      "查询近期市场表现",
      "查询历史估值",
      "查找历史上的相似事件",
    ];
    for (const item of planItems) {
      const line = await addLine(stage, item, { running: true, delay: 380 });
      await sleep(220);
      await finishLine(line);
    }
    await addLine(stage, "已确定 6 个信息方向", { check: true, delay: 400 });
    completeStage(stage);

    // —— Step 3 第一轮检索 ——
    stage = addStage(root, "正在检索公开信息");
    setRunStatus(root, "● Searching");
    const round1 = [
      { label: "财务数据", found: "找到：2026 年半年度报告" },
      { label: "公司公告", found: "找到：海外核心客户合作进展公告" },
      { label: "行业信息", found: "找到：消费电子需求变化相关信息" },
      { label: "市场行情", found: "找到：近期价格及成交数据" },
      { label: "历史估值", found: "找到：过去三年估值数据" },
    ];
    for (const r of round1) {
      await addLine(stage, `<strong>${r.label}</strong> · ${r.found}`, { running: true, delay: 320 });
      const last = stage.querySelector(".agent-line:last-child");
      await sleep(480);
      await finishLine(last);
      const tag = document.createElement("span");
      tag.className = "line-status ok";
      tag.textContent = "✓ 已获取";
      last.appendChild(tag);
    }
    await addLine(stage, "第一轮检索完成，共获取 6 份主要材料。", { check: true, delay: 450 });
    completeStage(stage);

    // —— Step 4 第二轮补充 ——
    stage = addStage(root, "正在检查现有信息是否足够……");
    setRunStatus(root, "● Cross-checking");
    await sleep(600);
    await addLine(
      stage,
      "已发现：近期海外订单是一个重要变化。",
      { check: true, delay: 500 }
    );
    await addLine(
      stage,
      "仅有订单公告还不足以判断它对公司的实际影响，需要进一步查看历史上类似订单是否最终反映到收入和利润。",
      { kind: "note", delay: 700 }
    );
    const extra = await addLine(stage, "正在补充检索历史相似事件……", { running: true, delay: 650 });
    await finishLine(extra);
    await addLine(stage, "找到：2024 年海外订单增长及后续财务表现", { check: true, delay: 400 });
    await addLine(stage, "✓ 补充完成", { check: true, delay: 350 });
    await addLine(stage, "信息之间已建立关联", { check: true, delay: 400 });
    completeStage(stage);
    stage.querySelector(".stage-title").textContent = "交叉验证与补充检索";

    // —— Step 5 筛选 ——
    stage = addStage(root, "正在筛选信息");
    setRunStatus(root, "● Filtering");
    await addLine(stage, "已获取 18 条相关信息", { check: true, delay: 350 });
    await runCounter(stage, [18, 14, 11, 9], 420);
    await addLine(stage, "去除 4 条重复信息", { check: true, delay: 320 });
    await addLine(stage, "去除 3 条缺乏明确来源的信息", { check: true, delay: 320 });
    await addLine(stage, "去除 2 条纯观点内容", { check: true, delay: 320 });
    await addLine(stage, "保留 9 条核心事实", { check: true, delay: 350 });
    await addLine(stage, "已完成信息筛选", { check: true, delay: 350 });
    completeStage(stage);

    // —— Step 6 事实提取 ——
    stage = addStage(root, "正在提取关键事实");
    setRunStatus(root, "● Extracting facts");
    const facts = window.HUACHEN_DEMO.coreFacts || [];
    const board = el(`<div class="fact-board-inline" aria-label="核心事实"></div>`);
    stage.querySelector(".agent-stage-body").appendChild(board);
    for (let i = 0; i < facts.length; i++) {
      await addFactCard(board, facts[i], i, 360);
    }
    await addLine(stage, `已提取 ${facts.length} 条核心事实，并完成方向判断。`, { check: true, delay: 400 });
    completeStage(stage);

    // —— Step 7 分析 ——
    stage = addStage(root, "正在分析事实之间的关系");
    setRunStatus(root, "● Analyzing");
    const analysis = [
      ["分析收入与利润增速差异……", "发现：收入增长明显快于利润增长。"],
      ["检查毛利率变化……", "发现：盈利空间暂时受到一定压力。"],
      ["分析海外订单……", "发现：订单规模较大，但尚未完全转化为实际收入。"],
      ["对照历史相似事件……", "发现：2024 年类似订单增长后，公司收入增速曾明显提升，但同时出现短期毛利率下降。"],
      ["分析当前估值……", "发现：市场当前定价已经包含一定增长预期。"],
    ];
    for (const [a, b] of analysis) {
      const line = await addLine(stage, a, { running: true, delay: 420 });
      await sleep(380);
      await finishLine(line);
      await addLine(stage, b, { kind: "find", check: true, delay: 360 });
    }
    await addLine(stage, "已完成多空因素归纳。", { check: true, delay: 400 });
    completeStage(stage);

    // —— Step 8 框架 + 写报告 ——
    stage = addStage(root, "形成分析框架");
    setRunStatus(root, "● Writing report");
    await addLine(stage, "<strong>看涨因素</strong>", { delay: 200 });
    await addLine(stage, "1. 海外订单增加", { check: true, delay: 280 });
    await addLine(stage, "2. 公司收入保持增长", { check: true, delay: 280 });
    await addLine(stage, "3. 消费电子行业需求改善", { check: true, delay: 280 });
    await addLine(stage, "<strong>看跌因素</strong>", { delay: 200 });
    await addLine(stage, "1. 利润增长慢于收入", { check: true, delay: 280 });
    await addLine(stage, "2. 毛利率下降、库存增长", { check: true, delay: 280 });
    await addLine(stage, "3. 当前估值处于历史较高位置", { check: true, delay: 280 });
    completeStage(stage);

    stage = addStage(root, "正在整理分析报告……");
    for (const t of ["正在添加数据来源……", "正在生成白话解释……", "报告生成完成"]) {
      const line = await addLine(stage, t, { running: true, delay: 520 });
      await finishLine(line);
    }
    completeStage(stage);

    setRunStatus(root, "✓ Research complete", true);
    root.classList.add("complete");
    await sleep(400);

    return {
      summary:
        "已完成华辰科技近三个月投研分析（Demo 模拟数据）。\n\n看涨侧主要来自海外订单、收入增长与行业回暖；看跌侧主要来自利润增速落后、毛利率/库存压力，以及估值已处历史偏高位置。\n\n完整报告已在右侧打开，可点击文中来源查看原始材料与 AI 提取事实。",
      followups: demo.defaultFollowups,
      document: {
        title: "华辰科技｜近三个月投研分析",
        symbol: "600XXX · 华辰科技",
        html: demo.buildReportHtml(),
        updatedAt: Date.now(),
        demo: "huachen",
        sources: demo.sources,
      },
    };
  }

  window.AgentDemo = {
    isHuachenQuestion,
    matchFollowup,
    runHuachenResearch,
  };
})();
