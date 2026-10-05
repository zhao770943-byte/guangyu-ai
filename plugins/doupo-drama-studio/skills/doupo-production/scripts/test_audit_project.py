import unittest
from argparse import Namespace
from audit_project import audit,read_project

class AuditTests(unittest.TestCase):
    def test_empty_project_is_blocked(self):
        r=audit({'phase':'draft','plan':None})
        self.assertEqual(r['metadata_blockers'],1)
        self.assertEqual(r['actual_picture_audio_review'],'not_performed_by_this_script')

    def test_private_fields_do_not_appear_in_report(self):
        r=audit({'id':'a'*32,'secret':'TOPSECRET','source':'PRIVATE CHAPTER','jobs':[{'status':'failed','error':'SECRET ERROR','prompt':'PRIVATE PROMPT'}]})
        self.assertNotIn('SECRET',str(r));self.assertNotIn('PRIVATE',str(r))
        self.assertEqual(r['jobs_failed'],1)

    def test_rejects_non_loopback_and_credentials(self):
        for url in ('https://example.com','http://user:password@localhost:8786','http://127.0.0.1:8786/v1'):
            with self.assertRaises(ValueError):read_project(Namespace(file=None,base_url=url,project_id='a'*32))

    def test_unapproved_image_still_blocks(self):
        p={'production_book':{'enabled':True},'plan':{'episodes':[{'id':'e1','shots':[{'id':'s1','asset_ids':[],'dialogue':''}]}]},'images':{'shot:e1:s1':'image-id'}}
        codes=[i['code'] for i in audit(p)['issues']]
        self.assertIn('storyboard_current_version_not_approved',codes);self.assertNotIn('storyboard_missing',codes)

if __name__=='__main__':unittest.main()
