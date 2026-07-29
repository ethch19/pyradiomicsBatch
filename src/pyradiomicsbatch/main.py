import argparse
import csv
import os
import subprocess
import sys
import tkinter as tk
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from pyradiomicsbatch.dbnav import (
    RdmxApp,
    RegexHierarchyBuilder,
    StrictHierarchyBuilder,
)


def get_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S")


def get_optimal_jobs() -> int:
    total_cores = os.cpu_count() or 1
    return min(
        int(total_cores * 0.70), 6
    )  # max limit to 6 to prevent running out of RAM


def rdmx_ui():
    root = tk.Tk()
    _ = RdmxApp(root)
    root.mainloop()


def rdmx_headless(
    dataset_dir: Path,
    out_csv: Path,
    mode: str,
    id_regex: str,
    seg_regex: str,
    console: Console,
):
    console.print(f"[bold cyan]Scanning directory:[/bold cyan] {dataset_dir}")
    if mode == "strict":
        builder = StrictHierarchyBuilder()
    else:
        builder = RegexHierarchyBuilder(id_regex, seg_regex)

    try:
        result = builder.build(dataset_dir)
    except RuntimeError as e:
        console.print(f"[bold red]Failed to load image: {e}[/bold red]")
        sys.exit(1)
    except FileNotFoundError as e:
        console.print(f"[bold red]File does not exist: {e}[/bold red]")
        sys.exit(1)

    valid_set = [data for data in result if data.get("Image") and data.get("Mask")]
    orphans = len(result) - len(valid_set)

    console.print(
        f"Found [bold green]{len(valid_set)}[/bold green] matched pairs ({orphans} incomplete records skipped)"
    )

    if not valid_set:
        console.print("[bold red]No valid pairs found. Aborting[/bold red]")
        sys.exit(1)

    with open(out_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ID", "Image", "Mask"])
        writer.writeheader()
        for data in valid_set:
            writer.writerow(
                {
                    "ID": data["ID"],
                    "Image": str(data["Image"]),
                    "Mask": str(data["Mask"]),
                }
            )


def pyradiomics_cli(csv_path: Path, out_path: Path, config_path: Path, jobs: int):
    cmd = [
        "uv",
        "run",
        "pyradiomics",
        str(csv_path),
        "-o",
        str(out_path),
        "-f",
        "csv",
        "-p",
        str(config_path),
        "-j",
        str(jobs),
    ]

    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(
        prog="rdmx-batch",
        description="One-stop preprocessing, normalisation and feature extraction pipeline using pyradiomics",
    )
    subparsers = parser.add_subparsers(dest="cmd")

    subparsers.add_parser(
        "launch",
        help="Launch UI to generate batch.csv interactively (Does not support running pyradiomics, use CLI)",
    )

    init_parser = subparsers.add_parser(
        "init", help="Traverse directories to build csv for batch processing"
    )
    init_parser.add_argument(
        "-d", "--dir", type=Path, required=True, help="Path to dataset directory"
    )
    init_parser.add_argument(
        "-o",
        "--out",
        type=Path,
        required=True,
        help="Parent directory of /output where all outputs will be stored. /output will be created automatically",
    )
    init_parser.add_argument(
        "--mode",
        choices=["strict", "regex"],
        default="strict",
        help="Directory traversal strategy",
    )
    init_parser.add_argument(
        "--id-regex", default=r"([^/]+)/[^/]+\.nii\.gz$", help="Custom regex for ID"
    )
    init_parser.add_argument(
        "--seg-regex",
        default=r"(_seg|_label|_mask)\.nii\.gz$",
        help="Custom regex for segmentations",
    )

    rdmx_parser = subparsers.add_parser(
        "run", help="Batch processing with pyradiomics. Requires pre-built csv"
    )
    rdmx_parser.add_argument(
        "-o",
        "--out",
        type=Path,
        required=True,
        help="Parent directory of /output where all outputs will be stored. /output will be created automatically",
    )
    rdmx_parser.add_argument(
        "-f", "--file", type=Path, required=True, help="Path to pre-built csv."
    )
    rdmx_parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="Optional .yaml file for pyradiomics config. Defaults to repo root",
    )
    rdmx_parser.add_argument(
        "-j",
        "--jobs",
        type=Path,
        help="Optional number of threads to use for parallel processing. Defaults to 1 thread",
    )

    pipe_parser = subparsers.add_parser(
        "pipeline", help="Full pipeline running at once"
    )
    pipe_parser.add_argument(
        "-d", "--dir", type=Path, required=True, help="Path to dataset directory"
    )
    pipe_parser.add_argument(
        "-o",
        "--out",
        type=Path,
        required=True,
        help="Parent directory of /output where all outputs will be stored. /output will be created automatically",
    )
    pipe_parser.add_argument("--mode", choices=["strict", "regex"], default="strict")
    pipe_parser.add_argument(
        "--id-regex", default=r"([^/]+)/[^/]+\.nii\.gz$", help="Custom regex for ID"
    )
    pipe_parser.add_argument(
        "--seg-regex",
        default=r"(_seg|_label|_mask)\.nii\.gz$",
        help="Custom regex for segmentations",
    )
    pipe_parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="Optional .yaml file for pyradiomics config. Defaults to repo root",
    )
    pipe_parser.add_argument(
        "-j",
        "--jobs",
        type=Path,
        help="Optional number of threads to use for parallel processing. Defaults to 1 thread",
    )

    args = parser.parse_args()

    if not args.cmd or args.cmd == "launch":
        rdmx_ui()
        sys.exit(0)

    if not args.out:
        parser.error("The -o/--out argument is required for operating via CLI")

    console = Console()
    cur_timestamp = get_timestamp()
    base_output_dir = (
        args.out / "output" if args.out else (Path(__file__).parent / "output")
    )
    config_path = args.config if args.config else Path(__file__).parent / "config.yaml"
    n_jobs = args.jobs if args.jobs else get_optimal_jobs()

    if args.cmd == "init":
        output_dir: Path = base_output_dir / f"{args.dir.name}_{cur_timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path: Path = output_dir / "batch.csv"

        rdmx_headless(
            args.dir, csv_path, args.mode, args.id_regex, args.seg_regex, console
        )
        console.print(
            f"[bold green]Pre-built csv file saved to:[/bold green] {csv_path}"
        )
    elif args.cmd == "run":
        output_dir = (
            base_output_dir / f"{args.file.parent.name.split('_')[0]}_{cur_timestamp}"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        rdmx_csv = output_dir / "rdmx.csv"

        console.print(
            f"[bold cyan]Running pyradiomics batch with {n_jobs} threads[/bold cyan]"
        )
        pyradiomics_cli(args.file, rdmx_csv, config_path, n_jobs)
        console.print(
            f"[bold green]Radiomics csv file saved to:[/bold green] {rdmx_csv}"
        )
    else:
        output_dir = base_output_dir / f"{args.dir.name}_{cur_timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "batch.csv"
        rdmx_csv = output_dir / "rdmx.csv"

        rdmx_headless(
            args.dir, csv_path, args.mode, args.id_regex, args.seg_regex, console
        )
        console.print(
            f"[bold green]Pre-built csv file saved to:[/bold green] {csv_path}"
        )
        console.print(
            f"[bold cyan]Running pyradiomics batch with {n_jobs} threads[/bold cyan]"
        )
        pyradiomics_cli(csv_path, rdmx_csv, config_path, n_jobs)
        console.print(
            f"[bold green]Radiomics csv file saved to:[/bold green] {rdmx_csv}"
        )


if __name__ == "__main__":
    main()
