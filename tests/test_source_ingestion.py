from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.main import app
from app.services.source_ingestion_service import (
    IngestedSource,
    SourceIngestionError,
    source_ingestion_service,
    validate_public_url,
)


client = TestClient(app)


def test_text_upload_is_extracted_saved_and_deduplicated():
    client.post("/api/reset")
    source_text = (
        "A composer told me AI is most useful when it handles variations while "
        "the human keeps responsibility for taste, tension, and the final musical choice."
    )

    response = client.post(
        "/api/content-bank/upload",
        data={"category": "insights"},
        files={"file": ("composer-notes.txt", source_text, "text/plain")},
    )

    assert response.status_code == 200
    entry = response.json()
    assert entry["source_type"] == "file"
    assert entry["source_title"] == "composer-notes"
    assert entry["file_name"] == "composer-notes.txt"
    assert entry["raw_text"] == source_text
    assert entry["word_count"] > 15
    assert len(entry["content_hash"]) == 64

    duplicate = client.post(
        "/api/content-bank/upload",
        data={"category": "insights"},
        files={"file": ("renamed.txt", source_text, "text/plain")},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "source_duplicate"
    assert duplicate.json()["detail"]["entry_id"] == entry["id"]

    client.post("/api/reset")


def test_docx_text_is_extracted_without_storing_the_binary():
    document_xml = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>Human composers should remain responsible for musical judgment.</w:t></w:r></w:p>
        <w:p><w:r><w:t>AI can make exploration faster without choosing what the work means.</w:t></w:r></w:p>
      </w:body>
    </w:document>"""
    payload = BytesIO()
    with ZipFile(payload, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)

    source = source_ingestion_service.extract_upload(
        filename="composer-brief.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        data=payload.getvalue(),
    )

    assert source.source_type == "file"
    assert source.title == "composer-brief"
    assert "musical judgment" in source.text
    assert "exploration faster" in source.text


def test_pdf_text_is_extracted_from_a_real_pdf_stream():
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    content = DecodedStreamObject()
    content.set_data(
        b"BT /F1 12 Tf 20 200 Td "
        b"(AI helps composers explore variations while humans keep judgment.) Tj ET"
    )
    page[NameObject("/Contents")] = writer._add_object(content)
    payload = BytesIO()
    writer.write(payload)

    source = source_ingestion_service.extract_upload(
        filename="composer.pdf",
        content_type="application/pdf",
        data=payload.getvalue(),
    )

    assert source.mime_type == "application/pdf"
    assert source.title == "composer"
    assert "humans keep judgment" in source.text


def test_private_network_urls_are_rejected():
    with pytest.raises(SourceIngestionError) as error:
        validate_public_url("http://127.0.0.1:8000/private")

    assert error.value.code == "source_url_private"


def test_public_url_import_saves_extracted_provenance(monkeypatch):
    client.post("/api/reset")

    async def fake_import_url(url: str) -> IngestedSource:
        assert url == "https://example.com/founder-note"
        return IngestedSource(
            title="A founder note on human judgment",
            text=(
                "The useful role of AI in composition is expanding the search space. "
                "The composer still decides which musical idea deserves to survive."
            ),
            source_type="url",
            mime_type="text/html",
            source_url=url,
        )

    monkeypatch.setattr(source_ingestion_service, "import_url", fake_import_url)
    response = client.post(
        "/api/content-bank/import-url",
        json={"url": "https://example.com/founder-note", "category": "reading"},
    )

    assert response.status_code == 200
    entry = response.json()
    assert entry["source_type"] == "url"
    assert entry["source_title"] == "A founder note on human judgment"
    assert entry["source_url"] == "https://example.com/founder-note"

    client.post("/api/reset")


def test_selected_source_ids_ground_and_attribute_the_draft():
    client.post("/api/reset")
    selected = client.post(
        "/api/content-bank/upload",
        data={"category": "insights"},
        files={
            "file": (
                "human-composer.txt",
                (
                    "AI can help a human composer explore more variations, but the "
                    "composer remains responsible for taste and the final musical decision."
                ),
                "text/plain",
            )
        },
    ).json()
    client.post(
        "/api/content-bank",
        json={
            "category": "milestones",
            "raw_text": "I rebuilt a product website and learned about deployment workflows.",
        },
    )

    response = client.post(
        "/api/chat/message",
        json={
            "message": "Draft a LinkedIn post grounded in my selected Content Bank source.",
            "source_ids": [selected["id"]],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "draft_created" in payload["actions"]
    assert payload["post"]["source_ids"] == [selected["id"]]
    content_sources = [
        source
        for source in payload["post"]["sources"]
        if source.get("memory_id")
    ]
    assert content_sources == [
        {
            "type": "content_bank",
            "title": "human-composer",
            "memory_id": selected["id"],
            "source_type": "file",
            "url": None,
        }
    ]
    assert "website" not in payload["post"]["topic"].lower()

    client.post("/api/reset")


def test_chat_rejects_more_than_five_selected_sources():
    response = client.post(
        "/api/chat/message",
        json={"message": "Give me angles", "source_ids": [str(index) for index in range(6)]},
    )

    assert response.status_code == 422
