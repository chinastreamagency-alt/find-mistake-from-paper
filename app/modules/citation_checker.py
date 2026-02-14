"""Citation and reference verification module."""

import re
from typing import Optional

import httpx

from app.models import Issue, IssueCategory, ModuleResult, SeverityLevel


def _extract_references(ref_section: str) -> list[dict]:
    """Parse individual references from the references section."""
    refs = []
    if not ref_section:
        return refs

    # Try numbered reference format: [1], [2], etc.
    numbered = re.split(r'\n\s*\[(\d+)\]', ref_section)
    if len(numbered) > 2:
        for i in range(1, len(numbered) - 1, 2):
            num = numbered[i]
            text = numbered[i + 1].strip()
            refs.append({"number": int(num), "text": text, "raw": f"[{num}] {text}"})
        return refs

    # Try numbered format: 1., 2., etc.
    dotted = re.split(r'\n\s*(\d+)\.\s+', ref_section)
    if len(dotted) > 2:
        for i in range(1, len(dotted) - 1, 2):
            num = dotted[i]
            text = dotted[i + 1].strip()
            refs.append({"number": int(num), "text": text, "raw": f"{num}. {text}"})
        return refs

    # Fall back to line-by-line
    for i, line in enumerate(ref_section.split("\n"), 1):
        line = line.strip()
        if len(line) > 20:
            refs.append({"number": i, "text": line, "raw": line})

    return refs


def _extract_doi_from_ref(ref_text: str) -> Optional[str]:
    """Try to extract DOI from reference text."""
    doi_match = re.search(r'(10\.\d{4,}/[^\s,;]+)', ref_text)
    if doi_match:
        doi = doi_match.group(1).rstrip(".")
        return doi
    return None


def _extract_year_from_ref(ref_text: str) -> Optional[int]:
    """Try to extract publication year from reference text."""
    # Common patterns: (2020), 2020., (2020)
    year_match = re.search(r'\((\d{4})\)|[\s,.](\d{4})[),.\s]', ref_text)
    if year_match:
        year_str = year_match.group(1) or year_match.group(2)
        year = int(year_str)
        if 1900 <= year <= 2030:
            return year
    return None


def _find_citations_in_text(full_text: str) -> set[int]:
    """Find all citation numbers referenced in the text body."""
    # Pattern: [1], [2,3], [1-5], [1, 2, 3]
    cited = set()
    bracket_refs = re.findall(r'\[([^\]]+)\]', full_text)
    for ref in bracket_refs:
        # Handle ranges like 1-5
        if re.match(r'^[\d,\s\-–]+$', ref):
            parts = re.split(r'[,\s]+', ref)
            for part in parts:
                part = part.strip()
                range_match = re.match(r'(\d+)\s*[-–]\s*(\d+)', part)
                if range_match:
                    start, end = int(range_match.group(1)), int(range_match.group(2))
                    cited.update(range(start, end + 1))
                elif part.isdigit():
                    cited.add(int(part))
    return cited


async def verify_doi(doi: str) -> dict:
    """Verify a DOI exists via CrossRef."""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(f"https://api.crossref.org/works/{doi}")
            if resp.status_code == 200:
                data = resp.json()["message"]
                return {
                    "valid": True,
                    "title": data.get("title", [""])[0],
                    "year": data.get("published-print", {}).get("date-parts", [[None]])[0][0],
                    "authors": [
                        f"{a.get('given', '')} {a.get('family', '')}".strip()
                        for a in data.get("author", [])
                    ],
                }
            return {"valid": False}
        except Exception:
            return {"valid": None, "error": "Network error"}


def check_citation_consistency(full_text: str, references: list[dict]) -> list[Issue]:
    """Check that citations in text match references list."""
    issues = []

    cited_numbers = _find_citations_in_text(full_text)
    ref_numbers = {r["number"] for r in references}

    # Check for cited but not listed references
    missing_refs = cited_numbers - ref_numbers
    for num in sorted(missing_refs):
        if num > 0 and num < 500:  # filter noise
            issues.append(Issue(
                category=IssueCategory.CITATION_MISSING,
                severity=SeverityLevel.CONFIRMED,
                title=f"引用 [{num}] 在参考文献中缺失 / Citation [{num}] missing from references",
                description=f"正文中引用了 [{num}]，但参考文献列表中未找到该条目",
                confidence=0.9,
                suggestion="添加缺失的参考文献或修正引用编号",
            ))

    # Check for listed but never cited references
    uncited_refs = ref_numbers - cited_numbers
    for num in sorted(uncited_refs):
        ref_text = next((r["text"][:80] for r in references if r["number"] == num), "")
        issues.append(Issue(
            category=IssueCategory.CITATION_ERROR,
            severity=SeverityLevel.SUSPICIOUS,
            title=f"参考文献 [{num}] 未被引用 / Reference [{num}] never cited",
            description=f"参考文献 [{num}] 在正文中未被引用",
            evidence=f"[{num}] {ref_text}...",
            confidence=0.7,
            suggestion="确认是否遗漏了正文中的引用，或移除未使用的参考文献",
        ))

    # Check for numbering gaps
    if ref_numbers:
        expected = set(range(1, max(ref_numbers) + 1))
        gaps = expected - ref_numbers
        for num in sorted(gaps):
            issues.append(Issue(
                category=IssueCategory.CITATION_ERROR,
                severity=SeverityLevel.CONFIRMED,
                title=f"参考文献编号不连续: 缺少 [{num}] / Missing reference number [{num}]",
                description=f"参考文献编号存在间断，缺少第 [{num}] 条",
                confidence=0.85,
                suggestion="检查并修正参考文献编号",
            ))

    return issues


def check_reference_format(references: list[dict]) -> list[Issue]:
    """Check reference formatting consistency."""
    issues = []

    if not references:
        return issues

    # Check for year presence
    refs_with_year = 0
    refs_without_year = 0
    for ref in references:
        year = _extract_year_from_ref(ref["text"])
        if year:
            refs_with_year += 1
        else:
            refs_without_year += 1

    if refs_with_year > 0 and refs_without_year > 0:
        missing_pct = refs_without_year / len(references)
        if missing_pct > 0.1:
            issues.append(Issue(
                category=IssueCategory.CITATION_ERROR,
                severity=SeverityLevel.SUSPICIOUS,
                title="部分参考文献缺少年份 / Some references missing year",
                description=f"{refs_without_year}/{len(references)} 条参考文献缺少出版年份",
                confidence=0.6,
                suggestion="补全所有参考文献的出版年份信息",
            ))

    # Check for future dates
    from datetime import datetime
    current_year = datetime.now().year
    for ref in references:
        year = _extract_year_from_ref(ref["text"])
        if year and year > current_year:
            issues.append(Issue(
                category=IssueCategory.CITATION_ERROR,
                severity=SeverityLevel.CONFIRMED,
                title=f"参考文献 [{ref['number']}] 年份异常 / Reference [{ref['number']}] has future year",
                description=f"参考文献引用了未来的年份 {year}",
                evidence=ref["text"][:120],
                confidence=0.95,
                suggestion="核查并修正该参考文献的出版年份",
            ))

    # Check for duplicate references
    seen_texts = {}
    for ref in references:
        normalized = re.sub(r'\s+', ' ', ref["text"].lower().strip())[:200]
        if normalized in seen_texts:
            issues.append(Issue(
                category=IssueCategory.CITATION_ERROR,
                severity=SeverityLevel.CONFIRMED,
                title=f"重复参考文献: [{seen_texts[normalized]}] 和 [{ref['number']}] / Duplicate references",
                description=f"参考文献 [{seen_texts[normalized]}] 和 [{ref['number']}] 内容重复",
                evidence=ref["text"][:120],
                confidence=0.9,
                suggestion="移除重复的参考文献并更新引用编号",
            ))
        else:
            seen_texts[normalized] = ref["number"]

    return issues


async def verify_references_online(references: list[dict], max_check: int = 20) -> list[Issue]:
    """Verify references against CrossRef API."""
    issues = []

    checked = 0
    for ref in references:
        if checked >= max_check:
            break

        doi = _extract_doi_from_ref(ref["text"])
        if not doi:
            continue

        checked += 1
        result = await verify_doi(doi)

        if result.get("valid") is False:
            issues.append(Issue(
                category=IssueCategory.CITATION_ERROR,
                severity=SeverityLevel.CONFIRMED,
                title=f"参考文献 [{ref['number']}] DOI 无效 / Invalid DOI in reference [{ref['number']}]",
                description=f"DOI {doi} 在 CrossRef 中查询不到",
                evidence=ref["text"][:120],
                confidence=0.9,
                suggestion="核查该 DOI 是否正确",
            ))
        elif result.get("valid") is True:
            # Cross-check year
            ref_year = _extract_year_from_ref(ref["text"])
            cr_year = result.get("year")
            if ref_year and cr_year and abs(ref_year - cr_year) > 1:
                issues.append(Issue(
                    category=IssueCategory.CITATION_ERROR,
                    severity=SeverityLevel.SUSPICIOUS,
                    title=f"参考文献 [{ref['number']}] 年份不匹配 / Year mismatch in [{ref['number']}]",
                    description=f"论文中标注年份 {ref_year}，但 CrossRef 记录年份为 {cr_year}",
                    evidence=f"论文: {ref['text'][:80]}...\nCrossRef title: {result.get('title', '')}",
                    confidence=0.8,
                    suggestion="核对该参考文献的正确出版年份",
                ))

    return issues


async def analyze_citations(extracted: dict, paper_metadata: dict = None) -> ModuleResult:
    """Run all citation checks."""
    issues = []

    full_text = extracted.get("full_text", "")
    ref_section = extracted.get("references_section", "")

    references = _extract_references(ref_section)

    if not references and not ref_section:
        return ModuleResult(
            module_name="引用检查 / Citation Verification",
            summary="未找到参考文献章节，跳过引用检查",
        )

    # Offline checks
    issues.extend(check_citation_consistency(full_text, references))
    issues.extend(check_reference_format(references))

    # Online verification
    try:
        online_issues = await verify_references_online(references)
        issues.extend(online_issues)
    except Exception:
        pass

    summary_parts = [f"共检查 {len(references)} 条参考文献"]
    confirmed = sum(1 for i in issues if i.severity == SeverityLevel.CONFIRMED)
    suspicious = sum(1 for i in issues if i.severity == SeverityLevel.SUSPICIOUS)
    if confirmed:
        summary_parts.append(f"{confirmed} 个确凿问题")
    if suspicious:
        summary_parts.append(f"{suspicious} 个可疑问题")
    if not confirmed and not suspicious:
        summary_parts.append("未发现明显问题")

    return ModuleResult(
        module_name="引用检查 / Citation Verification",
        issues=issues,
        summary="；".join(summary_parts),
    )
