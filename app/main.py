"""Academic Integrity Checker - Main FastAPI Application."""

import os
import uuid
import shutil
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.models import AnalysisReport
from app.modules.text_extractor import extract_from_file
from app.modules.plagiarism_detector import analyze_plagiarism
from app.modules.citation_checker import analyze_citations
from app.modules.image_forensics import analyze_images
from app.modules.stats_checker import analyze_statistics
from app.modules.metadata_checker import analyze_metadata
from app.modules.paper_fetcher import fetch_from_doi, fetch_from_arxiv, fetch_from_url

UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="学术诚信检查器 / Academic Integrity Checker",
    description="开源学术论文不端行为检测系统",
    version="1.0.0",
)

# Static files and templates
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render the main page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/analyze")
async def analyze_paper(
    request: Request,
    file: UploadFile = File(None),
    doi: str = Form(None),
    url: str = Form(None),
    arxiv_id: str = Form(None),
):
    """Analyze a paper for academic integrity issues.

    Accepts either:
    - A file upload (PDF, DOCX, TXT)
    - A DOI identifier
    - An arXiv ID
    - A direct URL to a paper
    """
    pdf_path = None
    paper_source = ""
    paper_metadata = {}

    # 1. Get the paper
    if file and file.filename:
        # File upload
        ext = Path(file.filename).suffix.lower()
        if ext not in (".pdf", ".docx", ".doc", ".txt"):
            raise HTTPException(400, f"不支持的文件格式: {ext}。支持 PDF, DOCX, TXT")

        file_id = str(uuid.uuid4())[:8]
        pdf_path = str(UPLOAD_DIR / f"{file_id}_{file.filename}")
        with open(pdf_path, "wb") as f:
            content = await file.read()
            f.write(content)
        paper_source = file.filename

    elif doi:
        paper_source = f"DOI: {doi}"
        result = await fetch_from_doi(doi.strip())
        paper_metadata = result.get("metadata", {})
        pdf_path = result.get("pdf_path")
        if not pdf_path:
            # Return metadata-only analysis
            return JSONResponse({
                "status": "partial",
                "message": f"已获取 DOI 元数据，但无法下载开放获取PDF。仅进行元数据分析。",
                "metadata": paper_metadata,
                "report": None,
            })

    elif arxiv_id:
        paper_source = f"arXiv: {arxiv_id}"
        result = await fetch_from_arxiv(arxiv_id.strip())
        paper_metadata = result.get("metadata", {})
        pdf_path = result.get("pdf_path")
        if not pdf_path:
            raise HTTPException(400, f"无法从 arXiv 下载论文: {arxiv_id}")

    elif url:
        paper_source = f"URL: {url}"
        result = await fetch_from_url(url.strip())
        paper_metadata = result.get("metadata", {})
        pdf_path = result.get("pdf_path")
        if not pdf_path:
            raise HTTPException(400, f"无法从 URL 下载论文")

    else:
        raise HTTPException(400, "请上传文件或提供 DOI / arXiv ID / URL")

    # 2. Extract content
    try:
        extracted = extract_from_file(pdf_path)
    except Exception as e:
        raise HTTPException(500, f"文件解析失败: {str(e)}")

    if extracted.get("error"):
        raise HTTPException(500, f"文件解析错误: {extracted['error']}")

    # 3. Run all analysis modules
    report = AnalysisReport(
        paper_title=paper_metadata.get("title") or extracted.get("metadata", {}).get("Title"),
        paper_source=paper_source,
    )

    # Run modules (could be parallelized with asyncio.gather for independent ones)
    plagiarism_result = analyze_plagiarism(extracted)
    report.module_results.append(plagiarism_result)

    citation_result = await analyze_citations(extracted, paper_metadata)
    report.module_results.append(citation_result)

    image_result = analyze_images(extracted)
    report.module_results.append(image_result)

    stats_result = analyze_statistics(extracted)
    report.module_results.append(stats_result)

    metadata_result = analyze_metadata(extracted)
    report.module_results.append(metadata_result)

    # 4. Compute summary
    report.compute_summary()

    # 5. Cleanup uploaded file
    try:
        if pdf_path and os.path.exists(pdf_path):
            os.remove(pdf_path)
    except Exception:
        pass

    return JSONResponse({
        "status": "success",
        "report": report.model_dump(),
    })


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
