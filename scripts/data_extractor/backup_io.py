import os
import zipfile
from datetime import date, timedelta

import boto3
import yaml


def parse_io_sources(config_path):
    """
    Parse a config.yaml and return a dict of sources that use an S3
    connection whose bucket does NOT end with '-backup' (i.e. regular IO).

    Returns:
        io_sources: {source_name: {'file_pattern': ..., 'backup_bucket': ...}}
        error: str or None
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    connections = config.get('connections', {})
    sources     = config.get('sources', {})

    # Map connection name → backup bucket name
    io_conn_map = {}
    for name, conn in connections.items():
        if conn.get('type') == 's3':
            bucket = conn.get('bucket', '')
            if bucket and not bucket.endswith('-backup'):
                io_conn_map[name] = bucket + '-backup'

    if not io_conn_map:
        return {}, 'No regular S3 connections found in config.yaml'

    # Collect sources that use one of those connections
    io_sources = {}
    for src_name, src in sources.items():
        conn_name = src.get('connection')
        if conn_name in io_conn_map and src.get('type') == 's3':
            file_pattern = src.get('file', '')
            if file_pattern:
                io_sources[src_name] = {
                    'file_pattern':  file_pattern,
                    'backup_bucket': io_conn_map[conn_name],
                }

    if not io_sources:
        return {}, 'No S3 sources found that use a regular IO connection'

    return io_sources, None


def _connect_to_s3():
    session = boto3.Session(profile_name='prod')
    return session.client('s3')


def _download_one(s3, source_name, file_pattern, backup_bucket, target_date, day_dir):
    """
    Download a single source file for target_date.
    Tries plain key first, then key + '.zip'.
    Unzips if needed and saves as source_name.

    Returns a result dict.
    """
    s3_key      = target_date.strftime(file_pattern)
    local_path  = os.path.join(day_dir, source_name)

    # Try plain, then zipped (.csv.zip)
    for key in [s3_key, s3_key + '.zip']:
        try:
            is_zip   = key.endswith('.zip')
            tmp_path = local_path + ('.zip' if is_zip else '')

            s3.download_file(backup_bucket, key, tmp_path)

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

    # Fallback: paginator search within the directory prefix
    prefix       = '/'.join(s3_key.split('/')[:-1]) + '/'
    filename_key = s3_key.split('/')[-1]  # e.g. AU_..._2025-02-13_1.csv

    try:
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=backup_bucket, Prefix=prefix):
            for obj in page.get('Contents', []):
                key  = obj['Key']
                base = key.split('/')[-1]
                # Match if the base contains the expected filename (with or without .zip)
                if filename_key in base or filename_key.replace('.csv', '') in base:
                    is_zip   = key.endswith('.zip')
                    tmp_path = local_path + ('.zip' if is_zip else '')

                    s3.download_file(backup_bucket, key, tmp_path)

                    if is_zip:
                        with zipfile.ZipFile(tmp_path, 'r') as zf:
                            inner = zf.namelist()[0]
                            with zf.open(inner) as src_f, open(local_path, 'wb') as dst_f:
                                dst_f.write(src_f.read())
                        os.remove(tmp_path)

                    return {'source': source_name, 'status': 'ok', 'path': local_path}

    except Exception as e:
        return {'source': source_name, 'status': 'error', 'error': str(e)}

    return {
        'source': source_name,
        'status': 'not_found',
        'error':  f'Not found in s3://{backup_bucket}/{prefix}',
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
                s3, src_name,
                src_info['file_pattern'],
                src_info['backup_bucket'],
                current, day_dir,
            )
            result['date']  = date_str
            all_results.append(result)

        current += timedelta(days=1)

    return all_results, None
