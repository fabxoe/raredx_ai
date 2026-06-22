import argparse
import urllib.request
from pathlib import Path


DEFAULT_URLS = {
    "hp.obo": "http://purl.obolibrary.org/obo/hp.obo",
    "phenotype.hpoa": "https://purl.obolibrary.org/obo/hp/hpoa/phenotype.hpoa",
    "genes_to_phenotype.txt": "https://purl.obolibrary.org/obo/hp/hpoa/genes_to_phenotype.txt",
}


def download(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response:
        output_path.write_bytes(response.read())


def main() -> None:
    parser = argparse.ArgumentParser(description="Download official HPO ontology and annotation files.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    args = parser.parse_args()

    for filename, url in DEFAULT_URLS.items():
        output_path = args.output_dir / filename
        print(f"Downloading {url} -> {output_path}")
        download(url, output_path)


if __name__ == "__main__":
    main()

