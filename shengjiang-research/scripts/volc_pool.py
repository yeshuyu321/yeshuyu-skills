"""Private, serial quota routing for URL ASR. No automatic remote resource deletion."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / '.local/volc-asr-pool.json'


def config_path():
    return Path(os.environ.get('VOLC_ASR_POOL_CONFIG', str(DEFAULT_PATH))).expanduser()


def load():
    return json.loads(config_path().read_text())


def save(path, data):
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


@contextmanager
def locked():
    import fcntl
    path = config_path().with_suffix('.lock')
    with open(path, 'a') as f:
        os.chmod(path, 0o600)
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def eligible(profile):
    return (profile.get('enabled', False) and profile.get('status') == 'available'
            and profile['kind'] in ('v1', 'v3', 'streaming')
            and datetime.fromisoformat(profile['expires_at']) > datetime.now(timezone.utc))


def status():
    data = load()
    items = [{k: p.get(k) for k in ('id', 'label', 'kind', 'route', 'remaining_hours',
             'expires_at', 'status', 'enabled', 'snapshot_date', 'verification')} for p in data['profiles']]
    return {'configured': bool(data.get('credentials')), 'provider': 'volcengine-quota-pool',
            'cluster': 'automatic', 'config_file': str(config_path()),
            'active_profiles': [p['id'] for p in data['profiles'] if eligible(p)], 'profiles': items}


def clean_error(value, data):
    text = str(value)
    for cred in data.get('credentials', {}).values():
        for field in ('token', 'secret_key', 'api_key'):
            secret = cred.get(field)
            if secret:
                text = text.replace(secret, '<redacted>')
    # Never echo a submitted URL or signed query string in an error.
    import re
    return re.sub(r'https?://[^\s"<>]+', '<url-redacted>', text)[:1000]


def quota_rejection(message):
    value = str(message).lower()
    return ('audio_duration_lifetime' in value or 'audio_duration_month' in value
            or 'audio_duration_total' in value)


def transcribe(url, *, audio_format, uid, duration_seconds, profile_id=None,
               timeout_seconds=900, poll_interval=5, input_key=None, audio_data=None):
    import volc_auc
    if duration_seconds is None or not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError('Quota pool requires a verified positive duration_seconds before submission')
    reserve = (math.ceil(duration_seconds) + 1) / 3600
    ledger_path = config_path().with_name('asr-ledger.json')
    task_key = hashlib.sha256((uid + '\0' + (input_key or url) + '\0' + (profile_id or 'auto')).encode()).hexdigest()
    with locked():
        data = load()
        ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {'tasks': {}}
        tasks = ledger['tasks']
        job = tasks.get(task_key)
        if job and job['state'] == 'done':
            return job['result'], job['route']
        if job and job['state'] in ('submitting', 'uncertain', 'failed'):
            raise RuntimeError('ASR previous submission needs review; no resubmission or quota switch: ' + task_key)
        for p in data['profiles']:
            if p['kind'] in ('v1', 'v3', 'streaming') and p.get('enabled'):
                if datetime.fromisoformat(p['expires_at']) <= datetime.now(timezone.utc):
                    p.update(enabled=False, status='expired')
                elif float(p['remaining_hours']) <= 0 and not (job and job.get('state') in ('pending', 'streaming') and job.get('profile_id') == p['id']):
                    p.update(enabled=False, status='exhausted')
        save(config_path(), data)
        choices = sorted([p for p in data['profiles'] if eligible(p) and (not profile_id or p['id'] == profile_id)], key=lambda p: p['expires_at'])
        if job and job['state'] in ('pending', 'streaming'):
            choices = [next(p for p in data['profiles'] if p['id'] == job['profile_id'])]
            if job['state'] == 'streaming' and not eligible(choices[0]):
                raise RuntimeError('Streaming resource expired or disabled; completed chunks retained, no new audio sent')
        for p in choices:
            if p['kind'] == 'streaming':
                if audio_data is not None:
                    continue
                import volc_stream_pool
                if not (job and job.get('state') == 'streaming') and p['remaining_hours'] < volc_stream_pool.reserve_hours(duration_seconds):
                    continue
                try:
                    return volc_stream_pool.run(url, uid=uid, duration_seconds=duration_seconds,
                        profile=p, credentials=data['credentials'][p['credential']], data=data,
                        ledger=ledger, ledger_path=ledger_path, task_key=task_key, job=job)
                except QuotaRejected as exc:
                    p.update(enabled=False, status='exhausted', remaining_hours=0,
                             verification='API quota denied', last_error=clean_error(exc, data))
                    job = tasks[task_key]
                    job['state'] = 'quota_rejected'
                    job.setdefault('attempts', []).append({'profile_id': p['id'], 'error': clean_error(exc, data)})
                    save(config_path(), data); save(ledger_path, ledger)
                    continue
            resume = bool(job and job['state'] == 'pending')
            if not resume and float(p['remaining_hours']) < reserve:
                continue
            cred = data['credentials'][p['credential']]
            config = dict(cred, resource_id=p['route'], base_url='https://openspeech.bytedance.com/api/v3/auc/bigmodel')
            if not resume:
                p['remaining_hours'] = max(0, float(p['remaining_hours']) - reserve)
                attempts = (job or {}).get('attempts', [])
                job = {'attempts': attempts, 'state': 'submitting', 'profile_id': p['id'], 'route': p['route'],
                       'reserved_hours': reserve, 'duration_seconds': duration_seconds,
                       'request_id': str(uuid.uuid4()), 'created_at': datetime.now(timezone.utc).isoformat()}
                tasks[task_key] = job
                save(config_path(), data)
                save(ledger_path, ledger)
                try:
                    if p['kind'] == 'v3':
                        audio_payload = ({'data': audio_data, 'format': audio_format}
                                         if audio_data is not None else
                                         {'url': url, 'format': audio_format})
                        code, body, msg = volc_auc._v3_request('submit', {
                            'user': {'uid': uid}, 'audio': audio_payload,
                            'request': {'model_name': 'bigmodel', 'enable_itn': True,
                                        'enable_punc': True, 'enable_ddc': False, 'show_utterances': True}
                        }, config, job['request_id'])
                        accepted = code == '20000000'
                        detail = f'{code}: {msg}'
                        has_task = bool(body.get('task_id') or body.get('id'))
                    else:
                        body = volc_auc._submit(audio_url=url, audio_format=audio_format,
                            credentials=cred, cluster=p['route'], uid=uid, timeout=60)
                        resp = body.get('resp') or {}
                        accepted = str(resp.get('code')) == '1000' and bool(resp.get('id'))
                        has_task = bool(resp.get('id'))
                        if has_task:
                            job['request_id'] = str(resp['id'])
                        detail = json.dumps(resp, ensure_ascii=False)
                    if not accepted:
                        if quota_rejection(detail) and not has_task:
                            raise QuotaRejected(detail)
                        raise RuntimeError(detail)
                except Exception as exc:
                    message = clean_error(exc, data)
                    # Explicit quota denial before acceptance permits one attempt per next route.
                    if isinstance(exc, QuotaRejected):
                        p.update(enabled=False, status='exhausted', remaining_hours=0,
                                 verification='API quota denied', last_error=message)
                        job.update(state='quota_rejected', error=message)
                        job['attempts'].append({'profile_id': p['id'], 'error': message})
                        save(config_path(), data); save(ledger_path, ledger)
                        continue
                    job.update(state='uncertain', error=message)
                    save(ledger_path, ledger)
                    raise RuntimeError(f"ASR {p['id']} submission stopped: {message}") from None
                job['state'] = 'pending'
                save(ledger_path, ledger)
            try:
                if p['kind'] == 'v3':
                    deadline = time.monotonic() + timeout_seconds
                    while time.monotonic() < deadline:
                        time.sleep(poll_interval)
                        code, body, msg = volc_auc._v3_request('query', {}, config, job['request_id'])
                        if code == '20000000':
                            response = body.get('result') or {}
                            if not response.get('text'):
                                raise RuntimeError('Completed without transcript text')
                            result = {'resp': response, 'raw_v3': body, 'request_id': job['request_id']}
                            break
                        if code not in ('20000001', '20000002'):
                            raise volc_auc.ASRTaskFailed(f'Query {code}: {msg}')
                    else:
                        raise TimeoutError('ASR pending; rerun same input to query original task')
                else:
                    result = volc_auc._wait(task_id=job['request_id'], credentials=cred,
                        cluster=p['route'], timeout_seconds=timeout_seconds, poll_interval=poll_interval)
            except Exception as exc:
                if isinstance(exc, volc_auc.ASRTaskFailed):
                    job['state'] = 'failed'
                job['last_query_error'] = clean_error(exc, data)
                save(ledger_path, ledger)
                raise RuntimeError(f"ASR {p['id']} {job['state']} on original task: {job['last_query_error']}") from None
            # Keep a sanitized completed response so identical retries never pay twice.
            result = {'resp': result.get('resp', {}), 'request_id': job['request_id']}
            raw = json.dumps(result, ensure_ascii=False)
            for secret_cred in data['credentials'].values():
                for field in ('token', 'secret_key', 'api_key'):
                    if secret_cred.get(field):
                        raw = raw.replace(secret_cred[field], '<redacted>')
            result = json.loads(raw)
            if not result['resp'].get('text'):
                raise RuntimeError('No transcript text; original task retained')
            result['asr_pool'] = {'profile_id': p['id'], 'route': p['route'],
                'reserved_hours': job['reserved_hours'], 'task_key': task_key}
            job.update(state='done', result=result, finished_at=datetime.now(timezone.utc).isoformat())
            p['verification'] = 'transcript_received'
            p['last_success_at'] = job['finished_at']
            save(config_path(), data); save(ledger_path, ledger)
            return result, p['route']
        raise RuntimeError('No eligible quota with enough estimated remaining duration; no postpaid fallback')


class QuotaRejected(RuntimeError):
    pass


def main():
    import volc_auc
    ap = argparse.ArgumentParser()
    ap.add_argument('--status', action='store_true')
    ap.add_argument('--url')
    ap.add_argument('--format', default='mp3')
    ap.add_argument('--duration', type=float)
    ap.add_argument('--uid', default='shengjiang-asr')
    ap.add_argument('--profile')
    ap.add_argument('--out', type=Path)
    ap.add_argument('--timeout', type=int, default=900)
    args = ap.parse_args()
    if args.status:
        print(json.dumps(status(), ensure_ascii=False, indent=2)); return
    if not args.url or not args.out:
        ap.error('--url and --out required')
    try:
        result, route = transcribe(args.url, audio_format=args.format, uid=args.uid,
                                  duration_seconds=args.duration, profile_id=args.profile,
                                  timeout_seconds=args.timeout)
    except Exception as exc:
        ap.exit(1, str(exc) + '\n')
    files = volc_auc.write_transcript_files(result, args.out, title='转写结果', source=f'火山ASR {route}')
    print(json.dumps({'route': route, 'files': files, 'characters': len(result['resp']['text'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
