from pathlib import Path

from deepclaw.common.docling_parser import (
    DOCLING_SUPPORTED_SUFFIXES,
    DoclingDocumentParser,
    create_document_parser,
)
from deepclaw.common.text_splitter import LoadedPDFFile, PDFParser


class FakeReader:
    """返回固定文件字节的测试读取器。"""

    def __init__(self, file_name: str, file_bytes: bytes):
        """初始化测试读取器。

        Args:
            file_name: 文件名。
            file_bytes: 文件字节。
        """
        self.file_name = file_name
        self.file_bytes = file_bytes

    def load(self, *, bucket_name: str, file_path: str) -> LoadedPDFFile:
        """返回固定文件内容。

        Args:
            bucket_name: 存储桶名称。
            file_path: 文件路径。

        Returns:
            固定文件对象。
        """
        return LoadedPDFFile(file_bytes=self.file_bytes, file_name=self.file_name)


class FakeDocument:
    """提供 Docling 文档导出能力的测试替身。"""

    def __init__(self, markdown: str = ""):
        """初始化测试文档。

        Args:
            markdown: Markdown 内容。
        """
        self.markdown = markdown

    def export_to_markdown(self) -> str:
        """导出 Markdown 内容。

        Args:
            无。

        Returns:
            Markdown 文本。
        """
        return self.markdown


class FakeConversionResult:
    """Docling 转换结果测试替身。"""

    def __init__(self, document: FakeDocument):
        """初始化转换结果。

        Args:
            document: 文档对象。
        """
        self.document = document


class FakeConverter:
    """记录输入并返回固定文档的转换器替身。"""

    def __init__(self, document: FakeDocument):
        """初始化转换器。

        Args:
            document: 文档对象。
        """
        self.document = document
        self.source_path: Path | None = None

    def convert(self, source_path: Path) -> FakeConversionResult:
        """返回固定转换结果。

        Args:
            source_path: 输入文件路径。

        Returns:
            固定转换结果。
        """
        self.source_path = source_path
        return FakeConversionResult(self.document)


class FakeChunk:
    """提供标题和页码信息的切片替身。"""

    def __init__(self, text: str, headings: list[str], page_no: int):
        """初始化切片替身。

        Args:
            text: 切片文本。
            headings: 标题路径。
            page_no: 页码。
        """
        self.text = text
        self.meta = {
            "headings": headings,
            "doc_items": [{"prov": [{"page_no": page_no}]}],
        }


class FakeChunker:
    """返回固定切片的 Docling 切片器替身。"""

    def __init__(self, chunks: list[FakeChunk]):
        """初始化切片器替身。

        Args:
            chunks: 固定切片列表。
        """
        self.chunks = chunks

    def chunk(self, document: FakeDocument) -> list[FakeChunk]:
        """返回固定切片。

        Args:
            document: 文档对象。

        Returns:
            固定切片列表。
        """
        return self.chunks


class FailingChunker:
    """模拟 Docling 层级切片失败。"""

    def chunk(self, document: FakeDocument) -> list[FakeChunk]:
        """抛出切片异常。

        Args:
            document: 文档对象。

        Raises:
            RuntimeError: 始终抛出。
        """
        raise RuntimeError("chunker failed")


def test_docling_supported_suffixes_cover_requested_formats():
    """验证首批格式均进入 Docling 解析范围。

    Args:
        无。
    """
    expected = {
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".html",
        ".htm",
        ".md",
        ".markdown",
        ".txt",
    }
    assert expected.issubset(DOCLING_SUPPORTED_SUFFIXES)


def test_docling_parser_preserves_headings_and_page_number():
    """验证 Docling 切片保留标题路径和页码。

    Args:
        无。
    """
    parser = DoclingDocumentParser(
        bucket_name="knowledge_bases/guest/kb_1",
        file_path="doc_1_source.docx",
        file_id="doc_1",
        reader=FakeReader("source.docx", b"fake-docx"),
        converter=FakeConverter(FakeDocument()),
        chunker=FakeChunker(
            [FakeChunk("正文内容", ["第一章", "第一节"], 3)]
        ),
    )

    docs = parser.get_chunk()

    assert len(docs) == 1
    assert docs[0].page_content == "正文内容"
    assert docs[0].metadata["headings"] == ["第一章", "第一节"]
    assert docs[0].metadata["page_no"] == 3
    assert docs[0].metadata["segment_id"] == 1
    assert docs[0].metadata["parser_backend"] == "docling"


def test_docling_parser_falls_back_to_markdown_headings():
    """验证层级切片失败时按 Markdown 标题回退。

    Args:
        无。
    """
    markdown = "# 第一章\n\n正文一\n\n## 第一节\n\n正文二"
    parser = DoclingDocumentParser(
        bucket_name="knowledge_bases/guest/kb_1",
        file_path="doc_1_source.docx",
        file_id="doc_1",
        reader=FakeReader("source.docx", b"fake-docx"),
        converter=FakeConverter(FakeDocument(markdown=markdown)),
        chunker=FailingChunker(),
    )

    docs = parser.get_chunk()

    assert len(docs) == 2
    assert docs[0].metadata["headings"] == ["第一章"]
    assert docs[1].metadata["headings"] == ["第一章", "第一节"]
    assert docs[1].metadata["segment_id"] == 2


def test_create_document_parser_uses_docling_when_available(monkeypatch):
    """验证安装 Docling 后优先创建 Docling 解析器。

    Args:
        monkeypatch: pytest monkeypatch fixture。
    """
    monkeypatch.setattr(
        "deepclaw.common.docling_parser.is_docling_available",
        lambda: True,
    )

    parser = create_document_parser(
        bucket_name="knowledge_bases/guest/kb_1",
        file_path="doc_1_source.docx",
        original_file_name="source.docx",
        fallback_parser_cls=PDFParser,
    )

    assert isinstance(parser, DoclingDocumentParser)
