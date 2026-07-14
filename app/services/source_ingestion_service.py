import ipaddress
import socket
import zipfile
from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

import httpx
from pypdf import PdfReader


MAX_SOURCE_BYTES = 5 * 1024 * 1024
MAX_EXTRACTED_CHARS = 50_000
MAX_PDF_PAGES = 50
MAX_URL_REDIRECTS = 3
SUPPORTED_UPLOAD_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


class SourceIngestionError(ValueError):
    def __init__(self, message: str, code: str = "source_invalid") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class IngestedSource:
    title: str
    text: str
    source_type: str
    mime_type: str
    file_name: str | None = None
    source_url: str | None = None

    def metadata(self) -> dict:
        return {
            "source_type": self.source_type,
            "source_title": self.title,
            "mime_type": self.mime_type,
            "file_name": self.file_name,
            "source_url": self.source_url,
            "word_count": len(self.text.split()),
            "content_hash": sha256(self.text.casefold().encode("utf-8")).hexdigest(),
        }


class _ReadableHTMLParser(HTMLParser):
    BLOCK_TAGS = {
        "article", "blockquote", "br", "div", "h1", "h2", "h3", "h4",
        "h5", "h6", "li", "main", "p", "section", "td", "th", "tr",
    }
    SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
        else:
            self.parts.append(data)

    @property
    def title(self) -> str:
        return _single_line(" ".join(self.title_parts))

    @property
    def text(self) -> str:
        return _clean_text("".join(self.parts))


def _single_line(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split()).strip()


def _clean_text(value: str) -> str:
    lines = [_single_line(line) for line in value.splitlines()]
    return "\n\n".join(line for line in lines if line)[:MAX_EXTRACTED_CHARS].strip()


def validate_public_url(value: str) -> str:
    raw = value.strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise SourceIngestionError(
            "Enter a complete public http:// or https:// URL.",
            "source_url_invalid",
        )
    if parsed.username or parsed.password:
        raise SourceIngestionError(
            "URLs containing credentials are not supported.",
            "source_url_invalid",
        )

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise SourceIngestionError(
            "Private or local network URLs cannot be imported.",
            "source_url_private",
        )
    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        addresses = {
            result[4][0]
            for result in socket.getaddrinfo(hostname, port)
        }
    except ValueError as exc:
        raise SourceIngestionError(
            "The source URL contains an invalid port.",
            "source_url_invalid",
        ) from exc
    except socket.gaierror as exc:
        raise SourceIngestionError(
            "The source hostname could not be resolved.",
            "source_url_unreachable",
        ) from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise SourceIngestionError(
            "Private or local network URLs cannot be imported.",
            "source_url_private",
        )

    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, "")
    )


class SourceIngestionService:
    def extract_upload(
        self,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
    ) -> IngestedSource:
        safe_name = Path(filename or "source").name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
            raise SourceIngestionError(
                "Upload a PDF, DOCX, TXT, or Markdown file.",
                "source_type_unsupported",
            )
        self._validate_size(data)

        try:
            if suffix == ".pdf":
                text = self._extract_pdf(data)
                mime_type = "application/pdf"
            elif suffix == ".docx":
                text = self._extract_docx(data)
                mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            else:
                text = self._extract_plain_text(data)
                mime_type = "text/markdown" if suffix == ".md" else "text/plain"
        except SourceIngestionError:
            raise
        except Exception as exc:
            raise SourceIngestionError(
                "Blidx could not read this file. Check that it is not damaged or password-protected.",
                "source_parse_failed",
            ) from exc

        text = _clean_text(text)
        self._validate_extracted_text(text)
        return IngestedSource(
            title=Path(safe_name).stem[:160] or "Imported document",
            text=text,
            source_type="file",
            mime_type=mime_type or content_type or "application/octet-stream",
            file_name=safe_name[:255],
        )

    async def import_url(self, value: str) -> IngestedSource:
        current_url = validate_public_url(value)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(20.0, connect=8.0),
                follow_redirects=False,
                headers={"User-Agent": "BlidxSourceImporter/1.0"},
            ) as client:
                for redirect_count in range(MAX_URL_REDIRECTS + 1):
                    async with client.stream("GET", current_url) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location or redirect_count == MAX_URL_REDIRECTS:
                                raise SourceIngestionError(
                                    "The source redirected too many times.",
                                    "source_redirect_failed",
                                )
                            current_url = validate_public_url(urljoin(current_url, location))
                            continue
                        response.raise_for_status()
                        content_length = int(response.headers.get("content-length") or 0)
                        if content_length > MAX_SOURCE_BYTES:
                            raise SourceIngestionError(
                                "This source is larger than the 5 MB import limit.",
                                "source_too_large",
                            )
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > MAX_SOURCE_BYTES:
                                raise SourceIngestionError(
                                    "This source is larger than the 5 MB import limit.",
                                    "source_too_large",
                                )
                        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    break
                else:  # pragma: no cover - the redirect guard exits first
                    raise SourceIngestionError("The source could not be imported.")
        except SourceIngestionError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceIngestionError(
                "Blidx could not fetch that URL. The page may be private or blocking imports.",
                "source_fetch_failed",
            ) from exc

        raw = bytes(body)
        try:
            if content_type == "application/pdf":
                text = self._extract_pdf(raw)
                title = Path(urlsplit(current_url).path).stem or urlsplit(current_url).hostname or "Web PDF"
            elif content_type.startswith("text/plain"):
                text = self._extract_plain_text(raw)
                title = urlsplit(current_url).hostname or "Web source"
            elif content_type in {"text/html", "application/xhtml+xml", ""}:
                parser = _ReadableHTMLParser()
                parser.feed(raw.decode("utf-8", errors="replace"))
                text = parser.text
                title = parser.title or urlsplit(current_url).hostname or "Web source"
            else:
                raise SourceIngestionError(
                    "This URL does not return a readable webpage, text file, or PDF.",
                    "source_type_unsupported",
                )
        except SourceIngestionError:
            raise
        except Exception as exc:
            raise SourceIngestionError(
                "Blidx could not extract readable text from that URL.",
                "source_parse_failed",
            ) from exc

        text = _clean_text(text)
        self._validate_extracted_text(text)
        return IngestedSource(
            title=_single_line(title)[:160],
            text=text,
            source_type="url",
            mime_type=content_type or "text/html",
            source_url=current_url,
        )

    @staticmethod
    def _validate_size(data: bytes) -> None:
        if not data:
            raise SourceIngestionError("The selected file is empty.", "source_empty")
        if len(data) > MAX_SOURCE_BYTES:
            raise SourceIngestionError(
                "This file is larger than the 5 MB upload limit.",
                "source_too_large",
            )

    @staticmethod
    def _validate_extracted_text(text: str) -> None:
        if len(text) < 20:
            raise SourceIngestionError(
                "Blidx could not find enough readable text in this source.",
                "source_text_missing",
            )

    @staticmethod
    def _extract_plain_text(data: bytes) -> str:
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("cp1252", errors="replace")

    @staticmethod
    def _extract_pdf(data: bytes) -> str:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            try:
                if not reader.decrypt(""):
                    raise SourceIngestionError(
                        "Password-protected PDFs are not supported.",
                        "source_password_protected",
                    )
            except Exception as exc:
                raise SourceIngestionError(
                    "Password-protected PDFs are not supported.",
                    "source_password_protected",
                ) from exc
        pages = [page.extract_text() or "" for page in reader.pages[:MAX_PDF_PAGES]]
        return "\n\n".join(pages)

    @staticmethod
    def _extract_docx(data: bytes) -> str:
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                document = archive.read("word/document.xml")
        except (KeyError, zipfile.BadZipFile) as exc:
            raise SourceIngestionError(
                "This DOCX file is damaged or unsupported.",
                "source_parse_failed",
            ) from exc
        root = ElementTree.fromstring(document)
        paragraphs = []
        for node in root.iter():
            if not node.tag.endswith("}p"):
                continue
            text = "".join(
                child.text or ""
                for child in node.iter()
                if child.tag.endswith("}t")
            )
            if text.strip():
                paragraphs.append(text)
        return "\n\n".join(paragraphs)


source_ingestion_service = SourceIngestionService()
