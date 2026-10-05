"""Credential reuse is local and destination-bound; no paid requests."""
import copy
import unittest
from unittest.mock import patch
import test_storyboards as fixture
import storage
import model_catalog


class ProviderReuseTests(unittest.TestCase):
    setUp = fixture.StoryboardTests.setUp
    api = fixture.StoryboardTests.api

    def source(self):
        p = {**self.provider, 'secret': storage.crypt('fixture-key-not-real'), 'platform': 'custom'}
        storage.put('providers', p)
        return copy.deepcopy(p)

    def payload(self, source):
        return {'credential_source_id': source['id'], 'name': 'New text', 'kind': 'chat',
                'protocol': 'openai_chat', 'platform': 'custom', 'base_url': source['base_url'],
                'model': 'fixture-text', 'custom': {}, 'extra': {}}

    def test_create_independent_model_reuses_secret_without_exposure(self):
        source = self.source()
        saved = self.api('/api/providers/save', self.payload(source))
        self.assertNotEqual(source['id'], saved['id'])
        self.assertNotIn('secret', saved)
        self.assertTrue(saved['has_key'])
        self.assertEqual(storage.get('providers', source['id']), source)
        self.assertEqual(storage.get('providers', saved['id'])['secret'], source['secret'])
        self.assertEqual(len(storage.items('jobs')), 0)

    def test_changed_destination_and_deleted_source_cannot_reuse_secret(self):
        source = self.source(); payload = self.payload(source)
        for address in ('https://another.invalid/v1', 'https://example.invalid/v2'):
            self.api('/api/providers/save', {**payload, 'base_url': address}, 400)
            self.api('/api/models/discover', {**payload, 'base_url': address}, 400)
        self.api('/api/providers/save', {**payload, 'credential_source_id': 'a'*32}, 400)
        self.assertEqual(len(storage.items('providers')), 1)

    def test_discovery_uses_saved_credentials_without_mutating_source(self):
        source = self.source()
        with patch.object(model_catalog, 'discover_saved', return_value={'models': []}) as discover:
            self.api('/api/models/discover', self.payload(source))
            self.assertEqual(discover.call_args.args[0]['secret'], source['secret'])
        self.assertEqual(storage.get('providers', source['id']), source)

    def test_explicit_image_name_precedes_shared_wan_family(self):
        p = {**self.source(), 'kind': 'chat', 'protocol': 'openai_chat'}
        models, _ = model_catalog._normalize([{'id': 'wan2.7-image'}, {'id': 'wan2.7-image-pro'}, {'id': 'wan2.2-t2v'}], 'openai', p, '')
        self.assertEqual([m['model_kinds'] for m in models], [['image'], ['image'], ['video']])


if __name__ == '__main__': unittest.main()
