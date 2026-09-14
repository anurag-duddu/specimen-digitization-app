"""Independent synthetic accounting probes; no production/native clients."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest
import release_admission
import specimen_digitization.release_budget as policy
from test_approved_release_budget import successor
from test_release_cost_ledger_v2 import change_snapshot

# The canonical `uv run pytest` entry point does not add the repository root to
# sys.path. Load the sibling QA script explicitly, like other CI script tests.
spec = importlib.util.spec_from_file_location(
    "review_budget_acceptance", Path(__file__).resolve().parents[1] / "qa/live/acceptance.py"
)
assert spec and spec.loader
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)

def qa_budget(root):
    evidence=root/'cost-category.txt'
    evidence.write_text('Synthetic cost evidence, not billing.')
    descriptor={'path':evidence.name,'sha256':hashlib.sha256(evidence.read_bytes()).hexdigest()}
    return {'currency':'USD','authorization_reference':'synthetic approved projection',
            'scope':'entire_first_ten_all_sessions_and_retries','mode':'live',
            'categories':{k:{'reconciled':True,'artifacts':[descriptor]} for k in acceptance.COST_CATEGORIES}}



def sha(raw):return hashlib.sha256(raw.encode()).hexdigest()

def projection(root, ledger, packet):
    budget=qa_budget(root)
    raw=json.dumps(ledger)
    (root/'current-ledger.json').write_text(raw)
    budget.update(schema_version='cohort-budget/v2',approval_sha256=policy.APPROVAL_SHA256,
                  manifest_sha256=packet['pilot']['manifest_sha256'],total_limit_microusd=12000000,
                  daily_limit_microusd=12000000,release_ledger={'path':'current-ledger.json','sha256':sha(raw)},
                  entries=[{k:row[k] for k in ('operation_id','category','day_utc','state')}|
                           {'amount_microusd':row['amount_micros']}
                           for row in ledger['entries']+ledger['operator_entries']])
    return budget


def qa_cost(root,ledger,packet):
    return acceptance.cohort_budget(projection(root,ledger,packet),packet['pilot']['manifest_sha256'],root,
                                    approval_sha256=policy.APPROVAL_SHA256)


def test_complete_new_workflow_over_five_million_qualifies(tmp_path,monkeypatch):
    ledger,packet=successor(monkeypatch)
    ledger['entries'].append({**ledger['entries'][0], 'operation_id':'new-large-workflow','run_id':999,'amount_micros':6000000})
    release_admission.validate_cost_ledger(ledger,packet)
    assert qa_cost(tmp_path,ledger,packet)==8101000


def test_complete_new_operator_over_five_million_qualifies(tmp_path,monkeypatch):
    ledger,packet=successor(monkeypatch)
    new={**ledger['operator_entries'][0],'operation_id':'new-large-operator','amount_micros':6000000}
    ledger['operator_entries'].append(new)
    def add(s):
        s['entries'].append({**s['entries'][1],'operation_id':new['operation_id'],'held_micros':6000000})
        s['total_held_micros']+=6000000
    change_snapshot(ledger,add)
    release_admission.validate_cost_ledger(ledger,packet)
    assert qa_cost(tmp_path,ledger,packet)==8101000


def test_projection_rejects_omitted_new_snapshot_liability(tmp_path,monkeypatch):
    ledger,packet=successor(monkeypatch)
    def add(s):
        s['entries'].append({**s['entries'][1],'operation_id':'unprojected-current-operator','held_micros':10000000})
        s['total_held_micros']+=10000000
    change_snapshot(ledger,add)
    with pytest.raises(ValueError,match='omitted'):
        release_admission.validate_cost_ledger(ledger,packet)
    # This snapshot holds11,001,000 plus1,100,000 workflow =12,101,000,
    # yet an incomplete projection must not claim2,101,000 within the12M cap.
    with pytest.raises(acceptance.InvalidEvidence):
        qa_cost(tmp_path,ledger,packet)


@pytest.mark.parametrize('value',[True,12000000.0,-1,12000001])
def test_projection_rejects_invalid_current_snapshot_limit(tmp_path,monkeypatch,value):
    ledger,packet=successor(monkeypatch)
    change_snapshot(ledger,lambda s:s.update(limit_micros=value))
    with pytest.raises(ValueError):release_admission.validate_cost_ledger(ledger,packet)
    with pytest.raises(acceptance.InvalidEvidence):qa_cost(tmp_path,ledger,packet)
