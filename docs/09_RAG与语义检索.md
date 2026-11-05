# RAG 与语义检索

## 1. 这个项目中 RAG 解决什么

RAG 不查询业务明细数据，也不代替 SQL 规划器。它在 DeepSeek 理解问题前，只召回相关的数仓知识：

- 指标名称、别名、口径和可用维度；
- 数据集粒度、时间字段和限制；
- 业务术语；
- 跨表关系；
- 经过验收的标准问数示例。

真实销售明细不进入 RAG 文档或向量库。

## 2. 主链路

```text
自然语言问题
  → KeywordRetriever
  → Top 8 指标/表/术语/关系/示例文档
  → DeepSeek 结构化意图
  → 通用查询规划器
  → 受控 SQL、权限注入和查询执行
```

RAG 的输出是“参考知识”，不是可执行 SQL。能力矩阵、SQL 编译器和权限层仍是不可绕过的确定性边界。

## 3. 文件与职责

- `app/retrieval/models.py`：定义检索文档和命中结果；
- `app/retrieval/keyword.py`：关键词排序和指标→数据集、示例→指标/数据集的结构化关联扩展；
- `app/metadata/loader.py`：将 YAML 知识组装成 32 个可检索文档，并保持原有上层调用接口；
- `metadata/relationships.yaml`：跨表关联与口径；
- `metadata/examples.yaml`：标准问数示例；
- `evals/retrieval_questions.yaml`：检索标注集；
- `scripts/evaluate_retrieval.py`：计算 Recall@5、Recall@8 和 MRR。

## 4. 评测结果

```bash
uv run python scripts/evaluate_retrieval.py
```

当前 10 个标注问题的结果：

```json
{
  "total": 10,
  "recall_at_5": 0.8967,
  "mrr": 0.9,
  "recall_at_8": 1.0
}
```

全量上下文会携带 32 份知识，Top 8 在当前标注集上保持 100% 召回，同时将文档数减少 75%。接入 Top 8 RAG 后，DeepSeek 通用问法仍为 32/32 通过。

## 5. 为什么暂时不上向量库

当前知识库只有 32 份文档，关键词+结构化关联在 Top 8 已达到 100% 召回。Embedding 和向量库会引入额外费用、服务依赖和运维成本，当前没有可量化收益。

后续当指标和数据集大幅增长、同义表达导致 Recall@K 下降时，再用同一标注集对比关键词、Embedding 和混合检索，只在准确率/成本权衡更好时升级。

## 6. 对外展示边界

服务内部保留文档 ID、得分和命中词，便于评测与排障。运营端 API 默认不暴露完整 RAG 上下文和 Prompt，避免页面冗余和内部元数据泄露；对外只展示业务结果、指标口径和必要的查询依据。
