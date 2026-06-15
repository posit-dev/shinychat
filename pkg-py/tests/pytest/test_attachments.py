import base64

import pytest
from chatlas.types import ContentPDF, ContentText
from shinychat._attachments import (
    DEFAULT_MAX_ATTACHMENT_SIZE,
    SUPPORTED_ATTACHMENT_TYPES,
    Attachment,
    attachment_to_content,
    is_text_type,
    resolve_attachment_attrs,
    resolve_max_attachment_size,
)
from shinychat._utils_types import MISSING


def test_attachment_is_public():
    from shinychat import types

    assert types.Attachment is Attachment
    assert "Attachment" in types.__all__


def test_resolve_attachment_attrs_missing():
    assert resolve_attachment_attrs(MISSING) == (None, None)


def test_resolve_attachment_attrs_bool():
    assert resolve_attachment_attrs(True) == ("true", None)
    assert resolve_attachment_attrs(False) == ("false", None)


def test_resolve_attachment_attrs_list():
    assert resolve_attachment_attrs(["application/pdf"]) == (
        "true",
        "application/pdf",
    )
    assert resolve_attachment_attrs([]) == ("false", None)


def test_resolve_attachment_attrs_text_mime():
    assert resolve_attachment_attrs(["text/markdown"]) == (
        "true",
        "text/markdown",
    )


def test_resolve_attachment_attrs_invalid_mime_raises():
    with pytest.raises(ValueError):
        resolve_attachment_attrs(["application/msword"])


def test_resolve_max_attachment_size_uses_env(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SHINYCHAT_MAX_ATTACHMENT_SIZE", "2000000")
    assert resolve_max_attachment_size() == 2_000_000


def test_resolve_max_attachment_size_default_when_no_env(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("SHINYCHAT_MAX_ATTACHMENT_SIZE", raising=False)
    assert resolve_max_attachment_size() == DEFAULT_MAX_ATTACHMENT_SIZE


def test_resolve_max_attachment_size_invalid_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SHINYCHAT_MAX_ATTACHMENT_SIZE", "30MB")
    with pytest.raises(ValueError, match="not a valid integer"):
        resolve_max_attachment_size()


def test_resolve_max_attachment_size_negative_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SHINYCHAT_MAX_ATTACHMENT_SIZE", "-1")
    with pytest.raises(ValueError, match="non-negative"):
        resolve_max_attachment_size()


def test_supported_types_match_js():
    assert set(SUPPORTED_ATTACHMENT_TYPES) == {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "application/pdf",
        "text/markdown",
        "text/plain",
        "text/csv",
        "application/json",
        "text/x-python",
        "text/javascript",
        "text/typescript",
        "text/x-r",
        "text/yaml",
        "text/x-toml",
        "application/x-ipynb+json",
        "text/x-rst",
        "text/x-tex",
        "text/x-sql",
        "text/x-sh",
        "text/html",
        "text/css",
        "application/xml",
        "text/x-ini",
    }


def test_attachment_to_content_pdf_preserves_filename():
    pdf_bytes = b"%PDF-1.4 hello"
    b64 = base64.b64encode(pdf_bytes).decode()
    att = Attachment(
        mime="application/pdf",
        data_url=f"data:application/pdf;base64,{b64}",
        name="report.pdf",
    )
    content = attachment_to_content(att)
    assert isinstance(content, ContentPDF)
    assert content.filename == "report.pdf"
    assert content.data == pdf_bytes


def test_attachment_to_content_image_uses_content_image_url():
    from chatlas._content import ContentImage

    att = Attachment(
        mime="image/png",
        data_url="data:image/png;base64,AAAA",
        name="pic.png",
    )
    content = attachment_to_content(att)
    assert isinstance(content, ContentImage)


def test_attachment_to_content_unsupported_type_raises():
    att = Attachment(
        mime="application/octet-stream",
        data_url="data:application/octet-stream;base64,AAAA",
        name="blob.bin",
    )
    with pytest.raises(ValueError):
        attachment_to_content(att)


def test_attachment_to_content_text_wraps_in_file_attachment():
    md = "# Title\n\nbody"
    b64 = base64.b64encode(md.encode()).decode()
    att = Attachment(
        mime="text/markdown",
        data_url=f"data:text/markdown;base64,{b64}",
        name="notes.md",
    )
    content = attachment_to_content(att)
    assert isinstance(content, ContentText)
    assert content.text == (
        '<file-attachment name="notes.md" type="text/markdown">\n'
        f"{md}\n"
        "</file-attachment>"
    )


def test_attachment_to_content_text_escapes_attributes():
    b64 = base64.b64encode(b"x").decode()
    att = Attachment(
        mime="text/plain",
        data_url=f"data:text/plain;base64,{b64}",
        name='a"&<b.txt',
    )
    content = attachment_to_content(att)
    assert isinstance(content, ContentText)
    assert 'name="a&quot;&amp;&lt;b.txt"' in content.text


def test_attachment_to_content_text_non_utf8_does_not_raise():
    b64 = base64.b64encode(b"\xff\xfe bad bytes").decode()
    att = Attachment(
        mime="text/plain",
        data_url=f"data:text/plain;base64,{b64}",
        name="weird.txt",
    )
    content = attachment_to_content(att)
    assert isinstance(content, ContentText)
    assert "�" in content.text


def test_attachment_to_content_pdf_malformed_base64_raises_clean_error():
    att = Attachment(
        mime="application/pdf",
        data_url="data:application/pdf;base64,%%%not-base64%%%",
        name="broken.pdf",
    )
    with pytest.raises(ValueError, match="Malformed base64 payload in data URL"):
        attachment_to_content(att)


def test_is_text_type():
    assert is_text_type("text/markdown") is True
    assert is_text_type("application/x-ipynb+json") is True
    assert is_text_type("image/png") is False
    assert is_text_type("application/pdf") is False


def test_attachment_from_url_data_url():
    data = base64.b64encode(b"hello").decode()
    a = Attachment.from_url(f"data:text/plain;base64,{data}", name="hi.txt")
    assert a.mime == "text/plain"
    assert a.name == "hi.txt"
    assert a.size == 5
    assert a.data_url.startswith("data:text/plain;base64,")


def test_attachment_from_data():
    a = Attachment.from_data(b"\x89PNG\r\n", mime="image/png", name="x.png")
    assert a.mime == "image/png"
    assert a.size == 6
    assert (
        a.data_url
        == "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n").decode()
    )


def test_attachment_from_url_empty_mime_fallback():
    data = base64.b64encode(b"hello").decode()
    a = Attachment.from_url(f"data:;base64,{data}")
    assert a.mime == "application/octet-stream"
    assert a.size == 5


def test_attachment_from_path(tmp_path):
    p = tmp_path / "note.md"
    p.write_text("# hi")
    a = Attachment.from_path(str(p))
    assert a.name == "note.md"
    assert a.mime == "text/markdown"
    assert a.size == 4
