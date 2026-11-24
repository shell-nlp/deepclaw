"""权限目录与路由守卫的一致性回归测试。

断言两件事：代码里每个 require_permission 都出现在权限目录中；
目录里每一条规则都对应真实存在的受保护路由，避免出现装饰性权限。
"""

import re
from pathlib import Path

from deepclaw.web_backend.auth.rbac.permissions import (
    list_permission_definitions,
    matches_rule_path,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "deepclaw"
CALL_PATTERN = re.compile(
    r'(?:require_permission\(\s*|agent_has_permission\(\s*\w+,\s*)"([^"]+)"\s*,\s*"([^"]+)"'
)


def _scanned_calls() -> set[tuple[str, str]]:
    """扫描代码中带字面量参数的权限守卫调用。

    Args:
        无。

    Returns:
        set[tuple[str, str]]: (资源路径, 动作) 集合。
    """
    calls: set[tuple[str, str]] = set()
    for source in PACKAGE_ROOT.rglob("*.py"):
        calls.update(CALL_PATTERN.findall(source.read_text(encoding="utf-8")))
    return calls


def test_every_guard_is_covered_by_permission_catalog():
    """所有受保护的接口都能在权限目录里被勾选到。

    Args:
        无。
    """
    rules = [
        (rule.path, rule.action)
        for definition in list_permission_definitions()
        for rule in definition.rules
    ]
    uncovered = [
        (path, action)
        for path, action in sorted(_scanned_calls())
        if not any(
            rule_action == action and matches_rule_path(rule_path, path)
            for rule_path, rule_action in rules
        )
    ]
    assert uncovered == [], f"这些受保护接口没有对应的权限目录项：{uncovered}"


def test_every_catalog_rule_matches_a_real_guarded_route():
    """目录里的规则必须真实被某个守卫使用，不能是装饰性权限。

    Args:
        无。
    """
    calls = _scanned_calls()
    orphaned = [
        (rule.path, rule.action)
        for definition in list_permission_definitions()
        for rule in definition.rules
        if not any(
            action == rule.action and matches_rule_path(rule.path, path)
            for path, action in calls
        )
    ]
    assert orphaned == [], f"这些权限目录项没有对应的受保护路由：{orphaned}"
