"""The one-time cleanup tool: exact targets, prune keeps top-level files, links never followed."""
import json
import os
from pathlib import Path

import pytest


def test_prune_delete_links_and_unknown_items(tmp_path,monkeypatch):
    from scripts import cleanup_obsolete as tool
    root=tmp_path/'ws';(root/'evidence/kept-only-files').mkdir(parents=True)
    (root/'evidence/kept-only-files/summary.json').write_text('{}')
    bulky=root/'evidence/bulky';(bulky/'copy/deep').mkdir(parents=True);(bulky/'summary.json').write_text('{}');(bulky/'copy/deep/data.bin').write_bytes(b'x'*10)
    old=root/'old';old.mkdir();(old/'a.txt').write_text('a')
    outside=tmp_path/'outside';outside.mkdir();(outside/'precious.txt').write_text('keep')
    if os.name=='nt':
        import _winapi
        _winapi.CreateJunction(str(outside),str(old/'link'))  # junctions need no extra privilege
    else: os.symlink(outside,old/'link',target_is_directory=True)
    (root/'evidence/unlisted').mkdir()
    monkeypatch.setattr(tool,'WORKSPACE_ROOT',root)
    monkeypatch.setattr(tool,'TARGETS',[('prune','evidence/kept-only-files','p','r'),('prune','evidence/bulky','p','r'),('delete','old','p','r')])
    monkeypatch.setattr(tool,'WATCHED',['evidence']);monkeypatch.setattr(tool,'KEPT',set())
    monkeypatch.setattr(tool,'preconditions',lambda:([],[tmp_path/'live']))
    receipt=tmp_path/'receipt.json'
    monkeypatch.setattr('sys.argv',['x','apply',str(receipt)])
    tool.main()
    assert (root/'evidence/kept-only-files/summary.json').exists()  # a prune without subfolders deletes nothing
    assert (bulky/'summary.json').exists() and not (bulky/'copy').exists()
    assert not old.exists() and (outside/'precious.txt').read_text()=='keep'  # link removed, target untouched
    assert (root/'evidence/unlisted').exists()
    value=json.loads(receipt.read_text(encoding='utf-8'))
    assert value['unknown_not_touched']==['evidence/unlisted'] and not value['failures']


def test_targets_outside_workspace_or_live_roots_are_refused(tmp_path,monkeypatch):
    from scripts import cleanup_obsolete as tool
    monkeypatch.setattr(tool,'WORKSPACE_ROOT',tmp_path)
    with pytest.raises(ValueError): tool.resolve('../elsewhere',[])
    with pytest.raises(ValueError): tool.resolve('data/clinical',[tmp_path/'data'])
    with pytest.raises(ValueError): tool.resolve('data',[tmp_path/'data'/'clinical'])
    assert tool.resolve('old',[tmp_path/'data'])==Path(os.path.abspath(tmp_path/'old'))
