"""Fetch academic papers from DOI, arXiv, or URL."""

import os
import re
import tempfile
from pathlib import Path

import httpx

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


async def fetch_from_doi(doi: str) -> dict:
    """Fetch paper metadata and PDF from DOI via CrossRef and Unpaywall."""
    metadata = {}
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        # Get metadata from CrossRef
        cr_url = f"https://api.crossref.org/works/{doi}"
        try:
            resp = await client.get(cr_url)
            if resp.status_code == 200:
                data = resp.json()["message"]
                metadata["title"] = data.get("title", [""])[0]
                metadata["authors"] = [
                    f"{a.get('given', '')} {a.get('family', '')}".strip()
                    for a in data.get("author", [])
                ]
                metadata["journal"] = data.get("container-title", [""])[0]
                metadata["doi"] = doi
                metadata["references"] = data.get("reference", [])
                metadata["published"] = data.get("published-print", data.get("published-online", {}))
                metadata["type"] = data.get("type", "")
                metadata["abstract"] = data.get("abstract", "")
        except Exception:
            pass

        # Try to get open-access PDF via Unpaywall
        pdf_path = None
        try:
            oa_url = f"https://api.unpaywall.org/v2/{doi}?email=checker@academic-integrity.org"
            resp = await client.get(oa_url)
            if resp.status_code == 200:
                oa_data = resp.json()
                best_loc = oa_data.get("best_oa_location")
                if best_loc and best_loc.get("url_for_pdf"):
                    pdf_resp = await client.get(best_loc["url_for_pdf"], timeout=60)
                    if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1000:
                        pdf_path = UPLOAD_DIR / f"doi_{doi.replace('/', '_')}.pdf"
                        pdf_path.write_bytes(pdf_resp.content)
        except Exception:
            pass

    return {"metadata": metadata, "pdf_path": str(pdf_path) if pdf_path else None}


async def fetch_from_arxiv(arxiv_id: str) -> dict:
    """Fetch paper from arXiv."""
    clean_id = arxiv_id.replace("arXiv:", "").strip()
    metadata = {}
    pdf_path = None

    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        # Get metadata from arXiv API
        api_url = f"http://export.arxiv.org/api/query?id_list={clean_id}"
        try:
            resp = await client.get(api_url)
            if resp.status_code == 200:
                from xml.etree import ElementTree as ET
                root = ET.fromstring(resp.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                entry = root.find("atom:entry", ns)
                if entry is not None:
                    title_el = entry.find("atom:title", ns)
                    metadata["title"] = title_el.text.strip() if title_el is not None else ""
                    metadata["authors"] = [
                        a.find("atom:name", ns).text
                        for a in entry.findall("atom:author", ns)
                        if a.find("atom:name", ns) is not None
                    ]
                    summary_el = entry.find("atom:summary", ns)
                    metadata["abstract"] = summary_el.text.strip() if summary_el is not None else ""
                    metadata["arxiv_id"] = clean_id
        except Exception:
            pass

        # Download PDF
        try:
            pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"
            pdf_resp = await client.get(pdf_url, timeout=60)
            if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1000:
                pdf_path = UPLOAD_DIR / f"arxiv_{clean_id.replace('/', '_')}.pdf"
                pdf_path.write_bytes(pdf_resp.content)
        except Exception:
            pass

    return {"metadata": metadata, "pdf_path": str(pdf_path) if pdf_path else None}


async def fetch_from_url(url: str) -> dict:
    """Download a paper from a direct URL."""
    metadata = {"url": url}
    pdf_path = None

    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        try:
            resp = await client.get(url, timeout=60)
            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "")
                if "pdf" in content_type or url.lower().endswith(".pdf"):
                    fname = url.split("/")[-1][:50] or "downloaded.pdf"
                    if not fname.endswith(".pdf"):
                        fname += ".pdf"
                    pdf_path = UPLOAD_DIR / fname
                    pdf_path.write_bytes(resp.content)
        except Exception:
            pass

    return {"metadata": metadata, "pdf_path": str(pdf_path) if pdf_path else None}
