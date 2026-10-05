"""Distribution must exclude local production notes even when present on disk."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_windows import public_documentation


class ReleaseDocumentTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / 'scripts').mkdir()
        (self.root / 'docs').mkdir()
        (self.root / 'docs' / 'guide.md').write_text('Public guide', encoding='utf-8')
        (self.root / 'docs' / 'private-trial.md').write_text('Local trial', encoding='utf-8')

    def manifest(self, entries):
        (self.root / 'scripts' / 'public-documents.json').write_text(json.dumps(entries), encoding='utf-8')

    def test_unlisted_local_notes_are_not_distributed(self):
        self.manifest(['docs/guide.md'])
        self.assertEqual(public_documentation(self.root), [(self.root / 'docs' / 'guide.md').resolve()])

    def test_missing_public_document_stops_build(self):
        self.manifest(['docs/missing.md'])
        with self.assertRaises(FileNotFoundError):
            public_documentation(self.root)

    def test_paths_outside_docs_or_non_documents_are_rejected(self):
        for entry in ('../outside.md', 'data/config.md', 'docs/../data/config.md', 'docs/private.sqlite3'):
            with self.subTest(entry=entry):
                self.manifest([entry])
                with self.assertRaises(ValueError):
                    public_documentation(self.root)

    def test_repository_manifest_resolves(self):
        self.assertTrue(public_documentation())


if __name__ == '__main__':
    unittest.main()
