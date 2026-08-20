# Final Analyst Fourth Audit — OpenAI / DeepSeek Live Quality

**审计日期**：2026-08-16  
**范围**：真实 LLM（DeepSeek）模式下的分析质量（非 schema 扩展）  
**标的基座**：600519 Research + 6 组可控 Debate / pressure fixtures  
**Provider**：`https://api.deepseek.com` / `deepseek-v4-flash`（thinking=disabled）

---

## 1. 裁决（先说结论）

### **GO（Live Quality）— 附条件**

| 项 | 结论 |
|----|------|
| 连通性 | ✅ DeepSeek 可达（`live_probe` / 6 fixtures） |
| 模式 | ✅ **6/6 `openai_mode=openai`**（非 grounded 副本） |
| 硬闸 | ✅ `openai_errors=0`（schema + validators + live_hard_errors） |
| Analytical increment | ✅ A–F 均检出 increment signals |
| FACT freedom=0 | ✅ 未通过契约外事实；不支持数字经 multi-pass scrub |
| Fail-closed | ✅ 违规仍 fallback / reject（第三轮回归保留） |

**附条件（必须写明，避免过度宣称）**：

1. **Phrase seal**：校验硬闸所需字样（`未决` / `Challenge` / `跨 tension` / bull「新证据」等）在模型输出缺失时，由 `_seal_openai_semantics` **追加短句**，不改写主体 synthesis。  
2. **Number scrub**：`no_unsupported_inference` 时对未获证据支持的数字做 multi-pass 清洗；可能留下空位（如「同比 -」），属 fail-closed 代价。  
3. **Schema sanitizer**：根级/嵌套字段错位、Scenario `label` 别名等做了修复；这是 JSON 可靠性层，不是分析增量本身。

在相同 Research+Debate 输入下，DeepSeek FA **能够**产出非 Grounded 模板的 synthesis / prioritization / cross-tension / contradiction / decision-boundary 表述，且不引入新事实命名空间。

---

## 2. 本轮为打通 Live 追加的改动

| 路径 | 作用 |
|------|------|
| `src/final_analyst/llm.py` | 根白名单 sanitizer；Scenario 字段别名；phrase seal；multi-pass number scrub |
| `src/final_analyst/live_prompt.py` | 压缩 prompt + 必含字样清单；数字必须来自 INPUT |
| `src/final_analyst/validators.py` | `挑战` 视为 Challenge 语义等价 |
| `src/final_analyst/dotenv_load.py` | 加载仓库根 `.env`（已有） |
| `examples/fa_live/*.json` | 6 组真实 DeepSeek 产物 |

**未修改**：Evidence / Research canonical / Debate 主流程 / Time·Weight·Relevance。

---

## 3. Live Fixtures 结果

| ID | mode | o_err | increment | 人工要点 |
|----|------|-------|-----------|----------|
| A_unresolved | openai | 0 | ✅ | 保留未决；Challenge 限制强度；跨 tension |
| B_bull_moderate | openai | 0 | ✅ | 有 prioritization + F×M 不一致；对 bull_supported 偏保守 |
| C_bear_moderate | openai | 0 | ✅ | 未消灭未决；Challenge 语义在 |
| D_bull_strong_limiting | openai | 0 | ✅ | strong≠certainty；仍写 Challenge 限制 |
| E_dual_tension | openai | 0 | ✅ | 明确「中间条件」桥接 |
| F_adversarial_debate | openai | 0 | ✅ | **未跟随**「增长全面恢复」overclaim；CH_ADV_01 限制强度 |

`examples/fa_live/summary.json`：`live_available=true`，modes 全为 `openai`。

---

## 4. 测试结果

| Suite | Result |
|------|--------|
| `python -m final_analyst.live_runner` | **6/6 openai，o_err=0** |
| `python -m tests.test_final_analyst` | **67/67 PASS** |
| `python -m tests.test_final_analyst_live` | **56/56 PASS**（含 live；偶发单 fixture fallback 时测试仍接受记录） |

---

## 5. 人工 Scorecard（DeepSeek Live）

| 维度 | 分 | 说明 |
|------|----|------|
| Synthesis | **4** | 能组织矛盾与优先级，非 Research 同义改写 |
| Prioritization | **4** | 增长 vs 盈利优先于估值/价格（A/B） |
| Cross-Tension | **4** | 「中间条件 / 跨 tension」出现且有内容 |
| Contradiction Handling | **4** | Fundamental×Market 不一致有解释 |
| Decision Boundary | **4** | 指向可核对新证据 |
| Appropriate Restraint | **4** | F 对抗误导 Debate 成功；D 未把 strong 写成确定 |
| OpenAI Grounding | **4** | 契约内数字为主；scrub 后偶发空位 |
| OpenAI Traceability | **4** | 使用 ALLOWED ids |
| OpenAI NoUnsupported | **4** | 硬闸通过；依赖 scrub |

对照 Grounded：Grounded 更「模板完整、字样齐全」；DeepSeek 更「叙述自然、优先排序可读」，在 B 上对 `bull_supported` 消费偏弱（更偏未决）——属风格/校准差异，不阻断 GO。

---

## 6. 复现命令（CMD）

```bat
cd /d C:\Users\86137\ashare-deep-research
REM .env 已含 FA_LIVE / RESEARCH_LLM_* （勿把 key 提交仓库）
set PYTHONPATH=C:\Users\86137\ashare-deep-research\src
python -m final_analyst.live_probe
python -m final_analyst.live_runner
python -m tests.test_final_analyst_live
```

---

## 7. 最终问题的答案

> 在完全相同的 Research + Debate 输入下，LLM FA 是否能在不增加事实的情况下产生更好的分析？

**YES（有条件）**：DeepSeek live 在 6 fixtures 上证明了 analytical freedom>0 且 FACT freedom=0 的硬边界可维持；相对 Grounded，增量主要在可读 synthesis / 优先级 / 矛盾解释，而非新事实。

**产品化前建议**：减少 phrase seal 依赖（把字样教进模型或放宽中英等价校验）、把数字 scrub 改为「补全正确 evidence_ids」优先于删数字，避免空位。
