# Research Pipeline Second Audit

**标的**：600519（贵州茅台）  
**审计类型**：Research Layer 第二阶段 End-to-End Quality Audit（只读，不改代码）  
**审计日期**：2026-08-15  
**对照**：第一轮 `RESEARCH_PIPELINE_AUDIT.md`（总分 22/40，NO-GO）

> 原则：88/88 PASS ≠ Research Quality PASS。优先发现问题，不美化。  
> Grounded 模式本质是确定性模板合成——即使产出 Level 3 句子，也要标注其非涌现研究。

---

## 1. Test Status

| Suite | Result |
|------|--------|
| `tests.test_evidence` | 13/13 PASS |
| `tests.test_research_context_modules` | 23/23 PASS |
| `tests.test_research_agents` | 27/27 PASS |
| `tests.test_debate` | 25/25 PASS |
| **合计** | **88/88 PASS** |

**WARNING（非失败）**：契约/结构测试全部通过，但本审计发现：同 claim 跨 section 大量重复、Relevance 误把弱相关快讯标为 `industry_related`、Weight 对 synthesizer 选题影响有限、Debate 层 citation-incomplete 仍在。

---

## 2. Pipeline 状态

```
Evidence Pack (112)
  → ResearchTimeContext (research_as_of_date)
  → Weight rank + Relevance + Window buckets + excluded_audit
  → Fundamental / Market (cross / tension / insufficient)
  → Bull / Bear → Challenge → Rebuttal
  → Final Analyst（未实现）
```

实现核对（代码级）：`context.py` 确实调用 `assign_window_bucket` / `rank_evidence` / `classify_relevance`，并写出 `excluded_audit`。  
**字段存在且参与 context 构造**；但 Grounded synthesizer 仍按 subtype/bundle 选题，不完全按 weight 序消费列表。

---

## 3. Research Depth 前后对比

### Level 抽样（Fundamental ≥10）

| # | Finding（摘要） | 关系？ | Level |
|---|-----------------|--------|------:|
| 1 | 公司身份×行业归属已确认 | 弱关系（并列确认） | 2 |
| 2 | 客户结构 insufficient | 正确缺口 | — |
| 3 | 高 ROE/毛利率 × 净利/营收同比下滑 → 主要矛盾是增长承压 | **真张力** | **3–4** |
| 4 | 估值 PE/PB × ROE/增速 → 估值更依赖增长恢复 | **跨尺度张力** | **4** |
| 5 | 同 #3 在 profitability 再出现一遍 | 重复 | 3（重复不计新洞察） |
| 6 | 资产负债率/现金 × 营收/利润 | 关系偏模板“需对照” | 2–3 |
| 7 | OCF/利润 × 净利/同比 | 有对照框架，分析浅 | 2–3 |
| 8 | 单条公告 atomic | 复述事件 | 1–2 |
| 9 | 多期 EPS 一致预期 cross | 并列截面，非深度 | 2 |
| 10 | key_strengths/weaknesses 再贴 #3/#4 | 重复 | — |

**Fundamental 主导 Level：3**（核心 tension 稳定达到 Level 3，并偶发 Level 4；其余仍有模板与复述）

### Level 抽样（Market ≥10）

| # | Finding（摘要） | Level |
|---|-----------------|------:|
| 1 | 价格 × MA5/20/60/250，短中期多头排列 | **3** |
| 2 | 估值 × 价格/52周位置 | 2–3 |
| 3 | 短中期均线 × MA250 时间尺度冲突 | **3–4** |
| 4 | RSI × MACD | 2 |
| 5–7 | 同上 claim 在 trend / MA / technical / cross 重复 | 重复 |
| 8 | Current 7d “行业相关”资讯（外汇局/富维/*ST闻泰） | **伪 cross**（弱相关拼盘）→ 质量差 |
| 9 | macro_background atomic | 2（元说明正确） |
| 10 | news_narrative：Previous 不足 → insufficient | **正确** |

**Market 主导 Level：3**（价格/均线张力够格；新闻侧质量拖后腿）

### 代表性好例子（Level 3/4）

**Level 4（Fundamental）**  
> “公司仍保持较高资本回报/毛利率…但同期营收或净利润同比变化显示增长动能承压，因此当前主要矛盾并非盈利能力不足，而是增长动能承压。”  
> evidence_ids：ROE + 毛利率 + 净利同比 + 营收同比  

**Level 4（Fundamental，估值）**  
> “若高 ROE 主要反映既有盈利能力，而收入/利润增速承压，则估值合理性更依赖未来增长恢复…”  
> 显式跨 `data_date` 估值截面与 `report_date` 财务期  

**Level 3–4（Market）**  
> “短中期均线结构与长期均线（如 MA250）可能不一致…应分开表述，避免时间尺度混用。”

### 前后对比

| | 上一轮 | 本轮 |
|--|--------|------|
| Research Depth | **2**（大量 Level 1–2 复述） | **3**（核心张力稳定 Level 3，偶发 4） |
| 是否仍像分拣机 | 是 | **部分研究员 + 大量模板** |

**仍存在模板化**：Grounded synthesizer 固定句式（“联合引用：…”、“不能…而不…”）；同一 tension 被复制到多个 section。

---

## 4. Information Compression 前后对比

| 指标 | 数值 |
|------|------|
| Evidence Pack JSON | ~94k chars |
| Fundamental + Market | ~38k chars（约 41% 体积） |
| 同一 tension claim 出现次数 | 可见 **5–10+**（financial / profitability / cross / tensions / strengths / weaknesses） |
| 同一 `evidence_id`（如 ROE）出现在 ≥3 处 | **9 个 id** 级别复用 |

**评价**：

- 相对上一轮“112 条扁平复述”，现在有研究问题锚定 → 有进步。  
- 但 **压缩失败于结构重复**：cross finding 没有“替代”原子展开，反而在多栏目克隆。  
- 原子公告/预期仍占位。

**Information Compression：2 → 2**（组织更好，但重复仍严重；按门槛 **未到 ≥3**）

---

## 5. Time Context Audit

| 检查项 | 结果 |
|--------|------|
| `research_as_of_date` 明确存在 | **是**（输出与 context 均为 `2026-08-15`，来自 pack.generated_at） |
| 排除 as_of 之后 | **是**（单测 + `post_as_of` 机制；本 pack 无未来业务日样本） |
| Current 7d / Previous 8–30d 不重叠 | **是**（单测：`2026-08-08..14` vs `07-16..08-07`） |
| 业务时间不用 `retrieved_at` | **是**（published_at / report_date / data_date） |
| 公司事件 90d | **是**（>90d 股东变动 → `out_of_window`，见 excluded_audit age_days=228+） |
| 财务 report_date / 行情 data_date | **是** |
| Narrative change | Previous **n=0** → 正确输出 **insufficient**，未编造变化 |
| Current 窗内内容质量 | Current n=5，但多为弱相关“行业”误分类（见下） |

**结论**：Time Window **真正影响入窗**（尤其 out_of_window 与 Previous 空窗）。Narrative change 在数据不足时行为正确；在数据充足时尚未在本标的上验证“主题变化识别”深度（因 Previous 为空）。

---

## 6. Weight Audit

| 问题 | 判定 |
|------|------|
| context 是否按 weight 排序？ | **是**（`rank_evidence` + serialize 再 sort） |
| weight 是否写入 JSON？ | **是** |
| 是否改变 synthesizer“选哪条”？ | **基本否**：Grounded 按 subtype/bundle 取证，不按 weight 序挑选 |
| stale 是否进 recent？ | 公司 stale 事件被 90d 窗挡在外；新闻 stale 出 30d 窗 |
| very_recent vs periodic 差异 | 财务多为 periodic weight=0.8；行情 spot 常 1.0——排序有差异，但对最终 claim 选题影响小 |

**标记：`WEIGHT_PARTIALLY_USED`**

- 已解决上一轮的“只附录不入 context”。  
- **未完全解决**“weight 改变模型看到并采用什么”：对 Grounded 路径，weight 主要是列表排序装饰；真正选题规则仍是模板 bundle。

不可再标 `WEIGHT_NOT_USED`，但也不可宣称“权重驱动研究推理”。

---

## 7. Relevance Audit

**成功点**：

- CDN/液冷/GPU 算力快讯 → `excluded_audit.reason=irrelevant`（未进核心新闻推理句的主论据池意图正确）。

**失败点（重要）**：

`news_current_7d` 中被标为 `industry_related` 并进入 Market finding 的样本包括：

- 国家外汇局经常账户顺差  
- 富维股份座椅定点  
- *ST闻泰亏损  

这些与贵州茅台/白酒 **弱相关或无关**，却被写成：

> “Current 7d 内个股/行业相关资讯可用于短期叙事背景…”

并挂上上述 evidence_ids。

→ **Relevance 规则过宽 / 误分类**，导致“噪音从核心换到‘行业相关’标签后仍进入研究表述”。

宏观桶分离的意图正确，执行不完整。

---

## 8. Citation Audit

### Research 层

- `validate_research_citations(Fundamental/Market)` → **空错误列表**  
- 上一轮 Research 式“整句复述无 id”问题已大幅消除；cross/tension 的数字出现在 reasoning 时，对应 id 基本齐全。

**Research citation-incomplete：未发现硬错误。**

### Debate 层（回归，未修）

| 位置 | 事实 | 已挂 id | 缺失 | 严重度 |
|------|------|---------|------|--------|
| BULL_01.reasoning | 净利同比 **-4.53%** | 仅 ROE、毛利率 | `net_profit_yoy` | 中（与首轮相同） |
| BEAR_01.reasoning | ROE **33.65%** | 增速/利润类 | ROE id | 中 |
| BEAR_03.reasoning | 毛利率 **91.18%** | PE/预期/事件 | gross_margin id | 中 |

→ Research 修好了；**Bull/Bear 模板仍 citation-incomplete**（本阶段不改 Debate，记为遗留）。

---

## 9. Fundamental / Market Quality

**还是不是 Evidence 分拣机？**

- **不再只是分拣机**：已能主动写出“高盈利 vs 增长承压”“短趋势 vs MA250”等研究张力。  
- **也还不是成熟研究员**：Grounded 模板句、栏目克隆、新闻误用仍明显。

| 能力 | 判定 |
|------|------|
| 发现高盈利×增长张力 | **是** |
| 发现短×长均线冲突 | **是** |
| 估值×增长×价格联系 | **部分是**（估值×增长 tension 有；与价格趋势的统一叙事弱） |
| 新闻叙事变化 | 本样本 Previous 空 → insufficient（正确）；Current 内容质量差 |

---

## 10. Bull/Bear Regression

| 检查 | 结果 |
|------|------|
| 仍能消费新 Research JSON | **是**（debate 25/25） |
| Challenge/Rebuttal 结构 | **仍成立**（interpretation_conflict 等） |
| 新 citation 问题 | Debate 旧问题仍在；非 Research 引入 |
| 信息偏差 | Bull/Bear **几乎不吸收**新的 cross/tension 结构，仍走旧 grounded 卡片；Research 升级对对抗层增益有限 |

---

## 11. Scorecard：22/40 → 本轮

| 维度 | 上轮 | 本轮 | 变化 |
|------|-----:|-----:|------|
| 1. Evidence Grounding | 4 | **4** | 持平（Research 更好；Debate 仍漏引） |
| 2. Research Depth | 2 | **3** | +1 |
| 3. Fundamental Analysis | 3 | **4** | +1 |
| 4. Market Analysis | 2 | **3** | +1 |
| 5. Bull/Bear Differentiation | 3 | **3** | 持平 |
| 6. Challenge Quality | 3 | **3** | 持平 |
| 7. Rebuttal Quality | 3 | **3** | 持平 |
| 8. Information Compression | 2 | **2** | 持平（重复未解决） |
| **Total** | **22** | **25** | **+3** |

---

## 12. Major Remaining Problems

1. **Information Compression 未达标**：同一 Level 3/4 claim 在多 section / strengths / weaknesses 克隆。  
2. **Grounded 模板化**：深度句子可预判；不是 LLM 涌现研究。  
3. **Relevance 误分类**：弱相关 CLS 进入 Current“行业”叙事。  
4. **Weight 仅部分生效**：排序进入 context，但选题不按 weight。  
5. **Narrative change 未在双边有料时验证**（本标的 Previous 空）。  
6. **Debate citation-incomplete 遗留**；Bull/Bear 未消费新 Research tensions。  
7. 测试虚高：PASS 不覆盖“重复度 / 误相关 / 模板深度”。

---

## 13. GO / NO-GO

### 门槛核对

| 条件 | 要求 | 本轮 | 结果 |
|------|------|------|------|
| Evidence Grounding | ≥4 | 4 | PASS |
| Research Depth | ≥3 | 3 | PASS |
| Fundamental | ≥3 | 4 | PASS |
| Market | ≥3 | 3 | PASS |
| Bull/Bear | ≥3 | 3 | PASS |
| Challenge | ≥3 | 3 | PASS |
| Rebuttal | ≥3 | 3 | PASS |
| Information Compression | ≥3 | **2** | **FAIL** |

# 最终判定：**NO-GO**

**原因（硬门槛）**：Information Compression 仍为 2；按本阶段规则，Depth 或 Compression <3 → 不得进入 Final Analyst 开发。

### 进入 Final Analyst 前的最小必要项（仅建议，本次不改代码）

1. **去重压缩**：同一 `finding_kind=tension/cross` claim 全局只保留一处权威陈述；section 用引用而非复制。  
2. **收紧 Relevance**：禁止过宽 industry token；个股外 news 默认 macro/irrelevant，除非命中名称/代码/行业强词。  
3. **Weight 进入选题**：bundle 多候选时按 weight 取证，或降低低 weight 入 prompt。  
4. （可选，非本层）Debate 补齐 citation；让 Bull/Bear 显式引用 Research tensions。

---

## 附录：十问直答

1. Depth 是否稳定 Level 3？→ **是（核心张力）**，但模板化。  
2. Compression ≥3？→ **否（仍为 2）**。  
3. Weight 是否影响 context？→ **排序是，选题弱** → PARTIALLY_USED。  
4. Time Window 是否影响入窗？→ **是**。  
5. 7d vs 8–30d narrative change？→ Previous 空 → **正确 insufficient**；未验证双边主题对比。  
6. Relevance 是否排除无关？→ **部分**（CDN 成功；外汇局/富维等失败）。  
7. Citation Completeness？→ **Research 是；Debate 否**。  
8. 真跨证据 vs 换皮复述？→ **核心是真跨证据；周边仍有伪 cross / 重复**。  
9. 仍模板化？→ **是（Grounded）**。  
10. Research 是否足够可靠供 Bull/Bear / 进 Final Analyst？→ **供对抗消费有改善但仍不够；进 Final Analyst = NO-GO**。

---

*End of Second Audit — NO-GO for Final Analyst development.*
