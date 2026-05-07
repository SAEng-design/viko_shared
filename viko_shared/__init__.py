"""
viko_shared — Shared modules for ViKO design tools.

Public API:
    from viko_shared import (
        init_db, register_app, save_calculation, load_calculation,
        list_projects, list_members, list_calculations,
        get_or_create_project, get_or_create_member,
        render_project_info, project_info_is_complete,
    )
"""

from .viko_db import (
    init_db,
    register_app,
    save_calculation,
    load_calculation,
    list_projects,
    list_members,
    list_calculations,
    get_or_create_project,
    get_or_create_member,
    get_conn,
    get_db_path,
)

from .project_info import (
    render_project_info,
    project_info_is_complete,
)

__version__ = "0.1.0"

__all__ = [
    # viko_db
    "init_db",
    "register_app",
    "save_calculation",
    "load_calculation",
    "list_projects",
    "list_members",
    "list_calculations",
    "get_or_create_project",
    "get_or_create_member",
    "get_conn",
    "get_db_path",
    # project_info
    "render_project_info",
    "project_info_is_complete",
    # meta
    "__version__",
]
