// Academic Integrity Checker - Frontend JS

// ===== State =====
let currentUser = null;
let authToken = localStorage.getItem('token');

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initDropZone();
    initAnalyzeForm();
    initAuthForms();
    checkUrlParams();

    // Restore session
    if (authToken) {
        fetchCurrentUser();
    }
});

// ===== Section Switching =====
window.showSection = function(name) {
    document.getElementById('sectionHome').style.display = name === 'home' ? '' : 'none';
    document.getElementById('sectionPricing').style.display = name === 'pricing' ? '' : 'none';
    document.getElementById('sectionDashboard').style.display = name === 'dashboard' ? '' : 'none';

    if (name === 'dashboard' && currentUser) {
        loadDashboard();
    }
};

// ===== Tabs =====
function initTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
        });
    });
}

// ===== Drop Zone =====
function initDropZone() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const fileName = document.getElementById('fileName');

    if (!dropZone) return;

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
}

// ===== Analyze Form =====
function initAnalyzeForm() {
    const form = document.getElementById('analyzeForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        if (!authToken) {
            showAuthModal('login');
            return;
        }

        const fileInput = document.getElementById('fileInput');
        const submitBtn = document.getElementById('submitBtn');
        const loading = document.getElementById('loading');
        const errorMsg = document.getElementById('errorMsg');
        const report = document.getElementById('report');

        errorMsg.classList.remove('active');
        report.classList.remove('active');
        loading.classList.add('active');
        submitBtn.disabled = true;

        const formData = new FormData();
        const activeTab = document.querySelector('.tab.active').dataset.tab;

        if (activeTab === 'upload') {
            if (!fileInput.files.length) {
                showError('请选择一个文件');
                return;
            }
            formData.append('file', fileInput.files[0]);
        } else if (activeTab === 'doi') {
            const doi = document.getElementById('doiInput').value.trim();
            if (!doi) { showError('请输入 DOI'); return; }
            formData.append('doi', doi);
        } else if (activeTab === 'arxiv') {
            const arxivId = document.getElementById('arxivInput').value.trim();
            if (!arxivId) { showError('请输入 arXiv ID'); return; }
            formData.append('arxiv_id', arxivId);
        } else if (activeTab === 'url') {
            const url = document.getElementById('urlInput').value.trim();
            if (!url) { showError('请输入 URL'); return; }
            formData.append('url', url);
        }

        try {
            const resp = await fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${authToken}` },
                body: formData,
            });

            const data = await resp.json();

            if (resp.status === 401) {
                showAuthModal('login');
                showError('请先登录');
                return;
            }

            if (resp.status === 403) {
                showError('分析次数已用完，请购买套餐');
                showSection('pricing');
                return;
            }

            if (!resp.ok) {
                showError(data.detail || '分析请求失败');
                return;
            }

            if (data.status === 'partial') {
                showError(data.message);
                return;
            }

            renderReport(data.report);

            // Update credits display
            if (data.remaining_credits !== undefined && currentUser) {
                currentUser.credits = data.remaining_credits;
                updateNavUI();
            }
        } catch (err) {
            showError(`网络请求失败: ${err.message}`);
        } finally {
            loading.classList.remove('active');
            submitBtn.disabled = false;
        }
    });
}

function showError(msg) {
    const errorMsg = document.getElementById('errorMsg');
    const loading = document.getElementById('loading');
    const submitBtn = document.getElementById('submitBtn');
    errorMsg.textContent = msg;
    errorMsg.classList.add('active');
    loading.classList.remove('active');
    submitBtn.disabled = false;
}

// ===== Report Rendering =====
function renderReport(data) {
    const report = document.getElementById('report');
    report.classList.add('active');

    const title = data.paper_title || data.paper_source || '未知论文';
    document.getElementById('reportTitle').innerHTML = `
        ${escapeHtml(title)}
        <span class="risk-indicator risk-${data.overall_risk}">
            风险等级: ${riskLabel(data.overall_risk)}
        </span>
    `;

    document.getElementById('statsRow').innerHTML = `
        <span class="stat-badge confirmed">确凿问题: ${data.total_confirmed}</span>
        <span class="stat-badge suspicious">可疑问题: ${data.total_suspicious}</span>
        <span class="stat-badge info">信息提示: ${data.total_info}</span>
    `;

    const moduleContainer = document.getElementById('moduleResults');
    moduleContainer.innerHTML = '';

    data.module_results.forEach((mod, idx) => {
        const card = document.createElement('div');
        card.className = 'module-card';
        const hasIssues = mod.issues.length > 0;

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
        if (hasIssues) toggleModule(idx);
    });
}

function renderIssue(issue) {
    const sevClass = issue.severity;
    const sevLabel = { confirmed: '确凿', suspicious: '可疑', info: '信息' }[issue.severity] || issue.severity;

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
    return { low: '低', medium: '中', high: '高', critical: '极高' }[risk] || risk;
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

window.toggleModule = function(idx) {
    const body = document.getElementById(`module-body-${idx}`);
    const toggle = document.getElementById(`toggle-${idx}`);
    if (body) body.classList.toggle('open');
    if (toggle) toggle.classList.toggle('open');
};

// ===== Auth =====
function initAuthForms() {
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');

    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('loginEmail').value.trim();
            const password = document.getElementById('loginPassword').value;
            const errorEl = document.getElementById('loginError');
            errorEl.textContent = '';

            try {
                const resp = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password }),
                });
                const data = await resp.json();
                if (!resp.ok) {
                    errorEl.textContent = data.detail || '登录失败';
                    return;
                }
                onAuthSuccess(data.token, data.user);
            } catch (err) {
                errorEl.textContent = '网络错误';
            }
        });
    }

    if (registerForm) {
        registerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('regEmail').value.trim();
            const password = document.getElementById('regPassword').value;
            const name = document.getElementById('regName').value.trim();
            const referral_code = document.getElementById('regReferral').value.trim();
            const errorEl = document.getElementById('regError');
            errorEl.textContent = '';

            try {
                const resp = await fetch('/api/auth/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password, name, referral_code: referral_code || null }),
                });
                const data = await resp.json();
                if (!resp.ok) {
                    errorEl.textContent = data.detail || '注册失败';
                    return;
                }
                onAuthSuccess(data.token, data.user);
            } catch (err) {
                errorEl.textContent = '网络错误';
            }
        });
    }
}

function onAuthSuccess(token, user) {
    authToken = token;
    currentUser = user;
    localStorage.setItem('token', token);
    closeAuthModal();
    updateNavUI();
}

async function fetchCurrentUser() {
    try {
        const resp = await fetch('/api/auth/me', {
            headers: { 'Authorization': `Bearer ${authToken}` },
        });
        if (resp.ok) {
            const data = await resp.json();
            currentUser = data.user;
            updateNavUI();
        } else {
            authToken = null;
            localStorage.removeItem('token');
        }
    } catch {
        // Network error, keep token for retry
    }
}

function updateNavUI() {
    const navGuest = document.getElementById('navGuest');
    const navUser = document.getElementById('navUser');
    const navCredits = document.getElementById('navCredits');

    if (currentUser) {
        navGuest.style.display = 'none';
        navUser.style.display = '';
        navCredits.style.display = '';
        navCredits.textContent = `${currentUser.credits} 次`;
    } else {
        navGuest.style.display = '';
        navUser.style.display = 'none';
        navCredits.style.display = 'none';
    }
}

window.logout = function() {
    authToken = null;
    currentUser = null;
    localStorage.removeItem('token');
    updateNavUI();
    showSection('home');
};

// ===== Auth Modal =====
window.showAuthModal = function(tab) {
    document.getElementById('authModal').classList.add('active');
    switchModalTab(tab || 'login');

    // Auto-fill referral code from URL
    const urlParams = new URLSearchParams(window.location.search);
    const ref = urlParams.get('ref');
    if (ref && tab === 'register') {
        document.getElementById('regReferral').value = ref;
    }
};

window.closeAuthModal = function() {
    document.getElementById('authModal').classList.remove('active');
    document.getElementById('loginError').textContent = '';
    document.getElementById('regError').textContent = '';
};

window.switchModalTab = function(tab) {
    document.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`.modal-tab[data-modal-tab="${tab}"]`).classList.add('active');
    document.getElementById('loginForm').style.display = tab === 'login' ? '' : 'none';
    document.getElementById('registerForm').style.display = tab === 'register' ? '' : 'none';
};

// ===== Payment =====
window.buyPlan = async function(planId) {
    if (!authToken) {
        showAuthModal('login');
        return;
    }

    try {
        const resp = await fetch('/api/payment/create-checkout', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`,
            },
            body: JSON.stringify({ plan_id: planId }),
        });

        const data = await resp.json();

        if (!resp.ok) {
            alert(data.detail || '创建支付失败');
            return;
        }

        if (data.checkout_url) {
            window.location.href = data.checkout_url;
        }
    } catch (err) {
        alert('网络错误: ' + err.message);
    }
};

// ===== Dashboard =====
async function loadDashboard() {
    if (!currentUser) return;

    document.getElementById('dashEmail').textContent = currentUser.email;
    document.getElementById('dashCredits').textContent = currentUser.credits;

    const baseUrl = window.location.origin;
    document.getElementById('referralLink').value = `${baseUrl}/?ref=${currentUser.referral_code}`;
    document.getElementById('referralCodeDisplay').textContent = currentUser.referral_code;

    // Load referral stats
    try {
        const resp = await fetch('/api/referral/stats', {
            headers: { 'Authorization': `Bearer ${authToken}` },
        });
        if (resp.ok) {
            const data = await resp.json();
            document.getElementById('statReferred').textContent = data.total_referred;
            document.getElementById('statCommission').textContent = `$${(data.total_commission / 100).toFixed(2)}`;
            document.getElementById('statPending').textContent = `$${(data.pending_commission / 100).toFixed(2)}`;
        }
    } catch {
        // Silently fail
    }
}

window.copyReferralLink = function() {
    const input = document.getElementById('referralLink');
    input.select();
    navigator.clipboard.writeText(input.value).then(() => {
        const btn = input.nextElementSibling;
        const orig = btn.textContent;
        btn.textContent = '已复制';
        setTimeout(() => { btn.textContent = orig; }, 1500);
    });
};

// ===== URL Params =====
function checkUrlParams() {
    const params = new URLSearchParams(window.location.search);

    // Handle referral code from URL
    const ref = params.get('ref');
    if (ref && !authToken) {
        showAuthModal('register');
    }

    // Handle payment callback
    const payment = params.get('payment');
    if (payment === 'success') {
        if (authToken) {
            fetchCurrentUser();
        }
        window.history.replaceState({}, '', '/');
    } else if (payment === 'cancel') {
        window.history.replaceState({}, '', '/');
    }
}
