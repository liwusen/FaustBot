from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import requests

import faust_backend.config_loader as conf


DEFAULT_MARKET_INDEX_URL = "https://raw.githubusercontent.com/faustbot-dev/faust_plugin_market/main/plugins.json"
_SAFE_PLUGIN_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]{0,63}$")


class PluginMarketError(RuntimeError):
    pass


def resolve_market_index_url(override_url: str | None = None) -> str:
    if override_url and str(override_url).strip():
        return str(override_url).strip()
    cfg = getattr(conf, "config", {}) or {}
    return str(cfg.get("PLUGIN_MARKET_INDEX_URL") or DEFAULT_MARKET_INDEX_URL)


def _fetch_json(url: str, *, timeout: float = 20.0) -> dict[str, Any]:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise PluginMarketError(f"插件市场元数据格式错误: 顶层必须是对象, url={url}")
    return data


def fetch_catalog(index_url: str | None = None) -> dict[str, Any]:
    target = resolve_market_index_url(index_url)
    raw = _fetch_json(target)
    items = raw.get("plugins")
    if not isinstance(items, list):
        raise PluginMarketError("插件市场元数据格式错误: 缺少 plugins 列表")
    normalized: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        plugin_id = str(row.get("id") or "").strip()
        if not plugin_id:
            continue
        normalized.append(
            {
                "id": plugin_id,
                "name": str(row.get("name") or plugin_id),
                "description": str(row.get("description") or ""),
                "author": str(row.get("author") or ""),
                "version": str(row.get("version") or ""),
                "repo": str(row.get("repo") or ""),
                "release_url": str(row.get("release_url") or ""),
                "download_url": str(row.get("download_url") or ""),
                "asset_name": str(row.get("asset_name") or "plugin_pack.zip"),
                "homepage": str(row.get("homepage") or ""),
                "tags": list(row.get("tags") or []),
            }
        )
    return {
        "index_url": target,
        "updated_at": raw.get("updated_at"),
        "plugins": normalized,
    }


def _get_github_latest_release(repo: str, timeout: float = 20.0) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    resp = requests.get(url, timeout=timeout, headers={"Accept": "application/vnd.github+json"})
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict):
        raise PluginMarketError(f"GitHub releases/latest 返回异常: repo={repo}")
    return payload


def _resolve_download_url(plugin_entry: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    direct = str(plugin_entry.get("download_url") or "").strip()
    if direct:
        return direct, {"source": "download_url"}

    release_url = str(plugin_entry.get("release_url") or "").strip()
    if release_url:
        if release_url.endswith(".zip"):
            return release_url, {"source": "release_url"}

    repo = str(plugin_entry.get("repo") or "").strip()
    if not repo:
        raise PluginMarketError(f"插件 {plugin_entry.get('id')} 缺少可下载信息(download_url/repo)")

    release = _get_github_latest_release(repo)
    assets = release.get("assets") or []
    asset_name = str(plugin_entry.get("asset_name") or "plugin_pack.zip")
    selected = None
    for asset in assets:
        if str(asset.get("name")) == asset_name:
            selected = asset
            break
    if selected is None and assets:
        for asset in assets:
            name = str(asset.get("name") or "")
            if name.lower().endswith(".zip"):
                selected = asset
                break
    if selected is None:
        raise PluginMarketError(f"插件 {plugin_entry.get('id')} 在最新 release 中未找到 zip 资产")

    dl = str(selected.get("browser_download_url") or "").strip()
    if not dl:
        raise PluginMarketError(f"插件 {plugin_entry.get('id')} release 资产没有下载链接")
    return dl, {
        "source": "github_release_latest",
        "repo": repo,
        "release_tag": release.get("tag_name"),
        "asset_name": selected.get("name"),
    }


def _download_file(url: str, target_file: Path, timeout: float = 60.0) -> int:
    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        total = 0
        with target_file.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 128):
                if not chunk:
                    continue
                f.write(chunk)
                total += len(chunk)
        return total


def _find_plugin_root(extract_dir: Path, plugin_id: str) -> Path:
    candidates = [
        p.parent for p in extract_dir.rglob("plugin.json")
        if p.is_file() and "__MACOSX" not in p.parts
    ]

    if not candidates:
        children = [p for p in extract_dir.iterdir() if p.is_dir()]
        if len(children) == 1:
            return children[0]
        raise PluginMarketError("压缩包中未找到 plugin.json，无法判定插件目录")

    if len(candidates) == 1:
        return candidates[0]

    for c in candidates:
        if c.name == plugin_id:
            return c

    raise PluginMarketError("压缩包中存在多个 plugin.json，无法唯一识别插件目录")


def install_plugin_from_catalog(
    *,
    plugin_id: str,
    plugins_dir: Path,
    index_url: str | None = None,
) -> dict[str, Any]:
    plugin_id = str(plugin_id or "").strip()
    if not _SAFE_PLUGIN_ID.match(plugin_id):
        raise PluginMarketError(f"非法插件 ID: {plugin_id}")

    catalog = fetch_catalog(index_url=index_url)
    target_entry = None
    for item in catalog["plugins"]:
        if item.get("id") == plugin_id:
            target_entry = item
            break
    if not target_entry:
        raise PluginMarketError(f"插件市场中未找到插件: {plugin_id}")

    download_url, download_meta = _resolve_download_url(target_entry)

    plugins_dir = Path(plugins_dir)
    plugins_dir.mkdir(parents=True, exist_ok=True)
    target_dir = plugins_dir / plugin_id

    with tempfile.TemporaryDirectory(prefix=f"faust-plugin-{plugin_id}-") as td:
        tmp_dir = Path(td)
        zip_file = tmp_dir / "plugin_pack.zip"
        extract_dir = tmp_dir / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)

        size_bytes = _download_file(download_url, zip_file)
        try:
            with zipfile.ZipFile(zip_file, "r") as zf:
                zf.extractall(extract_dir)
        except zipfile.BadZipFile as exc:
            raise PluginMarketError("下载的插件包不是有效 zip 文件") from exc

        plugin_root = _find_plugin_root(extract_dir, plugin_id)
        manifest_file = plugin_root / "plugin.json"
        if not manifest_file.exists():
            raise PluginMarketError("插件包缺少 plugin.json")

        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest_id = str(manifest.get("id") or plugin_root.name)
        if manifest_id != plugin_id:
            raise PluginMarketError(
                f"插件包 ID 不匹配: 期望 {plugin_id}, 实际 {manifest_id}"
            )

        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(plugin_root, target_dir)

    return {
        "plugin_id": plugin_id,
        "install_dir": str(target_dir),
        "market": {
            "index_url": catalog.get("index_url"),
            "entry": target_entry,
        },
        "download": {
            "url": download_url,
            "size_bytes": size_bytes,
            **download_meta,
        },
    }
