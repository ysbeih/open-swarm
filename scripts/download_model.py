"""Download one official IBM artifact at an immutable revision, then verify SHA-256."""
import argparse
import hashlib
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", choices=["8b", "30b"], default="8b")
    parser.add_argument("--quant", choices=["Q4_K_M", "Q3_K_M"], default="Q4_K_M")
    args = parser.parse_args()
    repo = f"ibm-granite/granite-4.2-{args.size}-GGUF"
    filename = f"granite-4.2-{args.size}-{args.quant}.gguf"
    folder = ROOT / "models"
    folder.mkdir(exist_ok=True)
    target = folder / filename
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        response = client.get(f"https://huggingface.co/api/models/{repo}", params={"blobs": "true"})
        response.raise_for_status()
        metadata = response.json()
        record = next(item for item in metadata["siblings"] if item["rfilename"] == filename)
        expected = record["lfs"]["sha256"]
        size = record["size"]
        revision = metadata["sha"]
        print(f"Official artifact: {filename} · {size / 1e9:.2f} GB", flush=True)
        print(f"Revision: {revision}\nSHA-256: {expected}", flush=True)
        if target.exists():
            digest = hashlib.sha256()
            with target.open("rb") as file:
                for chunk in iter(lambda: file.read(8 * 1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() == expected:
                print("Existing file verified.")
                return
            raise SystemExit("Existing file has a different hash; preserve it and choose a clean model destination.")
        partial = target.with_suffix(".gguf.part")
        downloaded, next_progress = 0, 0
        digest = hashlib.sha256()
        with client.stream("GET", f"https://huggingface.co/{repo}/resolve/{revision}/{filename}") as response:
            response.raise_for_status()
            with partial.open("wb") as file:
                for chunk in response.iter_bytes(4 * 1024 * 1024):
                    file.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    if downloaded >= next_progress:
                        print(f"Downloaded {downloaded / 1e9:.2f} / {size / 1e9:.2f} GB", flush=True)
                        next_progress = downloaded + 500_000_000
        if digest.hexdigest() != expected or downloaded != size:
            raise SystemExit("Artifact verification failed. Partial file retained; do not use it.")
        partial.rename(target)
        (folder / (filename + ".json")).write_text(json.dumps({"repository": repo, "revision": revision,
            "filename": filename, "bytes": size, "sha256": expected}, indent=2))
        print("Verified and saved:", target, flush=True)


if __name__ == "__main__":
    main()
