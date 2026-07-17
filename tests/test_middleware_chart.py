import matplotlib.pyplot as plt

from deepclaw.middleware.chart import utils


def test_save_chart_to_workspace_returns_absolute_url(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "_CHARTS_DIR", tmp_path)
    monkeypatch.setattr(utils.settings, "CHART_PUBLIC_URL", "https://charts.example.com/")

    figure = plt.figure()
    chart_url = utils.save_chart_to_workspace(figure)

    assert chart_url.startswith("https://charts.example.com/charts/")
    assert (tmp_path / chart_url.rsplit("/", maxsplit=1)[-1]).is_file()


def test_save_chart_to_workspace_returns_relative_url_without_public_url(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "_CHARTS_DIR", tmp_path)
    monkeypatch.setattr(utils.settings, "CHART_PUBLIC_URL", "")

    chart_url = utils.save_chart_to_workspace(plt.figure())

    assert chart_url.startswith("/charts/")
