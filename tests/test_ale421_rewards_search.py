import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
import unittest

from backend.app.repositories.guides import guide_cascade_data, guide_name_sort_key
from backend.app.repositories.legacy_rewards import (
    legacy_rewards_filter_cascade, legacy_rewards_filter_options,
    list_legacy_reward_person_group, normalized_legacy_rewards_filters,
)
from tests import test_legacy_rewards_filters as fixture


ROOT = Path(__file__).resolve().parents[1]


class RewardsSearchTests(unittest.TestCase):
    setUp = fixture.LegacyRewardsFilterTests.setUp
    tearDown = fixture.LegacyRewardsFilterTests.tearDown
    _create_db = fixture.LegacyRewardsFilterTests._create_db

    def test_names_are_canonically_sorted_without_changing_cascade_membership(self):
        with sqlite3.connect(self.db_path) as db:
            db.executemany('insert into guide_lev_3 values (?, ?, ?)', [
                (30, 1, 'Якорь'), (31, 1, 'ёлка'), (32, 1, 'Елка'),
                (33, 9, 'Янтарь'), (34, 9, 'алмаз'),
            ])
        baseline = guide_cascade_data(self.db_path)
        cascade = legacy_rewards_filter_cascade(self.db_path)
        self.assertEqual(cascade['names'], sorted(baseline['names'], key=guide_name_sort_key))
        self.assertEqual({k: v for k, v in cascade.items() if k != 'names'}, {k: v for k, v in baseline.items() if k != 'names'})
        for parent in (1, 9, 1):
            expected = [row for row in cascade['names'] if row['idl'] == parent]
            options = legacy_rewards_filter_options(self.db_path, normalized_legacy_rewards_filters(subcategory_id=parent))
            self.assertEqual(options['names'], expected)
            self.assertCountEqual(options['names'], [row for row in baseline['names'] if row['idl'] == parent])
        self.assertEqual(guide_cascade_data(self.db_path), baseline)

    def test_two_and_three_word_queries_keep_global_matching(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("update person set fio='Жуков Георгий Константинович' where id=1")
        for query in ('Жуков', 'Жуков Георгий', 'Жуков Георгий Константинович', '  Жуков Георгий  '):
            rows = list_legacy_reward_person_group(self.db_path, normalized_legacy_rewards_filters(), letter='А', query=query)
            self.assertEqual([row['id'] for row in rows], [1])

    @unittest.skipUnless(shutil.which('node'), 'node is not installed')
    def test_completed_search_never_rewrites_visible_whitespace(self):
        runner = r'''
const fs = require('fs');
const events = {}, timers = [], requests = [], renders = [];
let state = null;
const node = () => ({dataset:{}, attrs:{}, scrollTop:0, className:'',
 addEventListener(){}, setAttribute(k,v){this.attrs[k]=v;}, getAttribute(k){return this.attrs[k];},
 replaceWith(){renders.push(true);}, focus(){}});
const list=node(), workspace=node(), toolbar=node(), main=node(), title=node();
workspace.querySelector=()=>state;workspace.append=s=>{state=s;};
const input={value:'',dataset:{},listeners:{},addEventListener(k,v){this.listeners[k]=v;}};
const parts={'[data-person-list]':list,'[data-person-quick-search]':input,
 '[data-legacy-person-workspace]':workspace,'.legacy-toolbar':toolbar,'.legacy-main':main,'.legacy-person-list-title':title};
const layout={querySelector:s=>parts[s]||null,querySelectorAll:()=>[]};
global.HTMLElement=class{};
global.CustomEvent=class{constructor(type,init){this.type=type;this.detail=init&&init.detail;}};
global.window=global;
window.location={href:'http://127.0.0.1/legacy?tab=rewards',origin:'http://127.0.0.1',pathname:'/legacy',search:'?tab=rewards'};
window.history={replaceState(){},pushState(){}};window.addEventListener=()=>{};
window.setTimeout=(cb,delay)=>{if(delay===180)timers.push(cb);return timers.length;};
window.clearTimeout=()=>{};
window.fetch=async url=>{requests.push(new URL(url,window.location.origin).searchParams.get('person_q')||'');return {ok:true,text:async()=>'<html/>'};};
global.DOMParser=class{parseFromString(){return {querySelector:()=>layout};}};
global.document={
 addEventListener(k,v){events[k]=v;},
 dispatchEvent(e){if(events[e.type])events[e.type](e);},
 querySelector:s=>s==='[data-legacy-rewards-layout]'?layout:layout.querySelector(s),
 querySelectorAll:()=>[],
 createElement:()=>({dataset:{},setAttribute(){},remove(){state=null;}})
};
eval(fs.readFileSync(process.argv[2],'utf8'));events.DOMContentLoaded();
(async()=>{
 const values=['Жуков','Жуков ','Жуков Георгий','Жуков Георгий ','Жуков Георгий Константинович','Жуков  Георгий','Жуков Георг',' Жуков Георгий ',''];
 const actual=[];
 for(const value of values){input.value=value;input.listeners.input();timers.shift()();await new Promise(setImmediate);actual.push(input.value);}
 process.stdout.write(JSON.stringify({values,actual,requests,renders:renders.length}));
})().catch(e=>{console.error(e);process.exit(1)});
'''
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'search.js'
            path.write_text(runner, encoding='utf-8')
            result = subprocess.run(['node', str(path), str(ROOT/'backend/app/static/legacy_rewards.js')], check=True, capture_output=True, text=True)
        evidence = json.loads(result.stdout)
        self.assertEqual(evidence['actual'], evidence['values'])
        self.assertEqual(evidence['requests'], [value.strip() for value in evidence['values']])
        self.assertGreaterEqual(evidence['renders'], len(evidence['values']))


if __name__ == '__main__':
    unittest.main()
