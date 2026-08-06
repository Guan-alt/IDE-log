/**
 * 通用 JS 工具函数
 * 包含：fetch 封装、进度条更新、标签页切换、模态框显示/隐藏
 */

/* ===================== fetch 封装 ===================== */

// 页面代际计数器：切换页面时递增，旧页面的回调自动忽略
var _pageGen = 0;

// GET 请求封装
async function apiGet(url) {
    var gen = _pageGen;
    const res = await fetch(url);
    if (gen !== _pageGen) return new Promise(function(){}); // 页面已切换，挂起回调
    if (!res.ok) {
        try {
            const data = await res.clone().json();
            if (data.token_expired) { showTokenExpiredModal(); return new Promise(function(){}); }
        } catch(e) {}
        throw new Error('请求失败: ' + res.status);
    }
    return res.json();
}

// POST 请求封装
async function apiPost(url, data) {
    var gen = _pageGen;
    const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data || {})
    });
    if (gen !== _pageGen) return new Promise(function(){});
    if (!res.ok) {
        try {
            const d = await res.clone().json();
            if (d.token_expired) { showTokenExpiredModal(); return new Promise(function(){}); }
        } catch(e) {}
        throw new Error('请求失败: ' + res.status);
    }
    return res.json();
}

// DELETE 请求封装
async function apiDelete(url) {
    var gen = _pageGen;
    const res = await fetch(url, {
        method: 'DELETE'
    });
    if (gen !== _pageGen) return new Promise(function(){});
    if (!res.ok) {
        try {
            const d = await res.clone().json();
            if (d.token_expired) { showTokenExpiredModal(); return new Promise(function(){}); }
        } catch(e) {}
        throw new Error('请求失败: ' + res.status);
    }
    return res.json();
}

// PUT 请求封装
async function apiPut(url, data) {
    var gen = _pageGen;
    const res = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data || {})
    });
    if (gen !== _pageGen) return new Promise(function(){});
    if (!res.ok) {
        try {
            const d = await res.clone().json();
            if (d.token_expired) { showTokenExpiredModal(); return new Promise(function(){}); }
        } catch(e) {}
        throw new Error('请求失败: ' + res.status);
    }
    return res.json();
}

/* ===================== Token 过期弹窗 ===================== */
function showTokenExpiredModal() {
    // 避免重复弹出
    if (document.getElementById('tokenExpiredModal')) return;
    var overlay = document.createElement('div');
    overlay.id = 'tokenExpiredModal';
    overlay.className = 'modal-overlay';
    overlay.style.cssText = 'display:flex !important; z-index:10000;';
    overlay.innerHTML =
        '<div class="modal-content" style="max-width:420px; text-align:center;">' +
            '<div class="modal-header"><span class="modal-title">OTA Token 已过期</span></div>' +
            '<div class="modal-body">' +
                '<div style="font-size:48px; margin-bottom:16px;">&#9888;</div>' +
                '<p style="margin-bottom:8px; font-size:16px;">OTA 服务 Token 已失效，无法查询设备信息或发起 OTA 升级。</p>' +
                '<p style="color:#6b7280; font-size:13px;">请前往设置页面更新 Token 后继续操作。</p>' +
            '</div>' +
            '<div class="modal-footer" style="padding:12px 24px; border-top:1px solid #f1f5f9; display:flex; gap:8px; justify-content:center;">' +
                '<button class="btn btn-primary" onclick="navigateTo(\'/settings\'); closeTokenExpiredModal();" style="min-width:120px;">前往设置</button>' +
                '<button class="btn btn-secondary" onclick="closeTokenExpiredModal()" style="min-width:80px;">稍后</button>' +
            '</div>' +
        '</div>';
    document.body.appendChild(overlay);
}
function closeTokenExpiredModal() {
    var m = document.getElementById('tokenExpiredModal');
    if (m) m.remove();
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

/* ===================== 确认弹窗（局内） ===================== */

/**
 * 局内确认弹窗，替代浏览器原生 confirm()
 * @param {object} options - 配置 { title, message, confirmText, cancelText, danger }
 * @param {function} callback - 回调 function(ok:boolean)
 */
function showConfirmDialog(options, callback) {
    var opts = options || {};
    var overlay = document.createElement('div');
    overlay.className = 'confirm-overlay';
    overlay.style.cssText = 'position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.45); z-index:10000; display:flex; align-items:center; justify-content:center;';
    var box = document.createElement('div');
    box.style.cssText = 'background:#fff; border-radius:10px; width:400px; max-width:90%; padding:22px 24px; box-shadow:0 10px 40px rgba(0,0,0,0.25);';
    var title = document.createElement('h3');
    title.textContent = opts.title || '操作确认';
    title.style.cssText = 'margin:0 0 12px; font-size:15px; font-weight:600; color:#0f172a;';
    var msg = document.createElement('p');
    msg.textContent = opts.message || '';
    msg.style.cssText = 'margin:0 0 20px; font-size:13px; color:#475569; line-height:1.6; word-break:break-all;';
    var footer = document.createElement('div');
    footer.style.cssText = 'text-align:right;';
    var cancelBtn = document.createElement('button');
    cancelBtn.className = 'btn btn-secondary';
    cancelBtn.textContent = opts.cancelText || '取消';
    cancelBtn.style.marginRight = '8px';
    var okBtn = document.createElement('button');
    okBtn.className = 'btn ' + (opts.danger === false ? 'btn-primary' : 'btn-danger');
    okBtn.textContent = opts.confirmText || '确定';
    footer.appendChild(cancelBtn);
    footer.appendChild(okBtn);
    box.appendChild(title);
    box.appendChild(msg);
    box.appendChild(footer);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    function close(confirmed) {
        if (overlay.parentNode) {
            overlay.parentNode.removeChild(overlay);
        }
        if (typeof callback === 'function') {
            callback(confirmed);
        }
    }
    okBtn.addEventListener('click', function() { close(true); });
    cancelBtn.addEventListener('click', function() { close(false); });
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            close(false);
        }
    });
}

/* ===================== 页面缓存与导航 ===================== */

var pageCache = {};
var currentPagePath = null;
var pageCleanupFn = null;

function clearPageResources() {
    if (typeof pageCleanupFn === 'function') {
        try { pageCleanupFn(); } catch (e) {}
        pageCleanupFn = null;
    }
    // 递增代际计数器，旧页面的 pending fetch 回调将被自动忽略
    _pageGen++;
}

function loadScript(src) {
    return new Promise(function(resolve, reject) {
        var script = document.createElement('script');
        script.src = src;
        script.onload = resolve;
        script.onerror = function() { reject(new Error('加载失败: ' + src)); };
        document.head.appendChild(script);
    });
}

function isScriptLoaded(src) {
    var scripts = document.querySelectorAll('script[src]');
    for (var i = 0; i < scripts.length; i++) {
        if (scripts[i].getAttribute('src') === src) return true;
    }
    return false;
}

async function navigateTo(path, forceReload) {
    if (currentPagePath === path && !forceReload) return;
    // 导航离开前，保存当前页面的 DOM 快照（含已加载的数据）到缓存
    if (currentPagePath && pageCache[currentPagePath]) {
        pageCache[currentPagePath].scrollY = window.scrollY;
        pageCache[currentPagePath].contentHtml = document.querySelector('main.container').innerHTML;
    }
    clearPageResources();

    if (!forceReload && pageCache[path]) {
        restorePage(path);
        history.pushState({ path: path }, '', path);
        return;
    }

    try {
        var res = await fetch(path);
        var html = await res.text();
        var parser = new DOMParser();
        var doc = parser.parseFromString(html, 'text/html');

        var contentEl = doc.querySelector('main.container');
        var contentHtml = contentEl ? contentEl.innerHTML : '';

        var scriptCode = '';
        var scriptSrcs = [];
        doc.querySelectorAll('script').forEach(function(s) {
            if (s.hasAttribute('src')) {
                var src = s.getAttribute('src');
                if (src.indexOf('app.js') >= 0) return;
                scriptSrcs.push(src);
            } else {
                scriptCode += s.textContent + '\n';
            }
        });

        var styleCode = '';
        doc.querySelectorAll('style').forEach(function(s) {
            styleCode += s.textContent + '\n';
        });

        pageCache[path] = {
            contentHtml: contentHtml,
            scriptCode: scriptCode,
            styleCode: styleCode,
            scriptSrcs: scriptSrcs,
            scrollY: 0
        };

        renderPage(path);
        history.pushState({ path: path }, '', path);
    } catch (err) {
        showToast('页面加载失败: ' + err.message, 'error');
    }
}

function renderPage(path) {
    var cached = pageCache[path];
    if (!cached) return;
    clearPageResources();

    var container = document.querySelector('main.container');
    container.innerHTML = cached.contentHtml;

    // 样式
    var existingStyle = document.getElementById('page-dynamic-style');
    if (existingStyle) existingStyle.remove();
    if (cached.styleCode) {
        var style = document.createElement('style');
        style.id = 'page-dynamic-style';
        style.textContent = cached.styleCode;
        container.appendChild(style);
    }

    // 模态框绑定（每次渲染都执行）
    container.querySelectorAll('.modal').forEach(function(modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                modal.classList.remove('show');
            }
        });
    });

    // 导航激活 + 滚动位置
    updateNavActive(path);
    window.scrollTo(0, cached.scrollY || 0);
    currentPagePath = path;

    // 执行脚本（重新绑定事件监听器 + 后台刷新数据）
    var existingScript = document.getElementById('page-dynamic-script');
    if (existingScript) existingScript.remove();

    var srcPromises = [];
    if (cached.scriptSrcs && cached.scriptSrcs.length > 0) {
        cached.scriptSrcs.forEach(function(src) {
            if (!isScriptLoaded(src)) {
                srcPromises.push(loadScript(src));
            }
        });
    }

    Promise.all(srcPromises).then(function() {
        if (cached.scriptCode) {
            var script = document.createElement('script');
            script.id = 'page-dynamic-script';
            script.textContent = cached.scriptCode;
            container.appendChild(script);
        }
    }).catch(function(err) {
        showToast('脚本加载失败: ' + err.message, 'error');
    });
}

function restorePage(path) {
    var cached = pageCache[path];
    if (!cached) { navigateTo(path, true); return; }
    renderPage(path);
}

function refreshCurrentPage() {
    if (currentPagePath) {
        delete pageCache[currentPagePath];
        navigateTo(currentPagePath, true);
    }
}

function updateNavActive(path) {
    document.querySelectorAll('.nav-link').forEach(function(link) {
        var href = link.getAttribute('data-path');
        if (href === path || (href !== '/' && path.indexOf(href) === 0)) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
}

window.addEventListener('popstate', function(e) {
    var path = (e.state && e.state.path) || window.location.pathname;
    if (pageCache[path]) {
        restorePage(path);
    } else {
        navigateTo(path, true);
    }
});

/* ===================== 页面初始化 ===================== */

document.addEventListener('DOMContentLoaded', function() {
    currentPagePath = window.location.pathname;
    history.replaceState({ path: currentPagePath }, '', currentPagePath);
    updateNavActive(currentPagePath);

    document.querySelectorAll('.modal').forEach(function(modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                modal.classList.remove('show');
            }
        });
    });
});
