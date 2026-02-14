"""Text plagiarism and similarity detection module."""

import re
from collections import Counter

from app.models import Issue, IssueCategory, ModuleResult, SeverityLevel


def _tokenize(text: str) -> list[str]:
    """Simple word tokenization."""
    return re.findall(r'\b\w+\b', text.lower())


def _ngrams(tokens: list[str], n: int) -> list[tuple]:
    """Generate n-grams from tokens."""
    return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]


def _cosine_similarity(counter1: Counter, counter2: Counter) -> float:
    """Compute cosine similarity between two frequency counters."""
    intersection = set(counter1.keys()) & set(counter2.keys())
    numerator = sum(counter1[x] * counter2[x] for x in intersection)
    sum1 = sum(v ** 2 for v in counter1.values()) ** 0.5
    sum2 = sum(v ** 2 for v in counter2.values()) ** 0.5
    if sum1 == 0 or sum2 == 0:
        return 0.0
    return numerator / (sum1 * sum2)


def _jaccard_similarity(set1: set, set2: set) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set1 or not set2:
        return 0.0
    intersection = set1 & set2
    union = set1 | set2
    return len(intersection) / len(union)


def detect_self_plagiarism(pages: list[dict]) -> list[Issue]:
    """Detect internal text reuse (self-plagiarism within the document)."""
    issues = []

    # Compare paragraphs across pages for internal duplication
    all_paragraphs = []
    for page in pages:
        text = page.get("text", "")
        paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 80]
        for para in paragraphs:
            all_paragraphs.append({
                "text": para,
                "page": page["page_num"],
                "tokens": _tokenize(para),
            })

    for i in range(len(all_paragraphs)):
        for j in range(i + 1, len(all_paragraphs)):
            p1 = all_paragraphs[i]
            p2 = all_paragraphs[j]

            if p1["page"] == p2["page"]:
                continue

            # Check n-gram overlap
            ng1 = set(_ngrams(p1["tokens"], 5))
            ng2 = set(_ngrams(p2["tokens"], 5))

            if not ng1 or not ng2:
                continue

            sim = _jaccard_similarity(ng1, ng2)

            if sim > 0.7:
                issues.append(Issue(
                    category=IssueCategory.PLAGIARISM,
                    severity=SeverityLevel.CONFIRMED,
                    title="内部文本重复 / Internal text duplication",
                    description=f"第{p1['page']}页和第{p2['page']}页存在高度相似的段落（相似度: {sim:.1%}）",
                    location=f"Page {p1['page']} & Page {p2['page']}",
                    evidence=f"段落1: {p1['text'][:100]}...\n段落2: {p2['text'][:100]}...",
                    confidence=min(sim, 1.0),
                    suggestion="检查是否为不当的自我引用或重复段落",
                ))
            elif sim > 0.4:
                issues.append(Issue(
                    category=IssueCategory.PLAGIARISM,
                    severity=SeverityLevel.SUSPICIOUS,
                    title="疑似内部文本复用 / Possible internal text reuse",
                    description=f"第{p1['page']}页和第{p2['page']}页存在相似段落（相似度: {sim:.1%}）",
                    location=f"Page {p1['page']} & Page {p2['page']}",
                    confidence=sim,
                    suggestion="请人工审核这两段内容是否为合理复用",
                ))

    return issues


def detect_excessive_quoting(full_text: str) -> list[Issue]:
    """Detect excessive direct quotation without proper attribution."""
    issues = []

    # Find quoted passages
    quotes = re.findall(r'"([^"]{50,})"', full_text)
    quotes += re.findall(r'"([^"]{50,})"', full_text)  # smart quotes

    total_words = len(_tokenize(full_text))
    quoted_words = sum(len(_tokenize(q)) for q in quotes)

    if total_words > 0 and quoted_words / total_words > 0.15:
        issues.append(Issue(
            category=IssueCategory.PLAGIARISM,
            severity=SeverityLevel.SUSPICIOUS,
            title="过度直接引用 / Excessive direct quotation",
            description=f"论文中直接引用内容占比过高 ({quoted_words/total_words:.1%})，"
                        f"共发现 {len(quotes)} 段直接引用",
            confidence=0.7,
            suggestion="考虑用自己的语言重述部分引用内容，并注明出处",
        ))

    # Check for very long unattributed quotes
    for q in quotes:
        words = len(_tokenize(q))
        if words > 100:
            issues.append(Issue(
                category=IssueCategory.PLAGIARISM,
                severity=SeverityLevel.SUSPICIOUS,
                title="过长直接引用 / Excessively long direct quote",
                description=f"发现一段超过{words}个词的直接引用",
                evidence=f'"{q[:150]}..."',
                confidence=0.6,
                suggestion="过长的直接引用应缩短并用自己的语言改述",
            ))

    return issues


def detect_writing_inconsistency(pages: list[dict]) -> list[Issue]:
    """Detect significant writing style changes that may indicate copy-paste."""
    issues = []

    if len(pages) < 3:
        return issues

    page_metrics = []
    for page in pages:
        text = page.get("text", "")
        tokens = _tokenize(text)
        if len(tokens) < 20:
            continue

        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

        avg_sentence_len = (
            sum(len(_tokenize(s)) for s in sentences) / max(len(sentences), 1)
        )
        vocab_richness = len(set(tokens)) / max(len(tokens), 1)

        page_metrics.append({
            "page": page["page_num"],
            "avg_sentence_len": avg_sentence_len,
            "vocab_richness": vocab_richness,
        })

    if len(page_metrics) < 3:
        return issues

    # Check for sudden style shifts
    for i in range(1, len(page_metrics)):
        prev = page_metrics[i - 1]
        curr = page_metrics[i]

        sent_diff = abs(curr["avg_sentence_len"] - prev["avg_sentence_len"])
        vocab_diff = abs(curr["vocab_richness"] - prev["vocab_richness"])

        if sent_diff > 10 and vocab_diff > 0.15:
            issues.append(Issue(
                category=IssueCategory.PLAGIARISM,
                severity=SeverityLevel.SUSPICIOUS,
                title="写作风格突变 / Writing style inconsistency",
                description=f"第{prev['page']}页到第{curr['page']}页之间写作风格发生显著变化",
                location=f"Page {prev['page']}-{curr['page']}",
                evidence=f"平均句长变化: {prev['avg_sentence_len']:.1f} → {curr['avg_sentence_len']:.1f}, "
                         f"词汇丰富度变化: {prev['vocab_richness']:.2f} → {curr['vocab_richness']:.2f}",
                confidence=0.5,
                suggestion="写作风格的突然变化可能暗示拼凑或代写，建议核查",
            ))

    return issues


def analyze_plagiarism(extracted: dict) -> ModuleResult:
    """Run all plagiarism detection checks."""
    issues = []

    pages = extracted.get("pages", [])
    full_text = extracted.get("full_text", "")

    if not full_text.strip():
        return ModuleResult(
            module_name="文本查重 / Plagiarism Detection",
            summary="未能提取到有效文本",
            error="No text content extracted",
        )

    issues.extend(detect_self_plagiarism(pages))
    issues.extend(detect_excessive_quoting(full_text))
    issues.extend(detect_writing_inconsistency(pages))

    summary_parts = []
    if not issues:
        summary_parts.append("未发现明显的文本重复或抄袭痕迹")
    else:
        confirmed = sum(1 for i in issues if i.severity == SeverityLevel.CONFIRMED)
        suspicious = sum(1 for i in issues if i.severity == SeverityLevel.SUSPICIOUS)
        if confirmed:
            summary_parts.append(f"{confirmed} 个确凿问题")
        if suspicious:
            summary_parts.append(f"{suspicious} 个可疑问题")

    return ModuleResult(
        module_name="文本查重 / Plagiarism Detection",
        issues=issues,
        summary="；".join(summary_parts) if summary_parts else "分析完成",
    )
