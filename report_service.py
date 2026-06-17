import json
import math
import re
from pathlib import Path
from datetime import datetime
from jinja2 import Template


# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

import os

env_output = os.environ.get("OUTPUT_FILE")
if env_output:
    op = Path(env_output)
    JSON_FILE = op if op.is_absolute() else BASE_DIR / op
else:
    JSON_FILE = BASE_DIR / "data" / "workforce_analysis_output.json"

env_input = os.environ.get("INPUT_FILE")
if env_input:
    ip = Path(env_input)
    EXTRACTED_JSON_FILE = ip if ip.is_absolute() else BASE_DIR / ip
else:
    EXTRACTED_JSON_FILE = BASE_DIR / "all_files_extracted_data.json"

TEMPLATE_FILE = BASE_DIR / "workforce_report_template.html"

env_report = os.environ.get("REPORT_HTML")
if env_report:
    rp = Path(env_report)
    OUTPUT_FILE = rp if rp.is_absolute() else BASE_DIR / rp
else:
    OUTPUT_FILE = BASE_DIR / "reports" / "workforce_report.html"


# ── Dynamic helpers ───────────────────────────────────────────────────────────

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


def _normalize_name(name):
    """
    Normalize a project/employee name for fuzzy matching.
    Strips whitespace, lowercases, collapses hyphens and multiple spaces,
    removes trailing/leading punctuation.
    'E-Mail automation ' → 'e-mail automation'
    'E-mail Automation'  → 'e-mail automation'
    """
    if not name:
        return ""
    s = str(name).strip().lower()
    # Collapse multiple spaces/tabs into single space
    s = re.sub(r'\s+', ' ', s)
    return s


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_employee_name(item):
    """
    Extract employee name from either a string or a dict.
    Handles:
      - "Pratik Sawant" (plain string)
      - {"name": "Pratik Sawant", "role": "..."} (dict with name key)
      - {"employee_name": "...", ...}
      - {"employee": "...", ...}
    Returns a clean string name, or empty string if not extractable.
    """
    if isinstance(item, str):
        return _clean_str(item)
    if isinstance(item, dict):
        return _clean_str(
            _safe_get(item, "name", "employee_name", "employee", "Name", "Employee")
        )
    return ""


def _map_project_types(active_projects_table):
    """
    Build a mapping: normalized project name → type metadata.
    Handles any key casing the LLM may emit.
    """
    mapping = {}
    for proj in active_projects_table or []:
        name = _clean_str(_safe_get(proj, "project", "project_name", "Project Name", "name"))
        ptype = _clean_str(_safe_get(proj, "type", "Type", "allocation_type")) or "Project"
        if name:
            mapping[_normalize_name(name)] = ptype
    return mapping


def _fuzzy_lookup_type(proj_name, proj_type_map):
    """
    Look up the project type using fuzzy matching.
    First tries exact normalized match, then tries substring containment.
    Falls back to heuristic if no match found.
    """
    norm = _normalize_name(proj_name)
    
    # 1. Exact normalized match
    if norm in proj_type_map:
        return proj_type_map[norm]
    
    # 2. Try matching with/without hyphens collapsed
    norm_no_hyphen = norm.replace("-", " ").replace("  ", " ")
    for key, ptype in proj_type_map.items():
        key_no_hyphen = key.replace("-", " ").replace("  ", " ")
        if norm_no_hyphen == key_no_hyphen:
            return ptype
    
    # 3. Substring containment (for slight variations)
    for key, ptype in proj_type_map.items():
        if norm in key or key in norm:
            return ptype
    
    # 4. Heuristic fallback
    lower = norm.lower()
    if any(w in lower for w in ["learning", "training", "automation", "internal"]):
        return "Internal"
    
    return "Project"


def _build_employee_lookup(extracted_data):
    """
    Scan the extracted master JSON for an 'Active' sheet and build a lookup
    keyed by employee name → {current_role, reporting_to}.
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


def _flatten_allocations(raw_allocs):
    """
    Robustly handle ALL possible LLM output formats for project_allocations.
    
    Format 1 – Flat string list:
      {"Vaultify": ["Pratik Sawant", "Agam Shah"]}
    
    Format 2 – List of employee objects:
      {"Vaultify": [{"name": "Pratik Sawant", "role": "..."}, ...]}
    
    Format 3 – Grouped by type:
      {"projects": [{"project": "ZEE5", "employees": [...]}], "retainers": [...]}
    
    Format 4 – Mixed (some keys are project names, some are type groups):
      Handled by checking if value items have an "employees" or "team" sub-key.
    
    Format 5 – List of project objects (new LLM output):
      [{"project_name":"Vaultify","type":"Retainer","allocated_employees":[...]}, ...]
    
    Returns a flat dictionary mapping project_name → [employee_name_strings]
    """
    flat = {}
    
    # Format 5: list of project objects
    if isinstance(raw_allocs, list):
        for item in raw_allocs:
            if not isinstance(item, dict):
                continue
            pname = _clean_str(_safe_get(item, "project_name", "project", "name", "Name"))
            if not pname:
                continue
            emps_raw = (
                item.get("allocated_employees")
                or item.get("employees")
                or item.get("team")
                or item.get("members")
                or []
            )
            emp_names = [_extract_employee_name(e) for e in emps_raw]
            flat[pname] = [n for n in emp_names if n]
        return flat
    
    if not isinstance(raw_allocs, dict):
        return flat
    
    for k, v in raw_allocs.items():
        if not isinstance(v, list):
            # Scalar or null value — skip
            continue
        
        if not v:
            # Empty list — could be a project with 0 employees, skip it
            continue
        
        first = v[0]
        
        if isinstance(first, str):
            # Format 1: flat string list — {"ProjectName": ["emp1", "emp2"]}
            flat[k] = [_clean_str(e) for e in v if _clean_str(e)]
        
        elif isinstance(first, dict):
            # Could be Format 2 or Format 3. Distinguish by checking
            # if items have an "employees"/"team" key (→ grouped project entries)
            # or just "name"/"role" keys (→ employee objects for project k).
            
            has_employees_key = any(
                "employees" in item or "team" in item or "members" in item
                for item in v if isinstance(item, dict)
            )
            has_project_key = any(
                any(pk in item for pk in ("project", "project_name", "name"))
                and ("employees" in item or "team" in item or "members" in item)
                for item in v if isinstance(item, dict)
            )
            
            if has_project_key:
                # Format 3: grouped — each item is a project with an employees list
                for item in v:
                    if not isinstance(item, dict):
                        continue
                    pname = _clean_str(_safe_get(
                        item, "project", "project_name", "name"
                    ))
                    emps_raw = (
                        item.get("employees")
                        or item.get("team")
                        or item.get("members")
                        or []
                    )
                    if pname:
                        emp_names = [_extract_employee_name(e) for e in emps_raw]
                        flat[pname] = [n for n in emp_names if n]
            else:
                # Format 2: list of employee objects — key `k` IS the project name
                emp_names = [_extract_employee_name(item) for item in v]
                flat[k] = [n for n in emp_names if n]
    
    return flat


def _safe_int(val, default=0):
    """Safely convert a value to int, returning default for None/NaN/non-numeric."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        if isinstance(val, float) and math.isnan(val):
            return default
        return int(val)
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# ── Report generation ──────────────────────────────────────────────────────
def generate_report() -> None:

    # 1. Load analysis JSON from LLM
    data = _load_json(JSON_FILE)

    # Load raw extracted data for enriching employee details
    extracted_data = {}
    if EXTRACTED_JSON_FILE.exists():
        extracted_data = _load_json(EXTRACTED_JSON_FILE)

    # 2. Workforce overview – compute true totals where possible instead of relying on LLM math
    wfo = data.get("workforce_overview") or {}

    active_employees = 0
    active_sheet_found = False
    if extracted_data:
        for fname, sheets in extracted_data.items():
            if isinstance(sheets, dict) and "Active" in sheets:
                active_list = sheets["Active"]
                if isinstance(active_list, list):
                    active_employees = sum(1 for x in active_list if str(x.get("Active Employee", "nan")).lower() != "nan")
                    active_sheet_found = True
                    break
    if not active_sheet_found:
        # Use explicit None check to avoid falsy-zero bug (0 or len([...]) → len([...]))
        llm_count = _safe_get(wfo, "total_filtered_employees", "total_active_employees", default=None)
        active_employees = _safe_int(llm_count, default=0)

    # For current_projects: prefer actual count from active_projects_table
    active_projects_table = data.get("active_projects_table") or []
    current_projects = len(active_projects_table) if active_projects_table else _safe_int(
        _safe_get(wfo, "total_active_projects", "active_projects", default=0)
    )

    # For unallocated: use explicit None check to avoid 0-is-falsy bug
    raw_unallocated = data.get("unallocated_employees") or []
    llm_unalloc = _safe_get(wfo, "total_unallocated_employees", "unallocated_employees", "total_bench_employees", "total_bench", default=None)
    if llm_unalloc is not None and isinstance(llm_unalloc, (int, float)):
        unallocated_employees = _safe_int(llm_unalloc)
    else:
        unallocated_employees = len(raw_unallocated)

    # 3. Categorise allocations using type metadata from active_projects_table
    proj_type_map = _map_project_types(active_projects_table)
    
    raw_allocs = data.get("project_allocations") or {}
    flat_allocations = _flatten_allocations(raw_allocs)

    projects, retainers, internal = [], [], []

    for proj_name in flat_allocations.keys():
        ptype = _fuzzy_lookup_type(proj_name, proj_type_map)
                
        entry = {"project_name": proj_name}
        ptype_lower = ptype.lower().strip()
        if ptype_lower in ("retainer", "retainers"):
            retainers.append(entry)
        elif ptype_lower in ("internal", "internals"):
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
    #    Include every project in project_allocations.
    project_allocation_summary = []
    for proj_name, employees in flat_allocations.items():
        project_allocation_summary.append({
            "project_name": proj_name,
            "employee_count": len(employees),
            "employees": employees,
        })

    # 5. Unallocated employees – enrich from extracted Active sheet
    emp_lookup = _build_employee_lookup(extracted_data)

    unallocated_employee_list = []
    for item in raw_unallocated:
        reason = "—"
        if isinstance(item, dict):
            name = _clean_str(_safe_get(item, "name", "Name", "employee_name", "employee"))
            # Handle both "role" and "current_role" keys from LLM
            role = _clean_str(_safe_get(item, "current_role", "Current Role", "role", "Role")) or ""
            manager = _clean_str(_safe_get(item, "reporting_to", "Reporting To", "manager", "Manager")) or ""
            reason = _clean_str(_safe_get(item, "reason", "Reason", "bench_reason")) or "—"
            
            # Enrich from extracted data if LLM didn't provide role/manager
            info = emp_lookup.get(name, {})
            if not role or role == "—":
                role = info.get("current_role", "—")
            if not manager or manager == "—":
                manager = info.get("reporting_to", "—")
        else:
            name = _clean_str(item)
            info = emp_lookup.get(name, {})
            role = info.get("current_role", "—")
            manager = info.get("reporting_to", "—")
            
        if name:  # Only add if we got a valid name
            unallocated_employee_list.append({
                "name": name,
                "current_role": role,
                "reporting_to": manager,
                "reason": reason,
            })

    generated_date = datetime.now().strftime("%d %B %Y")

    import base64
    # Auto-detect logo: first .webp in ui/, fallback to dashboard/public/logo.webp
    logo_candidates = [
        *(BASE_DIR / "ui").glob("*.webp"),
        BASE_DIR / "dashboard" / "public" / "logo.webp",
    ]
    logo_file = next((p for p in logo_candidates if p.exists()), None)
    logo_data_uri = ""
    if logo_file:
        with open(logo_file, "rb") as lf:
            b64 = base64.b64encode(lf.read()).decode("utf-8")
            logo_data_uri = f"data:image/webp;base64,{b64}"

    # 6. Render HTML
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        template = Template(f.read())

    html = template.render(
        workforce=overview,
        project_allocation_summary=project_allocation_summary,
        unallocated_employee_list=unallocated_employee_list,
        generated_date=generated_date,
        logo_data_uri=logo_data_uri,
    )

    # 7. Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report generated: {OUTPUT_FILE}")


# ── Entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    generate_report()