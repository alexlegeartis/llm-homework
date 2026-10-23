import argparse

from homework_01_rag.common import load_config
from homework_01_rag.embeddings import download_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    download_model(load_config(args.config)["embedding"], args.output)


if __name__ == "__main__":
    main()
