"""Create a private guest link and QR code for an already running gateway/tunnel."""
import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from swarm.config import load_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="The HTTPS URL printed by your guest-only tunnel")
    args = parser.parse_args()
    url = urlparse(args.url)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
        parser.error("Use the HTTPS origin printed by the guest tunnel, with no path, credentials or query.")
    settings = load_settings()
    access = json.loads((settings.state_path / "guest-pass.json").read_text())
    if access["expires_at"] <= time.time():
        raise SystemExit("Guest pass has expired; restart the guest gateway first.")
    try:
        import qrcode
        from qrcode.image.pure import PyPNGImage
    except ImportError:
        raise SystemExit("Install the optional QR dependencies: python -m pip install -r requirements-guest.txt")
    link = args.url.rstrip("/") + "/#pass=" + access["token"]
    destination = settings.state_path / "guest-url.txt"
    destination.touch(mode=0o600, exist_ok=True)
    destination.chmod(0o600)
    destination.write_text(link + "\n")
    image_path = settings.state_path / "guest-qr.png"
    image_path.touch(mode=0o600, exist_ok=True)
    image_path.chmod(0o600)
    qrcode.make(link, image_factory=PyPNGImage, box_size=7, border=4).save(str(image_path))
    print("Private guest link:", destination)
    print("Private QR image:", image_path)
    print("Share the full link or QR only with intended guests. They grant limited inference access until expiry.")


if __name__ == "__main__":
    main()
