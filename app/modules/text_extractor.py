"""Extract text and images from PDF/DOCX files."""

import io
import re
from pathlib import Path
from typing import Optional

from PIL import Image


def extract_text_from_pdf(pdf_path: str) -> dict:
    """Extract text, metadata, and images from a PDF file."""
    import pdfplumber

    result = {
        "full_text": "",
        "pages": [],
        "images": [],
        "metadata": {},
        "references_section": "",
        "figures_text": [],
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            result["metadata"] = pdf.metadata or {}

            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                result["pages"].append({"page_num": i + 1, "text": text})
                result["full_text"] += text + "\n"

                # Extract images from page
                for j, img in enumerate(page.images):
                    try:
                        img_bbox = (
                            float(img.get("x0", 0)),
                            float(img.get("top", 0)),
                            float(img.get("x1", 100)),
                            float(img.get("bottom", 100)),
                        )
                        cropped = page.crop(img_bbox)
                        pil_img = cropped.to_image(resolution=150)
                        img_bytes = io.BytesIO()
                        pil_img.save(img_bytes, format="PNG")
                        result["images"].append({
                            "page": i + 1,
                            "index": j,
                            "data": img_bytes.getvalue(),
                            "bbox": img_bbox,
                        })
                    except Exception:
                        pass

    except Exception as e:
        result["error"] = str(e)

    # Try to extract references section
    ref_pattern = re.compile(
        r'(?:references|bibliography|works cited)\s*\n(.*)',
        re.IGNORECASE | re.DOTALL
    )
    match = ref_pattern.search(result["full_text"])
    if match:
        result["references_section"] = match.group(1)

    # Extract figure captions
    fig_pattern = re.compile(
        r'(?:Fig(?:ure)?\.?\s*\d+[.:]\s*)(.*?)(?:\n\n|\n[A-Z])',
        re.IGNORECASE | re.DOTALL
    )
    result["figures_text"] = fig_pattern.findall(result["full_text"])

    return result


def extract_text_from_docx(docx_path: str) -> dict:
    """Extract text and images from a DOCX file."""
    from docx import Document

    result = {
        "full_text": "",
        "pages": [],
        "images": [],
        "metadata": {},
        "references_section": "",
    }

    try:
        doc = Document(docx_path)

        paragraphs_text = []
        for para in doc.paragraphs:
            paragraphs_text.append(para.text)

        result["full_text"] = "\n".join(paragraphs_text)
        result["pages"] = [{"page_num": 1, "text": result["full_text"]}]

        # Extract images from docx
        for i, rel in enumerate(doc.part.rels.values()):
            if "image" in rel.reltype:
                try:
                    img_data = rel.target_part.blob
                    result["images"].append({
                        "page": 1,
                        "index": i,
                        "data": img_data,
                    })
                except Exception:
                    pass

        # Extract references
        ref_pattern = re.compile(
            r'(?:references|bibliography|works cited)\s*\n(.*)',
            re.IGNORECASE | re.DOTALL
        )
        match = ref_pattern.search(result["full_text"])
        if match:
            result["references_section"] = match.group(1)

    except Exception as e:
        result["error"] = str(e)

    return result


def extract_from_file(file_path: str) -> dict:
    """Auto-detect file type and extract content."""
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return extract_text_from_docx(file_path)
    elif ext == ".txt":
        text = path.read_text(encoding="utf-8", errors="ignore")
        return {"full_text": text, "pages": [{"page_num": 1, "text": text}], "images": [], "metadata": {}}
    else:
        return {"error": f"Unsupported file type: {ext}", "full_text": "", "pages": [], "images": [], "metadata": {}}
