"""The helper commands: collect, compare, proof, check, printers."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from PIL import Image

from mosaic_poster.cli import main
from mosaic_poster.collect import _Collector, _handler
from mosaic_poster.compare import compare_targets


@pytest.fixture
def server(tmp_path):
    col = _Collector(tmp_path / "in", "secret-key", "Send photos", max_mb=1)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _handler(col))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", tmp_path / "in"
    httpd.shutdown()


def _post(url, data):
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_collect_saves_uploads_per_person(server):
    url, folder = server
    page = urllib.request.urlopen(f"{url}/?k=secret-key").read().decode()
    assert "Tap to choose photos" in page
    r = _post(f"{url}/upload?k=secret-key&name=IMG_0001.HEIC&who=Priya", b"x" * 100)
    assert r["photos"] == 1
    _post(f"{url}/upload?k=secret-key&name=IMG_0001.HEIC&who=Priya", b"y" * 100)
    names = sorted(p.name for p in (folder / "Priya").iterdir())
    assert names == ["IMG_0001 (2).HEIC", "IMG_0001.HEIC"]  # never overwritten


def test_collect_rejects_bad_requests(server):
    url, folder = server
    for path, data, code in [
        ("/upload?k=wrong&name=a.jpg", b"x", 403),                       # wrong key
        ("/upload?k=secret-key&name=virus.exe", b"x", 415),               # not a photo
        ("/upload?k=secret-key&name=big.jpg", b"x" * 2_000_000, 413),     # over max_mb
    ]:
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(url + path, data)
        assert e.value.code == code
    _post(f"{url}/upload?k=secret-key&name=../../evil.jpg&who=../..", b"x")
    saved = [p for p in folder.rglob("*") if p.is_file()]
    assert all(folder in p.parents for p in saved)  # no escaping the folder


def test_compare_ranks_targets(target, photos, tmp_path):
    flat = tmp_path / "flat.jpg"
    Image.new("RGB", (60, 90), (128, 128, 128)).save(flat)
    sheet = tmp_path / "cmp.jpg"
    ranked = compare_targets([str(flat), str(target)], [str(photos)], str(sheet), 6, 9,
                             sample=40, tile_px=8)
    assert ranked[0][0] == str(target)  # the detailed photo beats a flat gray one
    assert Image.open(sheet).width > 100


def test_cli_printers_and_check(target, photos, tmp_path, capsys):
    assert main(["printers"]) == 0
    assert "plotter-bond" in capsys.readouterr().out
    code = main(["check", str(target), str(photos), "--printer", "plotter-bond",
                 "--size", "48x36", "-o", str(tmp_path / "x.pdf")])
    assert code == 2  # too wide for a 36-inch roll
    assert "--size 36x48" in capsys.readouterr().err


def test_cli_make_with_printer_preset(target, photos, tmp_path):
    out = tmp_path / "p.pdf"
    code = main([str(target), str(photos), "--printer", "plotter-bond", "--size", "6x9",
                 "--dpi", "40", "-o", str(out), "--cache-dir", str(tmp_path / "c"), "-q"])
    assert code == 0
    assert b"/DeviceCMYK" in out.read_bytes()            # preset made it CMYK
    assert (tmp_path / "p.report.html").exists()


def test_cli_proof(tmp_path, capsys):
    f = tmp_path / "poster.jpg"
    Image.new("RGB", (300, 400), (30, 120, 220)).save(f)
    assert main(["proof", str(f), "--paper", "bond"]) == 0
    proof = Image.open(tmp_path / "poster.proof.jpg")
    assert max(proof.getpixel((150, 200))) < 220  # paper dulls the bright blue
