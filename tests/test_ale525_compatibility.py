"""Production parser/classifier and HMAC guard on genuine synthetic TEMP exports."""
from io import BytesIO
from unittest.mock import patch

from openpyxl import load_workbook
import pytest

from backend.app.services import biography_enrichment as bio
from backend.app.services import enrichment_workflow as workflow
from backend.app.services.enrichment_compatibility import inspect_final
from scripts.check_enrichment_compatibility import fixture_database, preflight, researched_fixture


@pytest.fixture
def glory(tmp_path):
    settings = fixture_database(tmp_path, ('Орден Славы 1 степени',))
    with patch.object(bio, '_state_path', return_value=tmp_path / 'state'):
        yield settings, bio.export_workbook(settings, '1/1/1/1')


def test_preflight_runs_export_to_preview_for_glory_and_hsu_set(glory, tmp_path):
    _, original = glory
    result = preflight(original)
    assert result['status'] == 'PREFLIGHT_PASS'
    assert {case['case'] for case in result['cases']} >= {'A', 'B', 'wrong_degree', 'wrong_number', 'wrong_digest'}
    hsu_root = tmp_path / 'hsu'
    hsu_root.mkdir()
    settings = fixture_database(hsu_root, ('Герой Советского Союза', 'Герой Советского Союза II'))
    result = preflight(bio.export_workbook(settings, '1/1/1'))
    assert result['status'] == 'PREFLIGHT_PASS'


@pytest.mark.parametrize('variant,fields,code', [
    ('A', {'biography', 'fio'}, 'verified'),
    ('B', {'biography'}, 'verified'),
    ('wrong_degree', set(), 'serial_evidence'),
    ('wrong_number', set(), 'serial_evidence'),
    ('wrong_award', set(), 'serial_evidence'),
    ('wrong_digest', set(), 'evidence_digest'),
    ('unknown_version', set(), 'unsupported_version'),
])
def test_same_admissions_in_online_temp_preview_and_offline_final(glory, variant, fields, code):
    settings, original = glory
    final = researched_fixture(original, 'glory-i', variant)
    before = settings.rewards_db_path.read_bytes()
    token, _ = bio.preview(settings, final)
    view = workflow.workspace(settings, token)
    assert {key for key, count in view['totals'].items() if count} == fields
    report = inspect_final(final, original)
    assert set(report['rows'][0]['fields']) == fields
    assert report['rows'][0]['code'] == code
    assert (report['status'] == 'OFFLINE_COMPATIBLE') == bool(fields)
    assert report['hmac'] == report['stale'] == 'not_checked'
    assert settings.rewards_db_path.read_bytes() == before


def test_zero_admission_blocks_final_and_unknown_selected_category(glory, tmp_path):
    _, original = glory
    assert 'zero_bio_admission' in inspect_final(original, original)['blockers']
    root = tmp_path / 'unsupported'
    root.mkdir()
    settings = fixture_database(root, ('Орден Славы 2 степени',))
    original = bio.export_workbook(settings, '1/1/1/1')
    with pytest.raises(bio.ValidationError, match='неподдерживаемая категория'):
        preflight(original)
    final = researched_fixture(original, 'glory-i', 'A')
    assert 'unsupported_contract' in inspect_final(final, original)['blockers']


def test_online_import_never_trusts_offline_signature_shape(glory):
    settings, original = glory
    book = load_workbook(BytesIO(researched_fixture(original, 'glory-i', 'A')))
    book[bio.METADATA_SHEET].cell(2, bio.HEADERS.index('snapshot_signature') + 1, '0' * 64)
    with BytesIO() as buffer:
        book.save(buffer)
        modified = buffer.getvalue()
    book.close()
    with pytest.raises(bio.ValidationError, match='подписи отличаются'):
        inspect_final(modified, original)
    token, _ = bio.preview(settings, modified)
    view = workflow.workspace(settings, token)
    assert view['fatal'] and view['eligible'] == 0
    assert view['guard_failures'][0]['code'] == 'signature_invalid'
