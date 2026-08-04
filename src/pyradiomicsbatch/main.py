import argparse
import csv
import os
import re
import subprocess
import sys
import tkinter as tk
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from tqdm import tqdm

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
    seg_regexes: dict[str, str],
    console: Console,
):
    console.print(f"[bold cyan]Scanning directory:[/bold cyan] {dataset_dir}")
    if mode == "strict":
        builder = StrictHierarchyBuilder()
    else:
        builder = RegexHierarchyBuilder(id_regex, seg_regexes)

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
        fieldnames = ["ID", "Image", "Mask"]
        if mode == "regex":
            fieldnames.append("Region")

        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for data in valid_set:
            row = {
                "ID": data["ID"],
                "Image": str(data["Image"]),
                "Mask": str(data["Mask"]),
            }
            if "Region" in data:
                row["Region"] = str(data["Region"])

            writer.writerow(row)


def pyradiomics_cli(
    csv_path: Path,
    out_path: Path,
    config_path: Path,
    logging_path: Path,
    total_cases: int,
    jobs: int,
):
    cmd = [
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
        "--logging-level",
        "INFO",
        "--log-file",
        str(logging_path),
        "-v",
        "4",
    ]

    _run_with_progress(cmd, total_cases)


def _run_with_progress(cmd: list[str], total_cases: int):
    case_pattern = re.compile(r"\(case\s+(\d+)\)", re.IGNORECASE)
    finished_cases: set[str] = set()

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )

    if process.stdout is not None:
        with tqdm(total=total_cases, desc="Extracting Features") as pbar:
            for line in process.stdout:
                if "failed!" in line.lower() or "processed" in line.lower():
                    match = case_pattern.search(line)
                    if match and match.group(1) not in finished_cases:
                        finished_cases.add(match.group(1))
                        pbar.update(1)

    process.wait()
    if process.returncode != 0:
        print(f"\nProcess exited with code {process.returncode}.")


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
        "--id-regex", default=r"/([^/]+)\.nii\.gz$", help="Custom regex for ID"
    )
    init_parser.add_argument(
        "--tumour-regex",
        default=r"/([^/]+)_mask\.nii\.gz$",
        help="Regex for Tumour mask",
    )
    init_parser.add_argument(
        "--parenchyma-regex",
        default=r"/([^/]+)p\.nii\.gz$",
        help="Regex for Parenchyma mask",
    )
    init_parser.add_argument(
        "--shell-regex", default=r"/([^/]+)s\.nii\.gz$", help="Regex for Shell mask"
    )
    init_parser.add_argument(
        "--ignore-tumour", action="store_true", help="Exclude tumour masks"
    )
    init_parser.add_argument(
        "--ignore-parenchyma", action="store_true", help="Exclude parenchyma masks"
    )
    init_parser.add_argument(
        "--ignore-shell", action="store_true", help="Exclude shell masks"
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
        "--tumour-regex",
        default=r"/([^/]+)_mask\.nii\.gz$",
        help="Regex for Tumour mask",
    )
    pipe_parser.add_argument(
        "--parenchyma-regex",
        default=r"/([^/]+)p\.nii\.gz$",
        help="Regex for Parenchyma mask",
    )
    pipe_parser.add_argument(
        "--shell-regex", default=r"/([^/]+)s\.nii\.gz$", help="Regex for Shell mask"
    )
    pipe_parser.add_argument(
        "--ignore-tumour", action="store_true", help="Exclude tumour masks"
    )
    pipe_parser.add_argument(
        "--ignore-parenchyma", action="store_true", help="Exclude parenchyma masks"
    )
    pipe_parser.add_argument(
        "--ignore-shell", action="store_true", help="Exclude shell masks"
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

    seg_regexes: dict[str, str] = {}
    if args.cmd in ["init", "pipeline"]:
        if not args.ignore_tumour:
            seg_regexes["Tumour"] = args.tumour_regex
        if not args.ignore_parenchyma:
            seg_regexes["Parenchyma"] = args.parenchyma_regex
        if not args.ignore_shell:
            seg_regexes["Shell"] = args.shell_regex

    if args.cmd == "init":
        output_dir: Path = base_output_dir / f"{args.dir.name}_{cur_timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path: Path = output_dir / "batch.csv"

        rdmx_headless(
            args.dir, csv_path, args.mode, args.id_regex, seg_regexes, console
        )
        console.print(
            f"[bold green]Pre-built csv file saved to:[/bold green] {csv_path}"
        )
    elif args.cmd == "run":
        if args.file.parent.parent.resolve() == base_output_dir.resolve():
            output_dir = args.file.parent
        else:
            output_dir = (
                base_output_dir
                / f"{args.file.parent.name.split('_')[0]}_{cur_timestamp}"
            )
            output_dir.mkdir(parents=True, exist_ok=True)
        rdmx_csv = output_dir / "rdmx.csv"
        logging_path = output_dir / "pyradiomics.log"

        try:
            with open(args.file, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                total_cases = sum(1 for _ in reader) - 1
        except FileNotFoundError:
            console.print(f"[bold red]Error: Could not find {args.file}[/bold red]")
            return

        if total_cases > 0:
            console.print(
                f"[bold cyan]Running pyradiomics batch with {n_jobs} threads[/bold cyan]"
            )
            pyradiomics_cli(
                args.file, rdmx_csv, config_path, logging_path, total_cases, n_jobs
            )
            console.print(
                f"[bold green]Radiomics csv file saved to:[/bold green] {rdmx_csv}"
            )
        else:
            console.print(
                f"[bold red]Batch CSV is empty or only contains a header[/bold red] {args.file}"
            )
    else:
        output_dir = base_output_dir / f"{args.dir.name}_{cur_timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "batch.csv"
        rdmx_csv = output_dir / "rdmx.csv"
        logging_path = output_dir / "pyradiomics.log"

        rdmx_headless(
            args.dir, csv_path, args.mode, args.id_regex, seg_regexes, console
        )
        console.print(
            f"[bold green]Pre-built csv file saved to:[/bold green] {csv_path}"
        )

        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                total_cases = sum(1 for _ in reader) - 1
        except FileNotFoundError:
            console.print(f"[bold red]Error: Could not find {csv_path}[/bold red]")
            return

        if total_cases > 0:
            console.print(
                f"[bold cyan]Running pyradiomics batch with {n_jobs} threads[/bold cyan]"
            )
            pyradiomics_cli(
                csv_path, rdmx_csv, config_path, logging_path, total_cases, n_jobs
            )
            console.print(
                f"[bold green]Radiomics csv file saved to:[/bold green] {rdmx_csv}"
            )
        else:
            console.print(
                f"[bold red]Batch CSV is empty or only contains a header[/bold red] {csv_path}"
            )


if __name__ == "__main__":
    main()
