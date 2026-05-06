"""
Fetch dated API export zips from fixed org buckets (legacy data_fetcher types 3 & 4).

Uses the first sink's ``filename`` template (strftime codes) and S3 prefix = dirname
of that path, matching ``run_fetcher.py`` / ``extract_api_validation.py`` behaviour.
"""
from __future__ import annotations

import os
import zipfile
from datetime import date, timedelta

import boto3
import yaml

# Buckets from legacy extract_api_validation.BUCKETS
API_BUCKETS = {
    'validation': 'onebeat-api-validation',
    'live':       'onebeat-api',
}


def _connect_to_s3():
    session = boto3.Session(profile_name='prod')
    return session.client('s3')


def _safe_extractall(zf: zipfile.ZipFile, dest_dir: str) -> None:
    """Extract all members under dest_dir; reject paths that escape dest_dir (zip slip)."""
    dest_abs = os.path.normpath(os.path.abspath(dest_dir))
    for member in zf.namelist():
        if not member or member.endswith('/'):
            continue
        target = os.path.normpath(os.path.join(dest_abs, member))
        if target != dest_abs and not target.startswith(dest_abs + os.sep):
            raise ValueError(f'Unsafe path in zip: {member!r}')
    zf.extractall(dest_dir)


def parse_primary_sink(config_path: str):
    """
    Return dict with ``prefix`` (S3 key prefix, may be '') and ``template`` (basename
    pattern with strftime codes, without .zip).
    """
    with open(config_path, encoding='utf-8') as f:
        config = yaml.safe_load(f)

    sinks = config.get('sinks') or {}
    if not sinks:
        return None, 'No sinks in config.yaml'

    first_name = next(iter(sinks))
    sink = sinks[first_name]
    fn = (sink.get('filename') or '').strip()
    if not fn:
        return None, 'First sink has no filename template'

    fn = fn.replace('\\', '/')
    dirname, basename = os.path.split(fn)
    prefix = (dirname + '/') if dirname else ''
    return {
        'sink_name':  first_name,
        'prefix':     prefix,
        'template':   basename,
    }, None


def _download_for_date(
    s3,
    bucket: str,
    prefix: str,
    template: str,
    target: date,
    day_dir: str,
    *,
    extract_zip: bool,
):
    """
    Build object basename = template formatted with ``target``, + ``.zip``,
    list under prefix, download first key whose path contains that basename.
    """
    try:
        stem = target.strftime(template)
    except ValueError as e:
        return {
            'source': 'api_sink',
            'status': 'error',
            'error':  f'Invalid filename template (strftime): {e}',
        }

    zip_token = stem if stem.lower().endswith('.zip') else f'{stem}.zip'
    os.makedirs(day_dir, exist_ok=True)

    try:
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
        for page in pages:
            for obj in page.get('Contents') or []:
                key = obj['Key']
                if zip_token in key:
                    local_name = os.path.basename(key)
                    local_path = os.path.join(day_dir, local_name)
                    s3.download_file(bucket, key, local_path)
                    if extract_zip:
                        try:
                            with zipfile.ZipFile(local_path, 'r') as zf:
                                _safe_extractall(zf, day_dir)
                            os.remove(local_path)
                        except Exception as e:
                            try:
                                os.remove(local_path)
                            except OSError:
                                pass
                            return {
                                'source': 'api_sink',
                                'status': 'error',
                                'error':  str(e),
                            }
                        return {
                            'source': 'api_sink',
                            'status': 'ok',
                            'path':   day_dir,
                        }
                    return {
                        'source': 'api_sink',
                        'status': 'ok',
                        'path':   local_path,
                    }
    except Exception as e:
        return {
            'source': 'api_sink',
            'status': 'error',
            'error':  str(e),
        }

    return {
        'source': 'api_sink',
        'status': 'not_found',
        'error':  f'No object matching {zip_token!r} under s3://{bucket}/{prefix}',
    }


def run(
    config_path: str,
    start_date: date,
    end_date: date,
    output_dir: str,
    mode: str,
    *,
    extract_zip: bool = False,
):
    """
    Args:
        mode: ``'validation'`` → onebeat-api-validation, ``'live'`` → onebeat-api
        extract_zip: If True, unzip each download into ``day_dir``, then delete the ``.zip``.

    Returns:
        (results, error) same shape as ``backup_io.run``.
    """
    if mode not in API_BUCKETS:
        return [], f'Invalid API fetch mode: {mode!r}'

    meta, err = parse_primary_sink(config_path)
    if err:
        return [], err

    bucket     = API_BUCKETS[mode]
    s3         = _connect_to_s3()
    output_dir = os.path.expanduser(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    all_results = []
    current     = start_date
    end         = end_date
    prefix      = meta['prefix']
    template    = meta['template']

    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        day_dir  = os.path.join(output_dir, date_str)
        result   = _download_for_date(
            s3, bucket, prefix, template, current, day_dir,
            extract_zip=extract_zip,
        )
        result['date'] = date_str
        all_results.append(result)
        current += timedelta(days=1)

    return all_results, None
