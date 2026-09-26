"""PDF 目录切分的内容完整性回归测试。"""

import fitz
import pytest

from deepclaw.common import text_splitter as pdf_module
from deepclaw.common.text_splitter import LoadedPDFFile, PDFParser, match_pdf_title


class MemoryPDFReader:
    """从内存提供测试 PDF。"""

    def __init__(self, file_bytes: bytes):
        """记录 PDF 内容。

        Args:
            file_bytes: 测试 PDF 的二进制内容。
        """
        self.file_bytes = file_bytes

    def load(self, bucket_name: str, file_path: str) -> LoadedPDFFile:
        """返回内存 PDF。

        Args:
            bucket_name: 存储桶名称。
            file_path: 文件路径。
        """
        return LoadedPDFFile(self.file_bytes, file_path)


def test_pdf_title_matching_normalizes_format_and_rejects_unrelated_text():
    """格式差异和高置信近似可匹配，缺少标题则不猜测边界。

    Args:
        无。
    """
    lines = [
        "第一章  项目概述\n",
        "项目概述内容。\n",
        "1) 固定资产包括办公设施设备和办公用品等\n",
        "这里是无关正文。\n",
    ]
    assert match_pdf_title("第一章：项目概述", lines, 0, len(lines)) == (0, "exact")
    assert match_pdf_title(
        "1)固定资产包括办公设施设备和办公用品", lines, 2, len(lines)
    ) == (2, "exact")
    assert match_pdf_title("其他章节", lines, 0, len(lines)) is None


def test_pdf_title_matching_across_two_lines():
    """提取器把书签标题断成两行时仍可定位首行。

    Args:
        无。
    """
    lines = ["第一章 项目\n", "概述\n", "详细内容\n"]
    assert match_pdf_title("第一章项目概述", lines, 0, len(lines)) == (0, "multiline")


def test_same_page_outline_preserves_text_without_duplicates():
    """同页目录和长段落不得重复或丢失。

    Args:
        无。
    """
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "PREFACE UNIQUE TEXT")
    page = pdf.new_page()
    page.insert_text((72, 72), "ALPHA CHAPTER")
    page.insert_text((72, 100), "A" * 400)
    page.insert_text((72, 128), "BETA CHAPTER")
    page.insert_text((72, 156), "B" * 800)
    pdf.set_toc([[1, "ALPHA CHAPTER", 2], [1, "BETA CHAPTER", 2]])
    file_bytes = pdf.tobytes()
    pdf.close()

    docs = PDFParser("", "test.pdf", reader=MemoryPDFReader(file_bytes)).get_chunk()
    content = "".join(doc.metadata["ori_text"] for doc in docs)
    assert content.count("PREFACE UNIQUE TEXT") == 1
    assert content.count("ALPHA CHAPTER") == 1
    assert content.count("BETA CHAPTER") == 1
    assert content.count("A" * 100) == 4
    assert content.count("B" * 100) == 8
    assert any(len(doc.page_content) > 600 for doc in docs)


def test_outline_title_missing_from_page_does_not_drop_text():
    """书签文字与正文不一致时仍保留正文。

    Args:
        无。
    """
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "FIRST PAGE CONTENT")
    page = pdf.new_page()
    page.insert_text((72, 72), "SECOND PAGE CONTENT")
    pdf.set_toc([[1, "MISSING BOOKMARK NAME", 2]])
    file_bytes = pdf.tobytes()
    pdf.close()

    docs = PDFParser("", "test.pdf", reader=MemoryPDFReader(file_bytes)).get_chunk()
    content = "".join(doc.metadata["ori_text"] for doc in docs)
    assert content.count("FIRST PAGE CONTENT") == 1
    assert content.count("SECOND PAGE CONTENT") == 1


def test_page_extraction_falls_back_to_pymupdf(monkeypatch):
    """单页主提取失败时使用 PyMuPDF，并保留真实页码。

    Args:
        monkeypatch: pytest 的替换依赖夹具。
    """
    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "FALLBACK PAGE TEXT")
    file_bytes = pdf.tobytes()
    pdf.close()

    class FailingPage:
        """模拟 pdfplumber 页面提取失败。"""

        def extract_text(self):
            """抛出模拟提取错误。

            Args:
                无。
            """
            raise ValueError("primary failed")

    class FakePlumberPDF:
        """模拟主解析器返回一页。"""

        pages = [FailingPage()]

        def __enter__(self):
            """进入模拟 PDF 上下文。

            Args:
                无。
            """
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            """退出模拟 PDF 上下文。

            Args:
                exc_type: 异常类型。
                exc_value: 异常对象。
                traceback: 异常栈。
            """
            return False

    monkeypatch.setattr(pdf_module._require_pdfplumber(), "open", lambda _: FakePlumberPDF())
    parser = PDFParser("", "fallback.pdf")
    pages, page_count = parser._extract_page_data(
        file_bytes, "test-id", use_table=False, use_image=False, s3_client=None
    )
    assert page_count == 1
    assert pages[0]["pages_number"] == 1
    assert "FALLBACK PAGE TEXT" in pages[0]["text"]


def test_both_extractors_fail_with_page_number(monkeypatch):
    """双重提取失败不能静默跳过页面。

    Args:
        monkeypatch: pytest 的替换依赖夹具。
    """
    class FailingPage:
        """模拟失败的 pdfplumber 页面。"""

        def extract_text(self):
            """抛出模拟主解析异常。

            Args:
                无。
            """
            raise ValueError("primary failed")

    class FakePlumberPDF:
        """模拟两页 PDF。"""

        pages = [FailingPage(), FailingPage()]

        def __enter__(self):
            """进入模拟 PDF 上下文。

            Args:
                无。
            """
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            """退出模拟 PDF 上下文。

            Args:
                exc_type: 异常类型。
                exc_value: 异常对象。
                traceback: 异常栈。
            """
            return False

    class BrokenFitz:
        """模拟备用解析器无法打开文件。"""

        def open(self, **kwargs):
            """抛出备用解析异常。

            Args:
                kwargs: PyMuPDF 打开参数。
            """
            raise ValueError("fallback failed")

    monkeypatch.setattr(pdf_module._require_pdfplumber(), "open", lambda _: FakePlumberPDF())
    monkeypatch.setattr(pdf_module, "_require_pymupdf", lambda: BrokenFitz())
    parser = PDFParser("", "broken.pdf")
    with pytest.raises(RuntimeError, match="第 1 页文本提取失败"):
        parser._extract_page_data(
            b"bad pdf", "test-id", use_table=False, use_image=False, s3_client=None
        )


def test_blank_page_is_not_an_extraction_failure():
    """真实空白页允许正常解析，不视作提取异常。

    Args:
        无。
    """
    pdf = fitz.open()
    pdf.new_page()
    pdf.new_page().insert_text((72, 72), "CONTENT ON PAGE TWO")
    file_bytes = pdf.tobytes()
    pdf.close()

    parser = PDFParser("", "blank.pdf")
    pages, count = parser._extract_page_data(
        file_bytes, "test-id", use_table=False, use_image=False, s3_client=None
    )
    assert count == 2
    assert [page["pages_number"] for page in pages] == [1, 2]
    assert pages[0]["text"] == ""
