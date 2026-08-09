import csv
import re
import tkinter as tk
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk


class HierarchyBuilder(ABC):
    @abstractmethod
    def build(self, dataset_dir: Path) -> list[dict[str, str]]:
        pass


class StrictHierarchyBuilder(HierarchyBuilder):
    """
    Assumes the largest file is the image and others are masks
    """

    def build(self, dataset_dir: Path) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []

        for sub_dir in [d for d in dataset_dir.iterdir() if d.is_dir()]:
            files = list(sub_dir.rglob("*.nii.gz"))
            if len(files) >= 2:  # subdirectories with less than 2 files are ignored
                files.sort(key=lambda p: p.stat().st_size, reverse=True)
                pt_id = sub_dir.name
                img = str(files[0].resolve())
                for i in range(1, len(files)):
                    result.append(
                        {"ID": pt_id, "Image": img, "Mask": str(files[i].resolve())}
                    )
        return result


class RegexHierarchyBuilder(HierarchyBuilder):
    """
    User-specified regex to identify images and masks
    """

    def __init__(self, id_regex: str, seg_regexes: dict[str, str]):
        self.id_regex = re.compile(id_regex)
        self.seg_regexes: dict[str, re.Pattern[str]] = {
            region: re.compile(pattern) for region, pattern in seg_regexes.items()
        }

    def build(self, dataset_dir: Path) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        imgs: dict[str, Path] = {}
        masks: dict[str, list[tuple[Path, str]]] = defaultdict(list)

        for file_path in dataset_dir.rglob("*.nii.gz"):
            path_str = file_path.relative_to(dataset_dir).as_posix()

            matched_mask = False
            for region, seg_regex in self.seg_regexes.items():
                seg_match = seg_regex.search(path_str)
                if seg_match:
                    pt_id = str(seg_match.group(1))
                    masks[pt_id].append((file_path, region))
                    matched_mask = True
                    break

            if matched_mask:
                continue

            id_match = self.id_regex.search(path_str)
            if id_match:
                pt_id = str(id_match.group(1))
                if pt_id not in imgs:
                    imgs[pt_id] = file_path
                continue

        all_pt_ids = set(imgs.keys()).union(masks.keys())

        for pt_id in all_pt_ids:
            img = str(imgs[pt_id]) if pt_id in imgs else ""
            if masks.get(pt_id):
                for mask_path, region in masks[pt_id]:
                    result.append(
                        {
                            "ID": pt_id,
                            "Image": img,
                            "Mask": str(mask_path),
                            "Region": region,
                        }
                    )
            else:
                result.append(
                    {"ID": pt_id, "Image": img, "Mask": "", "Region": "Unknown"}
                )

        return result


class RdmxApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("rdmx-batch")
        self.root.geometry("700x650")

        self.dataset_dir = tk.StringVar(value=str(Path(__file__).parent))
        self.nav_mode = tk.StringVar(value="strict")

        self.id_regex = tk.StringVar(value=r"/([^/]+)\.nii\.gz$")

        self.use_tumour = tk.BooleanVar(value=True)
        self.tumour_regex = tk.StringVar(value=r"/([^/]+)_mask\.nii\.gz$")

        self.use_parenchyma = tk.BooleanVar(value=True)
        self.parenchyma_regex = tk.StringVar(value=r"/([^/]+)p\.nii\.gz$")

        self.use_shell = tk.BooleanVar(value=True)
        self.shell_regex = tk.StringVar(value=r"/([^/]+)s\.nii\.gz$")

        self.hierarchy: list[dict[str, str]] = []

        self.build_ui()

    def build_ui(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            main_frame, text="1. Dataset Root Directory:", font=("Arial", 10, "bold")
        ).pack(anchor="w", pady=(0, 5))
        dir_frame = ttk.Frame(main_frame)
        dir_frame.pack(fill=tk.X, pady=(0, 15))
        ttk.Entry(dir_frame, textvariable=self.dataset_dir).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5)
        )
        ttk.Button(dir_frame, text="Browse", command=self.browse_dir).pack(side=tk.LEFT)

        ttk.Label(
            main_frame, text="2. Traverse Strategy:", font=("Arial", 10, "bold")
        ).pack(anchor="w", pady=(0, 5))
        ttk.Radiobutton(
            main_frame,
            text="Strict (One folder one patient, largest nii.gz is image)",
            variable=self.nav_mode,
            value="strict",
            command=self.toggle_regex_frame,
        ).pack(anchor="w")
        ttk.Radiobutton(
            main_frame,
            text="Regex (Self-defined matching))",
            variable=self.nav_mode,
            value="regex",
            command=self.toggle_regex_frame,
        ).pack(anchor="w")

        self.regex_frame = ttk.LabelFrame(
            main_frame, text=" Regex Configuration ", padding="10"
        )

        # Base ID
        ttk.Label(self.regex_frame, text="Base ID Regex:").grid(
            row=0, column=0, sticky="w", pady=(5, 15)
        )
        ttk.Entry(self.regex_frame, textvariable=self.id_regex, width=40).grid(
            row=0, column=1, padx=10, pady=(5, 15)
        )

        # Tumour
        self.chk_tumour = ttk.Checkbutton(
            self.regex_frame,
            text="Tumour Mask:",
            variable=self.use_tumour,
            command=self.toggle_regex_entries,
        )
        self.chk_tumour.grid(row=1, column=0, sticky="w", pady=2)
        self.ent_tumour = ttk.Entry(
            self.regex_frame, textvariable=self.tumour_regex, width=40
        )
        self.ent_tumour.grid(row=1, column=1, padx=10, pady=2)

        # Parenchyma
        self.chk_parenchyma = ttk.Checkbutton(
            self.regex_frame,
            text="Parenchyma Mask:",
            variable=self.use_parenchyma,
            command=self.toggle_regex_entries,
        )
        self.chk_parenchyma.grid(row=2, column=0, sticky="w", pady=2)
        self.ent_parenchyma = ttk.Entry(
            self.regex_frame, textvariable=self.parenchyma_regex, width=40
        )
        self.ent_parenchyma.grid(row=2, column=1, padx=10, pady=2)

        # Shell
        self.chk_shell = ttk.Checkbutton(
            self.regex_frame,
            text="Shell/Annular Mask:",
            variable=self.use_shell,
            command=self.toggle_regex_entries,
        )
        self.chk_shell.grid(row=3, column=0, sticky="w", pady=2)
        self.ent_shell = ttk.Entry(
            self.regex_frame, textvariable=self.shell_regex, width=40
        )
        self.ent_shell.grid(row=3, column=1, padx=10, pady=2)

        self.action_frame = ttk.Frame(main_frame)
        self.action_frame.pack(fill=tk.X, pady=20)

        ttk.Button(
            self.action_frame, text="Generate Preview", command=self.generate_preview
        ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(self.action_frame, text="Export", command=self.export_csv).pack(
            side=tk.LEFT
        )

        ttk.Label(main_frame, text="Preview:", font=("Arial", 10, "bold")).pack(
            anchor="w"
        )
        self.console = scrolledtext.ScrolledText(main_frame, height=12)
        self.console.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        self.toggle_regex_entries()

    def browse_dir(self):
        init_path = self.dataset_dir.get()
        d = filedialog.askdirectory(
            title="Select directory", initialdir=init_path if init_path else None
        )
        if d:
            self.dataset_dir.set(d)

    def toggle_regex_frame(self):
        if self.nav_mode.get() == "regex":
            self.regex_frame.pack(fill=tk.X, pady=(10, 0), before=self.action_frame)
        else:
            self.regex_frame.pack_forget()

    def toggle_regex_entries(self):
        self.ent_tumour.state(["!disabled"] if self.use_tumour.get() else ["disabled"])
        self.ent_parenchyma.state(
            ["!disabled"] if self.use_parenchyma.get() else ["disabled"]
        )
        self.ent_shell.state(["!disabled"] if self.use_shell.get() else ["disabled"])

    def log(self, message: str | list[str]):
        timestamp = f"[{self.cur_timestamp()}]"
        indent = " " * len(timestamp)
        if isinstance(message, list):
            formatted: list[str] = []
            for i, line in enumerate(message):
                if i == 0:
                    formatted.append(f"{timestamp} {line}")
                else:
                    formatted.append(f"{indent} {line}")
            full_message = "\n".join(formatted)
            self.console.insert(tk.END, full_message)
        else:
            self.console.insert(tk.END, f"[{self.cur_timestamp()}] {message}\n")
        self.console.see(tk.END)

    def generate_preview(self):
        dataset_path = Path(self.dataset_dir.get())
        if not dataset_path.is_dir():
            messagebox.showerror("Error", "Please select a valid dataset directory.")
            return

        self.console.delete(1.0, tk.END)

        if self.nav_mode.get() == "strict":
            builder = StrictHierarchyBuilder()
        else:
            id_regex = self.id_regex.get()
            if "(" not in id_regex:
                messagebox.showerror(
                    "Error", "ID regex must contain a capture group '()'"
                )
                return

            seg_regexes: dict[str, str] = {}
            if self.use_tumour.get():
                if "(" not in self.tumour_regex.get():
                    messagebox.showerror(
                        "Error", "Tumour regex must contain a capture group '()'"
                    )
                    return
                seg_regexes["Tumour"] = self.tumour_regex.get()

            if self.use_parenchyma.get():
                if "(" not in self.parenchyma_regex.get():
                    messagebox.showerror(
                        "Error", "Parenchyma regex must contain a capture group '()'"
                    )
                    return
                seg_regexes["Parenchyma"] = self.parenchyma_regex.get()

            if self.use_shell.get():
                if "(" not in self.shell_regex.get():
                    messagebox.showerror(
                        "Error", "Shell regex must contain a capture group '()'"
                    )
                    return
                seg_regexes["Shell"] = self.shell_regex.get()

            if not seg_regexes:
                messagebox.showwarning(
                    "Warning", "At least one mask regex must be selected."
                )
                return

            builder = RegexHierarchyBuilder(id_regex, seg_regexes)

        try:
            result = builder.build(dataset_path)
        except RuntimeError as e:
            self.log(f"Failed to load image: {e}")
            return
        except FileNotFoundError as e:
            self.log(f"File does not exist: {e}")
            return

        valid_set = [data for data in result if data.get("Image") and data.get("Mask")]
        orphans = [data for data in result if data not in valid_set]
        self.hierarchy = valid_set

        self.log(
            f"{len(valid_set)} matched pairs ({len(orphans)} incomplete files skipped)"
        )

        log_str: list[str] = []
        if valid_set:
            log_str.append("\n")
            log_str.append("--- Matched Files ---")
            for idx, data in enumerate(valid_set):
                if idx >= 15:
                    log_str.append(f"... and {len(valid_set) - 15} more records")
                    break
                log_str.append(f"ID: {data['ID']}")
                log_str.append(f"  IMG: {Path(data['Image']).name}")
                log_str.append(
                    f"  MASK [{data.get('Region', 'Unknown')}]: {Path(data['Mask']).name}"
                )

        if orphans:
            log_str.append("\n")
            log_str.append("--- Skipped Files ---")
            for idx, data in enumerate(orphans):
                if idx >= 5:
                    log_str.append(f"... and {len(orphans) - 5} more orphaned records")
                    break

                log_str.append(f"ID: {data['ID']}")

                img_name = Path(data["Image"]).name if data.get("Image") else "N/A"
                mask_name = Path(data["Mask"]).name if data.get("Mask") else "N/A"

                log_str.append(f"  IMG: {img_name}")
                log_str.append(f"  MASK [{data.get('Region', 'Unknown')}]: {mask_name}")

        if log_str:
            self.log(log_str)

    def cur_timestamp(self) -> str:
        return datetime.now(UTC).strftime("%Y%m%d%H%M%S")

    def export_csv(self):
        if not self.hierarchy:
            messagebox.showwarning(
                "Warning", "No data to export. Please generate a preview first."
            )
            return

        out_dir = filedialog.askdirectory(title="Select Output Directory")

        if out_dir:
            input_dir = Path(self.dataset_dir.get())
            dataset_name = input_dir.name if input_dir.name else "dataset"

            target_folder = Path(out_dir) / f"{dataset_name}_{self.cur_timestamp()}"

            target_folder.mkdir(parents=True, exist_ok=True)

            save_path = target_folder / "batch.csv"

            try:
                with open(save_path, mode="w", newline="", encoding="utf-8") as f:
                    fieldnames = ["ID", "Image", "Mask"]
                    if self.nav_mode.get() == "regex":
                        fieldnames.append("Region")

                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for data in self.hierarchy:
                        row = {
                            "ID": data["ID"],
                            "Image": str(data["Image"]),
                            "Mask": str(data["Mask"]),
                        }
                        if "Region" in data:
                            row["Region"] = str(data["Region"])

                        writer.writerow(row)
                self.log(f"\nExported to:\n{save_path}")
                messagebox.showinfo(
                    "Success", f"Export completed\nSaved to: {save_path}"
                )
            except PermissionError:
                messagebox.showerror("Error", "Permission denied")
            except FileNotFoundError:
                messagebox.showerror(
                    "Error", f"The folder path for '{save_path}' does not exist."
                )
            except OSError as e:
                messagebox.showerror(
                    "Error", f"System error occurred while saving the file {e}"
                )
