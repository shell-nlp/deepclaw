# metric_config 表分析报告

| 项目 | 内容 |
|------|------|
| 数据库 | PostgreSQL |
| Schema | `ai` |
| 表名 | `metric_config` |
| 总行数 | 731 |
| 表注释 | 无 |

## 列定义

| 序号 | 列名 | 类型 | 可空 | 默认值 | 说明 |
|------|------|------|------|--------|------|
| 1 | `id` | `character varying` | NO | - | 主键，32 位 hex 标识符 |
| 2 | `metric_name` | `character varying` | NO | - | 指标名称（中文） |
| 3 | `synonyms_list` | `ARRAY` | YES | - | 同义词列表（数组） |
| 4 | `metric_description` | `character varying` | YES | - | 指标描述 |
| 5 | `schema_name` | `character varying` | YES | - | 来源库 schema |
| 6 | `table_name` | `character varying` | YES | - | 来源表名 |
| 7 | `column_name` | `character varying` | YES | - | 来源字段名 |
| 8 | `column_type` | `character varying` | YES | - | 字段类型 |
| 9 | `metric_type` | `character varying` | YES | - | 指标分类编码 |
| 10 | `unit` | `character varying` | YES | - | 单位（%、pp、万元） |
| 11 | `calculation_condition` | `character varying` | YES | - | 计算过滤条件 |
| 12 | `embedding` | `USER-DEFINED` | YES | - | 1024 维向量嵌入（语义检索） |
| 13 | `tags` | `jsonb` | NO | '{}'::jsonb | 标签（JSON） |
| 14 | `status` | `boolean` | NO | true | 启用状态 |
| 15 | `created_at` | `timestamp with time zone` | NO | now() | 创建时间 |
| 16 | `mom_column_name` | `character varying` | YES | - | 环比参照列名 |
| 17 | `order_sort` | `integer` | YES | - | 排序序号 |

## 约束与索引

| 名称 | 类型 | 定义 |
|------|------|------|
| `metric_config_pkey` | b'p' | PRIMARY KEY (id) |
| `idx_metric_embedding_hnsw` | INDEX | CREATE INDEX idx_metric_embedding_hnsw ON ai.metric_config USING hnsw (embedding public.vector_cosine_ops) WITH (m='16', ef_construction='64') |
| `idx_synonyms_gin` | INDEX | CREATE INDEX idx_synonyms_gin ON ai.metric_config USING gin (synonyms_list) |
| `uq_metric_name` | INDEX | CREATE UNIQUE INDEX uq_metric_name ON ai.metric_config USING btree (table_name, metric_name) |

## 数据分布

### metric_type（指标分类）

| metric_type | 数量 |
|:-----------:|:----:|
| 8 | 110 |
| 2 | 81 |
| 3 | 42 |
| 6 | 37 |
| 10 | 18 |
| 4 | 17 |
| 1 | 14 |
| 11 | 13 |
| 5 | 13 |
| 12 | 9 |
| 9 | 9 |
| 7 | 4 |
| NULL | 364 |

未分类（NULL）占 49.8%

### unit（单位）

| unit | 数量 |
|:----:|:----:|
| NULL | 504 |
| % | 201 |
| 万元 | 14 |
| pp | 12 |

### table_name TOP 10（来源表）

| 表名 | 指标数 |
|------|:------:|
| `TB_KR_FM_SK_ZDYW_FZ_KD_DAY` | 231 |
| `TB_KR_GRP_SK_OPPO_TOL_RH_DAY` | 110 |
| `TB_KR_GRP_SK_SCENE_SHARES_DAY` | 63 |
| `TB_KR_GRP_SK_PK_BENCHMARK_DAY` | 40 |
| `TB_KR_GRP_SK_POI_PACK_TOL_DAY` | 39 |
| `TB_KR_GRP_SK_POI_KD_SHARES_DAY` | 36 |
| `TB_KR_GRP_SK_FCP_TOTAL_FEE_DAY` | 30 |
| `TB_KR_GRP_SK_BIG_ZX_CUST_DAY` | 20 |
| `TB_KR_GRP_SK_GRP_TOL_DAY` | 19 |
| `TB_KR_GRP_SK_LOWPACK_TOTAL_MON` | 18 |

共涉及 23 张来源表，全部属于 `GISTOOLS` schema。

### status（状态）

全部 731 条记录均为 `true`（启用）。

## 功能用途分析

`metric_config` 是一个**指标配置元数据表**，服务于 NL2SQL 或智能 BI 场景：

1. **语义检索** — `embedding` 列存储 1024 维向量，配合 HNSW 索引（cosine 距离），支持通过自然语言查询找到最相近的指标定义
2. **指标溯源** — `schema_name` / `table_name` / `column_name` 三字段定位指标在数据仓库中的物理位置
3. **计算条件** — `calculation_condition` 记录计算时的 WHERE 过滤条件（如场景类型、指标编码等）
4. **同义词扩展** — `synonyms_list` 配合 GIN 索引支持同义词匹配（但当前覆盖率极低）
5. **环比分析** — `mom_column_name` 指定环比参照列
6. **排序展示** — `order_sort` 控制指标在界面/API 返回中的展示顺序

## 潜在改进项

- `metric_description` 全表为空（仅 0 条有值），应补充业务描述以提升 NL2SQL 语义理解质量
- 364 条（49.8%）记录 `metric_type` 为 NULL，建议完成分类标注
- `synonyms_list` 覆盖率仅 0.3%，应系统性地补充同义词以提升召回率
- `column_type` 全表为空，补充后可用于类型感知的 SQL 生成