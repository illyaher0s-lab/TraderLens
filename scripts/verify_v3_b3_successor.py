from __future__ import annotations
import hashlib, json
from pathlib import Path


def verify_v3_b3_successor(artifact: Path, repo_root: Path) -> dict:
    artifact=Path(artifact); repo_root=Path(repo_root)
    try:
        p=artifact/'manifest.json'; raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest() != (artifact/'manifest.json.sha256').read_text().split()[0]: return {'status':'invalid','reason':'sidecar'}
        m=json.loads(raw)
        if m.get('artifact_id') != artifact.name or m.get('status') != 'published' or m.get('package_status') != 'published': return {'status':'invalid','reason':'package status/id'}
        for key in ('predecessor_package','listing_lifecycle_successor','liquidity_ref'):
            item=m[key]; path=repo_root/item['path']; mp=path/'manifest.json';
            if hashlib.sha256(mp.read_bytes()).hexdigest() != item['manifest_sha256']: return {'status':'invalid','reason':key+' hash'}
        liq=json.loads((repo_root/m['liquidity_ref']['path']/'manifest.json').read_text())
        stats=liq['scope']['stats']
        if stats != m['liquidity_ref']['stats']: return {'status':'invalid','reason':'liquidity stats'}
        if stats != {'complete_count':5519,'data_fault_count':0,'expected_scope_count':5522,'first_data_fault':None,'unavailable_ineligible_count':3}: return {'status':'invalid','reason':'liquidity acceptance stats'}
        old=json.loads((repo_root/m['predecessor_package']['path']/'manifest.json').read_text())
        if old.get('status') != 'incomplete': return {'status':'invalid','reason':'predecessor package status changed'}
        for name,item in m['verified_exact_inputs'].items():
            if item['interface_hash'] != json.loads((repo_root/m['predecessor_package']['path']/'input_index.json').read_text())['interfaces'][name]['interface_content_hash']: return {'status':'invalid','reason':'exact input '+name}
        return {'status':'verified','artifact_id':m['artifact_id'],'package_status':m['package_status'],'liquidity_stats':stats}
    except (OSError,KeyError,ValueError,json.JSONDecodeError) as exc: return {'status':'invalid','reason':str(exc)}
