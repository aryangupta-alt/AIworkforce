import os
import sys
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from ollama import Client, ResponseError

# Load environment variables from .env file
load_dotenv()

# ==========================================
# ADAPTIVE CONFIGURATION (no hardcoding)
# ==========================================
MODEL_NAME = os.environ.get("OLLAMA_MODEL", "gemma4:31b-cloud")
INPUT_FILE = os.environ.get("INPUT_FILE", "all_files_extracted_data.json")
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "data/workforce_analysis_output.json")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "https://ollama.com")
USE_CHAT_API = os.environ.get("OLLAMA_USE_CHAT", "false").lower() in ("true", "1", "yes")

_api_key = os.environ.get('OLLAMA_API_KEY', '')
if not _api_key:
    print("[ERROR] OLLAMA_API_KEY not found in .env file.")
    print("        Please add: OLLAMA_API_KEY=your-key-here")
    sys.exit(1)

client = Client(
    host=OLLAMA_HOST,
    headers={'Authorization': f'Bearer {_api_key}'}
)
print(f"[INFO] Connected to Ollama at: {OLLAMA_HOST}")
print(f"[INFO] Model: {MODEL_NAME} | API: {'chat' if USE_CHAT_API else 'generate'}")


# ==========================================
# DATA LOADING
# ==========================================

def load_input_data(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Could not find {filepath}. Run drive_extract.py first.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"[ERROR] {filepath} is not valid JSON.")
        sys.exit(1)


# ==========================================
# ADAPTIVE PROMPT BUILDER
# ==========================================

def build_prompt(json_data):
    data_string = json.dumps(json_data, indent=2)
    # Truncate if data is extremely large
    max_chars = 150000
    if len(data_string) > max_chars:
        print(f"[WARNING] Input JSON too large ({len(data_string)} chars). Truncating...")
        data_string = data_string[:max_chars] + '\n... [truncated]'

    system_prompt = """You are an Expert HR & Project Allocation Auditor.
Analyze the provided workforce data and return ONLY valid JSON.

Your task:
1. Extract all active employees from the data
2. Identify unallocated employees (bench)
3. Map project allocations (projects, retainers, internal)
4. Find multi-allocated employees
5. Calculate totals

RULES:
- Tech Leads should NOT appear in unallocated list
- Interns ARE active employees
- Projects with status Done/Closed/Finished are NOT active

You must output ONLY a JSON object with these top-level keys:
step_by_step_reasoning, active_employees_filtered_list, unallocated_employees,
project_allocations, active_projects_table, workforce_overview, audit_logs"""

    user_prompt = f"""Analyze this workforce data and return the audit JSON:

{data_string}

Return ONLY valid JSON matching the expected schema."""

    return system_prompt, user_prompt


# ==========================================
# ADAPTIVE JSON EXTRACTION (handles any format)
# ==========================================

def extract_json_from_response(text):
    """Extract JSON from LLM response regardless of wrapping format."""
    if not text or not text.strip():
        return None

    text = text.strip()

    # Method 1: Extract from markdown code blocks
    code_block_patterns = [
        r'```json\s*(.*?)\s*```',
        r'```\s*(.*?)\s*```',
    ]
    for pattern in code_block_patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue

    # Method 2: Find outermost JSON object/array
    # Try to find the first { and last } that form valid JSON
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start_idx = text.find(start_char)
        if start_idx == -1:
            continue
        # Try progressively smaller slices from the end
        end_idx = text.rfind(end_char)
        while end_idx > start_idx:
            candidate = text[start_idx:end_idx + 1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                # Try next potential closing brace
                end_idx = text.rfind(end_char, 0, end_idx)

    # Method 3: Return raw text if it starts with { or [
    if text.startswith('{') or text.startswith('['):
        return text

    return None


# ==========================================
# LLM CALL (adaptive: generate or chat)
# ==========================================

def call_llm(system_prompt, user_prompt):
    """Call Ollama with fallback between generate and chat APIs."""
    errors = []

    # Try generate API first (or if USE_CHAT_API is false)
    if not USE_CHAT_API:
        try:
            print("[LLM] Trying generate API...")
            response = client.generate(
                model=MODEL_NAME,
                system=system_prompt,
                prompt=user_prompt,
                options={'temperature': 0.1}
            )
            print(f"[LLM] Response type: {type(response).__name__}")
            
            # Handle various response formats (dict, object with .response, generator, etc)
            result = ''
            if isinstance(response, dict):
                result = response.get('response', '')
            elif hasattr(response, 'response'):
                result = response.response
            elif hasattr(response, 'content'):
                result = response.content
            elif hasattr(response, '__iter__') and not isinstance(response, (str, bytes)):
                # Streaming response - collect all parts
                parts = []
                for part in response:
                    if isinstance(part, dict):
                        parts.append(part.get('response', ''))
                    elif hasattr(part, 'response'):
                        parts.append(part.response)
                result = ''.join(parts)
            else:
                result = str(response)
            
            print(f"[LLM] Response length: {len(result) if result else 0} chars")
            if result and result.strip():
                return result
            errors.append("generate API returned empty response")
        except Exception as e:
            errors.append(f"generate API failed: {e}")

    # Fallback to chat API
    try:
        print("[LLM] Trying chat API...")
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]
        response = client.chat(
            model=MODEL_NAME,
            messages=messages,
            options={'temperature': 0.1}
        )
        
        print(f"[LLM] Response type: {type(response).__name__}")
        
        result = ''
        if isinstance(response, dict):
            if 'message' in response and isinstance(response['message'], dict):
                result = response['message'].get('content', '')
            else:
                result = response.get('response', '') or response.get('content', '')
        elif hasattr(response, 'message'):
            msg = response.message
            if hasattr(msg, 'content'):
                result = msg.content
            elif isinstance(msg, dict):
                result = msg.get('content', '')
        elif hasattr(response, '__iter__') and not isinstance(response, (str, bytes)):
            # Streaming chat response
            parts = []
            for part in response:
                if isinstance(part, dict) and 'message' in part:
                    parts.append(part['message'].get('content', ''))
                elif hasattr(part, 'message') and hasattr(part.message, 'content'):
                    parts.append(part.message.content)
            result = ''.join(parts)
        else:
            result = str(response)
        
        print(f"[LLM] Response length: {len(result) if result else 0} chars")
        if result and result.strip():
            return result
        errors.append("chat API returned empty response")
    except Exception as e:
        errors.append(f"chat API failed: {e}")

    raise RuntimeError(f"All LLM APIs failed:\n" + "\n".join(errors))


# ==========================================
# MAIN AUDIT PIPELINE
# ==========================================

def run_audit(input_file=None, output_file=None):
    input_path = input_file or INPUT_FILE
    output_path = output_file or OUTPUT_FILE

    print("Loading extracted JSON data...")
    input_data = load_input_data(input_path)

    system_prompt, user_prompt = build_prompt(input_data)

    print(f"Sending data to {MODEL_NAME}...")
    print(f"[INFO] Input size: ~{len(json.dumps(input_data))} chars")

    try:
        raw_response = call_llm(system_prompt, user_prompt)

        if not raw_response or not raw_response.strip():
            print("[ERROR] LLM returned empty response.")
            sys.exit(1)

        print(f"[INFO] LLM response length: {len(raw_response)} chars")

        # Extract JSON
        clean_json = extract_json_from_response(raw_response)
        if not clean_json:
            print("[ERROR] Could not extract valid JSON from LLM response.")
            print("[DEBUG] Raw response preview:")
            print(raw_response[:500])
            sys.exit(1)

        # Parse and validate
        try:
            parsed_json = json.loads(clean_json)
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON parse error: {e}")
            print("[DEBUG] Extracted JSON preview:")
            print(clean_json[:500])
            sys.exit(1)

        # Validate required keys exist
        required_keys = [
            'workforce_overview',
            'project_allocations',
            'active_projects_table',
            'unallocated_employees'
        ]
        missing = [k for k in required_keys if k not in parsed_json]
        if missing:
            print(f"[WARNING] Missing keys in output: {missing}")

        # Ensure output directory exists
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(parsed_json, f, indent=2, ensure_ascii=False)

        print(f"[SUCCESS] Audit report saved to: {output_path}")
        return output_path

    except ResponseError as e:
        print(f"[ERROR] Ollama API error (status {e.status_code}): {e.error}")
        if e.status_code == 401:
            print("[HINT] Your OLLAMA_API_KEY may be invalid or expired.")
        elif e.status_code == 404:
            print(f"[HINT] Model '{MODEL_NAME}' not found. Check available models.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_audit()
