from __future__ import annotations
import hashlib, json
from pathlib import Path


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _load(p: Path) -> dict:
    raw = p.read_bytes(); side = p.with_name(p.name + '.sha256').read_text().split()[0]
    if _sha(p) != side: raise ValueError(f"sidecar mismatch: {p}")
    return json.loads(raw)


def publish_v3_b3_successor(*, repo_root: Path, predecessor_package: Path, lifecycle: Path, liquidity: Path, output_root: Path, template_hash: str, data_requirements_hash: str) -> dict:
    repo_root=Path(repo_root).resolve(); predecessor_package=Path(predecessor_package).resolve(); lifecycle=Path(lifecycle).resolve(); liquidity=Path(liquidity).resolve()
    old=_load(predecessor_package/'manifest.json'); index=_load(predecessor_package/'input_index.json'); life=_load(lifecycle/'manifest.json'); liq=_load(liquidity/'manifest.json')
    if old.get('status') not in ('published','incomplete') or not old.get('frozen'): raise ValueError('predecessor package not frozen')
    if life.get('successor_id') != '49b09326f35936c6': raise ValueError('lifecycle successor mismatch')
    if liq.get('artifact_id') != liquidity.name or liq.get('scope',{}).get('stats',{}).get('data_fault_count') != 0: raise ValueError('liquidity successor invalid')
    if liq.get('scope',{}).get('stats',{}).get('expected_scope_count') != 5522: raise ValueError('liquidity scope mismatch')
    refs={name: {'path': str((predecessor_package/'input_index.json').relative_to(repo_root)), 'sha256': _sha(predecessor_package/'input_index.json'), 'interface_hash': item.get('interface_content_hash'), 'availability':'verified'} for name,item in index.get('interfaces',{}).items() if name in {'membership','daily','daily_basic','adj_factor','stk_limit','suspend_d','stock_st','trade_cal'}}
    payload={'schema_version':'v3_b3_execution_input_package.v1','status':'published','package_status':'published','authorization_scope':'b3_execution_input_binding_only','frozen':True,'template':{'template_id':'relative_strength_rotation_shsz_sw2021_v3','template_version':'v3_shsz_sw2021_pit_12m_liquidity20d','template_hash':template_hash,'data_requirements_hash':data_requirements_hash},'predecessor_package':{'artifact_id':old['artifact_id'],'path':str(predecessor_package.relative_to(repo_root)),'manifest_sha256':_sha(predecessor_package/'manifest.json'),'input_index_sha256':_sha(predecessor_package/'input_index.json')},'listing_lifecycle_successor':{'artifact_id':life['successor_id'],'path':str(lifecycle.relative_to(repo_root)),'manifest_sha256':_sha(lifecycle/'manifest.json')},'liquidity_ref':{'artifact_id':liq['artifact_id'],'path':str(liquidity.relative_to(repo_root)),'manifest_sha256':_sha(liquidity/'manifest.json'),'stats':liq['scope']['stats']},'verified_exact_inputs':refs}
    aid=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:16]; payload['artifact_id']=aid
    target=Path(output_root).resolve()/aid
    if target.exists(): raise ValueError('successor already exists')
    target.mkdir(parents=True); raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode(); (target/'manifest.json').write_bytes(raw); (target/'manifest.json.sha256').write_text(_sha(target/'manifest.json')+'  manifest.json\n')
    return {'status':'published','artifact_id':aid,'path':str(target)}
