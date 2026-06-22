import shutil
import subprocess
from pathlib import Path


REQUIRED_FILES = [
    Path(".env"),
    Path("data/raw/hp.obo"),
    Path("data/raw/phenotype.hpoa"),
    Path("data/raw/genes_to_phenotype.txt"),
    Path("data/processed/phenotypes.json"),
    Path("data/processed/disease_phenotypes.json"),
    Path("data/processed/gene_phenotypes.json"),
    Path("data/processed/faiss/disease.faiss"),
    Path("data/processed/faiss/disease_ids.json"),
]


def main() -> None:
    print("RARE_DX_AI setup check\n")
    check_command("uv", "brew install uv")
    check_command("docker", "brew install --cask docker && open -a Docker")
    check_docker_daemon()
    check_files()


def check_command(command: str, install_hint: str) -> None:
    if shutil.which(command):
        print(f"[OK] {command} found")
    else:
        print(f"[MISSING] {command}")
        print(f"  Install: {install_hint}")


def check_docker_daemon() -> None:
    if not shutil.which("docker"):
        return
    result = subprocess.run(["docker", "info"], capture_output=True, text=True, check=False)
    if result.returncode == 0:
        print("[OK] Docker daemon is running")
    else:
        print("[MISSING] Docker daemon is not running")
        print("  Run: open -a Docker")


def check_files() -> None:
    print("\nGenerated files")
    for path in REQUIRED_FILES:
        if path.exists():
            print(f"[OK] {path}")
        else:
            print(f"[MISSING] {path}")

    print("\nIf generated files are missing, run in order:")
    print("  cp .env.example .env")
    print("  uv sync")
    print("  docker compose up -d neo4j")
    print("  uv run scripts/download_hpo.py")
    print("  uv run scripts/build_processed.py")
    print("  uv run scripts/build_faiss.py")
    print("  uv run scripts/load_neo4j.py")


if __name__ == "__main__":
    main()
