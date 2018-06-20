#!/usr/bin/env python3
#
# MIT License
#
# Copyright (c) 2018 Trung Dong Huynh
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from collections import OrderedDict
import csv
import json
import logging
import requests
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = 'https://openprovenance.org/store/'

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description='Upload a local backup of all your provenance documents to a new ProvStore. '
                    'Get the API Key for your account at your new ProvStore (for example: '
                    '%saccount/developer/.' % DEFAULT_BASE_URL
    )
    parser.add_argument('username', help='your ProvStore username')
    parser.add_argument('api_key', help='your API Key')
    parser.add_argument('-p', '--path', help='the location for the downloaded documents',
                        action='store', default='.')
    parser.add_argument('-u', '--server-url', help='the base URL of the target server (default: %s)' % DEFAULT_BASE_URL,
                        action='store', default=DEFAULT_BASE_URL)
    parser.add_argument('-d', '--debug', help='enable debug logging',
                        action='store_true', default=False)
    args = parser.parse_args()

    username = args.username
    api_key = args.api_key
    base_path = Path(args.path)
    base_url = args.server_url.strip()
    if not base_url.endswith('/'):
        base_url += '/'

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARN)

    headers = {
        'Accept': 'application/json',
        'Authorization': 'ApiKey %s:%s' % (username, api_key),
        'Content-type': 'application/json',
    }

    api_base_url = base_url + 'api/v0/'
    r = requests.get(api_base_url + 'me', headers=headers)
    if not r.ok:
        raise SystemExit(
            '[ERROR] Could not authenticate with the provided username and API key at %s end-point.\nReason: %s' %
            (api_base_url, r.reason)
        )

    meta_filepath = base_path / 'meta.csv'
    if not meta_filepath.exists():
        raise SystemExit(
            '[ERROR] Could not find the file %s. We expect a "meta.csv" file in the backup folder. This file should be '
            'generated by the backup script.' % meta_filepath
        )

    statuses = OrderedDict()
    status_filepath = base_path / 'status.csv'
    if status_filepath.exists():
        try:
            with status_filepath.open() as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    statuses[row['old_id']] = row['new_id']
        except Exception as e:
            logger.warn('Error reading the previous statuses of backed up documemts from <%s>', status_filepath)
            logger.debug(e)

    try:
        with meta_filepath.open() as meta_file:
            logger.debug('Reading the backup meta.csv file...')
            meta_reader = csv.DictReader(meta_file)
            for row in meta_reader:
                if row['id'] in statuses:
                    # TODO Handling failed uploads
                    logger.warn('Document #%s has previously been uploaded. Skipping', row['id'])
                    continue

                logger.debug('Uploading document #%s <%s>...', row['id'], row['document_name'])
                try:
                    filepath = base_path / row['filename']
                    with filepath.open() as f:
                        doc_content = f.read()
                    payload = json.dumps({
                        'content': doc_content,
                        'public': row['public'] == 'True',
                        'rec_id': row['document_name']
                    })
                    r = requests.post(api_base_url + 'documents/', data=payload, headers=headers)
                    if r.ok:
                        response = r.json()
                        statuses[row['id']] = response['id']
                        logger.debug('New document ID: %d', response['id'])
                    else:
                        statuses[row['id']] = 'Error'
                        logger.error('Could not upload document #%s <%s>.\nReason: %s',
                                     row['id'], row['document_name'], r.reason)
                except FileNotFoundError as e:
                    statuses[row['id']] = 'NotFound'
                    logger.debug(e)
                    logger.warning('Cannot find the file <%s> (Document No. #%s). Skipping.', row['document_name'], row['id'])
                except Exception as e:
                    statuses[row['id']] = 'Error'
                    logger.debug('Unexpected exception >>>>> %s ', e)
    except KeyboardInterrupt:
        print('User interuption, exiting.')
    finally:
        with status_filepath.open('w') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(('old_id', 'new_id'))
            writer.writerows(statuses.items())
