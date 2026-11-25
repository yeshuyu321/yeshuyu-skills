#!/usr/bin/env python3
"""Minimal Volcengine AUC URL transcription client.

Credentials are read from environment variables or the user's macOS Keychain.
The module never prints credential values and only supports third-party API
transcription; it does not contain a local-model fallback.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


DEFAULT_SERVICE_URL = "https://openspeech.bytedance.com/api/v1/auc"
DEFAULT_CLUSTER = "volc_auc_meeting"
DEFAULT_KEYCHAIN_SERVICE = "volc-asr"


def _keychain_get(service: str, account: str) -> str:
    if platform.system() != "Darwin":
        return ""
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                service,
                "-a",
                account,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def probe_duration(source: str | Path) -> float:
    """Measure the exact submitted media; never trust a title or guessed length."""
    import math
    try:
        run = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "json", str(source)], capture_output=True,
            text=True, timeout=90, check=True)
        duration = float(json.loads(run.stdout)["format"]["duration"])
    except Exception:
        raise RuntimeError("Cannot measure ASR input duration with ffprobe; no submission") from None
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("Invalid ASR input duration; no submission")
    return duration


def resolve_credentials() -> tuple[dict[str, str], dict[str, str]]:
    """Return credentials and non-secret source labels."""
    service = os.environ.get(
        "VOLC_ASR_KEYCHAIN_SERVICE", DEFAULT_KEYCHAIN_SERVICE
    ).strip()
    env_appid = os.environ.get("VOLC_ASR_APPID", "").strip()
    env_token = os.environ.get("VOLC_ASR_ACCESS_TOKEN", "").strip()
    appid = env_appid or _keychain_get(service, "appid")
    token = env_token or _keychain_get(service, "access_token")
    return (
        {"appid": appid, "token": token},
        {
            "appid": "environment:VOLC_ASR_APPID" if env_appid else "macOS Keychain",
            "token": (
                "environment:VOLC_ASR_ACCESS_TOKEN"
                if env_token
                else "macOS Keychain"
            ),
        },
    )


def resolve_v3_config() -> dict[str, str]:
    path = Path(os.environ.get("VOLC_ASR_CONFIG", "~/.config/shengjiang/volc-asr.json")).expanduser()
    config = json.loads(path.read_text()) if path.exists() else {}
    key = os.environ.get("VOLC_ASR_API_KEY", "").strip() or config.get("api_key", "")
    return {"api_key": key, "resource_id": config.get("resource_id", "volc.seedasr.auc"),
            "base_url": config.get("base_url", "https://openspeech.bytedance.com/api/v3/auc/bigmodel")}


def _v3_request(action: str, payload: dict, config: dict, request_id: str) -> tuple[str, dict, str]:
    headers = {"Content-Type": "application/json",
               "X-Api-Resource-Id": config["resource_id"], "X-Api-Request-Id": request_id,
               "X-Api-Sequence": "-1"}
    if config.get("api_key"):
        headers["x-api-key"] = config["api_key"]
    else:
        headers.update({"X-Api-App-Key": config["appid"], "X-Api-Access-Key": config["token"]})
    req = urllib.request.Request(config["base_url"].rstrip("/") + "/" + action,
                                 data=json.dumps(payload).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return (response.headers.get("X-Api-Status-Code", ""), json.load(response),
                    response.headers.get("X-Api-Message", ""))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        for field in ("api_key", "token", "secret_key"):
            if config.get(field):
                detail = detail.replace(config[field], "<redacted>")
        if exc.code in (400, 403, 429):
            try:
                body = json.loads(detail)
            except ValueError:
                body = None
            if isinstance(body, dict):
                return (exc.headers.get("X-Api-Status-Code", str(exc.code)), body,
                        exc.headers.get("X-Api-Message", detail))
        raise RuntimeError(f"Volc V3 HTTP {exc.code}: " + detail[:500]) from None


def _transcribe_v3(audio_url: str, audio_format: str, uid: str,
                   timeout_seconds: int, poll_interval: int, config: dict) -> tuple[dict, str]:
    request_id = str(uuid.uuid4())
    code, body, message = _v3_request("submit", {
        "user": {"uid": uid}, "audio": {"url": audio_url, "format": audio_format},
        "request": {"model_name": "bigmodel", "enable_itn": True,
                    "enable_punc": True, "enable_ddc": False, "show_utterances": True}
    }, config, request_id)
    if code != "20000000":
        raise RuntimeError(f"Volc V3 submit {code}: {message}")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        code, body, message = _v3_request("query", {}, config, request_id)
        if code == "20000000":
            result = body.get("result") or {}
            if not result.get("text"):
                raise RuntimeError("Volc V3 completed without transcript text")
            # Keep existing consumers compatible and retain the original response.
            return {"resp": result, "raw_v3": body, "request_id": request_id}, config["resource_id"]
        if code not in {"20000001", "20000002"}:
            raise RuntimeError(f"Volc V3 query {code}: {message}")
    raise TimeoutError(f"Volc V3 timeout: {request_id}")


def configuration_status() -> dict[str, Any]:
    import volc_pool
    if volc_pool.config_path().exists():
        return volc_pool.status()
    v3 = resolve_v3_config()
    if v3["api_key"]:
        return {"configured": True, "provider": "volcengine-seedasr-v3",
                "cluster": v3["resource_id"], "credential_sources": {"api_key": "private local config or VOLC_ASR_API_KEY"}}
    credentials, sources = resolve_credentials()
    return {
        "configured": bool(credentials["appid"] and credentials["token"]),
        "provider": "volcengine-auc-url",
        "cluster": os.environ.get("VOLC_ASR_CLUSTER", DEFAULT_CLUSTER),
        "credential_sources": sources,
    }


def _post_json(
    url: str,
    payload: dict[str, Any],
    token: str,
    *,
    timeout: int = 60,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer; {token}",
            "Content-Type": "application/json",
            "User-Agent": "Shengjiang-Research/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").replace(
            token, "<redacted>"
        )
        if exc.code in (400, 403, 429):
            try:
                denied = json.loads(detail)
            except ValueError:
                denied = None
            if isinstance(denied, dict) and isinstance(denied.get("resp"), dict):
                return denied
        raise RuntimeError(f"Volc ASR HTTP {exc.code}: {detail[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Volc ASR request failed: {exc.reason}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Volc ASR returned a non-JSON response: "
            + raw.decode("utf-8", errors="replace")[:500]
        ) from exc


def _submit(
    *,
    audio_url: str,
    audio_format: str,
    credentials: dict[str, str],
    cluster: str,
    uid: str,
    timeout: int,
) -> dict[str, Any]:
    service_url = os.environ.get("VOLC_ASR_SERVICE_URL", DEFAULT_SERVICE_URL).rstrip(
        "/"
    )
    payload = {
        "app": {
            "appid": credentials["appid"],
            "token": credentials["token"],
            "cluster": cluster,
        },
        "user": {"uid": uid},
        "audio": {"format": audio_format, "url": audio_url},
        "additions": {"use_itn": "True", "with_speaker_info": "False"},
    }
    return _post_json(
        f"{service_url}/submit",
        payload,
        credentials["token"],
        timeout=timeout,
    )


def _submit_with_quota_fallback(
    *,
    audio_url: str,
    audio_format: str,
    credentials: dict[str, str],
    cluster: str,
    uid: str,
    timeout: int,
) -> tuple[dict[str, Any], str]:
    def submit(target_cluster: str) -> dict[str, Any]:
        return _submit(
            audio_url=audio_url,
            audio_format=audio_format,
            credentials=credentials,
            cluster=target_cluster,
            uid=uid,
            timeout=timeout,
        )

    try:
        submitted = submit(cluster)
    except RuntimeError as exc:
        if "audio_duration_lifetime" not in str(exc) or not cluster.endswith(
            "_flash"
        ):
            raise
        fallback_cluster = cluster[: -len("_flash")]
        return submit(fallback_cluster), fallback_cluster

    response = submitted.get("resp") or {}
    response_text = json.dumps(response, ensure_ascii=False)
    if (
        str(response.get("code") or "") != "1000"
        and "audio_duration_lifetime" in response_text
        and cluster.endswith("_flash")
    ):
        fallback_cluster = cluster[: -len("_flash")]
        return submit(fallback_cluster), fallback_cluster
    return submitted, cluster


class ASRTaskFailed(RuntimeError):
    """The accepted remote task returned a terminal failure."""


def _wait(
    *,
    task_id: str,
    credentials: dict[str, str],
    cluster: str,
    timeout_seconds: int,
    poll_interval: int,
) -> dict[str, Any]:
    service_url = os.environ.get("VOLC_ASR_SERVICE_URL", DEFAULT_SERVICE_URL).rstrip(
        "/"
    )
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last = _post_json(
            f"{service_url}/query",
            {
                "appid": credentials["appid"],
                "token": credentials["token"],
                "cluster": cluster,
                "id": task_id,
            },
            credentials["token"],
            timeout=60,
        )
        response = last.get("resp") or {}
        code = str(response.get("code") or "")
        if code == "1000" and response.get("text"):
            return last
        if code not in {"1000", "2000", "2001"}:
            raise ASRTaskFailed(
                "Volc ASR task failed: "
                + json.dumps(last, ensure_ascii=False)[:1000]
            )
        time.sleep(poll_interval)
    raise TimeoutError(
        f"Volc ASR task timed out: {task_id}; last="
        + json.dumps(last, ensure_ascii=False)[:500]
    )


def transcribe_url(
    audio_url: str,
    *,
    audio_format: str,
    uid: str,
    timeout_seconds: int = 900,
    poll_interval: int = 5,
    duration_seconds: float | None = None,
    profile_id: str | None = None,
    input_key: str | None = None,
) -> tuple[dict[str, Any], str]:
    import volc_pool
    if volc_pool.config_path().exists():
        return volc_pool.transcribe(audio_url, audio_format=audio_format, uid=uid,
                                   duration_seconds=duration_seconds, profile_id=profile_id, input_key=input_key,
                                   timeout_seconds=timeout_seconds, poll_interval=poll_interval)
    v3 = resolve_v3_config()
    if v3["api_key"]:
        return _transcribe_v3(audio_url, audio_format, uid, timeout_seconds, poll_interval, v3)
    credentials, _ = resolve_credentials()
    if not credentials["appid"] or not credentials["token"]:
        raise RuntimeError(
            "Volc ASR credentials are not configured in environment variables "
            "or the user's macOS Keychain."
        )
    primary_cluster = os.environ.get("VOLC_ASR_CLUSTER", DEFAULT_CLUSTER)
    submitted, selected_cluster = _submit_with_quota_fallback(
        audio_url=audio_url,
        audio_format=audio_format,
        credentials=credentials,
        cluster=primary_cluster,
        uid=uid,
        timeout=60,
    )
    response = submitted.get("resp") or {}
    if str(response.get("code") or "") != "1000" or not response.get("id"):
        raise RuntimeError(
            "Volc ASR submission failed: "
            + json.dumps(submitted, ensure_ascii=False)[:1000]
        )
    result = _wait(
        task_id=str(response["id"]),
        credentials=credentials,
        cluster=selected_cluster,
        timeout_seconds=timeout_seconds,
        poll_interval=poll_interval,
    )
    return result, selected_cluster


def write_transcript_files(
    result: dict[str, Any],
    output_dir: Path,
    *,
    title: str,
    source: str,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    response = result.get("resp") or {}
    text = str(response.get("text") or "").strip()
    raw_path = output_dir / "transcript.raw.json"
    text_path = output_dir / "transcript.txt"
    markdown_path = output_dir / "transcript.md"
    raw_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    text_path.write_text(text + ("\n" if text else ""), encoding="utf-8")
    lines = [f"# {title or '视频逐字稿'}", "", f"来源：{source}", "", "## 全文", "", text]
    utterances = response.get("utterances") or []
    if utterances:
        lines.extend(["", "## 分句", ""])
        for item in utterances:
            start = int(item.get("start_time") or 0) / 1000
            end = int(item.get("end_time") or 0) / 1000
            sentence = str(item.get("text") or "").strip()
            lines.append(f"- [{start:.2f}-{end:.2f}] {sentence}")
    markdown_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {
        "raw": str(raw_path),
        "txt": str(text_path),
        "md": str(markdown_path),
    }
