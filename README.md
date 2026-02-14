# 学术诚信检查器 / Academic Integrity Checker

开源的一站式学术论文不端行为检测系统。上传论文（PDF/DOCX）或输入 DOI/arXiv ID/URL，自动检测以下问题：

## 功能模块

| 模块 | 检测内容 | 技术原理 |
|------|---------|---------|
| **文本查重** | 内部文本重复、过度引用、写作风格突变 | N-gram 相似度、Jaccard/余弦距离、句法统计 |
| **引用核查** | 引用缺失、编号断裂、重复引用、DOI验证、年份错误 | CrossRef API 在线验证、正则解析 |
| **图片取证** | 图片篡改(ELA)、复制-移动伪造、图片重复使用 | Error Level Analysis、块匹配、归一化互相关 |
| **统计验证** | p值错误、统计不一致、GRIM检验、样本量矛盾 | statcheck 原理、GRIM/GRIMMER 检验、scipy 统计计算 |
| **元数据检查** | PDF时间戳异常、模板占位符、撤稿通知、结构缺失 | 元数据解析、关键词匹配 |

## 问题分级

- **确凿 (Confirmed)** — 数学或逻辑上可证明的错误（如不可能的p值、GRIM不通过、图片完全重复）
- **可疑 (Suspicious)** — 需要人工审核的异常信号（如ELA异常、风格突变、年份不匹配）
- **信息 (Info)** — 供参考的元数据和结构提示

## 快速开始

### 方式一：直接运行

```bash
pip install -r requirements.txt
python run.py
```

打开浏览器访问 `http://localhost:8000`

### 方式二：Docker

```bash
docker-compose up --build
```

打开浏览器访问 `http://localhost:8000`

## API 接口

### POST /api/analyze

接受以下参数（form-data）：

| 参数 | 类型 | 说明 |
|------|------|------|
| `file` | File | 上传 PDF/DOCX/TXT 文件 |
| `doi` | string | DOI 标识符，如 `10.1038/s41586-023-06600-9` |
| `arxiv_id` | string | arXiv ID，如 `2301.07041` |
| `url` | string | 论文 PDF 的直接下载链接 |

四个参数任选其一。

### 返回示例

```json
{
  "status": "success",
  "report": {
    "paper_title": "论文标题",
    "overall_risk": "medium",
    "total_confirmed": 2,
    "total_suspicious": 5,
    "total_info": 1,
    "module_results": [...]
  }
}
```

## 技术栈

- **后端**: FastAPI + Python 3.11
- **图片分析**: OpenCV、Pillow、scikit-image、NumPy
- **文本处理**: pdfplumber、python-docx、NLTK、scikit-learn
- **引用验证**: CrossRef API、Unpaywall API
- **前端**: 原生 HTML/CSS/JS（无框架依赖）

## 商业替代品对比

| 服务 | 价格（USD） | 覆盖范围 |
|------|-----------|---------|
| iThenticate | $100-125/篇 | 仅文本查重 |
| Turnitin | $3-7/学生/年 | 仅文本查重（机构） |
| Imagetwin | €10-29/次 | 仅图片检测 |
| Proofig | $99-610/年 | 仅图片检测 |
| **本项目** | **免费** | **文本+图片+引用+统计+元数据** |

## 开源许可

MIT License
