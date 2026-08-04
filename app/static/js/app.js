/**
 * 通用 JS 工具函数
 * 包含：fetch 封装、进度条更新、标签页切换、模态框显示/隐藏
 */

/* ===================== fetch 封装 ===================== */

// GET 请求封装
async function apiGet(url) {
    const res = await fetch(url);
    if (!res.ok) {
        throw new Error('请求失败: ' + res.status);
    }
    return res.json();
}

// POST 请求封装
async function apiPost(url, data) {
    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data || {})
    });
    if (!res.ok) {
        throw new Error('请求失败: ' + res.status);
    }
    return res.json();
}

// DELETE 请求封装
async function apiDelete(url) {
    const res = await fetch(url, {
        method: 'DELETE'
    });
    if (!res.ok) {
        throw new Error('请求失败: ' + res.status);
    }
    return res.json();
}

// PUT 请求封装
async function apiPut(url, data) {
    const res = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data || {})
    });
    if (!res.ok) {
        throw new Error('请求失败: ' + res.status);
    }
    return res.json();
}

/* ===================== 进度条更新 ===================== */

/**
 * 更新进度条
 * @param {string} barId - 进度条内部填充元素的 id
 * @param {number} percent - 进度百分比 (0-100)
 * @param {string} status - 状态：success / fail（可选）
 */
function updateProgress(barId, percent, status) {
    const bar = document.getElementById(barId);
    if (!bar) return;
    // 限制百分比范围
    const pct = Math.min(100, Math.max(0, percent));
    bar.style.width = pct + '%';
    // 更新文字
    const wrapper = bar.closest('.progress-wrapper');
    if (wrapper) {
        const text = wrapper.querySelector('.progress-text');
        if (text) {
            text.textContent = pct.toFixed(1) + '%';
        }
    }
    // 更新状态样式
    bar.classList.remove('success', 'fail');
    if (status) {
        bar.classList.add(status);
    }
}

/* ===================== 标签页切换 ===================== */

/**
 * 切换标签页
 * @param {string} tabGroup - 标签组名称（data-tab-group 属性值）
 * @param {string} tabId - 要显示的内容区域 id
 */
function switchTab(tabGroup, tabId) {
    const group = document.querySelector('[data-tab-group="' + tabGroup + '"]');
    if (!group) return;
    // 隐藏所有内容
    group.querySelectorAll('.tab-content').forEach(function(c) {
        c.classList.remove('active');
    });
    // 取消所有按钮激活
    group.querySelectorAll('.tab-btn').forEach(function(t) {
        t.classList.remove('active');
    });
    // 显示目标内容
    var target = document.getElementById(tabId);
    if (target) {
        target.classList.add('active');
    }
    // 激活目标按钮
    var btn = group.querySelector('.tab-btn[data-target="' + tabId + '"]');
    if (btn) {
        btn.classList.add('active');
    }
}

/* ===================== 模态框显示/隐藏 ===================== */

/**
 * 显示模态框
 * @param {string} modalId - 模态框元素 id
 */
function showModal(modalId) {
    var modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('show');
    }
}

/**
 * 隐藏模态框
 * @param {string} modalId - 模态框元素 id
 */
function hideModal(modalId) {
    var modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('show');
    }
}

/* ===================== 提示消息 ===================== */

/**
 * 显示提示消息
 * @param {string} message - 消息内容
 * @param {string} type - 类型：info / success / error
 */
function showToast(message, type) {
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + (type || 'info');
    toast.textContent = message;
    document.body.appendChild(toast);
    // 延迟显示动画
    setTimeout(function() {
        toast.classList.add('show');
    }, 10);
    // 3 秒后移除
    setTimeout(function() {
        toast.classList.remove('show');
        setTimeout(function() {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }, 3000);
}

/* ===================== 页面初始化 ===================== */

document.addEventListener('DOMContentLoaded', function() {
    // 根据当前路径设置导航栏激活状态
    var path = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(function(link) {
        var href = link.getAttribute('href');
        if (href === path || (href !== '/' && path.indexOf(href) === 0)) {
            link.classList.add('active');
        }
    });

    // 点击模态框背景区域关闭模态框
    document.querySelectorAll('.modal').forEach(function(modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                modal.classList.remove('show');
            }
        });
    });
});
