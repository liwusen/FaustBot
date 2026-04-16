from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import py7zr
import requests
from tqdm import tqdm


BACKEND_DIR = Path(__file__).resolve().parent
TTS_HUB_DIR = BACKEND_DIR / "tts-hub"
DOWNLOAD_DIR = TTS_HUB_DIR / ".downloads"

NVIDIA50_URL = "https://www.modelscope.cn/models/FlowerCry/gpt-sovits-7z-pacakges/resolve/master/GPT-SoVITS-v2pro-20250604-nvidia50.7z"
STANDARD_URL = "https://www.modelscope.cn/models/FlowerCry/gpt-sovits-7z-pacakges/resolve/master/GPT-SoVITS-v2pro-20250604.7z"


def ask_yes_no(prompt: str) -> bool:
    while True:
        answer = input(f"{prompt} [y/n]: ").strip().lower()
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("请输入 y 或 n。")


def choose_download() -> tuple[str, str]:
    is_nvidia50 = ask_yes_no("是否为 50 系列显卡？")
    if is_nvidia50:
        return NVIDIA50_URL, "GPT-SoVITS-v2pro-20250604-nvidia50.7z"
    return STANDARD_URL, "GPT-SoVITS-v2pro-20250604.7z"


def choose_download_by_variant(variant: str | None) -> tuple[str, str]:
    normalized = str(variant or "").strip().lower()
    if normalized == "nvidia50":
        return NVIDIA50_URL, "GPT-SoVITS-v2pro-20250604-nvidia50.7z"
    if normalized == "standard":
        return STANDARD_URL, "GPT-SoVITS-v2pro-20250604.7z"
    return choose_download()


def download_with_progress(url: str, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=600) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0) or 0)
        with archive_path.open("wb") as file_obj, tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=f"Downloading {archive_path.name}",
        ) as progress:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                file_obj.write(chunk)
                progress.update(len(chunk))


def extract_with_progress(archive_path: Path, destination_dir: Path) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(archive_path, mode="r") as archive:
        names = archive.getnames()
        with tqdm(total=len(names), unit="file", desc=f"Extracting {archive_path.name}") as progress:
            for name in names:
                archive.extract(targets=[name], path=destination_dir)
                progress.update(1)


def normalize_tts_layout() -> None:
    nested_50 = TTS_HUB_DIR / "GPT-SoVITS-v2pro-20250604-nvidia50" / "GPT-SoVITS-v2pro-20250604-nvidia50"
    nested_std = TTS_HUB_DIR / "GPT-SoVITS-v2pro-20250604" / "GPT-SoVITS-v2pro-20250604"
    for nested in (nested_50, nested_std):
        if not nested.exists():
            continue
        for item in nested.iterdir():
            target = nested.parent / item.name
            if target.exists():
                continue
            shutil.move(str(item), str(target))


def main() -> int:
    parser = argparse.ArgumentParser(description="下载并解压本地 TTS 包")
    parser.add_argument("--gpu-variant", choices=["nvidia50", "standard"], default=None)
    args = parser.parse_args()

    try:
        url, filename = choose_download_by_variant(args.gpu_variant)
        archive_path = DOWNLOAD_DIR / filename
        print(f"下载地址: {url}")
        download_with_progress(url, archive_path)
        extract_with_progress(archive_path, TTS_HUB_DIR)
        normalize_tts_layout()
        print("TTS 下载并解压完成。")
        return 0
    except KeyboardInterrupt:
        print("用户取消。")
        return 1
    except Exception as exc:
        print(f"download_tts 失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())