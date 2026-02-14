"""Data models for the academic integrity checker."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    CONFIRMED = "confirmed"       # 确凿的问题
    SUSPICIOUS = "suspicious"     # 可疑的问题
    INFO = "info"                 # 信息提示


class IssueCategory(str, Enum):
    PLAGIARISM = "plagiarism"                   # 文本抄袭
    IMAGE_MANIPULATION = "image_manipulation"   # 图片篡改
    IMAGE_DUPLICATION = "image_duplication"      # 图片重复使用
    CITATION_ERROR = "citation_error"           # 引用错误
    CITATION_MISSING = "citation_missing"       # 缺失引用
    STATISTICAL_ERROR = "statistical_error"     # 统计错误
    DATA_INCONSISTENCY = "data_inconsistency"   # 数据不一致
    METADATA_ISSUE = "metadata_issue"           # 元数据问题


class Issue(BaseModel):
    """A single detected issue in the paper."""
    category: IssueCategory
    severity: SeverityLevel
    title: str
    description: str
    location: Optional[str] = None          # 页码、段落、图片编号等
    evidence: Optional[str] = None          # 具体证据
    confidence: float = Field(ge=0.0, le=1.0)  # 置信度 0-1
    suggestion: Optional[str] = None        # 修改建议


class ModuleResult(BaseModel):
    """Result from a single analysis module."""
    module_name: str
    issues: list[Issue] = []
    summary: str = ""
    error: Optional[str] = None


class AnalysisRequest(BaseModel):
    """Request to analyze a paper."""
    doi: Optional[str] = None
    url: Optional[str] = None
    arxiv_id: Optional[str] = None
    # file upload handled separately via form data


class AnalysisReport(BaseModel):
    """Complete analysis report for a paper."""
    paper_title: Optional[str] = None
    paper_source: str = ""                  # DOI, URL, or filename
    module_results: list[ModuleResult] = []
    total_confirmed: int = 0
    total_suspicious: int = 0
    total_info: int = 0
    overall_risk: str = "low"               # low, medium, high, critical

    def compute_summary(self):
        all_issues = []
        for mr in self.module_results:
            all_issues.extend(mr.issues)
        self.total_confirmed = sum(1 for i in all_issues if i.severity == SeverityLevel.CONFIRMED)
        self.total_suspicious = sum(1 for i in all_issues if i.severity == SeverityLevel.SUSPICIOUS)
        self.total_info = sum(1 for i in all_issues if i.severity == SeverityLevel.INFO)
        if self.total_confirmed >= 3:
            self.overall_risk = "critical"
        elif self.total_confirmed >= 1:
            self.overall_risk = "high"
        elif self.total_suspicious >= 3:
            self.overall_risk = "medium"
        else:
            self.overall_risk = "low"
