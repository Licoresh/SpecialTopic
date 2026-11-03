import json
from pathlib import Path
import shutil
import subprocess

import pandas as pd
import pytest

from src.timeline_table import timeline_table_data


def test_table_retains_selected_undated_titles_without_inventing_zero_counts():
    monthly = pd.DataFrame({"month": ["2026-01", "2026-02"], "job_title": ["analyst"] * 2, "job_ads": [2, 3]})
    data = timeline_table_data(monthly, ["analyst", "engineer"])
    assert data == {"months": ["2026-01", "2026-02"],
                    "series": [{"title": "analyst", "counts": [2, 3]}, {"title": "engineer", "counts": None}]}


def test_browser_table_play_pause_seek_completion_and_download_counts(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the browser playback logic check")
    module = tmp_path / "timeline_table.mjs"
    module.write_text((Path(__file__).parents[1] / "src/timeline_table.js").read_text(encoding="utf-8"), encoding="utf-8")
    script = '''
import assert from 'node:assert/strict';
import {createPlayback, rowsAt} from MODULE;
let tick, view, cancelled = 0;
const control = createPlayback(3, (index, playing) => {view = {index, playing};},
    callback => {tick = callback; return 1;}, () => {tick = undefined; cancelled++;});
control.play(); assert.deepEqual(view, {index:0, playing:true});
tick(); assert.deepEqual(view, {index:1, playing:true});
control.pause(); assert.deepEqual(view, {index:1, playing:false}); assert.equal(tick, undefined);
control.play(); tick(); assert.deepEqual(view, {index:2, playing:false}); assert.equal(tick, undefined);
control.play(); assert.equal(view.index,0);
control.seek(1); assert.deepEqual(view, {index:1, playing:false}); assert.equal(tick,undefined);
control.dispose(); assert.ok(cancelled > 0);
const data={months:['2026-01','2026-02','2026-03'],series:[{title:'analyst',counts:[2,0,3]},{title:'engineer',counts:null}]};
assert.deepEqual(rowsAt(data,1),[{title:'analyst',count:0,total:2,trend:[2,0]}, {title:'engineer',count:null,total:null,trend:null}]);
assert.deepEqual(rowsAt(data,2)[0],{title:'analyst',count:3,total:5,trend:[2,0,3]});
'''.replace("MODULE", json.dumps(module.as_uri()))
    result = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
