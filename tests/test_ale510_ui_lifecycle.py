"""Exercise the shared lifecycle exception without suppressing ordinary navigation."""
import json
from pathlib import Path
import subprocess
import unittest


class BiographyDownloadLifecycleTests(unittest.TestCase):
    def test_attachment_forms_skip_navigation_feedback_but_normal_get_still_loads(self):
        source=Path(__file__).resolve().parents[1]/'backend/app/static/transition_lifecycle.js'
        runner=r'''
const fs=require('fs');
const listeners={}; const messages=[];
global.Element=class {};
global.HTMLFormElement=class extends Element {
 constructor(method,attributes=[]){super();this.method=method;this.dataset={};this.attributes=attributes;}
 matches(selector){return this.attributes.some(a=>selector.split(',').map(s=>s.trim()).includes(`[${a}]`));}
};
global.window=global;
window.location={href:'http://localhost/biographies',origin:'http://localhost'};
window.addEventListener=()=>{};
window.FedorinovWriteFeedback={showStatus:m=>messages.push(m)};
global.document={documentElement:{dataset:{}},querySelector:()=>null,addEventListener:(t,f)=>listeners[t]=f};
eval(fs.readFileSync(process.argv[1],'utf8'));
const send=form=>listeners.submit({target:form,defaultPrevented:false});
send(new HTMLFormElement('get',['data-no-transition']));
const afterDownload={messages:[...messages],pending:document.documentElement.dataset.navigationPending||null};
send(new HTMLFormElement('post'));
const afterPost=[...messages];
send(new HTMLFormElement('get'));
process.stdout.write(JSON.stringify({afterDownload,afterPost,afterGet:messages,pending:document.documentElement.dataset.navigationPending}));
'''
        result=subprocess.run(['node','-e',runner,str(source)],check=True,text=True,capture_output=True)
        self.assertEqual(json.loads(result.stdout),{'afterDownload':{'messages':[],'pending':None},'afterPost':[],
            'afterGet':['Загружаем…'],'pending':'true'})
