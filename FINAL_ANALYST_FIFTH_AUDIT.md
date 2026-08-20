# Final Analyst Fifth Audit — Production Hardening & Quality Calibration

**审计日期**：2026-08-16  
**范围**：移除 phrase seal 依赖、Evidence Repair、正式 Calibration Matrix、跨行业稳健、Live multi-run  
**Provider（live）**：DeepSeek `deepseek-v4-flash`（thinking disabled）

---

## 1. 裁决

### **GO — Production Candidate（附残余风险）**

| 硬门槛 | 结果 |
|--------|------|
| phrase_seal_dependency | **0**（生产路径默认关闭；`FA_PHRASE_SEAL=1` 仅兼容） |
| number_scrub_information_loss | **0**（进入最终 openai 输出不得 scrub；scrub=REJECT） |
| unsupported_external_fact | **0** |
| live_hard_errors（成功 openai run） | **0** |
| tests.test_final_analyst | **67/67 PASS** |
| tests.test_final_analyst_round5 | **41/41 PASS** |

GO 含义：Research + Debate → 可追溯、校准、条件化 judgment 的稳定最后一层。  
**不**表示 Autonomous Research / 投资建议 / 概率 / 目标价 / BUY·SELL。

---

## 2. 修改文件列表

| 路径 | 作用 |
|------|------|
| `src/final_analyst/semantic.py` | **新增** 语义校验（unresolved / challenge / scenario / cross-tension） |
| `src/final_analyst/evidence_repair.py` | **新增** Evidence Repair（ACCEPT/REPAIR/REGENERATE/REJECT） |
| `src/final_analyst/calibration.py` | `calibrate_assessment` 正式矩阵 |
| `src/final_analyst/validators.py` | 关键词硬闸 → semantic；生产 gate |
| `src/final_analyst/llm.py` | 关闭默认 phrase seal；repair 优先；应用 calibration |
| `src/final_analyst/live_prompt.py` | 语义要求取代必含字样 |
| `src/final_analyst/live_quality.py` | unresolved 用语义检测 |
| `src/final_analyst/synthesize.py` | grounded 走 `calibrate_assessment` |
| `src/final_analyst/industry_fixtures.py` | **新增** 消费/制造/半导体 fixtures |
| `tests/test_final_analyst_round5.py` | **新增** Round-5 测试套件 |
| `examples/fa_fixtures/round5/` | 跨行业产物 + live multi-run 统计 |

**未修改**：Evidence / Research canonical / Debate 主流程 / Time·Weight·Relevance。

---

## 3. 新增测试（Round-5）

Semantic / Evidence / Calibration / Cross-industry / Live：见 `tests/test_final_analyst_round5.py`（41 checks）。

---

## 4. 完整测试结果

| Suite | Result |
|------|--------|
| `python -m tests.test_final_analyst` | **67/67 PASS** |
| `python -m tests.test_final_analyst_round5` | **41/41 PASS** |

---

## 5. Live multi-run（A_unresolved × 3）

摘自 `examples/fa_fixtures/round5/live_multi_run_stats.json`（最近一次）：

| 指标 | 值 |
|------|----|
| run_count | 3 |
| modes | openai / grounded(fallback) / openai（波动） |
| phrase_seal_dependency | 0 |
| information_loss | 0 |
| assessment_drift | 0（均 unresolved） |
| fallback_count | ≤2（允许；至少 1 次 openai 成功） |

说明：DeepSeek 仍有偶发 semantic/citation 失败 → fail-closed fallback grounded，符合生产安全下限。

---

## 6. Evidence repair 统计

| 场景 | 行为 |
|------|------|
| 合法数字缺 citation | **REPAIR** 自动补 `evidence_ids`（Level1/2） |
| 无法 grounding 数字 | **REGENERATE/REJECT**，不 scrub 进生产输出 |
| scrub 仅 `allow_scrub=True` | 标记 `information_loss=true`，不得 production PASS |

---

## 7. Phrase seal dependency

| 模式 | 依赖 |
|------|------|
| 默认 openai 路径 | **0**（不调用 seal） |
| `FA_PHRASE_SEAL=1` | deprecated 兼容，notes 含 `openai_phrase_seal` → validator 拒绝生产 PASS |

---

## 8. Cross-industry 对照

| Fixture | resolution | pressure | 观察 |
|---------|------------|----------|------|
| consumer_unresolved (600519) | unresolved | elevated | 白酒增长/盈利结构 |
| mfg_bull_moderate (000338) | bull_supported | elevated | 量增利不增 / 订单 |
| semi_bear_moderate (688981) | bear_supported | — | ASP / 利用率 |
| mfg_bull_strong_mild vs semi_bull_strong_severe | 同 bull_supported/strong | elevated vs **severe** | **signature 不同**；severe 压低 assessment |

相同 resolution **不会**自动产出同一 judgment signature。

---

## 9. 600519 前后对照

| 维度 | Round-4 | Round-5 |
|------|---------|---------|
| 过闸手段 | phrase seal + number scrub | semantic validation + evidence repair |
| 信息损失 | scrub 可留下「同比 -」 | scrub 不得进入生产 PASS |
| calibration | 有 support/pressure | 正式 matrix + drift 检查 |
| live | 6 fixtures 通 | + multi-run invariants |

---

## 10. 人工 Scorecard

| 维度 | 分 | 说明 |
|------|----|------|
| Analytical Depth | **4** | |
| Analytical Increment | **4** | |
| Evidence Grounding | **4** | repair 后 grounding；偶发 fallback |
| Evidence Preservation | **5** | 禁止生产 scrub 残缺 |
| Fact / Inference | **4** | |
| Uncertainty | **4** | 语义保留未裁定意图 |
| Scenario | **4** | 条件边界语义化 |
| Debate Consumption | **4** | |
| Traceability | **5** | |
| Non-Redundancy | **4** | |
| Judgment Calibration | **4** | matrix + severe cap |
| Cross-industry robustness | **4** | |
| Live Stability | **4** | 仍有偶发 fallback |

### 人工十问（摘要）

1. **是否改变解释层？** 是（优先级/矛盾/条件），非 Research 复述。  
2. **Debate 强弱幅度？** 单调且受 pressure 限制。  
3. **severe 限制 strong？** 是 → moderate + limiting_factors。  
4. **同 resolution 不同 Research？** signature / pressure 不同。  
5. **外部事实？** 未观察到。  
6. **数字保留？** repair 优先；未 grounding 则拒收。  
7. **为过闸堆词？** 生产路径已去 seal。  
8. **Scenario 条件？** 语义边界通过。  
9. **gap 继承？** grounded/industry 保留。  
10. **Grounded fallback？** 仍是可接受安全下限。

---

## 11. GO / NO-GO

### **GO — Production Candidate**

---

## 12. 残余问题

1. DeepSeek live **仍非 100% 稳定**（multi-run 可出现 1 次 grounded fallback）。  
2. Evidence repair **尚未做 Level-3 LLM repair prompt**（当前 Level1/2 足够多数 case）。  
3. 跨行业 fixture 复用 600519 EvidencePack 骨架做 claim 改写，非独立全量 Evidence 重建（边界允许：不改 Evidence 构建）。  
4. `calibrate_assessment` 在 openai 路径会**覆写** meta.assessment_strength；模型原文 strength 仅作参考。

---

## 复现

```bat
cd /d C:\Users\86137\ashare-deep-research
set PYTHONPATH=C:\Users\86137\ashare-deep-research\src
python -m tests.test_final_analyst
python -m tests.test_final_analyst_round5
```
