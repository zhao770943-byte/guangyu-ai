"""Model-aware canvas settings must survive into requests, without paid calls."""
import threading
import urllib.request
from http.server import ThreadingHTTPServer
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import capabilities
import image_controls
import providers
import storage
import server


def provider(model='gpt-image-2.5-sunburst', protocol='openai_image', **extra):
    return {'kind': 'image', 'protocol': protocol, 'model': model, 'extra': {}, **extra}


def job(size='auto', **parameters):
    return {'prompt': 'A mountain landscape', 'size': size, 'parameters': parameters}


class ImageControlsTests(unittest.TestCase):
    def test_canvas_script_is_served_by_the_local_server(self):
        app = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        origin = f'http://127.0.0.1:{app.server_port}'
        with patch.object(server, 'PORT', app.server_port), patch.object(server, 'ORIGIN', origin):
            thread = threading.Thread(target=app.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(origin + '/') as response:
                    self.assertIn(b'/image-controls.js', response.read())
                with urllib.request.urlopen(origin + '/image-controls.js') as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(b'function imageCanvas', response.read())
            finally:
                app.shutdown()
                app.server_close()
                thread.join()

    def test_all_presets_are_exact_ratios_and_valid_requests(self):
        for model in ('gpt-image-2', 'gpt-image-2.5-sunburst', 'gpt-image-2.5-flare'):
            p = provider(model)
            for ratio in image_controls.options(p)['ratios']:
                x, y = map(int, ratio['value'].split(':'))
                for size in ratio['sizes'].values():
                    with self.subTest(model=model, ratio=ratio['value'], size=size):
                        w, h = map(int, size.split('x'))
                        self.assertEqual(w * y, h * x)
                        path, body, multipart = providers.build(p, job(size))
                        self.assertEqual(path, '/images/generations')
                        self.assertEqual(body['size'], size)
                        self.assertNotIn('aspect_ratio', body)
                        self.assertFalse(multipart)

    def test_social_sizes(self):
        self.assertEqual(image_controls.dimensions('9:16', 'standard'), '864x1536')
        self.assertEqual(image_controls.dimensions('16:9', 'large'), '2048x1152')
        self.assertEqual(image_controls.dimensions('9:16', 'ultra'), '2160x3840')

    def test_bad_sizes_rejected_before_requests(self):
        for size in ('1080x1920', '512x512', '4096x4096', '3840x3840', '3072x512', '0x1024', 'wrong'):
            with self.subTest(size=size), self.assertRaises(ValueError):
                providers.build(provider(), job(size))

    def test_legacy_sizes_remain_model_specific(self):
        for model, allowed in [('gpt-image-1', '1536x1024'), ('dall-e-2', '512x512'), ('dall-e-3', '1792x1024')]:
            p = provider(model)
            self.assertEqual(image_controls.options(p)['mode'], 'fixed')
            providers.build(p, job(allowed))
            with self.assertRaises(ValueError):
                providers.build(p, job('864x1536'))

    def test_quality_format_compression_and_count_reach_native_body(self):
        params = {'quality': 'max', 'n': 3, 'output_format': 'webp', 'output_compression': 65, 'background': 'transparent'}
        _, body, _ = providers.build(provider(), job('864x1536', **params))
        for key, value in params.items():
            self.assertEqual(body[key], value)
        with self.assertRaises(ValueError):
            providers.build(provider('gpt-image-2'), job(quality='max'))

    def test_edits_keep_advanced_options_and_file_parts(self):
        p = provider()
        j = job('2048x1152', quality='xhigh', output_format='jpeg', output_compression=80)
        j['input_assets'] = {'references': ['fixture-upload']}
        with patch('uploads.get', return_value={}), patch('uploads.binary', return_value=({'filename': 'ref.png', 'mime': 'image/png'}, b'fixture')):
            path, body, multipart = providers.build(p, j)
        self.assertEqual(path, '/images/edits')
        self.assertTrue(multipart)
        self.assertEqual(body['output_compression'], 80)
        self.assertEqual(body['image[]'][0].raw, b'fixture')

    def test_format_constraints_and_types(self):
        for params in ({'output_compression': 10}, {'output_format': 'gif'},
                       {'output_format': 'jpeg', 'background': 'transparent'},
                       {'output_format': 'webp', 'output_compression': True},
                       {'output_format': 'webp', 'output_compression': 101},
                       {'output_format': 'webp', 'output_compression': 12.5}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                providers.build(provider(), job(**params))
        for compression in (0, 100):
            providers.build(provider(), job(output_format='jpeg', output_compression=compression))
        with self.assertRaises(ValueError):
            providers.build(provider(extra={'background': 'transparent'}), job(output_format='jpeg'))

    def test_unsupported_native_controls_remain_blocked(self):
        for key, value in [('seed', 123), ('negative_prompt', 'blur'), ('strength', 0.5)]:
            with self.assertRaises(ValueError):
                providers.build(provider(), job(**{key: value}))

    def test_native_aspect_adapters(self):
        gemini = provider('gemini-3-pro-image-preview', 'gemini')
        _, body, _ = providers.build(gemini, job(aspect_ratio='9:16', resolution='2K'))
        self.assertEqual(body['generationConfig']['imageConfig'], {'aspectRatio': '9:16', 'imageSize': '2K'})
        self.assertNotIn('size', body)
        mini = provider('image-01-live', 'minimax_image')
        self.assertNotIn('21:9', [r['value'] for r in image_controls.options(mini)['ratios']])

    def test_custom_mapping_still_required_and_typed(self):
        p = provider('private-image', 'custom', custom={'submit_path': '/create',
            'body': {'prompt': '{{prompt}}', 'compression': '{{output_compression}}'},
            'capabilities': {'output_compression': True}})
        _, body, _ = providers.build(p, job(output_compression=0))
        self.assertEqual(body['compression'], 0)
        p['custom']['body'].pop('compression')
        with self.assertRaises(ValueError):
            providers.build(p, job(output_compression=0))

    def test_public_metadata_has_options_without_secret(self):
        data = storage.public_provider(provider(secret='not-a-real-key'))
        self.assertNotIn('secret', data)
        self.assertEqual(len(data['image_controls']['ratios']), 13)
        self.assertTrue(data['capabilities']['output_format'])


if __name__ == '__main__':
    unittest.main()
