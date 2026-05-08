"""
viko_db.py — Shared database layer for ViKO design tools.

Stores projects, members, and calculations from all design apps in a single
SQLite database on the W: drive (or local fallback for development).

Usage:
    from viko_db import get_conn, init_db, save_calculation, ...

Notes on concurrency:
    Currently using default SQLite journal mode. With 2-5 engineers performing
    short-lived writes (saving a calc), contention is negligible. If you ever
    see "database is locked" errors in practice, switch to WAL mode by
    uncommenting the PRAGMA in _configure_connection().
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Primary location on the office network
NETWORK_DB_PATH = Path(
    r"W:\Central Information\DESIGN\VIKO Design Tool\database\viko_calcs.db"
)

# Local fallback for development / Streamlit Cloud testing
LOCAL_DB_PATH = Path(__file__).parent / "viko_calcs_local.db"

# ---------------------------------------------------------------------------
# Source-app URLs (for the dashboard "open in app" links)
# ---------------------------------------------------------------------------
# Map app_name (matches member_type in the DB) -> deployed Streamlit URL.
# Update these as apps are deployed/renamed. Used by the dashboard to build
# clickable links back to the source app for a given member type.
APP_URLS: dict[str, str] = {
    "concrete_beam":            "https://beam-optimiser-humdu84vwhksgdscj72pmp.streamlit.app/",
    "concrete_column_mn":       "https://concretecolumninteractiondiagram-h3i4mrpokucpa3pft2p6se.streamlit.app/",
    "welded_angle_tension":     "https://angle-tension-weld-design-9grv9yn6tuxtihpxf2hjxu.streamlit.app/",
    "bolted_angle_tension":     "https://angle-tension-bolted-design-iw9jfmngacorkf4cyhfsdy.streamlit.app/",
    "hi_section_compression":   "https://hicompressionapp-aotarm3guenobx57j8ojnb.streamlit.app/",
}


def get_db_path() -> Path:
    """Return the network DB path if reachable, otherwise the local fallback."""
    try:
        if NETWORK_DB_PATH.parent.exists():
            return NETWORK_DB_PATH
    except OSError:
        # Network drive unreachable
        pass
    return LOCAL_DB_PATH


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _configure_connection(conn: sqlite3.Connection) -> None:
    """Apply standard PRAGMAs to a new connection."""
    conn.execute("PRAGMA foreign_keys = ON;")
    # If you start hitting lock errors on the network share, uncomment:
    # conn.execute("PRAGMA journal_mode = WAL;")
    conn.row_factory = sqlite3.Row


def get_conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open a connection to the ViKO database, creating the file if needed."""
    path = Path(db_path) if db_path else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    _configure_connection(conn)
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    project_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    project_number  TEXT    NOT NULL UNIQUE,
    project_name    TEXT    NOT NULL,
    client          TEXT,
    notes           TEXT,
    status          TEXT    NOT NULL DEFAULT 'active',
    created_at      TEXT    NOT NULL,
    created_by      TEXT    NOT NULL,
    deleted_at      TEXT
);

CREATE TABLE IF NOT EXISTS members (
    member_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL REFERENCES projects(project_id),
    member_mark  TEXT    NOT NULL,
    member_type  TEXT    NOT NULL,
    description  TEXT,
    created_at   TEXT    NOT NULL,
    created_by   TEXT    NOT NULL,
    deleted_at   TEXT,
    UNIQUE (project_id, member_mark, member_type)
);

CREATE TABLE IF NOT EXISTS calculations (
    calc_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id               INTEGER NOT NULL REFERENCES members(member_id),
    app_name                TEXT    NOT NULL,
    app_version             TEXT    NOT NULL,
    calc_label              TEXT,
    inputs_json             TEXT    NOT NULL,
    results_json            TEXT    NOT NULL,
    summary_json            TEXT    NOT NULL,
    status                  TEXT    NOT NULL,
    governing_utilisation   REAL,
    is_current              INTEGER NOT NULL DEFAULT 1,
    created_at              TEXT    NOT NULL,
    created_by              TEXT    NOT NULL,
    deleted_at              TEXT
);

CREATE TABLE IF NOT EXISTS app_registry (
    app_name             TEXT PRIMARY KEY,
    display_name         TEXT NOT NULL,
    current_version      TEXT NOT NULL,
    code_standard        TEXT,
    summary_schema_json  TEXT,
    updated_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    user          TEXT NOT NULL,
    action        TEXT NOT NULL,
    entity_type   TEXT,
    entity_id     INTEGER,
    details_json  TEXT
);

CREATE INDEX IF NOT EXISTS idx_members_project   ON members(project_id);
CREATE INDEX IF NOT EXISTS idx_calcs_member      ON calculations(member_id);
CREATE INDEX IF NOT EXISTS idx_calcs_current     ON calculations(is_current);
CREATE INDEX IF NOT EXISTS idx_calcs_app         ON calculations(app_name);
"""


def init_db(db_path: Optional[Path] = None) -> None:
    """Create tables and indexes if they don't exist. Safe to call repeatedly."""
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    """ISO-8601 timestamp, second precision, no timezone (local office time)."""
    return datetime.now().replace(microsecond=0).isoformat()


def _audit(conn: sqlite3.Connection, user: str, action: str,
           entity_type: str, entity_id: Optional[int],
           details: Optional[dict] = None) -> None:
    conn.execute(
        "INSERT INTO audit_log (timestamp, user, action, entity_type, entity_id, details_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (_now(), user, action, entity_type, entity_id,
         json.dumps(details) if details else None),
    )


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def get_or_create_project(project_number: str, project_name: str,
                          created_by: str, client: str = "",
                          notes: str = "") -> int:
    """Return project_id; create the project if it doesn't exist."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT project_id FROM projects WHERE project_number = ? AND deleted_at IS NULL",
            (project_number,),
        ).fetchone()
        if row:
            return row["project_id"]

        cur = conn.execute(
            "INSERT INTO projects (project_number, project_name, client, notes, "
            "created_at, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (project_number, project_name, client, notes, _now(), created_by),
        )
        project_id = cur.lastrowid
        _audit(conn, created_by, "create_project", "project", project_id,
               {"project_number": project_number, "project_name": project_name})
        conn.commit()
        return project_id


def list_projects(include_archived: bool = False) -> list[dict]:
    sql = "SELECT * FROM projects WHERE deleted_at IS NULL"
    if not include_archived:
        sql += " AND status = 'active'"
    sql += " ORDER BY created_at DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

def get_or_create_member(project_id: int, member_mark: str,
                         member_type: str, created_by: str,
                         description: str = "") -> int:
    """Return member_id; create the member if it doesn't exist."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT member_id FROM members "
            "WHERE project_id = ? AND member_mark = ? AND member_type = ? "
            "AND deleted_at IS NULL",
            (project_id, member_mark, member_type),
        ).fetchone()
        if row:
            return row["member_id"]

        cur = conn.execute(
            "INSERT INTO members (project_id, member_mark, member_type, "
            "description, created_at, created_by) VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, member_mark, member_type, description, _now(), created_by),
        )
        member_id = cur.lastrowid
        _audit(conn, created_by, "create_member", "member", member_id,
               {"member_mark": member_mark, "member_type": member_type})
        conn.commit()
        return member_id


def list_members(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM members WHERE project_id = ? AND deleted_at IS NULL "
            "ORDER BY member_type, member_mark",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------

def save_calculation(*,
                     project_number: str,
                     project_name: str,
                     member_mark: str,
                     member_type: str,
                     app_name: str,
                     app_version: str,
                     inputs: dict,
                     results: dict,
                     summary: dict,
                     status: str,
                     governing_utilisation: Optional[float],
                     created_by: str,
                     calc_label: str = "",
                     member_description: str = "",
                     client: str = "",
                     project_notes: str = "") -> int:
    """
    Save a calculation. Creates project and member if needed.
    Marks any previous current calc for the same member+app as not current.
    Returns the new calc_id.
    """
    project_id = get_or_create_project(
        project_number=project_number, project_name=project_name,
        created_by=created_by, client=client, notes=project_notes,
    )
    member_id = get_or_create_member(
        project_id=project_id, member_mark=member_mark, member_type=member_type,
        created_by=created_by, description=member_description,
    )

    with get_conn() as conn:
        # Demote previous current calc for this member+app
        conn.execute(
            "UPDATE calculations SET is_current = 0 "
            "WHERE member_id = ? AND app_name = ? AND is_current = 1",
            (member_id, app_name),
        )

        cur = conn.execute(
            "INSERT INTO calculations (member_id, app_name, app_version, "
            "calc_label, inputs_json, results_json, summary_json, status, "
            "governing_utilisation, is_current, created_at, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (member_id, app_name, app_version, calc_label,
             json.dumps(inputs), json.dumps(results), json.dumps(summary),
             status, governing_utilisation, _now(), created_by),
        )
        calc_id = cur.lastrowid
        _audit(conn, created_by, "save_calc", "calculation", calc_id,
               {"app_name": app_name, "status": status})
        conn.commit()
        return calc_id


def load_calculation(calc_id: int) -> dict:
    """Load a single calculation with inputs/results/summary deserialised."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT c.*, m.member_mark, m.member_type, m.description AS member_description, "
            "p.project_number, p.project_name, p.client "
            "FROM calculations c "
            "JOIN members m  ON m.member_id  = c.member_id "
            "JOIN projects p ON p.project_id = m.project_id "
            "WHERE c.calc_id = ? AND c.deleted_at IS NULL",
            (calc_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Calculation {calc_id} not found")
        d = dict(row)
        d["inputs"]  = json.loads(d.pop("inputs_json"))
        d["results"] = json.loads(d.pop("results_json"))
        d["summary"] = json.loads(d.pop("summary_json"))
        return d


def list_calculations(member_id: int, current_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM calculations WHERE member_id = ? AND deleted_at IS NULL"
    if current_only:
        sql += " AND is_current = 1"
    sql += " ORDER BY created_at DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, (member_id,)).fetchall()]


# ---------------------------------------------------------------------------
# App registry
# ---------------------------------------------------------------------------

def register_app(app_name: str, display_name: str, current_version: str,
                 code_standard: str = "", summary_schema: Optional[dict] = None) -> None:
    """Each app calls this on startup to declare itself to the dashboard."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO app_registry (app_name, display_name, current_version, "
            "code_standard, summary_schema_json, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(app_name) DO UPDATE SET "
            "display_name = excluded.display_name, "
            "current_version = excluded.current_version, "
            "code_standard = excluded.code_standard, "
            "summary_schema_json = excluded.summary_schema_json, "
            "updated_at = excluded.updated_at",
            (app_name, display_name, current_version, code_standard,
             json.dumps(summary_schema) if summary_schema else None, _now()),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Dashboard queries
# ---------------------------------------------------------------------------

def list_projects_with_summary(include_archived: bool = False) -> list[dict]:
    """
    Return every project with a member count and worst-case utilisation
    across its current calcs. Drives the dashboard's project list.
    """
    sql = """
    SELECT
        p.project_id,
        p.project_number,
        p.project_name,
        p.client,
        p.status,
        p.created_at,
        p.created_by,
        COUNT(DISTINCT m.member_id) AS member_count,
        COUNT(c.calc_id)            AS calc_count,
        MAX(c.governing_utilisation) AS max_utilisation,
        SUM(CASE WHEN c.status = 'fail' THEN 1 ELSE 0 END) AS fail_count
    FROM projects p
    LEFT JOIN members m
        ON m.project_id = p.project_id AND m.deleted_at IS NULL
    LEFT JOIN calculations c
        ON c.member_id = m.member_id
        AND c.is_current = 1
        AND c.deleted_at IS NULL
    WHERE p.deleted_at IS NULL
    """
    if not include_archived:
        sql += " AND p.status = 'active' "
    sql += " GROUP BY p.project_id ORDER BY p.created_at DESC"

    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def get_project_dashboard(project_id: int) -> list[dict]:
    """
    Return one row per member in the project, joined to its current calc
    and the app's display name. Drives the project detail view.
    """
    sql = """
    SELECT
        m.member_id,
        m.member_mark,
        m.member_type,
        m.description,
        m.created_at  AS member_created_at,
        c.calc_id,
        c.app_name,
        c.app_version,
        c.calc_label,
        c.summary_json,
        c.status,
        c.governing_utilisation,
        c.created_at  AS calc_created_at,
        c.created_by  AS calc_created_by,
        a.display_name AS app_display_name,
        a.code_standard
    FROM members m
    LEFT JOIN calculations c
        ON c.member_id = m.member_id
        AND c.is_current = 1
        AND c.deleted_at IS NULL
    LEFT JOIN app_registry a
        ON a.app_name = c.app_name
    WHERE m.project_id = ? AND m.deleted_at IS NULL
    ORDER BY m.member_type, m.member_mark
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (project_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("summary_json"):
            d["summary"] = json.loads(d["summary_json"])
        else:
            d["summary"] = {}
        del d["summary_json"]
        out.append(d)
    return out


def get_project(project_id: int) -> Optional[dict]:
    """Single-project header info."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE project_id = ? AND deleted_at IS NULL",
            (project_id,),
        ).fetchone()
        return dict(row) if row else None


def get_member(member_id: int) -> Optional[dict]:
    """Single-member info, joined to its project."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT m.*, p.project_number, p.project_name "
            "FROM members m JOIN projects p ON p.project_id = m.project_id "
            "WHERE m.member_id = ? AND m.deleted_at IS NULL",
            (member_id,),
        ).fetchone()
        return dict(row) if row else None


def at_risk_calcs(util_threshold: float = 0.95) -> list[dict]:
    """
    Return current calcs that have utilisation >= threshold OR status='fail'.
    Drives the dashboard's "what should I look at" panel.
    """
    sql = """
    SELECT
        c.calc_id, c.governing_utilisation, c.status, c.calc_label,
        c.created_at AS calc_created_at,
        m.member_id, m.member_mark, m.member_type,
        p.project_id, p.project_number, p.project_name,
        a.display_name AS app_display_name
    FROM calculations c
    JOIN members m  ON m.member_id  = c.member_id  AND m.deleted_at IS NULL
    JOIN projects p ON p.project_id = m.project_id AND p.deleted_at IS NULL
    LEFT JOIN app_registry a ON a.app_name = c.app_name
    WHERE c.is_current = 1
      AND c.deleted_at IS NULL
      AND (c.governing_utilisation >= ? OR c.status = 'fail')
    ORDER BY
        CASE c.status WHEN 'fail' THEN 0 ELSE 1 END,
        c.governing_utilisation DESC
    """
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, (util_threshold,)).fetchall()]
