import os
import zipfile
from datetime import timedelta

import boto3
import yaml

# Standard IO buckets — same keys/patterns as in config; only the bucket differs by flow.
BUCKET_IO_LIVE = 'onebeat-io'
BUCKET_IO_BACKUP = 'onebeat-io-backup'


def parse_io_sources(config_path):
    """
    Parse a config.yaml and return a dict of sources that use an S3
    connection whose bucket does NOT end with '-backup' (i.e. regular IO).

    Returns:
        io_sources: {source_name: {'file_pattern': ...}}
        error: str or None

    Each S3 source pattern is read from ``file`` if set, else legacy ``path``.
    Actual S3 bucket is chosen by the caller: ``BUCKET_IO_LIVE`` or ``BUCKET_IO_BACKUP``.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    connections = config.get('connections', {})
    sources     = config.get('sources', {})

    # Map connection name → eligible if this is a non-backup S3 connection (any bucket name)
    io_conn_map = {}
    for name, conn in connections.items():
        if conn.get('type') == 's3':
            bucket = conn.get('bucket', '')
            if bucket and not bucket.endswith('-backup'):
                io_conn_map[name] = True

    if not io_conn_map:
        return {}, 'No regular S3 connections found in config.yaml'

    # Collect sources that use one of those connections
    io_sources = {}
    for src_name, src in sources.items():
        conn_name = src.get('connection')
        if conn_name in io_conn_map and src.get('type') == 's3':
            # Prefer "file" (current schema); older configs used "path" for the same pattern
            file_pattern = (src.get('file') or src.get('path') or '').strip()
            if file_pattern:
                io_sources[src_name] = {'file_pattern': file_pattern}

    if not io_sources:
        return {}, 'No S3 sources found that use a regular IO connection'

    return io_sources, None


def _connect_to_s3():
    session = boto3.Session(profile_name='prod')
    return session.client('s3')


def _download_one(
    s3,
    source_name,
    file_pattern,
    bucket,
    target_date,
    day_dir,
    *,
    live_primary_bucket=False,
):
    """
    Download a single source file for target_date.
    Tries plain key first, then key + '.zip'.
    Unzips if needed and saves as source_name.

    Returns a result dict.
    """
    s3_key     = target_date.strftime(file_pattern)
    local_path = os.path.join(day_dir, source_name)

    # Try plain, then zipped (.csv.zip)
    for key in [s3_key, s3_key + '.zip']:
        try:
            is_zip   = key.endswith('.zip')
            tmp_path = local_path + ('.zip' if is_zip else '')

            s3.download_file(bucket, key, tmp_path)

            if is_zip:
                with zipfile.ZipFile(tmp_path, 'r') as zf:
                    inner = zf.namelist()[0]
                    with zf.open(inner) as src_f, open(local_path, 'wb') as dst_f:
                        dst_f.write(src_f.read())
                os.remove(tmp_path)

            return {'source': source_name, 'status': 'ok', 'path': local_path}

        except Exception:
            # Clean up any partial download before retrying
            for p in [local_path, local_path + '.zip']:
                try:
                    os.remove(p)
                except OSError:
                    pass
            continue

    # Fallback: list under the parent prefix (never use Prefix='/' for root keys — that matches almost nothing)
    parts = s3_key.replace('\\', '/').split('/')
    filename_key = parts[-1]
    list_prefix = '/'.join(parts[:-1]) + '/' if len(parts) > 1 else None

    if list_prefix is not None:
        try:
            paginator = s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket, Prefix=list_prefix):
                for obj in page.get('Contents', []):
                    key  = obj['Key']
                    base = key.split('/')[-1]
                    # Match if the base contains the expected filename (with or without .zip)
                    if filename_key in base or filename_key.replace('.csv', '') in base:
                        is_zip   = key.endswith('.zip')
                        tmp_path = local_path + ('.zip' if is_zip else '')

                        s3.download_file(bucket, key, tmp_path)

                        if is_zip:
                            with zipfile.ZipFile(tmp_path, 'r') as zf:
                                inner = zf.namelist()[0]
                                with zf.open(inner) as src_f, open(local_path, 'wb') as dst_f:
                                    dst_f.write(src_f.read())
                            os.remove(tmp_path)

                        return {'source': source_name, 'status': 'ok', 'path': local_path}

        except Exception as e:
            return {'source': source_name, 'status': 'error', 'error': str(e)}

    if list_prefix is not None:
        probe = f'prefix listing under {list_prefix!r}'
    else:
        probe = 'no folder prefix in key (only exact paths were tried)'
    base_msg = (
        f'Not found at s3://{bucket}/{s3_key} (or .zip). '
        f'Exact key and {probe} did not match.'
    )
    if live_primary_bucket:
        base_msg += (
            ' The live bucket (onebeat-io) often only holds recent or in-flight objects; '
            'older dated files are often only in onebeat-io-backup — use Backup IO for those dates.'
        )

    return {
        'source': source_name,
        'status': 'not_found',
        'error':  base_msg,
    }


def run(config_path, start_date, end_date, output_dir):
    """
    Parse config.yaml, iterate over the date range, download every detected
    IO source from the corresponding backup bucket.

    Args:
        config_path: path to config.yaml
        start_date:  datetime.date — first day to fetch (inclusive)
        end_date:    datetime.date — last day to fetch (inclusive)
        output_dir:  local directory to save files under {date}/{source_name}

    Returns:
        results: list of result dicts (keys: date, source, status, path/error)
        error:   str or None
    """
    io_sources, err = parse_io_sources(config_path)
    if err:
        return [], err

    s3         = _connect_to_s3()
    output_dir = os.path.expanduser(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    all_results = []
    current     = start_date
    end         = end_date

    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        day_dir  = os.path.join(output_dir, date_str)
        os.makedirs(day_dir, exist_ok=True)

        for src_name, src_info in io_sources.items():
            result          = _download_one(
                s3,
                src_name,
                src_info['file_pattern'],
                BUCKET_IO_BACKUP,
                current,
                day_dir,
            )
            result['date']  = date_str
            all_results.append(result)

        current += timedelta(days=1)

    return all_results, None


def run_io_live(config_path, start_date, end_date, output_dir):
    """
    Same as :func:`run` (patterns, unzip, listing fallback), but uses
    ``BUCKET_IO_LIVE`` (``onebeat-io``) instead of ``BUCKET_IO_BACKUP``
    (``onebeat-io-backup``).
    """
    io_sources, err = parse_io_sources(config_path)
    if err:
        return [], err

    s3         = _connect_to_s3()
    output_dir = os.path.expanduser(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    all_results = []
    current     = start_date
    end         = end_date

    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        day_dir  = os.path.join(output_dir, date_str)
        os.makedirs(day_dir, exist_ok=True)

        for src_name, src_info in io_sources.items():
            result = _download_one(
                s3,
                src_name,
                src_info['file_pattern'],
                BUCKET_IO_LIVE,
                current,
                day_dir,
                live_primary_bucket=True,
            )
            result['date'] = date_str
            all_results.append(result)

        current += timedelta(days=1)

    return all_results, None
