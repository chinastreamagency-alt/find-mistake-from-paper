// Academic Integrity Checker - Frontend JS

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('analyzeForm');
    const fileInput = document.getElementById('fileInput');
    const dropZone = document.getElementById('dropZone');
    const fileName = document.getElementById('fileName');
    const submitBtn = document.getElementById('submitBtn');
    const loading = document.getElementById('loading');
    const errorMsg = document.getElementById('errorMsg');
    const report = document.getElementById('report');

    // Tab switching
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
        });
    });

    // File drop zone
    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            fileName.textContent = e.dataTransfer.files[0].name;
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) {
            fileName.textContent = fileInput.files[0].name;
        }
    });

    // Form submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Reset state
        errorMsg.classList.remove('active');
        report.classList.remove('active');
        loading.classList.add('active');
        submitBtn.disabled = true;

        const formData = new FormData();

        // Determine active tab
        const activeTab = document.querySelector('.tab.active').dataset.tab;

        if (activeTab === 'upload') {
            if (!fileInput.files.length) {
                showError('请选择一个文件');
                return;
            }
            formData.append('file', fileInput.files[0]);
        } else if (activeTab === 'doi') {
            const doi = document.getElementById('doiInput').value.trim();
            if (!doi) {
                showError('请输入 DOI');
                return;
            }
            formData.append('doi', doi);
        } else if (activeTab === 'arxiv') {
            const arxivId = document.getElementById('arxivInput').value.trim();
            if (!arxivId) {
                showError('请输入 arXiv ID');
                return;
            }
            formData.append('arxiv_id', arxivId);
        } else if (activeTab === 'url') {
            const url = document.getElementById('urlInput').value.trim();
            if (!url) {
                showError('请输入 URL');
                return;
            }
            formData.append('url', url);
        }

        try {
            const resp = await fetch('/api/analyze', {
                method: 'POST',
                body: formData,
            });

            const data = await resp.json();

            if (!resp.ok) {
                showError(data.detail || '分析请求失败');
                return;
            }

            if (data.status === 'partial') {
                showError(data.message);
                return;
            }

            renderReport(data.report);
        } catch (err) {
            showError(`网络请求失败: ${err.message}`);
        } finally {
            loading.classList.remove('active');
            submitBtn.disabled = false;
        }
    });

    function showError(msg) {
        errorMsg.textContent = msg;
        errorMsg.classList.add('active');
        loading.classList.remove('active');
        submitBtn.disabled = false;
    }

    function renderReport(data) {
        report.classList.add('active');

        // Title
        const title = data.paper_title || data.paper_source || '未知论文';
        document.getElementById('reportTitle').innerHTML = `
            ${escapeHtml(title)}
            <span class="risk-indicator risk-${data.overall_risk}">
                风险等级: ${riskLabel(data.overall_risk)}
            </span>
        `;

        // Stats
        const statsRow = document.getElementById('statsRow');
        statsRow.innerHTML = `
            <span class="stat-badge confirmed">确凿问题: ${data.total_confirmed}</span>
            <span class="stat-badge suspicious">可疑问题: ${data.total_suspicious}</span>
            <span class="stat-badge info">信息提示: ${data.total_info}</span>
        `;

        // Module results
        const moduleContainer = document.getElementById('moduleResults');
        moduleContainer.innerHTML = '';

        data.module_results.forEach((mod, idx) => {
            const card = document.createElement('div');
            card.className = 'module-card';

            const issueCount = mod.issues.length;
            const hasIssues = issueCount > 0;

            card.innerHTML = `
                <div class="module-header" onclick="toggleModule(${idx})">
                    <div>
                        <div class="module-name">${escapeHtml(mod.module_name)}</div>
                        <div class="module-summary">${escapeHtml(mod.summary)}</div>
                    </div>
                    <span class="module-toggle" id="toggle-${idx}">&#9660;</span>
                </div>
                <div class="module-body" id="module-body-${idx}">
                    ${mod.error ? `<div class="issue info"><div class="issue-desc">错误: ${escapeHtml(mod.error)}</div></div>` : ''}
                    ${hasIssues ? mod.issues.map(issue => renderIssue(issue)).join('') : '<div class="no-issues">&#10003; 未发现问题</div>'}
                </div>
            `;

            moduleContainer.appendChild(card);

            // Auto-expand modules with issues
            if (hasIssues) {
                toggleModule(idx);
            }
        });
    }

    function renderIssue(issue) {
        const sevClass = issue.severity;
        const sevLabel = {
            confirmed: '确凿',
            suspicious: '可疑',
            info: '信息',
        }[issue.severity] || issue.severity;

        return `
            <div class="issue ${sevClass}">
                <div class="issue-header">
                    <div class="issue-title">${escapeHtml(issue.title)}</div>
                    <span class="issue-severity ${sevClass}">${sevLabel} (${(issue.confidence * 100).toFixed(0)}%)</span>
                </div>
                <div class="issue-desc">${escapeHtml(issue.description)}</div>
                ${issue.location ? `<div class="issue-location">位置: ${escapeHtml(issue.location)}</div>` : ''}
                ${issue.evidence ? `<div class="issue-evidence">${escapeHtml(issue.evidence)}</div>` : ''}
                ${issue.suggestion ? `<div class="issue-suggestion">建议: ${escapeHtml(issue.suggestion)}</div>` : ''}
            </div>
        `;
    }

    function riskLabel(risk) {
        return {
            low: '低',
            medium: '中',
            high: '高',
            critical: '极高',
        }[risk] || risk;
    }

    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // Expose toggle globally
    window.toggleModule = function(idx) {
        const body = document.getElementById(`module-body-${idx}`);
        const toggle = document.getElementById(`toggle-${idx}`);
        body.classList.toggle('open');
        toggle.classList.toggle('open');
    };
});
