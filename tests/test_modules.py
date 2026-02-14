"""Tests for the academic integrity checker modules."""

import pytest
from app.models import SeverityLevel
from app.modules.plagiarism_detector import (
    analyze_plagiarism,
    detect_self_plagiarism,
    detect_excessive_quoting,
)
from app.modules.stats_checker import (
    extract_statistical_tests,
    extract_means_and_ns,
    check_p_value_bounds,
    check_grim,
    _grim_test,
)
from app.modules.citation_checker import (
    _extract_references,
    _find_citations_in_text,
    check_citation_consistency,
    check_reference_format,
)
from app.modules.image_forensics import (
    error_level_analysis,
    detect_copy_move,
)
from app.modules.metadata_checker import (
    check_pdf_metadata,
    check_text_structure,
)


# ========== GRIM Test ==========

class TestGRIM:
    def test_possible_mean(self):
        # Mean 2.5 with N=2: 2.5*2=5 (integer) -> passes
        assert _grim_test(2.5, 2, 1) is True

    def test_impossible_mean(self):
        # Mean 1.23 with N=10: 1.23*10=12.3 (not integer) -> fails
        assert _grim_test(1.23, 10, 2) is False

    def test_possible_mean_large_n(self):
        # Mean 3.14 with N=100: 3.14*100=314 (integer) -> passes
        assert _grim_test(3.14, 100, 2) is True


# ========== Statistical Tests ==========

class TestStatsExtraction:
    def test_extract_t_test(self):
        text = "The analysis revealed a significant effect, t(45) = 2.34, p < .05."
        tests = extract_statistical_tests(text)
        assert len(tests) >= 1
        t_test = [t for t in tests if t["type"] == "t"][0]
        assert t_test["df"] == 45.0
        assert t_test["statistic"] == 2.34

    def test_extract_f_test(self):
        text = "ANOVA results: F(2, 57) = 4.56, p = .014"
        tests = extract_statistical_tests(text)
        f_tests = [t for t in tests if t["type"] == "F"]
        assert len(f_tests) >= 1
        assert f_tests[0]["statistic"] == 4.56

    def test_extract_correlation(self):
        text = "We found r = .85, p < .001"
        tests = extract_statistical_tests(text)
        r_tests = [t for t in tests if t["type"] == "r"]
        assert len(r_tests) >= 1

    def test_impossible_p_value(self):
        tests = [{"type": "t", "p_value": 1.5, "p_relation": "=", "raw": "t(10)=2, p=1.5"}]
        issues = check_p_value_bounds(tests)
        assert len(issues) >= 1
        assert issues[0].severity == SeverityLevel.CONFIRMED


# ========== Citation Tests ==========

class TestCitations:
    def test_extract_references(self):
        ref_section = """
[1] Smith, J. (2020). Title of paper. Journal, 1, 1-10.
[2] Doe, A. (2021). Another paper. Nature, 500, 100-105.
[3] Lee, B. (2019). Third paper. Science, 300, 50-55.
"""
        refs = _extract_references(ref_section)
        assert len(refs) == 3
        assert refs[0]["number"] == 1
        assert refs[2]["number"] == 3

    def test_find_citations(self):
        text = "As shown in [1], and confirmed by [2,3], the results [4-6] suggest..."
        cited = _find_citations_in_text(text)
        assert 1 in cited
        assert 2 in cited
        assert 3 in cited
        assert 4 in cited
        assert 5 in cited
        assert 6 in cited

    def test_missing_citation(self):
        text = "According to [1] and [3]."
        refs = [
            {"number": 1, "text": "Ref 1 text"},
            {"number": 2, "text": "Ref 2 text"},
        ]
        issues = check_citation_consistency(text, refs)
        # [3] is cited but not in refs -> missing
        missing = [i for i in issues if "缺失" in i.title or "missing" in i.title.lower()]
        assert len(missing) >= 1

    def test_duplicate_reference(self):
        refs = [
            {"number": 1, "text": "Smith, J. (2020). The same paper title. Journal, 1."},
            {"number": 2, "text": "Smith, J. (2020). The same paper title. Journal, 1."},
        ]
        issues = check_reference_format(refs)
        dup = [i for i in issues if "重复" in i.title or "Duplicate" in i.title]
        assert len(dup) >= 1


# ========== Plagiarism Tests ==========

class TestPlagiarism:
    def test_detect_self_plagiarism(self):
        # Same paragraph on different pages
        repeated = "This is a very long paragraph that contains many words and is used " * 5
        pages = [
            {"page_num": 1, "text": repeated},
            {"page_num": 5, "text": repeated},
        ]
        issues = detect_self_plagiarism(pages)
        assert len(issues) >= 1

    def test_no_false_positive_short_text(self):
        pages = [
            {"page_num": 1, "text": "Hello world"},
            {"page_num": 2, "text": "Goodbye world"},
        ]
        issues = detect_self_plagiarism(pages)
        assert len(issues) == 0


# ========== Metadata Tests ==========

class TestMetadata:
    def test_template_detection(self):
        text = "This paper by [Author Name] from [Institution] presents insert title here."
        issues = check_text_structure(text * 5)  # make it long enough
        template = [i for i in issues if "模板" in i.title or "Template" in i.title]
        assert len(template) >= 1

    def test_retraction_detection(self):
        text = "RETRACTION NOTICE: This article has been retracted by the authors. " * 5
        issues = check_text_structure(text)
        retraction = [i for i in issues if "撤稿" in i.title or "Retraction" in i.title]
        assert len(retraction) >= 1


# ========== Image Forensics Tests ==========

class TestImageForensics:
    def test_ela_on_clean_image(self):
        from PIL import Image
        # Create a clean gradient image
        img = Image.new("RGB", (200, 200), color=(128, 128, 128))
        result = error_level_analysis(img)
        assert "mean_error" in result
        assert "suspicious_ratio" in result
        # Clean image should have low suspicious ratio
        assert result["suspicious_ratio"] < 0.5

    def test_copy_move_on_small_image(self):
        from PIL import Image
        img = Image.new("RGB", (30, 30))
        result = detect_copy_move(img)
        assert result["detected"] is False
