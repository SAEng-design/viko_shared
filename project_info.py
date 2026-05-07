"""
project_info.py — Shared Streamlit component for capturing Project Info.

Each design app imports `render_project_info()` and places it in the sidebar.
Returns a dict with the standard fields, which the app passes to
viko_db.save_calculation() when the user saves.

Usage in an app:

    from viko_shared.project_info import render_project_info
    from viko_shared.viko_db import save_calculation, init_db, register_app

    init_db()
    register_app("welded_angle_tension",
                 display_name="Welded Angle Tensile Resistance",
                 current_version="1.0.0",
                 code_standard="SANS 10162-1")

    proj = render_project_info()

    # ... user runs calc ...

    if st.button("Save calculation"):
        save_calculation(
            project_number=proj["project_number"],
            project_name=proj["project_name"],
            member_mark=proj["member_mark"],
            member_type="welded_angle_tension",
            app_name="welded_angle_tension",
            app_version="1.0.0",
            inputs=inputs_dict,
            results=results_dict,
            summary={"section": ..., "Tr_kN": ..., "utilisation": ...},
            status="pass" if util <= 1.0 else "fail",
            governing_utilisation=util,
            created_by=proj["designer"],
            calc_label=proj.get("calc_label", ""),
        )
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import streamlit as st


def render_project_info(*, location: str = "sidebar",
                        require_all: bool = True) -> Optional[dict]:
    """
    Render the standard Project Info fields and return them as a dict.

    Args:
        location: "sidebar" (default) or "main" — where to place the form.
        require_all: if True, returns None until all required fields are filled.

    Returns a dict with keys:
        project_number, project_name, member_mark, designer, design_date,
        calc_label  (may be "")
    """
    container = st.sidebar if location == "sidebar" else st

    with container:
        st.markdown("### Project Info")

        project_number = st.text_input(
            "Project Number",
            key="vk_project_number",
            help="From the ViKO project register.",
        )
        project_name = st.text_input(
            "Project Name",
            key="vk_project_name",
        )
        member_mark = st.text_input(
            "Member Mark",
            key="vk_member_mark",
            help="e.g. B1, C-12, BR-3",
        )
        designer = st.text_input(
            "Designer",
            key="vk_designer",
            help="Your name or initials.",
        )
        design_date = st.date_input(
            "Date",
            value=date.today(),
            key="vk_design_date",
        )
        calc_label = st.text_input(
            "Calc Label (optional)",
            key="vk_calc_label",
            help="e.g. 'Initial design', 'Revision A'.",
        )

    info = {
        "project_number": project_number.strip(),
        "project_name":   project_name.strip(),
        "member_mark":    member_mark.strip(),
        "designer":       designer.strip(),
        "design_date":    design_date.isoformat(),
        "calc_label":     calc_label.strip(),
    }

    if require_all:
        missing = [k for k in
                   ("project_number", "project_name", "member_mark", "designer")
                   if not info[k]]
        if missing:
            return None

    return info


def project_info_is_complete(info: Optional[dict]) -> bool:
    """Convenience for `if project_info_is_complete(proj): show save button`."""
    if info is None:
        return False
    return all(info.get(k) for k in
               ("project_number", "project_name", "member_mark", "designer"))