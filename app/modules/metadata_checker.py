"""Metadata and structural integrity checker module."""

import re
from datetime import datetime

from app.models import Issue, IssueCategory, ModuleResult, SeverityLevel


def check_pdf_metadata(metadata: dict) -> list[Issue]:
    """Check PDF metadata for suspicious properties."""
    issues = []

    if not metadata:
        return issues

    # Check creation/modification dates
    creation_date = metadata.get("CreationDate", "") or metadata.get("creation_date", "")
    mod_date = metadata.get("ModDate", "") or metadata.get("mod_date", "")

    if creation_date and mod_date:
        # Some PDF dates are in format D:YYYYMMDDHHmmSS
        def parse_pdf_date(d):
            d = d.replace("D:", "").strip()
            try:
                return datetime.strptime(d[:14], "%Y%m%d%H%M%S")
            except Exception:
                try:
                    return datetime.strptime(d[:8], "%Y%m%d")
                except Exception:
                    return None

        created = parse_pdf_date(creation_date)
        modified = parse_pdf_date(mod_date)

        if created and modified and modified < created:
            issues.append(Issue(
                category=IssueCategory.METADATA_ISSUE,
                severity=SeverityLevel.SUSPICIOUS,
                title="PDF日期异常 / Suspicious PDF dates",
                description=f"修改日期 ({modified}) 早于创建日期 ({created})",
                evidence=f"Created: {creation_date}, Modified: {mod_date}",
                confidence=0.7,
                suggestion="文件的时间戳可能被篡改或存在元数据错误",
            ))

    # Check producer/creator for suspicious tools
    producer = (metadata.get("Producer", "") or "").lower()
    creator = (metadata.get("Creator", "") or "").lower()

    suspicious_tools = ["photoshop", "gimp", "paint", "screenshot"]
    for tool in suspicious_tools:
        if tool in producer or tool in creator:
            issues.append(Issue(
                category=IssueCategory.METADATA_ISSUE,
                severity=SeverityLevel.INFO,
                title=f"PDF由图像编辑工具创建 / PDF created with image editor",
                description=f"PDF元数据显示使用了 '{producer or creator}' 创建",
                evidence=f"Producer: {producer}, Creator: {creator}",
                confidence=0.5,
                suggestion="学术论文通常使用 LaTeX/Word 生成，使用图像编辑工具可能表明文件经过额外处理",
            ))

    return issues


def check_text_structure(full_text: str) -> list[Issue]:
    """Check structural integrity of the paper."""
    issues = []

    if not full_text or len(full_text.strip()) < 100:
        return issues

    text_lower = full_text.lower()

    # Check for essential sections
    essential_sections = {
        "abstract": [r'\babstract\b'],
        "introduction": [r'\bintroduction\b'],
        "conclusion": [r'\bconclusion', r'\bsummary\b'],
        "references": [r'\breferences\b', r'\bbibliography\b'],
    }

    missing_sections = []
    for section, patterns in essential_sections.items():
        found = any(re.search(p, text_lower) for p in patterns)
        if not found:
            missing_sections.append(section)

    if missing_sections:
        issues.append(Issue(
            category=IssueCategory.METADATA_ISSUE,
            severity=SeverityLevel.INFO,
            title="缺少标准章节 / Missing standard sections",
            description=f"未检测到以下标准章节: {', '.join(missing_sections)}",
            confidence=0.5,
            suggestion="标准学术论文通常包含摘要、引言、结论和参考文献等部分",
        ))

    # Check for retraction notices
    retraction_patterns = [
        r'\bretract(?:ed|ion)\b',
        r'\bwithdraw(?:n|al)\b',
        r'\bcorrection notice\b',
        r'\berratum\b',
    ]
    for pattern in retraction_patterns:
        if re.search(pattern, text_lower):
            issues.append(Issue(
                category=IssueCategory.METADATA_ISSUE,
                severity=SeverityLevel.CONFIRMED,
                title="检测到撤稿/更正通知 / Retraction or correction notice detected",
                description=f"论文中包含可能的撤稿或更正通知关键词",
                confidence=0.7,
                suggestion="请查证该论文是否已被撤稿或存在勘误",
            ))
            break

    # Check for boilerplate/template text
    template_markers = [
        "insert title here",
        "your name here",
        "lorem ipsum",
        "[author name]",
        "[institution]",
        "xxx university",
        "enter the abstract",
    ]
    for marker in template_markers:
        if marker in text_lower:
            issues.append(Issue(
                category=IssueCategory.METADATA_ISSUE,
                severity=SeverityLevel.CONFIRMED,
                title="检测到模板占位符 / Template placeholder detected",
                description=f"论文中包含未替换的模板文本: '{marker}'",
                confidence=0.95,
                suggestion="请替换所有模板占位符文本",
            ))

    return issues


def analyze_metadata(extracted: dict) -> ModuleResult:
    """Run all metadata and structural checks."""
    issues = []

    metadata = extracted.get("metadata", {})
    full_text = extracted.get("full_text", "")

    issues.extend(check_pdf_metadata(metadata))
    issues.extend(check_text_structure(full_text))

    summary_parts = []
    confirmed = sum(1 for i in issues if i.severity == SeverityLevel.CONFIRMED)
    suspicious = sum(1 for i in issues if i.severity == SeverityLevel.SUSPICIOUS)
    info = sum(1 for i in issues if i.severity == SeverityLevel.INFO)

    if confirmed:
        summary_parts.append(f"{confirmed} 个确凿问题")
    if suspicious:
        summary_parts.append(f"{suspicious} 个可疑问题")
    if info:
        summary_parts.append(f"{info} 条信息提示")
    if not issues:
        summary_parts.append("未发现明显问题")

    return ModuleResult(
        module_name="元数据与结构检查 / Metadata & Structure",
        issues=issues,
        summary="；".join(summary_parts),
    )
