"""Bounded institutional HTML reader. No bypass, private DB, or blind URL guessing."""
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin,urlparse,quote
from urllib.request import Request,HTTPRedirectHandler,build_opener
from urllib.error import HTTPError
from urllib.robotparser import RobotFileParser
from html.parser import HTMLParser

MUSEUM_HOST='xn----7sbajiedzjdfe3ac7bmi.xn--p1ai'
BASE='https://'+MUSEUM_HOST
USER_AGENT='BiographyResearchPilot/0.1'


class NoAutomaticRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,message,headers,new_url):
        # Keep one ledger operation = one GET, and never leak a query off-host.
        return None


def urlopen(request,timeout):
    return build_opener(NoAutomaticRedirect()).open(request,timeout=timeout)


class TextAndLinks(HTMLParser):
    def __init__(self):
        super().__init__();self.text=[];self.links=[];self.ignore=0;self.anchor=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in ('script','style','noscript'):self.ignore+=1
        if tag=='a' and attrs.get('href'):self.anchor=[attrs['href'],[]]
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript'):self.ignore=max(0,self.ignore-1)
        if tag=='a' and self.anchor:
            self.links.append((self.anchor[0],' '.join(self.anchor[1])));self.anchor=None
    def handle_data(self,data):
        if not self.ignore:
            value=' '.join(data.split())
            if value:self.text.append(value)
            if self.anchor and value:self.anchor[1].append(value)


class MuseumReader:
    def __init__(self,evidence_dir,max_requests=6):
        self.root=Path(evidence_dir);self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.max_requests=max_requests;self.delay=10
        history=self.root/'http_evidence.json'
        self.requests=json.loads(history.read_text()) if history.exists() else []
        self.last=time.monotonic()-max(0,time.time()-history.stat().st_mtime) if history.exists() else 0
        robot_records=[(i,r) for i,r in enumerate(self.requests,1) if r['url']==BASE+'/robots.txt' and r['status']==200]
        cached=self.root/f'source-{robot_records[-1][0]:02}.html' if robot_records else None
        if cached and cached.exists() and time.time()-cached.stat().st_mtime<600:
            robots={'status':200,'text':cached.read_text()}
        else:robots=self._get(BASE+'/robots.txt',check_robots=False)
        if robots['status'] not in (200,404):raise ValueError('STOP: robots unavailable/disallowed')
        self.robots=RobotFileParser();self.robots.parse(robots['text'].splitlines())
        delay=re.search(r'(?im)^Crawl-delay:\s*(\d+)',robots['text'])
        if delay:self.delay=max(10,int(delay.group(1)))
    def _get(self,url,check_robots=True):
        if urlparse(url).hostname!=MUSEUM_HOST:raise ValueError('Institutional host only')
        if len(self.requests)>=self.max_requests:raise ValueError('STOP: HTTP request budget exhausted')
        if check_robots and not self.robots.can_fetch(USER_AGENT,url):raise ValueError('STOP: robots disallows URL')
        time.sleep(max(0,self.delay-(time.monotonic()-self.last)))
        self.last=time.monotonic()
        # Preserve already form-encoded '+' (space), '%' and query delimiters.
        safe_url=quote(url,safe=':/?=&%#+')
        try:
            with urlopen(Request(safe_url,headers={'User-Agent':USER_AGENT,'Accept':'text/html,text/plain'}),timeout=20) as response:
                body=response.read(2_000_001)
                if len(body)>2_000_000:raise ValueError('STOP: source size budget exceeded')
                encoding=response.headers.get_content_charset() or 'utf-8'
                record={'url':url,'resolved_url':response.url,'status':response.status,'content_type':response.headers.get('Content-Type'),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
                text=body.decode(encoding,errors='replace')
        except HTTPError as error:
            record={'url':url,'resolved_url':error.url,'status':error.code,'bytes':0,'location':error.headers.get('Location') if error.headers else None};body=b'';text=''
        if urlparse(record['resolved_url']).hostname!=MUSEUM_HOST:raise ValueError('STOP: cross-host redirect')
        self.requests.append(record)
        name=f'source-{len(self.requests):02}'
        if body:
            p=self.root/(name+'.html');p.write_bytes(body);p.chmod(0o600)
        p=self.root/'http_evidence.json';p.write_text(json.dumps(self.requests,ensure_ascii=False,indent=2));p.chmod(0o600)
        if record['status'] in (401,403,429):raise ValueError('STOP: authentication/access/throttling; no retry or bypass')
        if re.search(r'(?i)captcha|verify you are human|access denied',text):raise ValueError('STOP: human/access challenge')
        return {**record,'text':text}
    def read(self,url):
        record=self._get(url);parser=TextAndLinks();parser.feed(record['text'])
        record['plain_text']='\n'.join(parser.text)
        record['links']=[(urljoin(url,href),label) for href,label in parser.links if urlparse(urljoin(url,href)).hostname==MUSEUM_HOST]
        return record
