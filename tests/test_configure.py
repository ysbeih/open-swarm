import importlib.util
import json
from pathlib import Path
import pytest

from swarm.config import Settings


@pytest.mark.parametrize('extra_args,size,quant', [([], '8b', 'Q4_K_M'),
    (['--model', '30b', '--quant', 'Q3_K_M'], '30b', 'Q3_K_M')])
def test_fresh_checkout_creates_matching_two_peer_configs(tmp_path, monkeypatch, extra_args, size, quant):
    source = Path(__file__).resolve().parents[1] / "scripts/configure.py"
    spec = importlib.util.spec_from_file_location("configure", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["configure.py", "--a", "192.168.1.10", "--b", "192.168.1.11"] + extra_args)
    module.main()
    a, b = [Settings.model_validate_json((tmp_path / "config" / f"peer-{key}.json").read_text()) for key in "ab"]
    assert a.token == b.token and len(a.token) >= 32
    assert a.peers == b.peers and len(a.peers) == 2
    assert a.peer_id == "a" and b.peer_id == "b"
    assert a.bind_host != b.bind_host
    assert a.tensor_split == b.tensor_split == [1, 1]
    assert a.worker_device == b.worker_device == "MTL0"
    assert a.model_path == b.model_path == f'models/granite-4.2-{size}-{quant}.gguf'
    assert a.model_name == b.model_name == f'Granite 4.2 {size.upper()} · {quant}'
    assert not (tmp_path / "config/peer-c.json").exists()
