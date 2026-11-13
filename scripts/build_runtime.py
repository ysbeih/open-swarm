"""Build the same llama.cpp revision on macOS, Linux or Windows. No model download."""
import argparse
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVISION = "5676dfbe01e7ebe0387913680eee0ed39bf4a363"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpu", action="store_true", help="Disable Metal (Windows uses CPU by default)")
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    source = ROOT / ".tools/llama.cpp"
    source.mkdir(parents=True, exist_ok=True)
    if not (source / ".git").exists():
        subprocess.run(["git", "init", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "remote", "add", "origin", "https://github.com/ggml-org/llama.cpp.git"], check=True)
    subprocess.run(["git", "-C", str(source), "fetch", "--depth", "1", "origin", REVISION], check=True)
    subprocess.run(["git", "-C", str(source), "checkout", "--detach", REVISION], check=True)
    build = source / "build"
    mac = platform.system() == "Darwin"
    command = ["cmake", "--fresh", "-S", str(source), "-B", str(build),
               "-DGGML_RPC=ON", "-DCMAKE_BUILD_TYPE=Release", "-DLLAMA_BUILD_TESTS=OFF",
               "-DLLAMA_BUILD_EXAMPLES=OFF", "-DLLAMA_CURL=OFF",
               "-DGGML_METAL=" + ("ON" if mac and not args.cpu else "OFF")]
    if mac:
        command += ["-DGGML_METAL_EMBED_LIBRARY=ON", "-DGGML_METAL_USE_BF16=OFF", "-DCMAKE_BUILD_RPATH=@loader_path"]
    subprocess.run(command, check=True)
    subprocess.run(["cmake", "--build", str(build), "--config", "Release", "--target",
                    "llama-server", "ggml-rpc-server", "-j", str(args.jobs)], check=True)
    binary_dir = build / "bin"
    if (binary_dir / "Release").exists():
        binary_dir /= "Release"
    (binary_dir / "runtime-revision.txt").write_text(REVISION + "\n")
    print("Runtime binaries:", binary_dir)
    print("Set runtime_bin in config/local.json to this path.")


if __name__ == "__main__":
    main()
