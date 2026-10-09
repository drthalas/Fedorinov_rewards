import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode,parse_qs,urlparse
from unittest.mock import patch
from direct_source import MuseumReader,BASE,MUSEUM_HOST
from research import validate


class Response:
    status=200
    def __init__(self,url,body):self.url=url;self.body=body;self.headers=self
    def get_content_charset(self):return 'utf-8'
    def get(self,key):return 'text/html; charset=utf-8'
    def read(self,size):return self.body
    def __enter__(self):return self
    def __exit__(self,*args):pass


class DirectSourceTests(unittest.TestCase):
    def fetch(self,request,timeout):
        body=b'Crawl-delay: 10\n' if request.full_url.endswith('/robots.txt') else b'<html><p>synthetic public fact</p></html>'
        return Response(request.full_url,body)
    def test_query_semantics_and_persistent_budget(self):
        with tempfile.TemporaryDirectory() as folder,patch('direct_source.urlopen',side_effect=self.fetch),patch('direct_source.time.sleep') as wait:
            reader=MuseumReader(folder,max_requests=2)
            url=BASE+'/?'+urlencode({'s':'Тестовый Персонаж','post_type':'product'})
            result=reader.read(url)
            self.assertEqual(parse_qs(urlparse(result['resolved_url']).query),parse_qs(urlparse(url).query))
            self.assertTrue(any(call.args[0]>0 for call in wait.call_args_list))
            resumed=MuseumReader(folder,max_requests=2)
            self.assertEqual(len(resumed.requests),2)
            with self.assertRaisesRegex(ValueError,'budget'):resumed.read(BASE+'/electronic-database/synthetic/')
    def test_robots_denial(self):
        def deny(request,timeout):return Response(request.full_url,b'User-agent: *\nDisallow: /electronic-database/\n')
        with tempfile.TemporaryDirectory() as folder,patch('direct_source.urlopen',side_effect=deny),patch('direct_source.time.sleep'):
            reader=MuseumReader(folder)
            with self.assertRaisesRegex(ValueError,'robots'):reader.read(BASE+'/electronic-database/synthetic/')
    def test_only_institution_host_and_card_citations(self):
        with tempfile.TemporaryDirectory() as folder,patch('direct_source.urlopen',side_effect=self.fetch),patch('direct_source.time.sleep'):
            reader=MuseumReader(folder)
            with self.assertRaisesRegex(ValueError,'host'):reader.read('https://unapproved.example/')
        record={'person_id':'synthetic','biography':'','status':'Требует проверки','source_urls':[BASE+'/electronic-database/synthetic/'],'identity':[],'evidence':[],'notes':''}
        validate(record,{'person_id':'synthetic'})
        record['source_urls']=[BASE+'/?s=synthetic']
        with self.assertRaisesRegex(ValueError,'domain'):validate(record,{'person_id':'synthetic'})


if __name__=='__main__':unittest.main()
