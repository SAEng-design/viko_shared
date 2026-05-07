# viko_shared

Shared Python package used by all ViKO Streamlit design tools.

## What's in here

- **`viko_db.py`** — SQLite database layer. Stores projects, members, and calculations from every design app in a single database (`W:\Central Information\DESIGN\VIKO Design Tool\database\viko_calcs.db`), with a local fallback for development.
- **`project_info.py`** — Streamlit sidebar component for capturing Project Number, Project Name, Member Mark, Designer, Date, and an optional Calc Label.

## Installation

Add this line to the `requirements.txt` of any ViKO design app:

```
git+https://github.com/SAEng-design/viko_shared.git@main
```

Then in the app:

```python
from viko_shared import (
    init_db, register_app, save_calculation,
    render_project_info, project_info_is_complete,
)
```

## Updating the package

When this package is updated, each consuming app needs to be rebuilt to pick up the new version. On Streamlit Community Cloud, redeploy the app. Locally, run:

```
pip install --upgrade --force-reinstall git+https://github.com/SAEng-design/viko_shared.git@main
```

## Versioning

Bump the version in both `pyproject.toml` and `viko_shared/__init__.py` when making breaking changes.
