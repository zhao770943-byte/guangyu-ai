"""Usage accounting tests; only generated in-memory or temporary records."""
import csv
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storage
import usage

NOW = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
PROVIDER = {'id': 'provider-1', 'name': '我的模型', 'model': 'model-a',
            'kind': 'chat', 'protocol': 'openai_chat', 'base_url': 'https://example.test/v1',
            'secret': 'private-encrypted-secret'}


def job(identity='1', *, provider=None, tokens=None, **fields):
    provider = provider or PROVIDER
    value = {'id': identity, 'provider_id': provider['id'], 'provider_name': provider['name'],
             'model': provider['model'], 'kind': provider['kind'], 'provider_snapshot': dict(provider),
             'status': 'succeeded', 'created_at': '2026-09-28T08:00:00+00:00',
             'elapsed_ms': 1000, 'result': {'text': 'private response', 'assets': [], 'usage': tokens}}
    value.update(fields)
    return value


def report(jobs=None, providers=None, **kwargs):
    return usage.build_report(jobs=jobs or [], providers=[PROVIDER] if providers is None else providers, now=NOW, **kwargs)


class UsageTests(unittest.TestCase):
    def test_openai_cache_and_reasoning_are_subsets(self):
        tokens = {'input_tokens': 100, 'output_tokens': 20, 'cached_input_tokens': 70,
                  'reasoning_tokens': 8, 'total_tokens': 198, 'source': 'openai'}
        value = report([job(tokens=tokens)])
        self.assertEqual(value['summary']['total_tokens'], 120)
        self.assertEqual(value['summary']['cached_input_tokens'], 70)
        self.assertEqual(value['summary']['reasoning_tokens'], 8)
        self.assertEqual(value['models'][0]['total_tokens'], 120)

    def test_unknown_usage_is_not_zero_and_zero_is_reported(self):
        value = report([job('unknown'), job('zero', tokens={'input_tokens': 0, 'output_tokens': 0})])
        self.assertEqual(value['summary']['usage_missing_requests'], 1)
        self.assertEqual(value['summary']['usage_reported_requests'], 1)
        self.assertEqual(value['summary']['total_tokens'], 0)
        self.assertEqual(value['summary']['coverage_percent'], 50)
        unknown = next(row for row in value['requests'] if row['id'] == 'unknown')
        self.assertIsNone(unknown['total_tokens'])
        empty = report()
        self.assertIsNone(empty['summary']['total_tokens'])
        self.assertEqual(empty['summary']['connected_models'], 1)
        self.assertEqual(empty['models'][0]['requests'], 0)

    def test_partial_and_total_only_reports_remain_distinct(self):
        value = report([job('partial', tokens={'input_tokens': 10}),
                        job('total', tokens={'reported_total_tokens': 99})])
        self.assertEqual(value['summary']['input_tokens'], 10)
        self.assertIsNone(value['summary']['output_tokens'])
        self.assertEqual(value['summary']['total_tokens'], 99)
        self.assertEqual(value['summary']['usage_reported_requests'], 2)
        self.assertEqual(value['summary']['token_incomplete_requests'], 1)

    def test_top_level_usage_retained_for_failure_without_double_count(self):
        value = report([job(tokens={'input_tokens': 10, 'output_tokens': 5},
                            usage={'input_tokens': 10, 'output_tokens': 5}, status='failed')])
        self.assertEqual(value['summary']['total_tokens'], 15)
        self.assertEqual(value['summary']['failed'], 1)
        self.assertEqual(value['summary']['error_rate'], 100)

    def test_renamed_and_changed_models_keep_historical_identity(self):
        renamed = {**PROVIDER, 'name': '新名字'}
        changed = {**PROVIDER, 'model': 'model-b'}
        deleted = {**PROVIDER, 'id': 'deleted-id', 'name': '已删连接'}
        value = report([job('original'), job('changed', provider=changed), job('deleted', provider=deleted)], providers=[renamed])
        self.assertEqual(value['summary']['connected_models'], 1)
        self.assertEqual(value['summary']['historical_models'], 3)
        connected = next(row for row in value['models'] if row['connected'])
        self.assertEqual(connected['provider_name'], '新名字')
        self.assertEqual(connected['requests'], 0)
        self.assertEqual(sum(row['requests'] for row in value['models']), 3)
        encoded = json.dumps(value)
        self.assertNotIn('private-encrypted-secret', encoded)
        self.assertNotIn('private response', encoded)
        self.assertNotIn('provider_snapshot', encoded)

    def test_changed_endpoint_does_not_relabel_previous_usage(self):
        changed = {**PROVIDER, 'base_url': 'https://other.test/v1'}
        value = report([job()], providers=[changed])
        self.assertEqual(len(value['models']), 2)
        self.assertEqual(value['models'][0]['requests'], 0)

    def test_shanghai_today_and_seven_day_boundaries(self):
        records = [job('today', created_at='2026-09-27T16:00:00Z'),
                   job('yesterday', created_at='2026-09-27T15:59:59Z'),
                   job('start', created_at='2026-09-21T16:00:00Z'),
                   job('before', created_at='2026-09-21T15:59:59Z'),
                   job('future', created_at='2026-09-29T00:00:00Z')]
        today = report(records, period='today')
        self.assertEqual(today['summary']['requests'], 1)
        self.assertEqual(today['daily'][0]['date'], '2026-09-28')
        week = report(records, period='7d')
        self.assertEqual(week['summary']['requests'], 3)
        self.assertEqual(len(week['daily']), 7)
        self.assertEqual(week['daily'][0]['date'], '2026-09-22')

    def test_all_database_records_are_aggregated_and_exported(self):
        with tempfile.TemporaryDirectory(prefix='guangyu-usage-') as folder:
            with patch.object(storage, 'DATA', Path(folder)):
                with closing(sqlite3.connect(Path(folder) / 'workspace.sqlite3')) as conn:
                    conn.executescript('CREATE TABLE providers(payload TEXT); CREATE TABLE jobs(payload TEXT);')
                    conn.execute('INSERT INTO providers VALUES (?)', (json.dumps(PROVIDER),))
                    conn.executemany('INSERT INTO jobs VALUES (?)',
                                     [(json.dumps(job(str(number), tokens={'input_tokens': 1, 'output_tokens': 2})),)
                                      for number in range(305)])
                    conn.commit()
                value = usage.build_report(now=NOW)
                self.assertEqual(value['summary']['requests'], 305)
                self.assertEqual(value['summary']['total_tokens'], 915)
                self.assertEqual(len(value['requests']), 100)
                full = usage.build_report(now=NOW, request_limit=None)
                parsed = list(csv.reader(io.StringIO(usage.csv_export(full).lstrip('\ufeff'))))
                self.assertEqual(len(parsed), 306)

    def test_csv_formula_protection_and_blank_unknown_values(self):
        dangerous = {**PROVIDER, 'name': '  =HYPERLINK("bad")', 'model': '@cmd'}
        value = report([job(provider=dangerous)], providers=[dangerous])
        exported = usage.csv_export(value)
        self.assertTrue(exported.startswith('\ufeff'))
        parsed = list(csv.reader(io.StringIO(exported.lstrip('\ufeff'))))
        self.assertTrue(parsed[1][2].startswith("'"))
        self.assertTrue(parsed[1][3].startswith("'"))
        self.assertEqual(parsed[1][7:10], ['', '', ''])
        self.assertEqual(usage._csv_cell('\t=cmd'), "'\t=cmd")

    def test_media_and_duration_count_only_successful_outputs(self):
        image = job('image', kind='image', result={'assets': [{'type': 'image'}, {'type': 'image'}]})
        video = job('video', kind='video', seconds=8, result={'assets': [{'type': 'video'}]})
        failed = job('failed', kind='video', status='failed', seconds=8, result={'assets': [{'type': 'video'}]})
        value = report([image, video, failed])
        self.assertEqual(value['summary']['image_count'], 2)
        self.assertEqual(value['summary']['video_count'], 1)
        self.assertEqual(value['summary']['requested_video_seconds'], 8)
        self.assertIsNone(value['summary']['video_seconds'])
        verified = job('verified', seconds=8, result={'assets': [{'type': 'video', 'duration_seconds': 7.9}]})
        self.assertEqual(report([verified])['summary']['video_seconds'], 7.9)

    def test_latency_rates_do_not_treat_active_tasks_as_failures(self):
        value = report([job('good', elapsed_ms=100), job('bad', status='failed', elapsed_ms=300),
                        job('active', status='polling', elapsed_ms=9999)])
        self.assertEqual(value['summary']['avg_latency_ms'], 200)
        self.assertEqual(value['summary']['success_rate'], 50)
        self.assertEqual(value['summary']['active'], 1)

    def test_untrusted_counts_and_invalid_period_are_rejected(self):
        value = report([job(tokens={'input_tokens': -1, 'output_tokens': True, 'total_tokens': float('nan')})])
        self.assertIsNone(value['summary']['total_tokens'])
        with self.assertRaises(ValueError):
            report(period='invalid')


if __name__ == '__main__':
    unittest.main()
