from __future__ import annotations

import importlib.util
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterable

from langchain_core.documents import Document
from loguru import logger

from deepclaw.common.text_splitter import (
    LocalDirectoryPDFReader,
    PDFParser,
)


DOCLING_SUPPORTED_SUFFIXES = frozenset(
    {
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
)


def is_docling_available() -> bool:
    """判断当前环境是否已安装 Docling。

    Args:
        无。

    Returns:
        Docling 已安装时返回 True，否则返回 False。
    """
    return importlib.util.find_spec("docling") is not None


def create_document_parser(
    *,
    bucket_name: str,
    file_path: str,
    file_id: str | None = None,
    original_file_name: str | None = None,
    fallback_parser_cls: type[Any] = PDFParser,
    reader: Any | None = None,
) -> Any:
    """按文件格式和依赖情况创建统一文档解析器。

    Args:
        bucket_name: 文件所属存储桶名称。
        file_path: 文件在存储桶中的相对路径。
        file_id: 文档 ID，未传时由解析器生成。
        original_file_name: 原始文件名，用于判断文件格式。
        fallback_parser_cls: Docling 不可用或不支持格式时使用的解析器类。
        reader: 可选的文件读取器，用于对象存储或测试替身。

    Returns:
        可调用 get_chunk() 的文档解析器。
    """
    suffix = Path(original_file_name or file_path).suffix.lower()
    if suffix in DOCLING_SUPPORTED_SUFFIXES and is_docling_available():
        logger.info(f"使用 Docling 解析文件：{original_file_name or file_path}")
        return DoclingDocumentParser(
            bucket_name=bucket_name,
            file_path=file_path,
            file_id=file_id,
            reader=reader,
        )
    return fallback_parser_cls(
        bucket_name=bucket_name,
        file_path=file_path,
        file_id=file_id,
        reader=reader,
    )


class DoclingDocumentParser:
    """使用 Docling 解析文档并转换为知识库切片。"""

    def __init__(
        self,
        bucket_name: str,
        file_path: str,
        file_id: str | None = None,
        reader: Any | None = None,
        converter: Any | None = None,
        chunker: Any | None = None,
    ):
        """初始化 Docling 文档解析器。

        Args:
            bucket_name: 文件所属存储桶名称。
            file_path: 文件在存储桶中的相对路径。
            file_id: 文档 ID，未传时自动生成。
            reader: 可选的文档读取器。
            converter: 可选的 Docling 转换器。
            chunker: 可选的 Docling 层级切片器。
        """
        self.bucket_name = bucket_name
        self.file_path = file_path
        self.file_id = file_id
        self.reader = reader or LocalDirectoryPDFReader(PDFParser.DEFAULT_LOCAL_ROOT)
        self.converter = converter
        self.chunker = chunker

    def _build_file_id(self) -> str:
        """构建当前文档的 file_id。

        Args:
            无。

        Returns:
            文档 ID。
        """
        return self.file_id or uuid.uuid4().hex

    def _require_converter(self) -> Any:
        """按需创建 Docling 文档转换器。

        Args:
            无。

        Returns:
            Docling DocumentConverter 实例。
        """
        if self.converter is not None:
            return self.converter

        try:
            from docling.document_converter import DocumentConverter
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Docling 未安装，请执行 `uv sync --extra docling`。"
            ) from exc

        self.converter = DocumentConverter()
        return self.converter

    def _require_chunker(self) -> Any:
        """按需创建 Docling 层级切片器。

        Args:
            无。

        Returns:
            HierarchicalChunker 实例。
        """
        if self.chunker is not None:
            return self.chunker

        try:
            from docling_core.transforms.chunker.hierarchical_chunker import (
                HierarchicalChunker,
            )
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Docling 切片依赖未安装，请执行 `uv sync --extra docling`。"
            ) from exc

        self.chunker = HierarchicalChunker()
        return self.chunker

    def get_chunk(self) -> list[Document]:
        """解析文档并返回与现有知识库兼容的切片。

        Args:
            无。

        Returns:
            LangChain Document 切片列表。
        """
        if not self.file_path:
            return []

        file_id = self._build_file_id()
        loaded_file = self.reader.load(
            bucket_name=self.bucket_name,
            file_path=self.file_path,
        )
        suffix = Path(loaded_file.file_name).suffix.lower()
        if suffix not in DOCLING_SUPPORTED_SUFFIXES:
            raise RuntimeError(f"Docling 暂不支持该文件格式：{suffix or '<unknown>'}")

        with tempfile.TemporaryDirectory(prefix="docling-parse-") as temp_dir:
            source_path = Path(temp_dir) / f"source{suffix}"
            source_path.write_bytes(loaded_file.file_bytes)
            result = self._require_converter().convert(source_path)

        document = getattr(result, "document", None)
        if document is None:
            raise RuntimeError(f"Docling 未返回文档对象：{loaded_file.file_name}")

        docs = self._chunk_with_docling(
            document=document,
            file_id=file_id,
            file_name=loaded_file.file_name,
            source_format=suffix,
        )
        if not docs:
            docs = self._chunk_markdown(
                document=document,
                file_id=file_id,
                file_name=loaded_file.file_name,
                source_format=suffix,
            )
        if not docs:
            raise RuntimeError(f"Docling 未提取到可索引内容：{loaded_file.file_name}")

        return self._finalize_docs(
            docs=docs,
            file_id=file_id,
            file_name=loaded_file.file_name,
        )

    def _chunk_with_docling(
        self,
        *,
        document: Any,
        file_id: str,
        file_name: str,
        source_format: str,
    ) -> list[Document]:
        """使用 Docling 层级切片器生成文档切片。

        Args:
            document: DoclingDocument 对象。
            file_id: 文档 ID。
            file_name: 原始文件名。
            source_format: 文件后缀。

        Returns:
            LangChain Document 列表。
        """
        try:
            chunker = self._require_chunker()
            raw_chunks = list(chunker.chunk(document))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Docling 层级切片失败，将回退到 Markdown 标题切片：{exc}")
            return []

        docs: list[Document] = []
        for raw_chunk in raw_chunks:
            text = str(getattr(raw_chunk, "text", "") or "").strip()
            if not text:
                continue
            meta_dict = self._object_to_dict(getattr(raw_chunk, "meta", None))
            headings = self._normalize_headings(meta_dict.get("headings"))
            page_no = self._find_page_no(meta_dict)
            docs.append(
                Document(
                    page_content=text,
                    metadata=self._build_metadata(
                        file_id=file_id,
                        file_name=file_name,
                        source_format=source_format,
                        headings=headings,
                        page_no=page_no,
                        text=text,
                    ),
                )
            )
        return docs

    def _chunk_markdown(
        self,
        *,
        document: Any,
        file_id: str,
        file_name: str,
        source_format: str,
    ) -> list[Document]:
        """按 Docling 导出的 Markdown 标题层级生成切片。

        Args:
            document: DoclingDocument 对象。
            file_id: 文档 ID。
            file_name: 原始文件名。
            source_format: 文件后缀。

        Returns:
            LangChain Document 列表。
        """
        markdown = str(document.export_to_markdown() or "").strip()
        if not markdown:
            return []
        return self._split_markdown_by_headings(
            markdown=markdown,
            file_id=file_id,
            file_name=file_name,
            source_format=source_format,
        )

    def _split_markdown_by_headings(
        self,
        *,
        markdown: str,
        file_id: str,
        file_name: str,
        source_format: str,
    ) -> list[Document]:
        """按 Markdown 标题层级拆分内容。

        Args:
            markdown: Docling 导出的 Markdown 文本。
            file_id: 文档 ID。
            file_name: 原始文件名。
            source_format: 文件后缀。

        Returns:
            LangChain Document 列表。
        """
        matches = list(
            re.finditer(r"^(#{1,6})\s+(.+?)\s*$", markdown, flags=re.MULTILINE)
        )
        if not matches:
            return [
                Document(
                    page_content=markdown,
                    metadata=self._build_metadata(
                        file_id=file_id,
                        file_name=file_name,
                        source_format=source_format,
                        headings=[],
                        page_no=None,
                        text=markdown,
                    ),
                )
            ]

        docs: list[Document] = []
        heading_stack: dict[int, str] = {}
        if matches[0].start() > 0:
            preface = markdown[: matches[0].start()].strip()
            if preface:
                docs.append(
                    Document(
                        page_content=preface,
                        metadata=self._build_metadata(
                            file_id=file_id,
                            file_name=file_name,
                            source_format=source_format,
                            headings=[],
                            page_no=None,
                            text=preface,
                        ),
                    )
                )

        for index, match in enumerate(matches):
            level = len(match.group(1))
            title = match.group(2).strip()
            heading_stack = {
                key: value for key, value in heading_stack.items() if key < level
            }
            heading_stack[level] = title
            end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
            section = markdown[match.start() : end].strip()
            if not section:
                continue
            docs.append(
                Document(
                    page_content=section,
                    metadata=self._build_metadata(
                        file_id=file_id,
                        file_name=file_name,
                        source_format=source_format,
                        headings=list(heading_stack.values()),
                        page_no=None,
                        text=section,
                    ),
                )
            )
        return docs

    def _build_metadata(
        self,
        *,
        file_id: str,
        file_name: str,
        source_format: str,
        headings: Iterable[str],
        page_no: int | None,
        text: str,
    ) -> dict[str, Any]:
        """构建与现有知识库索引兼容的 metadata。

        Args:
            file_id: 文档 ID。
            file_name: 原始文件名。
            source_format: 文件后缀。
            headings: 当前切片所属标题路径。
            page_no: 当前切片所在页码。
            text: 当前切片文本。

        Returns:
            metadata 字典。
        """
        heading_list = list(headings)
        return {
            "file_name": file_name,
            "file_id": file_id,
            "source_format": source_format,
            "parser_backend": "docling",
            "headings": heading_list,
            "title": heading_list[0] if heading_list else Path(file_name).stem,
            "page_no": page_no,
            "pages_number": page_no or 1,
            "ori_text": text,
            "content_table": [],
            "content_image": self._extract_image_refs(text),
            "converted_pdf_temp_path": None,
        }

    @staticmethod
    def _object_to_dict(value: Any) -> dict[str, Any]:
        """将 Docling 元数据对象转换为普通字典。

        Args:
            value: 待转换对象。

        Returns:
            普通字典，无法转换时返回空字典。
        """
        if value is None:
            return {}
        if isinstance(value, dict):
            return value

        for method_name in ("model_dump", "dict", "export_json_dict", "to_dict"):
            method = getattr(value, method_name, None)
            if not callable(method):
                continue
            try:
                converted = method()
            except Exception:  # noqa: BLE001
                continue
            if isinstance(converted, dict):
                return converted
        return {}

    @classmethod
    def _find_page_no(cls, value: Any) -> int | None:
        """递归查找元数据中的页码。

        Args:
            value: 待查找的元数据对象。

        Returns:
            找到的页码，未找到时返回 None。
        """
        if isinstance(value, dict):
            for key in ("page_no", "page_number", "page"):
                page_no = value.get(key)
                if isinstance(page_no, int):
                    return page_no
            for child in value.values():
                page_no = cls._find_page_no(child)
                if page_no is not None:
                    return page_no
            return None

        if isinstance(value, list):
            for child in value:
                page_no = cls._find_page_no(child)
                if page_no is not None:
                    return page_no
            return None

        for attribute in ("page_no", "page_number"):
            page_no = getattr(value, attribute, None)
            if isinstance(page_no, int):
                return page_no
        return None

    @staticmethod
    def _normalize_headings(value: Any) -> list[str]:
        """规范化标题路径。

        Args:
            value: 原始标题值。

        Returns:
            标题字符串列表。
        """
        if value is None:
            return []
        if isinstance(value, str):
            normalized = value.strip()
            return [normalized] if normalized else []
        if isinstance(value, Iterable):
            return [
                str(item).strip()
                for item in value
                if str(item).strip()
            ]
        return []

    @staticmethod
    def _extract_image_refs(text: str) -> list[str]:
        """提取 Markdown 文本中的图片引用。

        Args:
            text: Markdown 文本。

        Returns:
            图片引用列表。
        """
        return re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)

    def _finalize_docs(
        self,
        *,
        docs: list[Document],
        file_id: str,
        file_name: str,
    ) -> list[Document]:
        """补齐现有知识库流程依赖的文档元数据。

        Args:
            docs: 待补齐的文档切片。
            file_id: 文档 ID。
            file_name: 原始文件名。

        Returns:
            补齐后的文档切片。
        """
        for segment_id, doc in enumerate(docs, start=1):
            doc.metadata.update(
                {
                    "file_name": file_name,
                    "file_id": file_id,
                    "segment_id": segment_id,
                    "state": True,
                    "bucket_name": self.bucket_name,
                    "file_path": self.file_path,
                }
            )
        return docs
