"""Chunked stream-quota adapter, called under volc_pool's serial lock."""
from __future__ import annotations
import math
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import volc_pool
import volc_auc

CHUNK_SECONDS = 45


def reserve_hours(duration):
    return (math.ceil(duration) + 2 * math.ceil(duration / CHUNK_SECONDS)) / 3600


def run(url, *, uid, duration_seconds, profile, credentials, data, ledger,
        ledger_path, task_key, job=None):
    import volc_stream
    profile_id = profile['id']
    tasks = ledger['tasks']
    reserve = reserve_hours(duration_seconds)
    if not job or job.get('state') != 'streaming':
        if profile['remaining_hours'] < reserve:
            raise RuntimeError('Streaming quota cannot cover the complete input')
        profile['remaining_hours'] -= reserve
        attempts = (job or {}).get('attempts', [])
        job = {'attempts': attempts, 'state': 'streaming', 'profile_id': profile_id, 'route': profile['route'],
               'reserved_hours': reserve, 'duration_seconds': duration_seconds,
               'chunks': [], 'created_at': datetime.now(timezone.utc).isoformat()}
        tasks[task_key] = job
        volc_pool.save(volc_pool.config_path(), data)
        volc_pool.save(ledger_path, ledger)
    if any(chunk['state'] != 'done' for chunk in job['chunks']):
        raise RuntimeError('A previous streaming chunk may have consumed quota; no automatic resubmission')
    count = math.ceil(duration_seconds / CHUNK_SECONDS)
    with tempfile.TemporaryDirectory(prefix='volc-stream-chunks-') as temporary:
        for index in range(len(job['chunks']), count):
            if not volc_pool.eligible(profile):
                raise RuntimeError('Streaming resource expired or disabled; no new chunk submitted')
            start = index * CHUNK_SECONDS
            duration = min(CHUNK_SECONDS, duration_seconds - start)
            path = Path(temporary) / f'{index}.wav'
            try:
                subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(start), '-i', url,
                    '-t', str(duration), '-vn', '-ac', '1', '-ar', '16000',
                    '-c:a', 'pcm_s16le', str(path)], capture_output=True, check=True, timeout=180)
            except Exception:
                raise RuntimeError('Could not prepare streaming audio chunk; completed chunks retained') from None
            chunk = {'index': index, 'state': 'submitting', 'offset_ms': start * 1000}
            job['chunks'].append(chunk)
            volc_pool.save(ledger_path, ledger)
            try:
                result = volc_stream.transcribe_file(path, profile, credentials, uid)
                if not result.get('resp', {}).get('text'):
                    raise RuntimeError('Streaming chunk completed without transcript')
            except Exception as exc:
                message = volc_pool.clean_error(exc, data)
                chunk.update(state='uncertain' if getattr(exc, 'audio_sent', True) else 'failed', error=message)
                job['state'] = chunk['state']
                volc_pool.save(ledger_path, ledger)
                if index == 0 and not getattr(exc, 'audio_sent', True) and volc_pool.quota_rejection(message):
                    raise volc_pool.QuotaRejected(message) from None
                raise RuntimeError(f'Streaming {profile_id} stopped at chunk {index + 1}: {message}') from None
            chunk.update(state='done', result={'resp': result['resp']},
                         request_id=result.get('request_id'))
            volc_pool.save(ledger_path, ledger)
            path.unlink()
    utterances = []
    texts = []
    for chunk in job['chunks']:
        resp = chunk['result']['resp']
        texts.append(resp['text'])
        for utterance in resp.get('utterances', []):
            row = dict(utterance)
            for field in ('start_time', 'end_time'):
                if isinstance(row.get(field), (int, float)):
                    row[field] += chunk['offset_ms']
            if row.get('words'):
                row['words'] = [dict(word, **{key: word[key] + chunk['offset_ms']
                    for key in ('start_time', 'end_time') if isinstance(word.get(key), (int, float))})
                    for word in row['words']]
            utterances.append(row)
    result = {'resp': {'text': ''.join(texts), 'utterances': utterances},
              'asr_pool': {'profile_id': profile_id, 'route': profile['route'],
                'reserved_hours': job['reserved_hours'], 'task_key': task_key,
                'stream_chunks': count}}
    job.update(state='done', result=result, finished_at=datetime.now(timezone.utc).isoformat())
    profile.update(verification='transcript_received', last_success_at=job['finished_at'])
    volc_pool.save(volc_pool.config_path(), data)
    volc_pool.save(ledger_path, ledger)
    return result, profile['route']
