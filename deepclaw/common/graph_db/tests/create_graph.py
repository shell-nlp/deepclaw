"""商科本体设计：基于 Neo4j 的指标体系知识图谱。

本体的核心是 指标 实体，指标之间通过 依赖/推导 关系构成知识网络。
指标的属性分为三类内嵌 JSON 字段，分别描述指标的生成逻辑、执行操作和元信息。

━━━ 实体 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
名称: 指标
描述: 核心实体，包含 name（可视化标题）和三类内嵌 JSON 属性：
   逻辑: 生成该指标涉及的数据库表、字段和计算公式
         {"表": "...", "字段": "...", "公式": "...", "过滤条件": "...", "说明": "..."}
   行动: 针对该指标需要执行的操作，每项含名称、描述、频率、负责人
         [{"名称": "数据采集", "描述": "...", "频率": "每月", "负责人": "..."}]
   属性: 该指标的元信息，如单位、数据来源等键值对
         [{"名称": "单位", "值": "万元"}, {"名称": "数据来源", "值": "..."}]

━━━ 关系 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
依赖: 指标━▶指标   前提依赖，A 依赖 B 表示计算 A 前必须先算出 B
推导: 指标━▶指标   可推导关系，A 推导 B 表示从 A 可间接推算出 B

━━━ 用法 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  uv run python deepclaw/common/graph_db/tests/test_neo4j.py
"""

import json

from deepclaw.common.graph_db.neo4j_db import Neo4jGraph


def _logic(
    table: str, fields: str, formula: str, *, filter_clause: str = "", desc: str = ""
) -> str:
    """构造逻辑内嵌属性 JSON 字符串。"""
    d: dict[str, str] = {"表": table, "字段": fields, "公式": formula}
    if filter_clause:
        d["过滤条件"] = filter_clause
    if desc:
        d["说明"] = desc
    return json.dumps(d, ensure_ascii=False)


def _actions(*items: dict) -> str:
    """构造行动内嵌属性 JSON 字符串。"""
    return json.dumps(list(items), ensure_ascii=False)


def _attrs(*items: dict) -> str:
    """构造属性内嵌属性 JSON 字符串。"""
    return json.dumps(list(items), ensure_ascii=False)


def build_ontology(graph: Neo4jGraph) -> None:
    """构建商科指标体系样例图。"""

    营业收入 = graph.add_node("指标", {
        "name": "营业收入",
        "描述": "企业日常经营活动产生的总收入",
        "逻辑": _logic(
            "financial_statements", "revenue", "SUM(revenue)",
            filter_clause="fiscal_year = $year AND statement_type = 'income'",
            desc="从 financial_statements 表按年度汇总 revenue 字段",
        ),
        "行动": _actions(
            {"名称": "数据采集", "描述": "从 ERP 系统抽取财务数据", "频率": "每月", "负责人": "财务部"},
        ),
        "属性": _attrs(
            {"名称": "单位", "值": "万元"},
            {"名称": "数据来源", "值": "财务系统 / 季报"},
        ),
    }, "ind_revenue")

    营业成本 = graph.add_node("指标", {
        "name": "营业成本",
        "描述": "与营业收入直接相关的成本",
        "逻辑": _logic(
            "financial_statements", "cost", "SUM(cost)",
            filter_clause="fiscal_year = $year AND statement_type = 'income'",
            desc="从 financial_statements 表按年度汇总 cost 字段",
        ),
        "行动": _actions(
            {"名称": "数据采集", "描述": "从 ERP 系统抽取财务数据", "频率": "每月", "负责人": "财务部"},
        ),
        "属性": _attrs(
            {"名称": "单位", "值": "万元"},
            {"名称": "数据来源", "值": "财务系统 / 季报"},
        ),
    }, "ind_cost")

    营业费用 = graph.add_node("指标", {
        "name": "营业费用",
        "描述": "销售、管理、研发等期间费用",
        "逻辑": _logic(
            "financial_statements", "opex", "SUM(opex)",
            filter_clause="fiscal_year = $year AND statement_type = 'income'",
            desc="从 financial_statements 表按年度汇总 opex 字段",
        ),
        "行动": _actions(
            {"名称": "数据采集", "描述": "从 ERP 系统抽取财务数据", "频率": "每月", "负责人": "财务部"},
        ),
        "属性": _attrs(
            {"名称": "单位", "值": "万元"},
            {"名称": "数据来源", "值": "财务系统 / 季报"},
        ),
    }, "ind_opex")

    总资产 = graph.add_node("指标", {
        "name": "总资产",
        "描述": "企业拥有或控制的全部资产",
        "逻辑": _logic(
            "balance_sheet", "total_assets", "total_assets",
            filter_clause="fiscal_year = $year",
            desc="从 balance_sheet 表取 total_assets 字段",
        ),
        "行动": _actions(
            {"名称": "数据采集", "描述": "从财务系统同步资产负债表数据", "频率": "每月", "负责人": "财务部"},
            {"名称": "数据校验", "描述": "核对总资产与总负债+所有者权益的勾稽关系", "频率": "每月", "负责人": "财务部"},
        ),
        "属性": _attrs(
            {"名称": "单位", "值": "万元"},
            {"名称": "数据来源", "值": "财务系统 / 季报"},
        ),
    }, "ind_total_assets")

    总负债 = graph.add_node("指标", {
        "name": "总负债",
        "描述": "企业需要偿还的全部债务",
        "逻辑": _logic(
            "balance_sheet", "total_liabilities", "total_liabilities",
            filter_clause="fiscal_year = $year",
            desc="从 balance_sheet 表取 total_liabilities 字段",
        ),
        "行动": _actions(
            {"名称": "数据采集", "描述": "从财务系统同步资产负债表数据", "频率": "每月", "负责人": "财务部"},
        ),
        "属性": _attrs(
            {"名称": "单位", "值": "万元"},
            {"名称": "数据来源", "值": "财务系统 / 季报"},
        ),
    }, "ind_total_liab")

    所得税 = graph.add_node("指标", {
        "name": "所得税费用",
        "描述": "当期应缴纳的所得税",
        "逻辑": _logic(
            "financial_statements", "tax", "SUM(tax)",
            filter_clause="fiscal_year = $year AND statement_type = 'income'",
            desc="从 financial_statements 表按年度汇总 tax 字段",
        ),
        "行动": _actions(
            {"名称": "数据采集", "描述": "从税务系统或财务系统取所得税数据", "频率": "每季度", "负责人": "税务部"},
        ),
        "属性": _attrs(
            {"名称": "单位", "值": "万元"},
            {"名称": "数据来源", "值": "财务系统 / 季报"},
        ),
    }, "ind_tax")

    毛利 = graph.add_node("指标", {
        "name": "毛利",
        "描述": "营业收入 - 营业成本",
        "逻辑": _logic(
            "financial_statements", "revenue, cost", "revenue - cost",
            filter_clause="fiscal_year = $year AND statement_type = 'income'",
            desc="从 financial_statements 表取营业收入和营业成本，计算差值",
        ),
        "行动": _actions(
            {"名称": "指标计算", "描述": "按逻辑公式自动计算派生指标", "频率": "每月", "负责人": "数据分析组"},
        ),
        "属性": _attrs(
            {"名称": "单位", "值": "万元"},
        ),
    }, "ind_gross_profit")

    毛利率 = graph.add_node("指标", {
        "name": "毛利率",
        "描述": "毛利 / 营业收入 × 100%",
        "逻辑": _logic(
            "financial_statements", "revenue, cost", "(revenue - cost) / revenue * 100",
            filter_clause="fiscal_year = $year AND statement_type = 'income'",
            desc="从 financial_statements 表取数，计算毛利率百分比",
        ),
        "行动": _actions(
            {"名称": "指标计算", "描述": "按逻辑公式自动计算派生指标", "频率": "每月", "负责人": "数据分析组"},
        ),
        "属性": _attrs(
            {"名称": "单位", "值": "百分比"},
        ),
    }, "ind_gross_margin")

    营业利润 = graph.add_node("指标", {
        "name": "营业利润",
        "描述": "毛利 - 营业费用",
        "逻辑": _logic(
            "financial_statements", "revenue, cost, opex", "revenue - cost - opex",
            filter_clause="fiscal_year = $year AND statement_type = 'income'",
            desc="从 financial_statements 表取数，依次减去成本和费用",
        ),
        "行动": _actions(
            {"名称": "指标计算", "描述": "按逻辑公式自动计算派生指标", "频率": "每月", "负责人": "数据分析组"},
        ),
        "属性": _attrs(
            {"名称": "单位", "值": "万元"},
        ),
    }, "ind_op_profit")

    净利润 = graph.add_node("指标", {
        "name": "净利润",
        "描述": "营业利润 - 所得税",
        "逻辑": _logic(
            "financial_statements", "revenue, cost, opex, tax",
            "revenue - cost - opex - tax",
            filter_clause="fiscal_year = $year AND statement_type = 'income'",
            desc="从 financial_statements 表取数，依次减去成本、费用和所得税",
        ),
        "行动": _actions(
            {"名称": "指标计算", "描述": "按逻辑公式自动计算派生指标", "频率": "每月", "负责人": "数据分析组"},
            {"名称": "报告生成", "描述": "生成经营分析报告并推送给管理层", "频率": "每季度", "负责人": "战略部"},
        ),
        "属性": _attrs(
            {"名称": "单位", "值": "万元"},
        ),
    }, "ind_net_profit")

    净利润率 = graph.add_node("指标", {
        "name": "净利润率",
        "描述": "净利润 / 营业收入 × 100%",
        "逻辑": _logic(
            "financial_statements", "revenue, cost, opex, tax",
            "(revenue - cost - opex - tax) / revenue * 100",
            filter_clause="fiscal_year = $year AND statement_type = 'income'",
            desc="从 financial_statements 表取数，计算净利润百分比",
        ),
        "行动": _actions(
            {"名称": "报告生成", "描述": "生成经营分析报告并推送给管理层", "频率": "每季度", "负责人": "战略部"},
        ),
        "属性": _attrs(
            {"名称": "单位", "值": "百分比"},
        ),
    }, "ind_net_margin")

    资产负债率 = graph.add_node("指标", {
        "name": "资产负债率",
        "描述": "总负债 / 总资产 × 100%",
        "逻辑": _logic(
            "balance_sheet", "total_liabilities, total_assets",
            "total_liabilities / total_assets * 100",
            filter_clause="fiscal_year = $year",
            desc="从 balance_sheet 表取负债和资产，计算比值",
        ),
        "行动": _actions(
            {"名称": "指标计算", "描述": "按逻辑公式自动计算派生指标", "频率": "每月", "负责人": "数据分析组"},
            {"名称": "报告生成", "描述": "生成经营分析报告并推送给管理层", "频率": "每季度", "负责人": "战略部"},
        ),
        "属性": _attrs(
            {"名称": "单位", "值": "百分比"},
        ),
    }, "ind_debt_ratio")

    # ------------------------------------------------------------------
    # 3. 添加前提依赖关系
    # ------------------------------------------------------------------
    graph.add_edge(毛利, 营业收入, "依赖", {"说明": "计算毛利需要营业收入"})
    graph.add_edge(毛利, 营业成本, "依赖", {"说明": "计算毛利需要营业成本"})
    graph.add_edge(毛利率, 毛利, "依赖", {"说明": "计算毛利率需要毛利"})
    graph.add_edge(毛利率, 营业收入, "依赖", {"说明": "计算毛利率需要营业收入"})
    graph.add_edge(营业利润, 毛利, "依赖", {"说明": "计算营业利润需要毛利"})
    graph.add_edge(营业利润, 营业费用, "依赖", {"说明": "计算营业利润需要营业费用"})
    graph.add_edge(净利润, 营业利润, "依赖", {"说明": "计算净利润需要营业利润"})
    graph.add_edge(净利润, 所得税, "依赖", {"说明": "计算净利润需要所得税"})
    graph.add_edge(净利润率, 净利润, "依赖", {"说明": "计算净利润率需要净利润"})
    graph.add_edge(净利润率, 营业收入, "依赖", {"说明": "计算净利润率需要营业收入"})
    graph.add_edge(资产负债率, 总负债, "依赖", {"说明": "计算资产负债率需要总负债"})
    graph.add_edge(资产负债率, 总资产, "依赖", {"说明": "计算资产负债率需要总资产"})

    # ------------------------------------------------------------------
    # 4. 添加可推导关系
    # ------------------------------------------------------------------
    graph.add_edge(营业收入, 毛利, "推导", {"说明": "营业收入可参与计算毛利"})
    graph.add_edge(营业成本, 毛利, "推导", {"说明": "营业成本可参与计算毛利"})
    graph.add_edge(毛利, 毛利率, "推导", {"说明": "毛利可用于推算毛利率"})
    graph.add_edge(毛利, 营业利润, "推导", {"说明": "毛利可用于推算营业利润"})
    graph.add_edge(营业利润, 净利润, "推导", {"说明": "营业利润可用于推算净利润"})
    graph.add_edge(净利润, 净利润率, "推导", {"说明": "净利润可用于推算净利润率"})
    graph.add_edge(总负债, 资产负债率, "推导", {"说明": "总负债可用于推算资产负债率"})
    graph.add_edge(总资产, 资产负债率, "推导", {"说明": "总资产可用于推算资产负债率"})


# ------------------------------------------------------------------
# 独立运行入口（uv run python deepclaw/common/graph_db/tests/test_neo4j.py）
# ------------------------------------------------------------------


def main() -> None:
    """独立运行：构建图谱并打印示例查询。"""
    graph = Neo4jGraph(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="neo4j@2025",
        database="neo4j",
    )
    graph.clear_database()
    try:
        build_ontology(graph)

        print("\n=== 所有指标 ===")
        for n in graph.get_nodes_by_label("指标"):
            p = n["properties"]
            actions_list = json.loads(p.get("行动", "[]"))
            action_names = [a["名称"] for a in actions_list]
            print(f"  [{n['id']}] {p.get('name')} — {p.get('描述')}")
            print(f"          行动: {', '.join(action_names)}")

        print("\n=== 资产负债率的三类内嵌属性 ===")
        results = graph.run_cypher_query("""
            MATCH (n:指标 {id: 'ind_debt_ratio'})
            RETURN n.逻辑 AS logic_json, n.行动 AS actions_json, n.属性 AS attrs_json
        """)
        for r in results:
            logic = json.loads(r["logic_json"])
            actions = json.loads(r["actions_json"])
            attrs = json.loads(r["attrs_json"])
            print(f"  逻辑: 表={logic['表']}, 字段={logic['字段']}, 公式={logic['公式']}")
            print(f"  行动: {', '.join(a['名称'] + '(' + a['负责人'] + ')' for a in actions)}")
            print(f"  属性: {', '.join(a['名称'] + '=' + a['值'] for a in attrs)}")

        print("\n=== 净利润的前提依赖链 ===")
        results = graph.run_cypher_query("""
            MATCH (n:指标 {id: 'ind_net_profit'})-[:依赖*1..]->(dep)
            RETURN dep.id AS id, dep.name AS name
        """)
        for r in results:
            print(f"  <- {r['name']} ({r['id']})")

        print("\n=== 净利润关联的行动（内嵌 JSON 属性）===")
        results = graph.run_cypher_query("""
            MATCH (n:指标 {id: 'ind_net_profit'})
            RETURN n.行动 AS actions_json
        """)
        for r in results:
            for a in json.loads(r["actions_json"]):
                print(f"  {a['名称']} (负责人: {a['负责人']}, 频率: {a['频率']})")

        print("\n=== 营业收入的可推导链路 ===")
        results = graph.run_cypher_query("""
            MATCH (n:指标 {id: 'ind_revenue'})-[:推导*1..]->(derived)
            RETURN derived.id AS id, derived.name AS name
        """)
        for r in results:
            print(f"  -> {r['name']} ({r['id']})")
    finally:
        graph.close()


if __name__ == "__main__":
    main()
