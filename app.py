#!/usr/bin/env python3
"""
Pipeline Orchestrator
Runs the full pipeline: Drive Extract -> LLM Analysis -> Report Generation
"""

import sys
import os

# Ensure the pipeline directory is the working directory for relative paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

# Import pipeline stages
from drive_extract import run_extraction
from llm_analysis import run_audit
from report_service import generate_report


def main():
    print("=" * 60)
    print("WORKFORCE INTELLIGENCE PIPELINE")
    print("=" * 60)

    # Stage 1: Extract data from Google Drive
    print("\n>>> STAGE 1: Google Drive Data Extraction")
    print("-" * 60)
    try:
        extracted_json = run_extraction()
        print(f"[OK] Extraction complete: {extracted_json}")
    except Exception as e:
        print(f"[FAIL] Extraction failed: {e}")
        sys.exit(1)

    # Stage 2: LLM Analysis
    print("\n>>> STAGE 2: LLM Analysis")
    print("-" * 60)
    try:
        analysis_json = run_audit()
        print(f"[OK] Analysis complete: {analysis_json}")
    except Exception as e:
        print(f"[FAIL] Analysis failed: {e}")
        sys.exit(1)

    # Stage 3: Generate HTML Report
    print("\n>>> STAGE 3: Report Generation")
    print("-" * 60)
    try:
        generate_report()
        print("[OK] Report generation complete")
    except Exception as e:
        print(f"[FAIL] Report generation failed: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()