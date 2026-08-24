# pyradiomicsBatch

#### One-stop preprocessing, normalisation and feature extraction pipeline
Batch processing files using Pyradiomics

## Table of Contents
- [Installation](#installation)
- [Usage](#usage)
- [Dev Guide & Build Instructions](#developer-guide--build-instructions)
- [Resources](#resources)
- [License](#license)

## Installation

### Step 1. Install uv
**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
**Windows:** Follow the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Step 2. Install as CLI
**Option A: Install directly from GitHub (Recommended)**
```bash
uv tool install git+https://github.com/Mitch-Chen-Group/pyradiomicsBatch.git --python 3.11
```
<br />

**Option B: Install from a downloaded release**
1. Go to the [Releases page](https://github.com/Mitch-Chen-Group/pyradiomicsBatch/releases/latest) and download the `.whl` file.
2. Run the following command in your terminal (replace the filename with the one you downloaded):
```bash
uv tool install ./pyradiomicsbatch-0.1.0-py3-none-any.whl --python 3.11
```

> Python version `<=3.13` is tested and working. For the most stable, reproducible environment, installing with Python `3.11` is highly recommended. 

## Usage
### 1. Generate Dataset Links
Creates mapped `batch.csv` containing paths to images and masks, inside your specified output (`-o`/`--out`) directory
<br /><br />

**Option A: Interactive UI (`launch`)**

Launches a graphical user interface for mapping out your files and generate the batch CSV
> *The UI only handles the initial csv generation, not the actual PyRadiomics feature extraction*
```bash
rdmx-batch

# alternative
rdmx-batch launch
```
<br />

**Option B: CLI (`init`)**

Same functionality as the UI.
```bash
# Default (Stict mode)
rdmx-batch init -d ./dataset -o ./radiomics

# Regex mode for custom matching with all mask types
rdmx-batch init -d ./dataset -o ./radiomics \
  --mode regex \
  --id-regex "([^/]+)/[^/]+\.nii\.gz$" \
  --tumour-regex "(_seg|_mask)\.nii\.gz$" \
  --parenchyma-regex "(_parenchyma|_patch)\.nii\.gz$" \
  --shell-regex "(_shell|_annular)\.nii\.gz$"

# Regex mode with tumour mask only
rdmx-batch init -d ./dataset -o ./radiomics \
  --mode regex \
  --id-regex "([^/]+)/[^/]+\.nii\.gz$" \
  --tumour-regex "(_seg|_mask)\.nii\.gz$" \
  --ignore-parenchyma \
  --ignore-shell

# Regex mode with custom mask types and specific nodule label mapping
rdmx-batch init -d ./dataset -o ./radiomics \
  --mode regex \
  --id-regex "([^/]+)/[^/]+\.nii\.gz$" \
  --tumour-regex "(_seg|_mask)\.nii\.gz$" \
  --parenchyma-regex "(_parenchyma|_patch)\.nii\.gz$" \
  --shell-regex "(_shell|_annular)\.nii\.gz$" \
  --label-csv ./label_indices.csv
```

### 2. Traversal Modes
**Strict mode**

Folder structure as below (choose DataFolder when prompted)
```
    DataFolder/ 
    ├── Dataset001/
    │   ├── Raw_image.nii.gz
    │   ├── Mask_1.nii.gz
    │   ├── Mask_2.nii.gz
    │   └── ...
    ├── Dataset002
    ├── Dataset003
    ├── Dataset004
    ├── Dataset005
    └── ...
```

Make sure all nifti are in .gz compressed format so that the largest nii.gz in each folder is the raw image

If the dataset subdirectories contain less than 2 files, the whole subdirectory will be ignored/skipped

You can have more than one mask for a single image.
<br /> <br />

**Regex mode**

If your file naming convention does not match the default strict mode, you can use Regular Expressions (Regex) to tell the parser exactly how to find IDs (images) and Segmentation masks.

- `\d+` matches one or more numbers (e.g., `123`, `12345`).
- `\d{3}` matches exactly 3 numbers (e.g., `123`, but not `12345`).
- `.*` matches any character combination.
- `$` indicates the very end of the file path.
- `()` creates a "capture group" to extract a specific part of the text.
    - ***First capture group must ALWAYS be the ID***

#### Example usage:

Folder structure:
```
```text
    DataFolder/ 
    ├── NIFTI/
    │   ├── 1.nii.gz
    │   ├── 2.nii.gz
    │   └── ...
    └── SEG/
        ├── seg1.nii.gz
        ├── seg1_parenchyma.nii.gz
        ├── seg1_annular.nii.gz
        ├── seg2.nii.gz
        ├── seg2_parenchyma.nii.gz
        ├── seg2_annular.nii.gz
        └── ...
```

Command:
```bash
rdmx-batch init -d ./DataFolder -o ./radiomics --mode regex \
  --id-regex "/NIFTI/(\d+)\.nii\.gz$" \
  --tumour-regex "/SEG/seg(\d+)\.nii\.gz$" \
  --parenchyma-regex "/SEG/seg(\d+)_parenchyma\.nii\.gz$" \
  --shell-regex "/SEG/seg(\d+)_annular\.nii\.gz$" \
  -l ./label_indices.csv
```

1. Extracting the ID:
    - The parser extracts whatever is in the *first* capture group `(...)` in the `--id-regex` flag and assigns it as the ID.
    - In this case, it's the numbers (`(\d+)` means as many numbers as there is)
2. Identifying the mask:
    - The parser applies the `--tumour-regex`, `--parenchyma-regex`, and `--shell-regex` flags to identify the respective `.nii.gz` files within the `/SEG` directory.
    - The ID must be identical to the one extracted in the previous step. Or else, nothing will match.
3. Custom Label Index Mapping (Optional):
    - You can provide a CSV file (`-l` / `--label-csv` or via the UI field) mapping patient IDs to specific integer labels (e.g., from `labelgen`).
    - The CSV must contain `ID` and `Label_Index` (or `Label Index`) headers.
    - When provided, a `Label` column is added to `batch.csv`. PyRadiomics uses this column to override default label settings and extract features exclusively from the specified integer label for each scan.

### 3. Run Feature Extraction (`run`)
Run the pyradiomics batch processing using a mapped CSV file.

The radiomics features (all classes) are saved in one .csv spreadsheet

`...` = Define your own path accordingly

```bash
# Basic
rdmx-batch run -f ./radiomics/.../batch.csv -o ./radiomics

# Run with custom pyradiomics config and run 4 threads in parallel
rdmx-batch run -f ./radiomics/.../batch.csv -o ./radiomics -c custom_config.yaml -j 4
```

### 4. Full Pipeline (`pipeline`)
Run both the `init` and `run` steps sequentially in a single command.

```bash
# Basic
rdmx-batch pipeline -d ./dataset -o ./radiomics

# Run with custom pyradiomics config and run 4 threads in parallel
rdmx-batch pipeline -d ./dataset -o ./radiomics -c custom_config.yaml -j 4

# Run full pipeline with custom regex matching, label mapping, and 4 worker threads
rdmx-batch pipeline -d ./dataset -o ./radiomics \
  --mode regex \
  --id-regex "([^/]+)/[^/]+\.nii\.gz$" \
  --tumour-regex "(_seg|_mask)\.nii\.gz$" \
  --label-csv ./label_indices.csv \
  -c custom_config.yaml -j 4
```

## Developer Guide & Build Instructions
### 1. Setup the Environment
Clone the repository and initialise the `uv` virtual environment.

```bash
git clone https://github.com/Mitch-Chen-Group/pyradiomicsBatch.git
cd pyradiomicsBatch
uv sync
```

### 2. Run Locally
To test the CLI during development without installing it globally:
```bash
# Example
uv run rdmx-batch pipeline -d ./test_data -o ./test_output
```

### 3. Linting and Formatting
Use [black](https://github.com/psf/black) for code formatting and [ruff](https://github.com/astral-sh/ruff) for linting.

Before committing changes, ensure your code passes:
```bash
# Format with Black
uvx black .

# Lint and auto-fix with Ruff
uvx ruff check --fix .
```

### 4. Build the Package
To build the distributable `.whl` and `.tar.gz` files:
```bash
uv build
```
The compiled binaries will be generated inside the `dist/` directory.

## Resources
[Pyradiomics Documentation](https://pyradiomics.readthedocs.io/en/latest/) <br />
[Pyradiomics Github](https://github.com/AIM-Harvard/pyradiomics) <br />
[Kaggle Worksheet](https://www.kaggle.com/code/mitchchen/msc-precision-medicine-lung-cancer-radiomics) <br />

## License
Distributed under the BSD 3-Clause License. See `LICENSE` for more information.