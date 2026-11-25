"""One-shot Seed ASR V3 WebSocket file client, with no retries or credential IO.

Protocol source: official unidirectional-streaming-automatic-speech-recognition-
websocket documentation and its sauc_python.zip/protocol.py (checked 2026-09-20).
Legacy V2: official Streamingautomaticspeechrecognition documentation.
Requires aiohttp and ffmpeg; V2 needs an explicitly configured cluster.
"""
from __future__ import annotations

import asyncio
import gzip
import io
import json
import struct
import subprocess
import uuid
import wave
from pathlib import Path

URL = 'wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream'
RESOURCE = 'volc.seedasr.sauc.duration'
QUOTA_MARKERS = ('audio_duration_lifetime', 'audio_duration_month', 'audio_duration_total')


def _quota_marker(value):
    text = str(value).lower()
    return next((marker for marker in QUOTA_MARKERS if marker in text), '')


class StreamError(RuntimeError):
    """Never includes remote text, credentials or request URLs."""
    def __init__(self, message, *, audio_sent=False, code=None, quota_marker=""):
        self.quota_marker = quota_marker if quota_marker in QUOTA_MARKERS else ""
        self.quota_denied = bool(self.quota_marker)
        self.audio_sent = bool(audio_sent)
        self.uncertain_consumption = self.audio_sent
        self.code = code if isinstance(code, int) else None
        suffix = '; consumption uncertain; do not retry or switch quota' if audio_sent else '; no audio sent'
        super().__init__(message + (f' (code={self.code})' if self.code is not None else '')
                         + (f' {self.quota_marker}' if self.quota_marker else '') + suffix)


def _packet(kind, seq, data, last=False, legacy=False):
    compressed = gzip.compress(data)
    if legacy:
        return (bytes([0x11, (kind << 4) | (2 if last else 0), 0x11 if kind == 1 else 0x01, 0])
                + struct.pack('>I', len(compressed)) + compressed)
    # Official demo uses JSON serialization nibble also for audio-only frames.
    return (bytes([0x11, (kind << 4) | (3 if last else 1), 0x11, 0])
            + struct.pack('>iI', -seq if last else seq, len(compressed)) + compressed)


def _parse(data):
    if not isinstance(data, bytes) or len(data) < 8 or data[0] >> 4 != 1:
        raise ValueError('invalid protocol header')
    offset = (data[0] & 15) * 4
    kind, flags = data[1] >> 4, data[1] & 15
    serialization, compression = data[2] >> 4, data[2] & 15
    if offset < 4 or kind not in (9, 15) or compression not in (0, 1):
        raise ValueError('unsupported protocol frame')
    def integer(signed=False):
        nonlocal offset
        if offset + 4 > len(data):
            raise ValueError('truncated protocol frame')
        value = struct.unpack('>i' if signed else '>I', data[offset:offset + 4])[0]
        offset += 4
        return value
    if flags & 1:
        integer(True)
    if flags & 4:
        integer(True)
    code = integer(True) if kind == 15 else 0
    size = integer()
    if size != len(data) - offset:
        raise ValueError('invalid payload size')
    raw = data[offset:]
    if compression:
        raw = gzip.decompress(raw)
    body = json.loads(raw) if raw and serialization == 1 else {}
    if not isinstance(body, dict):
        raise ValueError('invalid response object')
    # Error messages are not retained, even when returned inside successful frames.
    if not code and isinstance(body.get('code'), int):
        code = body['code'] if body['code'] not in (0, 1000, 20000000) else 0
    return {'last': bool(flags & 2), 'code': code, 'body': body,
            'quota_marker': _quota_marker(body.get('message') or body.get('msg') or (raw.decode(errors='replace') if kind == 15 else ''))}


def _audio(path):
    """Convert into memory; never modify or delete the input file."""
    if not Path(path).is_file():
        raise StreamError('Audio file does not exist')
    try:
        completed = subprocess.run(
            ['ffmpeg', '-v', 'error', '-nostdin', '-i', str(path), '-ac', '1',
             '-ar', '16000', '-f', 's16le', '-acodec', 'pcm_s16le', '-'],
            capture_output=True, check=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        raise StreamError('Audio conversion failed; ffmpeg is required') from None
    pcm = completed.stdout
    if not pcm or len(pcm) % 2:
        raise StreamError('Audio conversion produced invalid PCM')
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)
    return output.getvalue(), len(pcm) / 32000


def _headers(profile, credentials, request_id):
    route = profile.get('route') or RESOURCE
    if profile.get('route') == 'volcengine_streaming_common':
        if not profile.get('route') or not credentials.get('token') or not credentials.get('appid'):
            raise StreamError('Legacy streaming requires an explicit cluster and app credentials')
        return {'Authorization': 'Bearer; ' + credentials['token']}
    if route != RESOURCE:
        raise StreamError('Unsupported streaming resource')
    headers = {'X-Api-Resource-Id': route, 'X-Api-Request-Id': request_id}
    if credentials.get('api_key'):
        headers['X-Api-Key'] = credentials['api_key']
    else:
        appid = credentials.get('appid') or credentials.get('app_key')
        token = credentials.get('token') or credentials.get('access_key')
        if not appid or not token:
            raise StreamError('Streaming credentials are incomplete')
        headers.update({'X-Api-App-Key': str(appid), 'X-Api-Access-Key': token})
    return headers


def _normalized(body, request_id, duration):
    result = body.get('result') or {}
    if isinstance(result, list):
        result = result[0] if result else {}
    if not isinstance(result, dict) or not isinstance(result.get('text'), str) or not result['text'].strip():
        raise ValueError('final response has no transcript')
    utterances = []
    for item in result.get('utterances') or []:
        if not isinstance(item, dict):
            continue
        utterances.append({key: item[key] for key in ('text', 'start_time', 'end_time') if key in item})
    return {'resp': {'text': result['text'], 'utterances': utterances},
            'request_id': request_id, 'duration_seconds': duration}


async def _run(content, duration, profile, credentials, uid):
    request_id = str(uuid.uuid4())
    headers = _headers(profile, credentials, request_id)
    try:
        import aiohttp
    except ImportError:
        raise StreamError('Streaming requires the Python aiohttp package') from None
    legacy = profile.get('route') == 'volcengine_streaming_common'
    audio_sent = False
    sender = None
    final_sent = False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect('wss://openspeech.bytedance.com/api/v2/asr' if legacy else URL, headers=headers, timeout=30, max_msg_size=16 * 1024 * 1024) as ws:
                payload = {'user': {'uid': uid},
                           'audio': {'format': 'wav', 'codec': 'raw', 'rate': 16000, 'bits': 16, 'channel': 1},
                           'request': {'model_name': 'bigmodel', 'enable_itn': True, 'enable_punc': True,
                                       'enable_ddc': False, 'show_utterances': True, 'result_type': 'full'}}
                if legacy:
                    payload = {'app': {'appid': str(credentials['appid']), 'token': credentials['token'], 'cluster': profile['route']},
                               'user': {'uid': uid},
                               'audio': {'format': 'wav', 'rate': 16000, 'bits': 16, 'channel': 1, 'language': 'zh-CN'},
                               'request': {'reqid': request_id, 'sequence': 1, 'nbest': 1, 'show_utterances': True,
                                           'workflow': 'audio_in,resample,partition,vad,fe,decode,itn,nlu_punctuate'}}
                await ws.send_bytes(_packet(1, 1, json.dumps(payload).encode(), legacy=legacy))
                async def receive():
                    message = await asyncio.wait_for(ws.receive(), timeout=60)
                    if message.type != aiohttp.WSMsgType.BINARY:
                        raise ValueError('socket ended without final response')
                    frame = _parse(message.data)
                    if legacy and isinstance(frame['body'].get('sequence'), int) and frame['body']['sequence'] < 0:
                        frame['last'] = True
                    if frame['code']:
                        raise StreamError('Streaming server rejected the request', audio_sent=audio_sent, code=frame['code'], quota_marker=frame['quota_marker'])
                    return frame
                # Check initial configuration acknowledgement before sending audio.
                initial = await receive()
                if initial['last']:
                    raise ValueError('premature final response')
                async def send():
                    nonlocal audio_sent, final_sent
                    for index, offset in enumerate(range(0, len(content), 6400), start=2):
                        last = offset + 6400 >= len(content)
                        # A failed send may have reached the remote; mark before await.
                        audio_sent = True
                        await ws.send_bytes(_packet(2, index, content[offset:offset + 6400], last, legacy=legacy))
                        if last:
                            final_sent = True
                        else:
                            await asyncio.sleep(0.2)
                sender = asyncio.create_task(send())
                while True:
                    receiver = asyncio.create_task(receive())
                    try:
                        done, _ = await asyncio.wait([receiver, sender], return_when=asyncio.FIRST_COMPLETED)
                        if sender in done:
                            await sender  # propagate a failed audio send immediately
                        frame = await receiver
                    finally:
                        if not receiver.done():
                            receiver.cancel()
                            await asyncio.gather(receiver, return_exceptions=True)
                    if frame['last']:
                        if not final_sent:
                            raise ValueError('premature final response')
                        return _normalized(frame['body'], request_id, duration)
    except StreamError:
        raise
    except aiohttp.WSServerHandshakeError as exc:
        header = exc.headers or {}
        marker = _quota_marker(header.get('X-Api-Message', ''))
        code = header.get('X-Api-Status-Code', '')
        raise StreamError('Streaming handshake rejected', audio_sent=audio_sent,
                          code=int(code) if str(code).isdigit() else None, quota_marker=marker) from None
    except Exception:
        raise StreamError('Streaming failed', audio_sent=audio_sent) from None
    finally:
        if sender is not None:
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)


def _transcribe_in_process(path, profile, credentials, uid):
    """One connection; success requires final frame. Never retry after failure.

    Errors expose audio_sent/uncertain_consumption for the caller's durable ledger.
    This function does not manage balances, files, credentials or fallback routes.
    """
    _headers(profile, credentials, 'validation')
    content, duration = _audio(path)
    return asyncio.run(_run(content, duration, profile, credentials, uid))


def transcribe_file(path, profile, credentials, uid):
    """Use isolated optional dependencies; credentials travel only over stdin."""
    import importlib.util
    if importlib.util.find_spec('aiohttp') is not None:
        return _transcribe_in_process(path, profile, credentials, uid)
    python = Path(__file__).resolve().parents[1] / '.local/venv/bin/python'
    if not python.is_file():
        raise StreamError('Install aiohttp in the Skill private venv before streaming')
    payload = {'path': str(path), 'profile': profile, 'credentials': credentials, 'uid': uid}
    try:
        response = subprocess.run([str(python), str(Path(__file__).resolve()), '--worker'],
            input=json.dumps(payload), capture_output=True, text=True, timeout=420)
        body = json.loads(response.stdout)
    except Exception:
        raise StreamError('Streaming worker failed', audio_sent=True) from None
    if 'error' in body:
        info = body['error']
        raise StreamError('Streaming worker request failed', audio_sent=info.get('audio_sent', True),
                          code=info.get('code'), quota_marker=info.get('quota_marker', ''))
    if response.returncode or 'result' not in body:
        raise StreamError('Streaming worker returned no result', audio_sent=True)
    return body['result']


if __name__ == '__main__':
    import sys
    if sys.argv[1:] != ['--worker']:
        raise SystemExit('Use volc_pool.py or volc_local.py to preserve quota accounting')
    try:
        request = json.load(sys.stdin)
        result = _transcribe_in_process(request['path'], request['profile'], request['credentials'], request['uid'])
        print(json.dumps({'result': result}, ensure_ascii=False))
    except StreamError as exc:
        print(json.dumps({'error': {'audio_sent': exc.audio_sent, 'code': exc.code,
                                  'quota_marker': exc.quota_marker}}))
        raise SystemExit(1)
    except Exception:
        print(json.dumps({'error': {'audio_sent': True}}))
        raise SystemExit(1)
