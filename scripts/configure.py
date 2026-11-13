"""Create two or three ignored configurations from real LAN addresses. Run on one laptop."""
import argparse
import json
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True, help="M4 Pro's LAN IPv4 address")
    parser.add_argument("--b", required=True, help="M3 Pro's LAN IPv4 address")
    parser.add_argument("--c", help="Optional Windows laptop's LAN IPv4 address")
    parser.add_argument("--model", choices=["8b", "30b"], default="8b")
    args = parser.parse_args()
    import ipaddress
    hosts = [args.a, args.b] + ([args.c] if args.c else [])
    for host in hosts:
        address = ipaddress.ip_address(host)
        if address.version != 4 or not address.is_private or address.is_unspecified or address.is_multicast:
            raise SystemExit("Use real private LAN IPv4 addresses.")
    if len(set(hosts)) != len(hosts):
        raise SystemExit("The physical laptops must have distinct LAN addresses.")
    names = ["M4 Pro", "M3 Pro", "Ryzen laptop"]
    peers = [{"id": key, "name": name, "url": f"http://{host}:8000", "rpc_host": host, "rpc_port": 50052}
             for key, name, host in zip("abc", names, hosts)]
    targets = [ROOT / "config" / f"peer-{key}.json" for key in "abc"[:len(hosts)]]
    if any(p.exists() for p in targets):
        raise SystemExit("Peer configs already exist. Edit them or move them aside before regenerating the shared token.")
    token = secrets.token_urlsafe(32)
    (ROOT / "config").mkdir(parents=True, exist_ok=True)
    for i, path in enumerate(targets):
        config = {"peer_id": "abc"[i], "name": names[i], "bind_host": hosts[i],
                  "api_port": 8000, "rpc_port": 50052, "inference_port": 8081,
                  "token": token, "offer_bytes": 8_000_000_000,
                  "runtime_bin": ".tools/llama.cpp/build/bin" + ("/Release" if i == 2 else ""),
                  "model_path": f"models/granite-4.2-{args.model}-Q4_K_M.gguf",
                  "model_name": f"Granite 4.2 {args.model.upper()} · Q4_K_M",
                  "model_sha256": "", "worker_device": "CPU" if i == 2 else "MTL0",
                  "devices": [], "tensor_split": [1] * len(hosts), "peers": peers}
        path.write_text(json.dumps(config, indent=2))
        path.chmod(0o600)
        print("Wrote", path.name)
    print("Copy each peer's file to that laptop as config/local.json. The files contain a shared control token: do not commit them.")
    print("Discover native device names, then populate devices in coordinator configs. Ratios are not hard memory quotas.")


if __name__ == "__main__":
    main()
