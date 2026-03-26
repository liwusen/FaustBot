(() => {
  const API_BASE = 'http://127.0.0.1:13900';
  const PUBLIC_PROVIDER_KEYS = [
    'GUI_OPERATOR_LLM_MODEL',
    'GUI_OPERATOR_LLM_BASE',
    'SECURITY_VERIFIER_API_ENDPOINT',
    'SECURITY_VERIFIER_LLM_MODEL',
    'SECURITY_SYS_ENABLED',
    'RAG_ENABLED',
    'MC_OPERATOR_URL',
    'MC_EVENT_TRIGGER_ENABLED',
  ];
  const PRIVATE_PROVIDER_KEYS = [
    'DEEPSEEK_API_KEY',
    'SEARCH_API_KEY',
    'GUI_OPERATOR_LLM_KEY',
    'SECURITY_VERIFIER_LLM_KEY',
    'RAG_OPENAI_API_KEY',
  ];
  const LIVE2D_KEYS = [
    'LIVE2D_MODEL_PATH',
    'LIVE2D_MODEL_SCALE',
    'LIVE2D_MODEL_X',
    'LIVE2D_MODEL_Y',
    'FRONTEND_CLICK_THROUGH',
    'FRONTEND_DEFAULT_TTS_LANG',
  ];

  const state = {
    configView: null,
    runtimeSummary: null,
    selectedAgent: null,
    selectedFile: 'AGENT.md',
    agentDetail: null,
    services: [],
    selectedService: null,
  };

  const navItems = Array.from(document.querySelectorAll('.nav-item'));
  const panels = Array.from(document.querySelectorAll('.panel'));
  const pageTitle = document.getElementById('pageTitle');
  const pageSubtitle = document.getElementById('pageSubtitle');
  const feedbackBox = document.getElementById('feedbackBox');
  const toastHost = document.getElementById('toastHost');
  const publicConfigForm = document.getElementById('publicConfigForm');
  const privateConfigForm = document.getElementById('privateConfigForm');
  const live2dConfigForm = document.getElementById('live2dConfigForm');
  const runtimeSummaryEl = document.getElementById('runtimeSummary');
  const currentAgentStat = document.getElementById('currentAgentStat');
  const currentModelStat = document.getElementById('currentModelStat');
  const modelListEl = document.getElementById('modelList');
  const agentListEl = document.getElementById('agentList');
  const agentFilesTabs = document.getElementById('agentFilesTabs');
  const agentFileEditor = document.getElementById('agentFileEditor');
  const agentEditorTitle = document.getElementById('agentEditorTitle');
  const agentEditorSubtitle = document.getElementById('agentEditorSubtitle');
  const saveAgentFilesBtn = document.getElementById('saveAgentFilesBtn');
  const switchAgentBtn = document.getElementById('switchAgentBtn');
  const deleteAgentBtn = document.getElementById('deleteAgentBtn');
  const createAgentBtn = document.getElementById('createAgentBtn');
  const createAgentDialog = document.getElementById('createAgentDialog');
  const createAgentForm = document.getElementById('createAgentForm');
  const newAgentName = document.getElementById('newAgentName');
  const newAgentTemplate = document.getElementById('newAgentTemplate');
  const cancelCreateAgentBtn = document.getElementById('cancelCreateAgentBtn');
  const refreshAllBtn = document.getElementById('refreshAllBtn');
  const saveAllBtn = document.getElementById('saveAllBtn');
  const reloadAgentBtn = document.getElementById('reloadAgentBtn');
  const reloadAllBtn = document.getElementById('reloadAllBtn');
  const serviceListEl = document.getElementById('serviceList');
  const serviceLogView = document.getElementById('serviceLogView');

  function setFeedback(message, type = 'info') {
    feedbackBox.textContent = message;
    feedbackBox.dataset.type = type;
  }

  function showToast(title, message = '', type = 'info', duration = 2800) {
    if (!toastHost) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
      <span class="toast-title">${title}</span>
      <div class="toast-message">${message || ''}</div>
    `;
    toastHost.appendChild(toast);
    window.setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(-6px)';
      window.setTimeout(() => toast.remove(), 180);
    }, duration);
  }

  function handleRuntimeReloadCallback(payload) {
    const callback = payload?.callback;
    if (!callback || callback.type !== 'runtime_reloaded') return;
    const scopeTextMap = {
      config: '配置重载',
      agent: 'Agent Runtime 重建',
      all: '完整运行时重载',
      agent_switch: 'Agent 切换并重载',
    };
    const scopeText = scopeTextMap[callback.scope] || '运行时重载';
    const detail = `当前 Agent：${callback.agent_name || '-'}${callback.reset_dialog ? '；已重置对话上下文' : ''}`;
    setFeedback(`${scopeText}完成`);
    showToast(scopeText + '完成', detail, 'success');
  }

  function handleServiceActionCallback(payload) {
    const callback = payload?.callback;
    if (!callback || callback.type !== 'service_action') return;
    const actionMap = {
      start: '启动',
      stop: '停止',
      restart: '重启',
    };
    const actionText = actionMap[callback.action] || callback.action || '操作';
    showToast(`服务${actionText}完成`, callback.service_key || '-', 'success');
  }

  async function requestJson(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.error) {
      throw new Error(data.error || `请求失败: ${response.status}`);
    }
    return data;
  }

  function setActiveTab(tab) {
    navItems.forEach((btn) => btn.classList.toggle('active', btn.dataset.tab === tab));
    panels.forEach((panel) => panel.classList.toggle('active', panel.dataset.panel === tab));
    const active = navItems.find((btn) => btn.dataset.tab === tab);
    pageTitle.textContent = active ? active.textContent : 'Faust 配置中心';
    const subtitleMap = {
      overview: '查看当前运行状态与关键配置',
      providers: '维护 AI Provider 与后端配置项',
      agent: '管理 Agent 目录并编辑核心 Prompt 文件',
      live2d: '配置默认 Live2D 模型与展示参数',
      runtime: '执行重载与运行控制',
    };
    pageSubtitle.textContent = subtitleMap[tab] || '';
  }

  function createField(key, value) {
    const wrapper = document.createElement('div');
    wrapper.className = 'field';
    const label = document.createElement('label');
    label.textContent = key;
    const isBool = typeof value === 'boolean';
    const isLong = typeof value === 'string' && value.length > 80;
    let input;
    if (isBool) {
      input = document.createElement('select');
      input.innerHTML = '<option value="true">true</option><option value="false">false</option>';
      input.value = String(value);
    } else if (isLong) {
      input = document.createElement('textarea');
      input.rows = 4;
      input.value = value ?? '';
    } else {
      input = document.createElement('input');
      input.value = value ?? '';
      if (typeof value === 'number') input.type = 'number';
      if (/KEY|TOKEN|SECRET|PASSWORD/i.test(key)) input.type = 'password';
      if (key === 'RAG_OPENAI_API_KEY' && !value) input.placeholder = '留空表示不修改';
    }
    input.dataset.key = key;
    input.dataset.originalType = typeof value;
    wrapper.append(label, input);
    return wrapper;
  }

  function collectFormValues(container) {
    const values = {};
    container.querySelectorAll('[data-key]').forEach((el) => {
      const key = el.dataset.key;
      const originalType = el.dataset.originalType;
      let value = el.value;
      if (originalType === 'boolean') value = value === 'true';
      else if (originalType === 'number') value = value === '' ? null : Number(value);
      values[key] = value;
    });
    return values;
  }

  function renderConfigForms() {
    const publicCfg = state.configView?.public || {};
    const privateCfg = state.configView?.private || {};
    publicConfigForm.innerHTML = '';
    privateConfigForm.innerHTML = '';
    live2dConfigForm.innerHTML = '';

    PUBLIC_PROVIDER_KEYS.forEach((key) => publicConfigForm.appendChild(createField(key, publicCfg[key])));
    PRIVATE_PROVIDER_KEYS.forEach((key) => privateConfigForm.appendChild(createField(key, privateCfg[key])));
    LIVE2D_KEYS.forEach((key) => live2dConfigForm.appendChild(createField(key, publicCfg[key])));
  }

  function renderOverview() {
    currentAgentStat.textContent = state.runtimeSummary?.current_agent || '-';
    currentModelStat.textContent = state.runtimeSummary?.public_config?.LIVE2D_MODEL_PATH || '-';
    runtimeSummaryEl.textContent = JSON.stringify(state.runtimeSummary || {}, null, 2);
  }

  function renderModelList() {
    modelListEl.innerHTML = '';
    const models = state.runtimeSummary?.available_models || [];
    if (!models.length) {
      modelListEl.innerHTML = '<div class="muted">未发现可用 Live2D 模型</div>';
      return;
    }
    for (const model of models) {
      const item = document.createElement('button');
      item.className = 'model-item';
      item.textContent = `${model.label}：${model.path}`;
      item.addEventListener('click', () => {
        const input = live2dConfigForm.querySelector('[data-key="LIVE2D_MODEL_PATH"]');
        if (input) input.value = model.path;
      });
      modelListEl.appendChild(item);
    }
  }

  function renderAgentList() {
    agentListEl.innerHTML = '';
    const agents = state.runtimeSummary?.agents || [];
    newAgentTemplate.innerHTML = '<option value="">不复制模板</option>';
    agents.forEach((agent) => {
      const option = document.createElement('option');
      option.value = agent.name;
      option.textContent = agent.name;
      newAgentTemplate.appendChild(option);

      const item = document.createElement('div');
      item.className = 'agent-item';
      if (state.selectedAgent === agent.name) item.classList.add('active');
      item.innerHTML = `
        <strong>${agent.name}${agent.is_current ? '（当前）' : ''}</strong>
        <div class="agent-meta">${agent.can_delete ? '可删除' : '受保护'} · ${Object.keys(agent.core_files || {}).length} 个核心文件</div>
      `;
      item.addEventListener('click', () => selectAgent(agent.name));
      agentListEl.appendChild(item);
    });
  }

  function renderAgentEditor() {
    const files = state.agentDetail?.files || {};
    agentFilesTabs.innerHTML = '';
    ['AGENT.md', 'ROLE.md', 'COREMEMORY.md', 'TASK.md'].forEach((name) => {
      const btn = document.createElement('button');
      btn.className = `subtab ${state.selectedFile === name ? 'active' : ''}`;
      btn.textContent = name;
      btn.disabled = !state.selectedAgent;
      btn.addEventListener('click', () => {
        persistCurrentEditor();
        state.selectedFile = name;
        renderAgentEditor();
      });
      agentFilesTabs.appendChild(btn);
    });

    if (!state.selectedAgent) {
      agentEditorTitle.textContent = 'Agent 文件';
      agentEditorSubtitle.textContent = '请选择一个 Agent';
      agentFileEditor.value = '';
      agentFileEditor.disabled = true;
      saveAgentFilesBtn.disabled = true;
      switchAgentBtn.disabled = true;
      deleteAgentBtn.disabled = true;
      return;
    }

    const agentInfo = (state.runtimeSummary?.agents || []).find((item) => item.name === state.selectedAgent);
    agentEditorTitle.textContent = `${state.selectedAgent} · ${state.selectedFile}`;
    agentEditorSubtitle.textContent = agentInfo?.is_current ? '当前正在使用的 Agent' : '可编辑核心 Prompt 文件';
    agentFileEditor.disabled = false;
    agentFileEditor.value = files[state.selectedFile] ?? '';
    saveAgentFilesBtn.disabled = false;
    switchAgentBtn.disabled = !!agentInfo?.is_current;
    deleteAgentBtn.disabled = !agentInfo?.can_delete;
  }

  function persistCurrentEditor() {
    if (!state.agentDetail?.files || !state.selectedFile) return;
    state.agentDetail.files[state.selectedFile] = agentFileEditor.value;
  }

  function renderServices() {
    if (!serviceListEl) return;
    serviceListEl.innerHTML = '';
    const items = state.services || [];
    if (!items.length) {
      serviceListEl.innerHTML = '<div class="muted">暂无服务信息</div>';
      return;
    }
    items.forEach((service) => {
      const item = document.createElement('div');
      item.className = 'model-item';
      item.innerHTML = `
        <strong>${service.name}</strong>
        <div class="agent-meta">${service.description || ''} · 端口 ${service.port} · ${service.is_running ? '运行中' : '未运行'}</div>
      `;

      const actions = document.createElement('div');
      actions.className = 'button-stack';

      const logBtn = document.createElement('button');
      logBtn.className = 'ghost-btn';
      logBtn.textContent = '查看日志';
      logBtn.addEventListener('click', () => selectService(service.key));

      const startBtn = document.createElement('button');
      startBtn.className = 'ghost-btn';
      startBtn.textContent = '启动';
      startBtn.disabled = !!service.is_running;
      startBtn.addEventListener('click', () => runServiceAction(service.key, 'start'));

      const stopBtn = document.createElement('button');
      stopBtn.className = 'ghost-btn';
      stopBtn.textContent = '停止';
      stopBtn.disabled = !service.is_running;
      stopBtn.addEventListener('click', () => runServiceAction(service.key, 'stop'));

      const restartBtn = document.createElement('button');
      restartBtn.className = 'primary-btn';
      restartBtn.textContent = '重启';
      restartBtn.disabled = !service.is_running;
      restartBtn.addEventListener('click', () => runServiceAction(service.key, 'restart'));

      actions.append(logBtn, startBtn, stopBtn, restartBtn);
      item.appendChild(actions);
      serviceListEl.appendChild(item);
    });
  }

  async function loadConfigView() {
    state.configView = await requestJson('/faust/admin/config');
    renderConfigForms();
  }

  async function loadRuntimeSummary() {
    const data = await requestJson('/faust/admin/runtime');
    state.runtimeSummary = data.runtime;
    renderOverview();
    renderModelList();
    renderAgentList();
    renderAgentEditor();
  }

  async function loadServices() {
    const data = await requestJson('/faust/admin/services');
    state.services = data.items || [];
    renderServices();
    if (state.selectedService) {
      await selectService(state.selectedService, false);
    }
  }

  async function refreshAll() {
    await Promise.all([loadConfigView(), loadRuntimeSummary(), loadServices()]);
    setFeedback('已刷新配置与运行状态');
  }

  async function selectAgent(agentName) {
    state.selectedAgent = agentName;
    const data = await requestJson(`/faust/admin/agents/${encodeURIComponent(agentName)}`);
    state.agentDetail = data.detail;
    state.selectedFile = 'AGENT.md';
    renderAgentList();
    renderAgentEditor();
  }

  async function selectService(serviceKey, withToast = true) {
    state.selectedService = serviceKey;
    const data = await requestJson(`/faust/admin/services/${encodeURIComponent(serviceKey)}?include_log=true`);
    const item = data.item || {};
    if (serviceLogView) {
      serviceLogView.textContent = item.log_tail || '暂无日志';
    }
    if (withToast) {
      showToast('服务日志已加载', item.name || serviceKey, 'info', 1800);
    }
  }

  async function runServiceAction(serviceKey, action) {
    const actionTextMap = { start: '启动', stop: '停止', restart: '重启' };
    showToast(`正在${actionTextMap[action] || action}服务`, serviceKey, 'info', 1200);
    const payload = await requestJson(`/faust/admin/services/${encodeURIComponent(serviceKey)}/${action}`, {
      method: 'POST',
    });
    await loadServices();
    await selectService(serviceKey, false);
    setFeedback(`服务${actionTextMap[action] || action}完成：${serviceKey}`);
    handleServiceActionCallback(payload);
  }

  async function saveConfig() {
    const publicValues = {
      ...collectFormValues(publicConfigForm),
      ...collectFormValues(live2dConfigForm),
    };
    const privateValues = collectFormValues(privateConfigForm);
    state.configView = await requestJson('/faust/admin/config', {
      method: 'POST',
      body: JSON.stringify({ public: publicValues, private: privateValues }),
    });
    renderConfigForms();
    setFeedback('配置已保存到后端文件');
    showToast('保存成功', '配置已经写入后端配置文件。', 'success');
  }

  async function saveAgentFiles() {
    if (!state.selectedAgent) return;
    persistCurrentEditor();
    const data = await requestJson(`/faust/admin/agents/${encodeURIComponent(state.selectedAgent)}/files`, {
      method: 'PUT',
      body: JSON.stringify({ files: state.agentDetail.files }),
    });
    state.agentDetail.files = data.files;
    renderAgentEditor();
    setFeedback(`已保存 ${state.selectedAgent} 的核心文件`);
    showToast('Agent 文件已保存', `${state.selectedAgent} 的核心 Prompt 已更新。`, 'success');
  }

  async function switchAgent() {
    if (!state.selectedAgent) return;
    const payload = await requestJson('/faust/admin/agents/switch', {
      method: 'POST',
      body: JSON.stringify({ agent_name: state.selectedAgent }),
    });
    await refreshAll();
    await selectAgent(state.selectedAgent);
    handleRuntimeReloadCallback(payload);
  }

  async function deleteAgent() {
    if (!state.selectedAgent) return;
    const ok = window.confirm(`确定删除 Agent「${state.selectedAgent}」吗？该操作会删除对应目录。`);
    if (!ok) return;
    await requestJson(`/faust/admin/agents/${encodeURIComponent(state.selectedAgent)}`, { method: 'DELETE' });
    const deleted = state.selectedAgent;
    state.selectedAgent = null;
    state.agentDetail = null;
    await refreshAll();
    setFeedback(`已删除 Agent：${deleted}`);
    showToast('Agent 已删除', deleted, 'success');
  }

  async function createAgent() {
    const agent_name = newAgentName.value.trim();
    const template_agent = newAgentTemplate.value || undefined;
    if (!agent_name) return;
    await requestJson('/faust/admin/agents', {
      method: 'POST',
      body: JSON.stringify({ agent_name, template_agent }),
    });
    createAgentDialog.close();
    createAgentForm.reset();
    await refreshAll();
    await selectAgent(agent_name);
    setFeedback(`已创建 Agent：${agent_name}`);
    showToast('Agent 已创建', agent_name, 'success');
  }

  async function reloadAgentRuntime() {
    const payload = await requestJson('/faust/admin/runtime/reload-agent', { method: 'POST' });
    await refreshAll();
    handleRuntimeReloadCallback(payload);
  }

  async function reloadAllRuntime() {
    const payload = await requestJson('/faust/admin/runtime/reload-all', { method: 'POST' });
    await refreshAll();
    handleRuntimeReloadCallback(payload);
  }

  navItems.forEach((btn) => btn.addEventListener('click', () => setActiveTab(btn.dataset.tab)));
  refreshAllBtn.addEventListener('click', () => refreshAll().then(() => showToast('刷新完成', '已同步当前配置与运行状态。', 'info')).catch((e) => { setFeedback(String(e), 'error'); showToast('操作失败', String(e), 'error', 4200); }));
  saveAllBtn.addEventListener('click', () => saveConfig().catch((e) => { setFeedback(String(e), 'error'); showToast('保存失败', String(e), 'error', 4200); }));
  saveAgentFilesBtn.addEventListener('click', () => saveAgentFiles().catch((e) => { setFeedback(String(e), 'error'); showToast('保存失败', String(e), 'error', 4200); }));
  switchAgentBtn.addEventListener('click', () => switchAgent().catch((e) => { setFeedback(String(e), 'error'); showToast('切换失败', String(e), 'error', 4200); }));
  deleteAgentBtn.addEventListener('click', () => deleteAgent().catch((e) => { setFeedback(String(e), 'error'); showToast('删除失败', String(e), 'error', 4200); }));
  reloadAgentBtn.addEventListener('click', () => reloadAgentRuntime().catch((e) => { setFeedback(String(e), 'error'); showToast('重建失败', String(e), 'error', 4200); }));
  reloadAllBtn.addEventListener('click', () => reloadAllRuntime().catch((e) => { setFeedback(String(e), 'error'); showToast('重载失败', String(e), 'error', 4200); }));
  createAgentBtn.addEventListener('click', () => createAgentDialog.showModal());
  cancelCreateAgentBtn.addEventListener('click', () => createAgentDialog.close());
  createAgentForm.addEventListener('submit', (e) => {
    e.preventDefault();
    createAgent().catch((err) => { setFeedback(String(err), 'error'); showToast('创建失败', String(err), 'error', 4200); });
  });

  refreshAll()
    .then(() => showToast('配置中心已就绪', '可以开始进行配置、Agent 管理与运行控制。', 'info', 2200))
    .catch((e) => {
      setFeedback(`初始化失败：${e.message || e}`, 'error');
      showToast('初始化失败', e.message || String(e), 'error', 4200);
    });
})();
