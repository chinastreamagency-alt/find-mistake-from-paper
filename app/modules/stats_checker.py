"""Statistical consistency checker module.

Inspired by statcheck and GRIM test - detects impossible or inconsistent
statistical values reported in academic papers.
"""

import re
import math
from typing import Optional

from app.models import Issue, IssueCategory, ModuleResult, SeverityLevel


def _grim_test(mean: float, n: int, decimals: int = 2) -> bool:
    """GRIM test: check if a reported mean is mathematically possible.

    For integer-scale data, the mean * n should produce an integer (within rounding).
    Returns True if the mean is consistent (passes), False if impossible.
    """
    if n <= 0:
        return True

    product = mean * n
    granularity = 1.0 / (10 ** decimals)

    # Check if product rounds to an integer within precision
    rounded_product = round(product, decimals)
    nearest_int = round(rounded_product)

    return abs(rounded_product - nearest_int) < granularity * n * 0.6


def _check_p_value_consistency(test_stat: float, df: float, reported_p: float,
                                test_type: str) -> Optional[dict]:
    """Check if a reported p-value is consistent with the test statistic and df.

    Uses approximations since we don't have full statistical tables.
    """
    try:
        from scipy import stats as sp_stats
    except ImportError:
        return None

    try:
        if test_type == "t":
            computed_p = 2 * (1 - sp_stats.t.cdf(abs(test_stat), df))
        elif test_type == "F":
            # For F-test, df should be (df1, df2) but we often only get one
            computed_p = 1 - sp_stats.f.cdf(test_stat, 1, df)
        elif test_type == "chi2":
            computed_p = 1 - sp_stats.chi2.cdf(test_stat, df)
        elif test_type == "z":
            computed_p = 2 * (1 - sp_stats.norm.cdf(abs(test_stat)))
        else:
            return None

        # Compare with reported p
        if reported_p > 0 and computed_p > 0:
            ratio = max(reported_p, computed_p) / min(reported_p, computed_p)
            return {
                "computed_p": computed_p,
                "reported_p": reported_p,
                "ratio": ratio,
                "consistent": ratio < 5,  # allow generous tolerance
            }
    except Exception:
        pass

    return None


def extract_statistical_tests(text: str) -> list[dict]:
    """Extract reported statistical test results from text."""
    results = []

    # Pattern: t(df) = value, p < value  or  t(df) = value, p = value
    t_pattern = re.compile(
        r't\s*\(\s*(\d+\.?\d*)\s*\)\s*=\s*(-?\d+\.?\d*)\s*[,;]\s*p\s*([<>=≤≥])\s*\.?(\d+\.?\d*)',
        re.IGNORECASE
    )
    for m in t_pattern.finditer(text):
        results.append({
            "type": "t",
            "df": float(m.group(1)),
            "statistic": float(m.group(2)),
            "p_relation": m.group(3),
            "p_value": float(f"0.{m.group(4)}") if not m.group(4).startswith("0") else float(m.group(4)),
            "raw": m.group(0),
        })

    # Pattern: F(df1, df2) = value, p ...
    f_pattern = re.compile(
        r'F\s*\(\s*(\d+\.?\d*)\s*,\s*(\d+\.?\d*)\s*\)\s*=\s*(\d+\.?\d*)\s*[,;]\s*p\s*([<>=≤≥])\s*\.?(\d+\.?\d*)',
        re.IGNORECASE
    )
    for m in f_pattern.finditer(text):
        results.append({
            "type": "F",
            "df1": float(m.group(1)),
            "df2": float(m.group(2)),
            "statistic": float(m.group(3)),
            "p_relation": m.group(4),
            "p_value": float(f"0.{m.group(5)}") if not m.group(5).startswith("0") else float(m.group(5)),
            "raw": m.group(0),
        })

    # Pattern: χ²(df) = value, p ...  or chi2(df) = value
    chi2_pattern = re.compile(
        r'[χχ]²?\s*\(\s*(\d+\.?\d*)\s*\)\s*=\s*(\d+\.?\d*)\s*[,;]\s*p\s*([<>=≤≥])\s*\.?(\d+\.?\d*)',
        re.IGNORECASE
    )
    for m in chi2_pattern.finditer(text):
        results.append({
            "type": "chi2",
            "df": float(m.group(1)),
            "statistic": float(m.group(2)),
            "p_relation": m.group(3),
            "p_value": float(f"0.{m.group(4)}") if not m.group(4).startswith("0") else float(m.group(4)),
            "raw": m.group(0),
        })

    # Pattern: r = .value, p ...  (correlation)
    r_pattern = re.compile(
        r'r\s*=\s*(-?\.?\d+\.?\d*)\s*[,;]\s*p\s*([<>=≤≥])\s*\.?(\d+\.?\d*)',
        re.IGNORECASE
    )
    for m in r_pattern.finditer(text):
        r_val = float(m.group(1))
        if -1 <= r_val <= 1:
            results.append({
                "type": "r",
                "statistic": r_val,
                "p_relation": m.group(2),
                "p_value": float(f"0.{m.group(3)}") if not m.group(3).startswith("0") else float(m.group(3)),
                "raw": m.group(0),
            })

    return results


def extract_means_and_ns(text: str) -> list[dict]:
    """Extract reported means and sample sizes for GRIM testing."""
    results = []

    # Pattern: M = value, N = value  or  mean = value (n = value)
    mean_n_pattern = re.compile(
        r'[Mm](?:ean)?\s*=\s*(\d+\.?\d+)\s*.*?[Nn]\s*=\s*(\d+)',
    )
    for m in mean_n_pattern.finditer(text):
        mean_val = float(m.group(1))
        n_val = int(m.group(2))
        decimals = len(m.group(1).split(".")[-1]) if "." in m.group(1) else 0
        if n_val > 0 and decimals > 0:
            results.append({
                "mean": mean_val,
                "n": n_val,
                "decimals": decimals,
                "raw": m.group(0),
            })

    return results


def check_p_value_bounds(tests: list[dict]) -> list[Issue]:
    """Check for impossible p-values."""
    issues = []

    for test in tests:
        p = test["p_value"]

        if p < 0 or p > 1:
            issues.append(Issue(
                category=IssueCategory.STATISTICAL_ERROR,
                severity=SeverityLevel.CONFIRMED,
                title="不可能的p值 / Impossible p-value",
                description=f"p值 {p} 超出有效范围 [0, 1]",
                evidence=test["raw"],
                confidence=0.99,
                suggestion="p值必须在0到1之间，请检查报告的数值",
            ))

        # Suspiciously convenient p-values
        if test["p_relation"] in ["<", "≤"]:
            if p in [0.05, 0.01, 0.001]:
                # This is normal, but check if the stat supports it
                pass
        elif test["p_relation"] == "=":
            # Exact p = .000 is suspicious
            if p == 0:
                issues.append(Issue(
                    category=IssueCategory.STATISTICAL_ERROR,
                    severity=SeverityLevel.SUSPICIOUS,
                    title="p值为零 / p-value reported as zero",
                    description="p值报告为 .000 或 0，这在统计学上是不精确的表述",
                    evidence=test["raw"],
                    confidence=0.6,
                    suggestion="应报告为 p < .001 而非 p = .000",
                ))

    return issues


def check_statistical_consistency(tests: list[dict]) -> list[Issue]:
    """Check if reported statistics are internally consistent."""
    issues = []

    for test in tests:
        if test["type"] in ["t", "chi2"] and "df" in test:
            result = _check_p_value_consistency(
                test["statistic"], test["df"], test["p_value"], test["type"]
            )
            if result and not result["consistent"]:
                issues.append(Issue(
                    category=IssueCategory.STATISTICAL_ERROR,
                    severity=SeverityLevel.CONFIRMED if result["ratio"] > 20 else SeverityLevel.SUSPICIOUS,
                    title="统计检验结果不一致 / Inconsistent statistical result",
                    description=(
                        f"报告的p值 ({test['p_value']}) 与根据检验统计量和自由度 "
                        f"计算得到的p值 ({result['computed_p']:.4f}) 不一致 "
                        f"(比值: {result['ratio']:.1f}x)"
                    ),
                    evidence=test["raw"],
                    confidence=min(0.5 + result["ratio"] / 100, 0.9),
                    suggestion="请重新计算统计检验，或核查报告的数值是否有误",
                ))

        # Check correlation bounds
        if test["type"] == "r":
            if abs(test["statistic"]) > 1:
                issues.append(Issue(
                    category=IssueCategory.STATISTICAL_ERROR,
                    severity=SeverityLevel.CONFIRMED,
                    title="不可能的相关系数 / Impossible correlation coefficient",
                    description=f"相关系数 r = {test['statistic']} 超出 [-1, 1] 范围",
                    evidence=test["raw"],
                    confidence=0.99,
                    suggestion="相关系数必须在 -1 到 1 之间",
                ))

    return issues


def check_grim(means_data: list[dict]) -> list[Issue]:
    """Apply GRIM test to reported means."""
    issues = []

    for data in means_data:
        passes = _grim_test(data["mean"], data["n"], data["decimals"])
        if not passes:
            issues.append(Issue(
                category=IssueCategory.DATA_INCONSISTENCY,
                severity=SeverityLevel.CONFIRMED,
                title="GRIM检验不通过 / GRIM test failure",
                description=(
                    f"均值 {data['mean']}（精度: {data['decimals']}位小数）"
                    f"在样本量 N={data['n']} 下数学上不可能"
                ),
                evidence=data["raw"],
                confidence=0.85,
                suggestion="该均值在给定样本量下不可能出现，请核查原始数据或报告的数值",
            ))

    return issues


def check_sample_size_consistency(text: str) -> list[Issue]:
    """Check for inconsistent sample sizes across the paper."""
    issues = []

    # Find all N = X mentions
    n_pattern = re.compile(r'[Nn]\s*=\s*(\d+)')
    n_values = [(int(m.group(1)), m.start()) for m in n_pattern.finditer(text)]

    if len(n_values) < 2:
        return issues

    # Group nearby N values and check for inconsistencies
    # e.g., "N = 100" then later "N = 98" without explanation
    total_n = [v for v, _ in n_values if v > 50]  # likely total sample sizes
    if len(set(total_n)) > 3 and len(total_n) > 4:
        unique_totals = sorted(set(total_n))
        issues.append(Issue(
            category=IssueCategory.DATA_INCONSISTENCY,
            severity=SeverityLevel.SUSPICIOUS,
            title="样本量不一致 / Inconsistent sample sizes",
            description=f"论文中出现了多个不同的大样本量: {unique_totals[:5]}",
            confidence=0.4,
            suggestion="多个不同的样本量可能反映数据排除不当或报告错误，请核查",
        ))

    return issues


def analyze_statistics(extracted: dict) -> ModuleResult:
    """Run all statistical checks."""
    issues = []
    full_text = extracted.get("full_text", "")

    if not full_text.strip():
        return ModuleResult(
            module_name="统计一致性检查 / Statistical Consistency",
            summary="未提取到文本内容",
        )

    # Extract and check statistical tests
    tests = extract_statistical_tests(full_text)
    if tests:
        issues.extend(check_p_value_bounds(tests))
        issues.extend(check_statistical_consistency(tests))

    # Extract and check means (GRIM)
    means_data = extract_means_and_ns(full_text)
    if means_data:
        issues.extend(check_grim(means_data))

    # Check sample size consistency
    issues.extend(check_sample_size_consistency(full_text))

    summary_parts = [f"共检查 {len(tests)} 个统计检验, {len(means_data)} 个均值"]
    confirmed = sum(1 for i in issues if i.severity == SeverityLevel.CONFIRMED)
    suspicious = sum(1 for i in issues if i.severity == SeverityLevel.SUSPICIOUS)
    if confirmed:
        summary_parts.append(f"{confirmed} 个确凿问题")
    if suspicious:
        summary_parts.append(f"{suspicious} 个可疑问题")
    if not confirmed and not suspicious:
        summary_parts.append("未发现明显问题")

    return ModuleResult(
        module_name="统计一致性检查 / Statistical Consistency",
        issues=issues,
        summary="；".join(summary_parts),
    )
