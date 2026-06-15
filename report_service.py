import json
import math
import os
import base64
from pathlib import Path
from datetime import datetime
from jinja2 import Template


# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

JSON_FILE = Path(os.environ.get("OUTPUT_FILE", BASE_DIR / "data" / "workforce_analysis_output.json"))
EXTRACTED_JSON_FILE = Path(os.environ.get("INPUT_FILE", BASE_DIR / "all_files_extracted_data.json"))
TEMPLATE_FILE = BASE_DIR / "workforce_report_template.html"
OUTPUT_FILE = Path(os.environ.get("REPORT_HTML", BASE_DIR / "reports" / "workforce_report.html"))


# ── Dynamic helpers ────────────────────────────────────────────────────────

def _safe_get(record, *keys, default=""):
    """Case-insensitive, fallback-aware dict lookup."""
    if not isinstance(record, dict):
        return default
    record_lower = {str(k).lower().strip(): v for k, v in record.items()}
    for key in keys:
        val = record_lower.get(str(key).lower().strip())
        if val is not None:
            return val
    return default


def _clean_str(val):
    """Convert value to clean string, treating NaN / None as empty."""
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    s = str(val).strip()
    return s if s.lower() != "nan" else ""


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _map_project_types(active_projects_table):
    mapping = {}

    for proj in active_projects_table or []:

        name = _clean_str(
            _safe_get(
                proj,
                "project",
                "project_name",
                "Project Name"
            )
        )

        ptype = _clean_str(
            _safe_get(
                proj,
                "type",
                "Type"
            )
        ) or "Project"

        if name:
            mapping[name.lower()] = ptype

    return mapping


def _build_employee_lookup(extracted_data):
    """
    Scan the extracted master JSON for an 'Active' sheet and build a lookup
    keyed by employee name -> {current_role, reporting_to}.
    """
    lookup = {}
    for file_content in extracted_data.values():
        if not isinstance(file_content, dict):
            continue
        for sheet_name, rows in file_content.items():
            if str(sheet_name).strip().lower() != "active":
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                name = _clean_str(_safe_get(row, "Active Employee", "Name", "Employee"))
                if not name:
                    continue
                lookup[name] = {
                    "current_role": _clean_str(_safe_get(row, "Current Role", "Role")) or "—",
                    "reporting_to": _clean_str(_safe_get(row, "Reporting To", "Manager")) or "—",
                }
    return lookup


# ── Report generation ──────────────────────────────────────────────────────

def generate_report() -> None:

    # 1. Load analysis JSON from LLM
    data = _load_json(JSON_FILE)

    # Load raw extracted data for enriching employee details
    extracted_data = {}
    if EXTRACTED_JSON_FILE.exists():
        extracted_data = _load_json(EXTRACTED_JSON_FILE)

    # 2. Workforce overview – normalise varying LLM key names
    wfo = data.get("workforce_overview", {})

    active_employees = len(
    data.get("active_employees_filtered_list", [])
    )
    current_projects = len(
    data.get("active_projects_table", [])
    )
    unallocated_employees = len(
    data.get("unallocated_employees", [])
    )

    
    # 3. Categorise allocations using type metadata from active_projects_table
    
    proj_type_map = _map_project_types(data.get("active_projects_table", []))

    allocations = data.get("project_allocations", {})

    flat_allocations = {}

    # New Gemini structure
    if "projects" in allocations:
        flat_allocations.update(
        allocations.get("projects", {})
        )

    if "retainers" in allocations:
        flat_allocations.update(
        allocations.get("retainers", {})
        )

    if "internal" in allocations:
        flat_allocations.update(
        allocations.get("internal", {})
        )

    # Old Ollama structure
    if not flat_allocations:
        flat_allocations = allocations

    print("\n===== PROJECT TYPES =====")
    print(json.dumps(proj_type_map, indent=2))

    print("\n===== PROJECT ALLOCATIONS =====")
    print(json.dumps(flat_allocations, indent=2))

    projects = []
    retainers = []
    internal = []

    for proj_name in flat_allocations.keys():
        ptype = proj_type_map.get(proj_name.lower().strip())

        if not ptype:
            print(f"Skipping unknown project: {proj_name}")
            continue

        entry = {"project_name": proj_name}

        if ptype.lower() == "project":
            projects.append(entry)
        elif ptype.lower() in ("retainer", "retainers"):
            retainers.append(entry)
        elif ptype.lower() in ("internal", "internals"):
            internal.append(entry)
        else:
            projects.append(entry)

    overview = {
        "active_employees": active_employees,
        "current_projects": current_projects,
        "unallocated_employees": unallocated_employees,
        "project_distribution": {
            "client_projects": {
                "count": len(projects),
                "projects": [p["project_name"] for p in projects],
            },
            "retainer_projects": {
                "count": len(retainers),
                "projects": [p["project_name"] for p in retainers],
            },
            "internal_projects": {
                "count": len(internal),
                "projects": [p["project_name"] for p in internal],
            },
        },
    }

    # 4. Project allocation summary (Section 02 cards)
    project_allocation_summary = []
    for project in data.get("active_projects_table", []):
        project_name = (
            project.get("project")
            or project.get("project_name")
            or project.get("Project Name")
        )
        if not project_name:
            continue

        employees = []
        for alloc_name, alloc_employees in flat_allocations.items():
            if alloc_name.strip().lower() == project_name.strip().lower():
                employees = alloc_employees
                break

        project_allocation_summary.append({
            "project_name": project_name,
            "employee_count": len(employees),
            "employees": employees,
        })

    # 5. Unallocated employees – enrich from extracted Active sheet
    emp_lookup = _build_employee_lookup(extracted_data)
    raw_unallocated = data.get("unallocated_employees", [])

    unallocated_employee_list = []

    for item in raw_unallocated:
        if isinstance(item, dict):
            name = (
                item.get("name")
                or item.get("employee_name")
                or item.get("Employee Name")
                or item.get("Active Employee")
                or ""
            )
        else:
            name = str(item)

        info = emp_lookup.get(name, {})

        unallocated_employee_list.append({
            "name": name,
            "current_role": info.get("current_role", "—"),
            "reporting_to": info.get("reporting_to", "—"),
        })

    generated_date = datetime.now().strftime("%d %B %Y")

    # 6. Embed logo as base64
    logo_file = BASE_DIR / "ui" / "64e32576ae89c46bfb5ed1c3_wohlighighres (1).webp"
    logo_data_uri = ""
    if logo_file.exists():
        with open(logo_file, "rb") as lf:
            b64 = base64.b64encode(lf.read()).decode("utf-8")
            logo_data_uri = f"data:image/webp;base64,{b64}"

    # 7. Render HTML
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        template = Template(f.read())

    html = template.render(
        workforce=overview,
        project_allocation_summary=project_allocation_summary,
        unallocated_employee_list=unallocated_employee_list,
        generated_date=generated_date,
        logo_data_uri=logo_data_uri,
    )

    # 8. Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report generated: {OUTPUT_FILE}")


# ── Entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    generate_report()