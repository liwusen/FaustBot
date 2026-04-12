from __future__ import annotations

import json
from typing import Any

import requests

import faust_backend.config_loader as conf


LOCAL_TTS_ENDPOINT = "http://127.0.0.1:5000/"
LOCAL_ASR_ENDPOINT = "http://127.0.0.1:1000/v1/upload_audio"


class SpeechRuntimeError(RuntimeError):
    pass


def _resolve_api_url(base_url: str, suffix: str) -> str:
    base = str(base_url or "").strip()
    if not base:
        raise SpeechRuntimeError("未配置 OpenAI 兼容 API Base URL")
    if base.endswith(suffix):
        return base
    return base.rstrip("/") + suffix


def _split_csv_values(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def _current_tts_mode() -> str:
    return str(getattr(conf, "TTS_MODE", "local") or "local").strip().lower()


def _current_asr_mode() -> str:
    return str(getattr(conf, "ASR_MODE", "local") or "local").strip().lower()


def should_start_local_tts() -> bool:
    return _current_tts_mode() == "local"


def should_start_local_asr() -> bool:
    return _current_asr_mode() == "local"


def frontend_speech_config() -> dict[str, Any]:
    return {
        "tts_mode": _current_tts_mode(),
        "asr_mode": _current_asr_mode(),
        "asr_detection_mode": "energy" if _current_asr_mode() == "openai" else "vad",
        "frontend_default_tts_lang": getattr(conf, "FRONTEND_DEFAULT_TTS_LANG", "zh"),
        "openai_asr_energy_threshold": float(getattr(conf, "OPENAI_ASR_ENERGY_THRESHOLD", 0.02) or 0.02),
        "openai_asr_silence_ms": int(getattr(conf, "OPENAI_ASR_SILENCE_MS", 700) or 700),
        "openai_asr_min_speech_ms": int(getattr(conf, "OPENAI_ASR_MIN_SPEECH_MS", 250) or 250),
        "openai_asr_preroll_ms": int(getattr(conf, "OPENAI_ASR_PREROLL_MS", 250) or 250),
    }


def synthesize_tts(text: str, lang: str | None = None) -> tuple[bytes, str]:
    payload_text = str(text or "").strip()
    if not payload_text:
        raise SpeechRuntimeError("TTS 文本不能为空")

    if should_start_local_tts():
        payload = {
            "text": payload_text,
            "text_language": str(lang or getattr(conf, "FRONTEND_DEFAULT_TTS_LANG", "zh") or "zh"),
        }
        resp = requests.post(LOCAL_TTS_ENDPOINT, json=payload, timeout=120)
        if not resp.ok:
            raise SpeechRuntimeError(f"本地 TTS 服务错误: {resp.status_code} {resp.text}")
        return resp.content, (resp.headers.get("content-type") or "audio/wav")

    api_key = str(getattr(conf, "OPENAI_TTS_API_KEY", "") or "").strip()
    if not api_key:
        raise SpeechRuntimeError("未配置 OPENAI_TTS_API_KEY")

    payload: dict[str, Any] = {
        "model": getattr(conf, "OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
        "voice": getattr(conf, "OPENAI_TTS_VOICE", "alloy"),
        "input": payload_text,
        "response_format": getattr(conf, "OPENAI_TTS_RESPONSE_FORMAT", "mp3"),
        "speed": float(getattr(conf, "OPENAI_TTS_SPEED", 1.0) or 1.0),
    }
    instructions = str(getattr(conf, "OPENAI_TTS_INSTRUCTIONS", "") or "").strip()
    if instructions:
        payload["instructions"] = instructions

    url = _resolve_api_url(getattr(conf, "OPENAI_TTS_BASE_URL", "https://api.openai.com/v1"), "/audio/speech")
    resp = requests.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
    )
    if not resp.ok:
        raise SpeechRuntimeError(f"OpenAI TTS 服务错误: {resp.status_code} {resp.text}")
    content_type = resp.headers.get("content-type") or f"audio/{payload['response_format']}"
    return resp.content, content_type


def transcribe_audio(filename: str, audio_bytes: bytes, content_type: str | None = None) -> dict[str, Any]:
    safe_name = str(filename or "audio.wav")
    mime_type = str(content_type or "audio/wav")
    if not audio_bytes:
        raise SpeechRuntimeError("ASR 音频不能为空")

    if should_start_local_asr():
        resp = requests.post(
            LOCAL_ASR_ENDPOINT,
            files={"file": (safe_name, audio_bytes, mime_type)},
            timeout=120,
        )
        if not resp.ok:
            raise SpeechRuntimeError(f"本地 ASR 服务错误: {resp.status_code} {resp.text}")
        try:
            data = resp.json()
        except Exception as exc:
            raise SpeechRuntimeError(f"本地 ASR 返回非 JSON: {resp.text}") from exc
        if isinstance(data, dict) and data.get("status") == "success":
            return data
        if isinstance(data, dict) and data.get("text"):
            return {"status": "success", "text": str(data.get("text"))}
        raise SpeechRuntimeError(str(data.get("message") or data.get("error") or data))

    api_key = str(getattr(conf, "OPENAI_ASR_API_KEY", "") or "").strip()
    if not api_key:
        raise SpeechRuntimeError("未配置 OPENAI_ASR_API_KEY")

    payload: dict[str, Any] = {
        "model": getattr(conf, "OPENAI_ASR_MODEL", "gpt-4o-transcribe"),
        "response_format": getattr(conf, "OPENAI_ASR_RESPONSE_FORMAT", "json"),
        "temperature": float(getattr(conf, "OPENAI_ASR_TEMPERATURE", 0.0) or 0.0),
    }
    language = str(getattr(conf, "OPENAI_ASR_LANGUAGE", "") or "").strip()
    prompt = str(getattr(conf, "OPENAI_ASR_PROMPT", "") or "").strip()
    if language:
        payload["language"] = language
    if prompt:
        payload["prompt"] = prompt
    request_data: list[tuple[str, Any]] = list(payload.items())
    timestamp_granularities = _split_csv_values(getattr(conf, "OPENAI_ASR_TIMESTAMP_GRANULARITIES", ""))
    if payload.get("response_format") == "verbose_json" and timestamp_granularities:
        for item in timestamp_granularities:
            request_data.append(("timestamp_granularities[]", item))

    url = _resolve_api_url(getattr(conf, "OPENAI_ASR_BASE_URL", "https://api.openai.com/v1"), "/audio/transcriptions")
    resp = requests.post(
        url,
        data=request_data,
        files={"file": (safe_name, audio_bytes, mime_type)},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
    )
    if not resp.ok:
        raise SpeechRuntimeError(f"OpenAI ASR 服务错误: {resp.status_code} {resp.text}")

    response_format = str(payload.get("response_format") or "json")
    text = ""
    raw_body: Any = None
    if response_format in {"json", "verbose_json"}:
        try:
            raw_body = resp.json()
        except Exception as exc:
            raise SpeechRuntimeError(f"OpenAI ASR 返回非 JSON: {resp.text}") from exc
        if isinstance(raw_body, dict):
            text = str(raw_body.get("text") or "")
        else:
            text = str(raw_body or "")
    else:
        raw_body = resp.text
        text = str(raw_body or "")

    return {
        "status": "success",
        "text": text.strip(),
        "raw": raw_body,
        "mode": "openai",
    }