"""HTTP integration checks; real local storage, no paid model requests."""
import base64
import io
import json
import unittest
from PIL import Image
import test_storyboards
import storage
import visual_studio


class VisualStudioTests(unittest.TestCase):
    setUp = test_storyboards.StoryboardTests.setUp
    api = test_storyboards.StoryboardTests.api
    finish = test_storyboards.StoryboardTests.finish

    def image(self, color='red'):
        buf = io.BytesIO(); Image.new('RGB', (160, 90), color).save(buf, format='PNG')
        return self.api('/api/uploads', {'name': '角色.png', 'data_base64': base64.b64encode(buf.getvalue()).decode()}, 201)

    def project(self):
        a, b = self.image(), self.image('blue')
        ids = [storage.uid() for _ in range(4)]
        return self.api('/api/visual-projects/save', {'title': '多定稿', 'provider_id': self.provider['id'], 'story': 'Two settings', 'ratio': '9:16', 'nodes': [
            {'id': ids[0], 'title': '人物', 'kind': 'master', 'prompt': '同一角色', 'layout': 'sheet', 'ratio': '16:9', 'upload_id': a['id']},
            {'id': ids[1], 'title': '餐厅', 'kind': 'master', 'subtype': 'scene', 'prompt': '红桌布餐厅', 'upload_id': b['id']},
            {'id': ids[2], 'title': '镜头1', 'kind': 'shot', 'prompt': '人物近景', 'video_prompt': '轻轻转头', 'refs': [ids[0]]},
            {'id': ids[3], 'title': '镜头2', 'kind': 'shot', 'prompt': '人物在餐厅', 'video_prompt': '停下手里的动作', 'refs': ids[:2]}]})

    def generate(self, p, ids, token=None, status=202):
        return self.api('/api/visual-projects/generate', {'id': p['id'], 'version': p['version'], 'node_ids': ids, 'request_id': token or storage.uid()}, status)

    def adopt(self, p, node, **extra):
        return self.api('/api/visual-projects/adopt', {'id': p['id'], 'version': p['version'], 'node_id': node, **extra})

    def test_multi_reference_exact_job_inputs_and_idempotency(self):
        p = self.project(); ids = [n['id'] for n in p['nodes']]; token = storage.uid()
        generated = self.generate(p, ids[2:], token)
        self.assertEqual(self.mock_dispatch.call_count, 2)
        jobs = generated['jobs']; by_node = {j['visual_node_id']: j for j in jobs}
        upload_ids = [n['versions'][0]['upload_id'] for n in p['nodes'][:2]]
        self.assertEqual(by_node[ids[2]]['input_assets']['references'], upload_ids[:1])
        self.assertEqual(by_node[ids[3]]['input_assets']['references'], upload_ids)
        self.assertIn('参考图1：人物', by_node[ids[3]]['prompt'])
        self.assertIn('参考图2：餐厅', by_node[ids[3]]['prompt'])
        again = self.generate(p, ids[2:], token)
        self.assertEqual(again['version'], generated['version'])
        self.assertEqual(self.mock_dispatch.call_count, 2)
        reloaded = self.api('/api/visual-projects?id=' + p['id'])
        self.assertEqual(reloaded['jobs'], again['jobs'])

    def test_upstream_version_switch_retains_result_and_blocks_stale_video(self):
        p = self.project(); node = p['nodes'][2]['id']; master = p['nodes'][0]['id']
        p = self.generate(p, [node]); job_id = p['nodes'][2]['job_ids'][0]; self.finish(job_id)
        p = self.adopt(p, node, job_id=job_id)
        first_version = p['nodes'][2]['active_version_id']
        before = self.api('/api/visual-projects/transfer', {'id': p['id'], 'version': p['version'], 'node_id': node})
        self.assertEqual(before['ratio'], '9:16'); self.assertEqual(before['prompt'], '轻轻转头')
        p = self.adopt(p, master, upload_id=self.image('green')['id'])
        self.assertTrue(p['nodes'][2]['stale'])
        self.assertEqual(p['nodes'][2]['active_version_id'], first_version)
        self.assertEqual(p['nodes'][2]['job_ids'], [job_id])
        self.api('/api/visual-projects/transfer', {'id': p['id'], 'version': p['version'], 'node_id': node}, 400)
        p = self.api('/api/visual-projects/review', {'id': p['id'], 'version': p['version'], 'node_id': node})
        self.assertFalse(p['nodes'][2]['stale']); self.assertEqual(len(p['nodes'][2]['versions']), 2)
        self.assertEqual(p['nodes'][2]['versions'][0]['id'], first_version)
        self.api('/api/visual-projects/transfer', {'id': p['id'], 'version': p['version'], 'node_id': node})

    def test_rerun_is_candidate_until_explicit_adoption(self):
        p = self.project(); node = p['nodes'][0]['id']; original = p['nodes'][0]['active_version_id']
        p = self.generate(p, [node]); job_id = p['nodes'][0]['job_ids'][0]; self.finish(job_id)
        p = self.api('/api/visual-projects?id=' + p['id'])
        self.assertEqual(p['nodes'][0]['active_version_id'], original)
        p = self.adopt(p, node, job_id=job_id)
        self.assertNotEqual(p['nodes'][0]['active_version_id'], original)
        p = self.adopt(p, node, version_id=original)
        self.assertEqual(p['nodes'][0]['active_version_id'], original)
        job = storage.get('jobs', job_id)
        self.assertIn('左侧为清晰面部近景', job['prompt'])

    def test_invalid_graph_missing_reference_and_atomic_batch_failure(self):
        p = self.project(); original = p['version']
        p['nodes'][0]['refs'] = [p['nodes'][2]['id']]
        self.api('/api/visual-projects/save', p, 400)
        self.assertEqual(visual_studio.require(p['id'])['version'], original)
        p = self.api('/api/visual-projects?id=' + p['id'])
        p['nodes'][3]['prompt'] = ''
        p = self.api('/api/visual-projects/save', p)
        self.generate(p, [n['id'] for n in p['nodes'][2:]], status=400)
        self.assertEqual(self.mock_dispatch.call_count, 0)
        self.assertEqual(storage.items('jobs'), [])
        self.api('/api/visual-projects/save', {**p, 'version': original}, 400)

    def test_copy_upload_preserves_images_and_remapped_graph(self):
        p = self.project(); new_ids = [storage.uid(), storage.uid()]
        a = p['nodes'][0]; image = a['versions'][0]['upload_id']
        duplicate = self.api('/api/visual-projects/save', {'title': '复制到新项目', 'nodes': [
            {'id': new_ids[0], 'kind': 'master', 'title': '角色副本', 'prompt': a['prompt'], 'upload_id': image},
            {'id': new_ids[1], 'kind': 'shot', 'title': '镜头副本', 'prompt': '复制图', 'refs': [new_ids[0]], 'upload_id': image}]})
        self.assertFalse(duplicate['nodes'][1]['stale'])
        self.assertEqual(duplicate['nodes'][1]['versions'][0]['reference_snapshot'][0]['node_id'], new_ids[0])
        storage.init()
        self.assertEqual(self.api('/api/visual-projects?id='+duplicate['id'])['nodes'][0]['versions'][0]['asset']['id'], image)

    def test_legacy_import_preserves_original_and_is_repeatable(self):
        legacy = self.api('/api/storyboards/save', {'title': '旧项目', 'story': '人物饭局', 'provider_id': self.provider['id'], 'shots': [{'title': '场景一', 'prompt': '饭局'}]})
        legacy = self.api('/api/storyboards/generate', {'id': legacy['id'], 'version': legacy['version'], 'request_id': storage.uid(), 'stage': 'master'}, 202)
        self.finish(legacy['master_job_id'])
        legacy = self.api('/api/storyboards/confirm', {'id': legacy['id'], 'version': legacy['version']})
        before = json.dumps(storage.get('storyboards', legacy['id']), sort_keys=True)
        p = self.api('/api/visual-projects/import-legacy', {'legacy_id': legacy['id']})
        self.assertEqual(len(p['nodes']), 2); self.assertTrue(p['nodes'][0]['versions'])
        self.assertEqual(p['nodes'][1]['refs'], [p['nodes'][0]['id']])
        self.assertEqual(before, json.dumps(storage.get('storyboards', legacy['id']), sort_keys=True))
        self.assertEqual(self.api('/api/visual-projects/import-legacy', {'legacy_id': legacy['id']})['id'], p['id'])

    def test_external_paths_and_unknown_versions_rejected(self):
        p = self.project()
        self.api('/api/visual-projects/adopt', {'id':p['id'],'version':p['version'],'node_id':p['nodes'][0]['id'],'upload_id':'../../secret'},400)
        self.api('/api/visual-projects/adopt', {'id':p['id'],'version':p['version'],'node_id':p['nodes'][0]['id'],'version_id':storage.uid()},400)

if __name__ == '__main__':
    unittest.main()
