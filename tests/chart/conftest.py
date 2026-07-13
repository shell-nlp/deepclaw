import pytest

from deepclaw.middleware.chart import utils as chart_utils


@pytest.fixture(autouse=True)
def isolate_charts_dir(tmp_path):
    """测试中将图表输出目录隔离到临时路径，避免污染生产目录。"""
    original = chart_utils._get_charts_dir
    chart_utils._get_charts_dir = lambda: tmp_path / "charts"
    (tmp_path / "charts").mkdir(parents=True, exist_ok=True)
    yield
    chart_utils._get_charts_dir = original
