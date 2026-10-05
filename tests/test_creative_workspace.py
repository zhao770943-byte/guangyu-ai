"""Durable creative inputs and grouping, without external generation."""
import base64
import io
import unittest
from PIL import Image
import test_storyboards
import storage


class CreativeWorkspaceTests(unittest.TestCase):
    setUp = test_storyboards.StoryboardTests.setUp
    api = test_storyboards.StoryboardTests.api
    finish = test_storyboards.StoryboardTests.finish

    def image(self):
        b=io.BytesIO();Image.new('RGB',(80,120),'green').save(b,format='PNG')
        return self.api('/api/uploads',{'name':'input.png','data_base64':base64.b64encode(b.getvalue()).decode()},201)

    def draft(self):
        a=self.image()
        return {'title':'镜头一','kind':'image','provider_id':self.provider['id'], 'draft':{'prompt':'a person','mode':'reference','size':'1024x1536','seconds':4,'assets':{'references':[a['id']]},'parameters':{'quality':'high'}}}

    def test_draft_roundtrip_version_conflict_and_shared_material_delete(self):
        body=self.draft();d=self.api('/api/drafts/save',body)
        self.assertEqual(d['draft']['assets']['references'],body['draft']['assets']['references'])
        m=self.api('/api/materials/save',{'title':'reference','upload_id':d['assets'][0]['id']})
        self.api('/api/materials/delete',{'id':m['id'],'version':m['version']})
        again=self.api('/api/workspace')['drafts'][0]
        self.assertEqual(again['assets'][0]['id'],d['assets'][0]['id'])
        body.update(id=d['id'],version=d['version'],title='renamed')
        self.api('/api/drafts/save',body)
        self.api('/api/drafts/save',body,400)
        self.assertEqual(len(self.api('/api/workspace')['drafts']),1)
        self.assertFalse(self.mock_dispatch.called)

    def test_reject_missing_asset_extra_parameters_and_wrong_provider(self):
        body=self.draft();body['draft']['assets']['references']=['../bad']
        self.api('/api/drafts/save',body,400)
        body=self.draft();body['draft']['parameters']={'api_key':'no'}
        self.api('/api/drafts/save',body,400)
        body=self.draft();body['kind']='video'
        self.api('/api/drafts/save',body,400)
        self.assertEqual(self.api('/api/workspace')['drafts'],[])

    def test_collection_assignment_transaction_and_job_request_metadata(self):
        c=self.api('/api/collections/save',{'title':'film'})
        c2=self.api('/api/collections/save',{'title':'film2'})
        j=self.api('/api/jobs',{'provider_id':self.provider['id'],'prompt':'test','collection_id':c['id']},202)
        self.assertEqual(j['collection_id'],c['id']);self.finish(j['id'])
        self.api('/api/collections/assign',{'collection_id':c['id'],'job_ids':[j['id']]})
        self.api('/api/collections/assign',{'collection_id':c2['id'],'job_ids':[j['id'],'missing']},400)
        self.assertEqual(self.api('/api/workspace')['assignments'][j['id']],c['id'])
        self.api('/api/collections/assign',{'collection_id':c2['id'],'job_ids':[j['id']]})
        self.assertEqual(self.api('/api/workspace')['assignments'][j['id']],c2['id'])
        self.api('/api/jobs',{'provider_id':self.provider['id'],'prompt':'test','collection_id':'unknown'},400)

    def test_automatic_project_collections_and_private_fields_excluded(self):
        p=self.api('/api/visual-projects/save',{'title':'project','nodes':[]})
        data=self.api('/api/workspace')
        self.assertIn('visual:'+p['id'],[x['id'] for x in data['collections']])
        self.assertNotIn('providers',data)
        self.assertNotIn('secret',str(data))
        j=self.api('/api/jobs',{'provider_id':self.provider['id'],'prompt':'test','collection_id':'visual:'+p['id']},202)
        self.assertEqual(j['collection_id'],'visual:'+p['id'])


if __name__=='__main__':unittest.main()
