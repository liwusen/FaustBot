const state = {
  indexUrl: new URL('./plugins.json', window.location.href).href,
  plugins: [],
  filtered: [],
};

const dom = {
  searchInput: document.getElementById('searchInput'),
  metaInfo: document.getElementById('metaInfo'),
  pluginGrid: document.getElementById('pluginGrid'),
  emptyState: document.getElementById('emptyState'),
  previewDialog: document.getElementById('previewDialog'),
  closePreview: document.getElementById('closePreview'),
  previewTitle: document.getElementById('previewTitle'),
  previewDesc: document.getElementById('previewDesc'),
  previewMeta: document.getElementById('previewMeta'),
  previewInstall: document.getElementById('previewInstall'),
  previewDownload: document.getElementById('previewDownload'),
  previewRepo: document.getElementById('previewRepo'),
};

function esc(str) {
  return String(str ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function makeInstallLink(plugin) {
  const u = new URL('faustbot://install_plugin');
  u.searchParams.set('id', plugin.id);
  u.searchParams.set('market', state.indexUrl);
  return u.toString();
}

function makeDownloadLink(plugin) {
  if (plugin.download_url) return plugin.download_url;
  if (plugin.release_url) return plugin.release_url;
  if (plugin.repo) return `https://github.com/${plugin.repo}/releases/latest`;
  return '#';
}

function renderCards(items) {
  dom.pluginGrid.innerHTML = items.map((p) => {
    const tags = (p.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join('');
    return `
      <article class="card">
        <h3>${esc(p.name || p.id)}</h3>
        <div class="desc">${esc(p.description || '暂无描述')}</div>
        <div class="tags">${tags}</div>
        <div class="meta-line">ID: ${esc(p.id)} · 版本: ${esc(p.version || 'latest')} · 作者: ${esc(p.author || 'unknown')}</div>
        <div class="actions">
          <a class="btn btn--primary" href="${esc(makeInstallLink(p))}">安装</a>
          <button class="btn" data-action="preview" data-id="${esc(p.id)}">预览</button>
          <a class="btn" href="${esc(makeDownloadLink(p))}" target="_blank" rel="noopener">下载</a>
        </div>
      </article>
    `;
  }).join('');

  dom.emptyState.classList.toggle('hidden', items.length > 0);
}

function applyFilter() {
  const q = dom.searchInput.value.trim().toLowerCase();
  if (!q) {
    state.filtered = state.plugins.slice();
  } else {
    state.filtered = state.plugins.filter((p) => {
      const hay = [p.id, p.name, p.description, ...(p.tags || [])]
        .map((x) => String(x || '').toLowerCase())
        .join(' ');
      return hay.includes(q);
    });
  }
  renderCards(state.filtered);
}

function openPreview(plugin) {
  dom.previewTitle.textContent = plugin.name || plugin.id;
  dom.previewDesc.textContent = plugin.description || '暂无描述';
  dom.previewMeta.innerHTML = `
    <div><strong>ID</strong>: ${esc(plugin.id)}</div>
    <div><strong>版本</strong>: ${esc(plugin.version || 'latest')}</div>
    <div><strong>作者</strong>: ${esc(plugin.author || 'unknown')}</div>
    <div><strong>仓库</strong>: ${esc(plugin.repo || '-')}</div>
  `;
  dom.previewInstall.href = makeInstallLink(plugin);
  dom.previewDownload.href = makeDownloadLink(plugin);
  dom.previewRepo.href = plugin.repo ? `https://github.com/${plugin.repo}` : '#';
  dom.previewDialog.showModal();
}

async function loadCatalog() {
  const res = await fetch(state.indexUrl, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(`加载 plugins.json 失败: HTTP ${res.status}`);
  }
  const payload = await res.json();
  state.plugins = Array.isArray(payload.plugins) ? payload.plugins : [];
  state.filtered = state.plugins.slice();
  dom.metaInfo.textContent = `插件数: ${state.plugins.length} · 更新于: ${payload.updated_at || 'unknown'} · 索引: ${state.indexUrl}`;
  renderCards(state.filtered);
}

function bindEvents() {
  dom.searchInput.addEventListener('input', applyFilter);

  dom.pluginGrid.addEventListener('click', (e) => {
    const el = e.target;
    if (!(el instanceof HTMLElement)) return;
    if (el.dataset.action === 'preview') {
      const id = el.dataset.id;
      const target = state.plugins.find((p) => p.id === id);
      if (target) openPreview(target);
    }
  });

  dom.closePreview.addEventListener('click', () => dom.previewDialog.close());
}

(async function main() {
  bindEvents();
  try {
    await loadCatalog();
  } catch (e) {
    dom.metaInfo.textContent = `加载失败: ${String(e)}`;
    dom.emptyState.classList.remove('hidden');
  }
})();
