"""PDF 转换依赖提示测试。"""

from deepclaw.common.text_splitter import FileToPDFConverter


def test_libreoffice_hint_contains_windows_and_linux_install_methods():
    """缺少 LibreOffice 时同时给出 Windows 和 Linux 安装方式。"""
    hint = FileToPDFConverter()._get_soffice_install_hint()
    assert "https://www.libreoffice.org/download/download-libreoffice/" in hint
    assert (
        "winget install --id TheDocumentFoundation.LibreOffice -e "
        "--accept-package-agreements --accept-source-agreements"
    ) in hint
    assert "apt-get update" in hint
    assert "dnf install" in hint
