"""Image forensics module - detect manipulation, duplication, and other issues."""

import io
import math
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter

from app.models import Issue, IssueCategory, ModuleResult, SeverityLevel


def _bytes_to_image(data: bytes) -> Optional[Image.Image]:
    """Convert bytes to PIL Image."""
    try:
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None


def error_level_analysis(image: Image.Image, quality: int = 90) -> dict:
    """Perform Error Level Analysis (ELA) to detect image manipulation.

    Resaves image at a given quality and compares with original.
    Manipulated regions often show different error levels.
    """
    # Save at specified quality
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    resaved = Image.open(buffer).convert("RGB")

    # Compute difference
    orig_arr = np.array(image, dtype=np.float64)
    resaved_arr = np.array(resaved, dtype=np.float64)
    diff = np.abs(orig_arr - resaved_arr)

    # Analyze error levels
    mean_error = np.mean(diff)
    max_error = np.max(diff)
    std_error = np.std(diff)

    # Check for suspicious regions (high error in localized areas)
    block_size = 32
    h, w = diff.shape[:2]
    block_means = []

    for y in range(0, h - block_size, block_size):
        for x in range(0, w - block_size, block_size):
            block = diff[y:y+block_size, x:x+block_size]
            block_means.append(np.mean(block))

    block_means = np.array(block_means) if block_means else np.array([0])
    block_std = np.std(block_means)
    block_mean = np.mean(block_means)

    # High variation in block errors suggests manipulation
    suspicious_blocks = int(np.sum(block_means > block_mean + 2 * block_std))
    total_blocks = len(block_means)

    return {
        "mean_error": float(mean_error),
        "max_error": float(max_error),
        "std_error": float(std_error),
        "block_std": float(block_std),
        "suspicious_blocks": suspicious_blocks,
        "total_blocks": total_blocks,
        "suspicious_ratio": suspicious_blocks / max(total_blocks, 1),
    }


def detect_copy_move(image: Image.Image, block_size: int = 16, threshold: float = 10.0) -> dict:
    """Detect copy-move forgery using block matching.

    Divides image into blocks and checks for suspiciously similar
    blocks in different locations.
    """
    gray = np.array(image.convert("L"), dtype=np.float64)
    h, w = gray.shape

    if h < block_size * 3 or w < block_size * 3:
        return {"detected": False, "matches": 0, "reason": "Image too small"}

    # Extract blocks and their features (DCT-like using mean/std)
    blocks = []
    step = block_size // 2  # overlapping blocks

    for y in range(0, h - block_size, step):
        for x in range(0, w - block_size, step):
            block = gray[y:y+block_size, x:x+block_size]
            feature = (np.mean(block), np.std(block), np.median(block))
            blocks.append({
                "pos": (x, y),
                "feature": feature,
                "data": block,
            })

    # Compare blocks (limit comparisons for performance)
    matches = []
    max_blocks = min(len(blocks), 2000)
    blocks = blocks[:max_blocks]

    # Sort by feature for faster matching
    blocks.sort(key=lambda b: b["feature"])

    for i in range(len(blocks)):
        for j in range(i + 1, min(i + 50, len(blocks))):
            b1 = blocks[i]
            b2 = blocks[j]

            # Quick feature check
            feat_diff = sum(abs(a - b) for a, b in zip(b1["feature"], b2["feature"]))
            if feat_diff > threshold:
                continue

            # Position distance check (skip adjacent blocks)
            dx = abs(b1["pos"][0] - b2["pos"][0])
            dy = abs(b1["pos"][1] - b2["pos"][1])
            if dx < block_size * 2 and dy < block_size * 2:
                continue

            # Detailed comparison
            mse = np.mean((b1["data"] - b2["data"]) ** 2)
            if mse < threshold:
                matches.append({
                    "pos1": b1["pos"],
                    "pos2": b2["pos"],
                    "mse": float(mse),
                })

    return {
        "detected": len(matches) > 3,
        "matches": len(matches),
        "match_details": matches[:10],  # limit output
    }


def detect_image_duplication(images: list[dict]) -> list[Issue]:
    """Detect duplicate or near-duplicate images within the paper."""
    issues = []
    if len(images) < 2:
        return issues

    # Convert all images to comparable format
    processed = []
    for img_info in images:
        img = _bytes_to_image(img_info["data"])
        if img is None:
            continue

        # Resize to standard size for comparison
        thumb = img.resize((64, 64), Image.Resampling.LANCZOS)
        arr = np.array(thumb, dtype=np.float64)
        processed.append({
            "page": img_info.get("page", "?"),
            "index": img_info.get("index", "?"),
            "array": arr,
            "original_size": img.size,
        })

    # Compare all pairs
    for i in range(len(processed)):
        for j in range(i + 1, len(processed)):
            p1 = processed[i]
            p2 = processed[j]

            # Compute normalized cross-correlation
            a1 = p1["array"].flatten()
            a2 = p2["array"].flatten()

            # Normalize
            a1_norm = a1 - np.mean(a1)
            a2_norm = a2 - np.mean(a2)

            std1 = np.std(a1)
            std2 = np.std(a2)

            if std1 < 1 or std2 < 1:
                continue

            correlation = np.dot(a1_norm, a2_norm) / (len(a1) * std1 * std2)

            if correlation > 0.95:
                issues.append(Issue(
                    category=IssueCategory.IMAGE_DUPLICATION,
                    severity=SeverityLevel.CONFIRMED,
                    title="图片重复 / Duplicate images detected",
                    description=(
                        f"第{p1['page']}页图片{p1['index']+1}与"
                        f"第{p2['page']}页图片{p2['index']+1}高度相似 "
                        f"(相关系数: {correlation:.3f})"
                    ),
                    location=f"Page {p1['page']} Image {p1['index']+1} & Page {p2['page']} Image {p2['index']+1}",
                    confidence=float(correlation),
                    suggestion="检查这两张图片是否为重复使用，如果表示不同数据则为严重问题",
                ))
            elif correlation > 0.85:
                issues.append(Issue(
                    category=IssueCategory.IMAGE_DUPLICATION,
                    severity=SeverityLevel.SUSPICIOUS,
                    title="疑似图片相似 / Possibly similar images",
                    description=(
                        f"第{p1['page']}页图片{p1['index']+1}与"
                        f"第{p2['page']}页图片{p2['index']+1}存在较高相似度 "
                        f"(相关系数: {correlation:.3f})"
                    ),
                    location=f"Page {p1['page']} Image {p1['index']+1} & Page {p2['page']} Image {p2['index']+1}",
                    confidence=float(correlation) * 0.8,
                    suggestion="人工核查这两张图片是否存在复用或篡改",
                ))

    return issues


def analyze_single_image(img_data: bytes, page: int, index: int) -> list[Issue]:
    """Run forensic analysis on a single image."""
    issues = []
    img = _bytes_to_image(img_data)
    if img is None:
        return issues

    # Skip very small images (likely icons or decorations)
    if img.size[0] < 50 or img.size[1] < 50:
        return issues

    # Error Level Analysis
    try:
        ela_result = error_level_analysis(img)

        if ela_result["suspicious_ratio"] > 0.15 and ela_result["block_std"] > 15:
            issues.append(Issue(
                category=IssueCategory.IMAGE_MANIPULATION,
                severity=SeverityLevel.SUSPICIOUS,
                title=f"疑似图片篡改 (第{page}页图{index+1}) / Possible image manipulation",
                description=(
                    f"ELA分析检测到异常误差分布："
                    f"可疑区块占比 {ela_result['suspicious_ratio']:.1%}，"
                    f"区块标准差 {ela_result['block_std']:.1f}"
                ),
                location=f"Page {page}, Image {index + 1}",
                evidence=f"Mean error: {ela_result['mean_error']:.2f}, "
                         f"Max error: {ela_result['max_error']:.2f}, "
                         f"Suspicious blocks: {ela_result['suspicious_blocks']}/{ela_result['total_blocks']}",
                confidence=min(ela_result["suspicious_ratio"] * 2, 0.8),
                suggestion="该图片的误差级别分布不均匀，可能经过局部编辑。建议使用专业工具进一步分析",
            ))
    except Exception:
        pass

    # Copy-Move detection
    try:
        cm_result = detect_copy_move(img)
        if cm_result["detected"]:
            issues.append(Issue(
                category=IssueCategory.IMAGE_MANIPULATION,
                severity=SeverityLevel.SUSPICIOUS,
                title=f"疑似复制-移动篡改 (第{page}页图{index+1}) / Possible copy-move forgery",
                description=(
                    f"检测到 {cm_result['matches']} 个疑似复制-移动区块匹配"
                ),
                location=f"Page {page}, Image {index + 1}",
                confidence=min(cm_result["matches"] / 20.0, 0.75),
                suggestion="图片中存在疑似复制-粘贴的区域，可能用于隐藏或伪造数据",
            ))
    except Exception:
        pass

    return issues


def analyze_images(extracted: dict) -> ModuleResult:
    """Run all image forensics checks."""
    issues = []

    images = extracted.get("images", [])

    if not images:
        return ModuleResult(
            module_name="图片取证 / Image Forensics",
            summary="论文中未提取到图片",
        )

    # Check individual images
    for img_info in images:
        img_issues = analyze_single_image(
            img_info["data"],
            img_info.get("page", 0),
            img_info.get("index", 0),
        )
        issues.extend(img_issues)

    # Check for duplicates across images
    dup_issues = detect_image_duplication(images)
    issues.extend(dup_issues)

    summary_parts = [f"共分析 {len(images)} 张图片"]
    confirmed = sum(1 for i in issues if i.severity == SeverityLevel.CONFIRMED)
    suspicious = sum(1 for i in issues if i.severity == SeverityLevel.SUSPICIOUS)
    if confirmed:
        summary_parts.append(f"{confirmed} 个确凿问题")
    if suspicious:
        summary_parts.append(f"{suspicious} 个可疑问题")
    if not confirmed and not suspicious:
        summary_parts.append("未发现明显问题")

    return ModuleResult(
        module_name="图片取证 / Image Forensics",
        issues=issues,
        summary="；".join(summary_parts),
    )
