"""Verified E9E evidence-to-SVG report: no fabricated measurements."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from democracy_mrta.diagnostics import ProtocolError
from experiments.plot_e9d_results import (
    plot_e9d_results, load_e9d_plot_evidence,
    verify_e9d_plot_provenance, prepare_e9d_figure_root,
)
from experiments.run_e9d_natural_loss import run_e9d_natural_loss


class E9EFigureTests(unittest.TestCase):
    def run_raw(self, root, losses=(0.0,0.5,1.0)):
        with patch(
            "experiments.run_e9d_natural_loss.read_retirement_revision",
            return_value="test-e9e-dense-source",
        ):
            return run_e9d_natural_loss(
                robots=5,tasks=3,seeds=2,first_seed=0,
                loss_probabilities=losses,
                cbaa_safety_round_limit=15,
                democracy_safety_round_limit=20,
                latency_mode="constant",allow_download=False,
                output_root=root,
            )

    def test_figures_only_from_completed_SHA_verified_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"e9d_dense_figure_input"
            self.run_raw(root)
            out=plot_e9d_results(run_root=root)
            self.assertEqual(out,root/"figures"/"figure_manifest.json")
            record=json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(record["source_git_sha"],"test-e9e-dense-source")
            self.assertEqual(record["seeds"],2)
            self.assertEqual(record["loss_probabilities"],[0.0,0.5,1.0])
            expected={
                "e9d_full_success.svg","e9d_sender_payload.svg",
                "e9d_cbaa_agreement_vs_stop.svg",
                "e9d_guard_censoring.svg",
            }
            self.assertEqual(set(record["figure_sha256"]),expected)
            for name in expected:
                image=root/"figures"/name
                self.assertEqual(
                    record["figure_sha256"][name],
                    hashlib.sha256(image.read_bytes()).hexdigest(),
                )
                document=ET.parse(image)
                self.assertEqual(document.getroot().tag,
                    "{http://www.w3.org/2000/svg}svg")
                self.assertGreater(image.stat().st_size,2000)

    def test_zoom_figures_use_dense_measured_points_not_interpolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"e9d_dense_zoom"
            levels=(0.0,0.4,0.45,0.5,0.55,0.6,0.65,0.85,0.9,0.95,0.98)
            self.run_raw(root,levels)
            plot_e9d_results(run_root=root)
            for name in ("e9d_democracy_transition.svg",
                         "e9d_cbaa_high_loss_zoom.svg"):
                svg=(root/"figures"/name).read_text(encoding="utf-8")
                self.assertIn("<polyline",svg)
                self.assertIn("<circle",svg)
                self.assertIn("Packet loss probability",svg)
            record=json.loads((root/"figures"/"figure_manifest.json").read_text())
            self.assertEqual(record["loss_probabilities"],list(levels))
            self.assertEqual(len(record["figure_sha256"]),6)

    def test_missing_raw_rejected_before_any_picture_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"e9d_empty"
            root.mkdir()
            with self.assertRaises(ProtocolError) as cm:
                plot_e9d_results(run_root=root)
            d=cm.exception.diagnostic
            self.assertEqual((d.owner,d.function,d.category,d.code),(
                "experiments.plot_e9d_results","load_e9d_plot_evidence",
                "dependency","E9E_PLOT_EVIDENCE_MISSING",
            ))
            self.assertFalse((root/"figures").exists())

    def test_modified_source_detected_by_raw_sha_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"e9d_changed_raw"
            self.run_raw(root)
            raw=root/"per_seed_loss_method.csv"
            raw.write_bytes(raw.read_bytes()+b"\n")
            with self.assertRaises(ProtocolError) as cm:
                plot_e9d_results(run_root=root)
            self.assertEqual(cm.exception.diagnostic.code,
                             "E9E_PLOT_SHA256_MISMATCH")
            self.assertFalse((root/"figures").exists())

    def test_manifest_hash_update_cannot_hide_wrong_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"e9d_wrong_summary"
            self.run_raw(root)
            summary=root/"summary_by_loss.csv"
            with summary.open(newline="",encoding="utf-8") as handle:
                rows=list(csv.DictReader(handle))
            rows[0]["mean_total_sender_bytes"]="123456789"
            with summary.open("w",newline="",encoding="utf-8") as handle:
                writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            manifest_path=root/"manifest.json"
            manifest=json.loads(manifest_path.read_text())
            manifest["sha256"]["summary_by_loss.csv"]=hashlib.sha256(
                summary.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest),encoding="utf-8")
            with self.assertRaises(ProtocolError) as cm:
                plot_e9d_results(run_root=root)
            d=cm.exception.diagnostic
            self.assertEqual((d.function,d.category,d.code),(
                "verify_e9d_plot_provenance",
                "contract","E9E_PLOT_RAW_SUMMARY_CONTRACT",
            ))

    def test_no_overwrite_existing_figures_or_any_raw_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"e9d_no_overwrite"
            self.run_raw(root)
            raw=root/"per_seed_loss_method.csv"
            checksum=hashlib.sha256(raw.read_bytes()).hexdigest()
            plot_e9d_results(run_root=root)
            with self.assertRaises(ProtocolError) as cm:
                plot_e9d_results(run_root=root)
            self.assertEqual(cm.exception.diagnostic.code,
                             "E9E_PLOT_OUTPUT_NOT_EMPTY")
            self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(),checksum)


if __name__ == "__main__":
    unittest.main()
