"""E9M unified presentation source/provenance and workload-isolation tests."""
from __future__ import annotations
import csv
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

from democracy_mrta.diagnostics import ProtocolError
from experiments.plot_e9m_unified_comparison import (
    LEGACY_METHODS, NEW_METHODS, validate_legacy_source,
    validate_e9m_formal_source, summarize_formal_e9m,
    render_unified_svg, write_unified_outputs, file_sha256, git_blob_sha,
    verify_corrected_git_source,
)


class TestE9MUnifiedComparison(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.old=self.base/'old.csv'
        keys=['N','e9l_successes']
        for name,t,b,color in LEGACY_METHODS:
            keys += [t,b]
        keys=list(dict.fromkeys(keys))
        with self.old.open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=keys)
            writer.writeheader()
            for n in range(5,101,5):
                row={'N':n,'e9l_successes': 78 if n==100 else 100}
                for j,(label,t,b,c) in enumerate(LEGACY_METHODS):
                    row[t]=n/10+j
                    row[b]=n*500+j*100
                writer.writerow(row)
        self.new=self.base/'new'
        self.new.mkdir()
        self.raw=self.new/'per_seed_e9m.csv'
        fields=['seed','method','success','rounds','guard_censored','covered_tasks',
                'missing_tasks','duplicate_tasks','capacity_violations','sender_bytes',
                'sender_sends','receiver_attempts','receiver_delivered','receiver_dropped',
                'allocation_ms','total_distance_m','makespan_s','discounted_reward',
                'per_phase_ledger','routes_json']
        ledger={'task_announcement':{'sender_sends':1,'sender_bytes':100,
                'receiver_attempts':25,'receiver_delivered':25,'receiver_dropped':0}}
        routes=[list(range(i*4,(i+1)*4)) for i in range(25)]
        with self.raw.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=fields)
            w.writeheader()
            for seed in range(100):
                for method,_,_ in NEW_METHODS:
                    w.writerow(dict(seed=seed,method=method,success=1,
                        rounds=100 if method=='voting_multitask' else 15,
                        guard_censored=0,covered_tasks=100,missing_tasks=0,
                        duplicate_tasks=0,capacity_violations=0,sender_bytes=100,
                        sender_sends=1,receiver_attempts=25,receiver_delivered=25,
                        receiver_dropped=0,allocation_ms=5000 if method=='cbba' else 45000,
                        total_distance_m=2000,makespan_s=100,discounted_reward=5000,
                        per_phase_ledger=json.dumps(ledger),routes_json=json.dumps(routes)))
        self.summary=self.new/'summary_e9m.csv'
        self.summary.write_text('method,completed\ncbba,100\nvoting_multitask,100\n',encoding='utf-8')
        self.manifest={'study':'E9M','git_sha':'a'*40,'configuration':{
           'robots':25,'tasks':100,'capacity':4,'loss':0.30,
           'seeds':list(range(100)),'methods':['voting_multitask','cbba']},
           'sha256':{'per_seed_e9m.csv':file_sha256(self.raw),
                     'summary_e9m.csv':file_sha256(self.summary)}}
        self.manifest_file=self.new/'manifest.json'
        self._save_manifest()

    def _save_manifest(self):
        self.manifest_file.write_text(json.dumps(self.manifest),encoding='utf-8')

    def test_legacy_data_provenance_and_exact_grid(self):
        original_hash=git_blob_sha(self.old)
        rows=validate_legacy_source(self.old,expected_blob=original_hash)
        self.assertEqual(len(rows),20)
        self.assertEqual(rows[-1]['N'],100)
        with self.assertRaises(ProtocolError) as cm:
            validate_legacy_source(self.old, expected_blob='bad')
        self.assertEqual(cm.exception.diagnostic.code,'E9M_LEGACY_SOURCE_IDENTITY')

    @mock.patch('experiments.plot_e9m_unified_comparison.subprocess.run')
    def test_paired_formal_metrics_and_single_figure(self, run):
        run.return_value.returncode=0
        rows,metadata=validate_e9m_formal_source(self.new,repo_root=self.base)
        self.assertEqual(len(rows),200)
        result=summarize_formal_e9m(rows)
        self.assertEqual(result['cbba']['mean_all_seed_stop_s'],5.0)
        self.assertEqual(result['voting_multitask']['mean_all_seed_stop_s'],45.0)
        self.assertEqual(result['cbba']['completion_pct'],100.0)
        legacy=validate_legacy_source(self.old,expected_blob=git_blob_sha(self.old))
        svg=render_unified_svg(legacy,result,git_sha=metadata['git_sha'])
        self.assertEqual(svg.count('<svg '),1)
        self.assertEqual(ET.fromstring(svg).tag, '{http://www.w3.org/2000/svg}svg')
        self.assertIn('different scene size',svg.lower())
        self.assertIn('E9I / E9J / E9L',svg)
        self.assertIn('25 robots / 100 tasks / cap4',svg)
        output=self.base/'plot'
        svgfile,csvfile=write_unified_outputs(output,legacy,result,metadata,self.old,self.new)
        self.assertTrue(svgfile.exists())
        with csvfile.open(encoding="utf-8", newline="") as stream:
            rows=list(csv.DictReader(stream))
        self.assertEqual(len(rows),5)
        self.assertEqual({r['cohort'] for r in rows},
                         {'E9I/J/L legacy single-task','E9M multi-task capacity4'})
        self.assertEqual(rows[2]['completed'],'78')
        self.assertEqual(rows[-1]['mean_success_makespan_s'],'100.0')
        with self.assertRaises(ProtocolError):
            write_unified_outputs(output,legacy,result,metadata,self.old,self.new)

    @mock.patch('experiments.plot_e9m_unified_comparison.subprocess.run')
    def test_failed_seed_kept_and_missing_seed_rejected(self, run):
        run.return_value.returncode=0
        text=self.raw.read_text()
        self.raw.write_text(text.replace('voting_multitask,1,100,0,100',
              'voting_multitask,0,100,1,100',1),encoding='utf-8')
        self.manifest['sha256']['per_seed_e9m.csv']=file_sha256(self.raw)
        self._save_manifest()
        rows,_=validate_e9m_formal_source(self.new,repo_root=self.base)
        stats=summarize_formal_e9m(rows)
        self.assertEqual(stats['voting_multitask']['completed'],99)
        with self.assertRaises(ProtocolError):
            self.raw.write_text('\n'.join(self.raw.read_text().splitlines()[:-1])+'\n')
            self.manifest['sha256']['per_seed_e9m.csv']=file_sha256(self.raw)
            self._save_manifest()
            validate_e9m_formal_source(self.new,repo_root=self.base)

    @mock.patch('experiments.plot_e9m_unified_comparison.subprocess.run')
    def test_false_success_route_duplicates_are_rejected(self, run):
        run.return_value.returncode=0
        lines=self.raw.read_text().splitlines()
        reader=csv.DictReader(lines)
        fields=reader.fieldnames
        records=list(reader)
        routes=json.loads(records[0]['routes_json'])
        routes[1][0]=routes[0][0]  # duplicate task, despite metadata saying feasible
        records[0]['routes_json']=json.dumps(routes)
        with self.raw.open('w',newline='',encoding='utf-8') as out:
            writer=csv.DictWriter(out,fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
        self.manifest['sha256']['per_seed_e9m.csv']=file_sha256(self.raw)
        self._save_manifest()
        with self.assertRaises(ProtocolError) as error:
            validate_e9m_formal_source(self.new,repo_root=self.base)
        self.assertEqual(error.exception.diagnostic.code,'E9M_INVALID_ORIGINAL_RAW_ROW')

    @mock.patch('experiments.plot_e9m_unified_comparison.subprocess.run')
    def test_sha_mismatch_and_old_code_rejected(self, run):
        run.return_value.returncode=0
        self.raw.write_text(self.raw.read_text()+'corruption\n')
        with self.assertRaises(ProtocolError) as cm:
            validate_e9m_formal_source(self.new,repo_root=self.base)
        self.assertEqual(cm.exception.diagnostic.code,'E9M_EVIDENCE_SHA_MISMATCH')
        run.return_value.returncode=1
        with self.assertRaises(ProtocolError) as cm:
            verify_corrected_git_source('f347e260d9d76c347859dbc691de6d724946d9de',repo_root=self.base)
        self.assertEqual(cm.exception.diagnostic.code,'E9M_UNCORRECTED_VOTE_SOURCE')


if __name__=='__main__':
    unittest.main()
