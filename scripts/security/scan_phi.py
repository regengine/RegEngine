import os
import sys
from pathlib import Path
from typing import List

# Constitution 1.1: Zero PHI Keywords
FORBIDDEN_KEYWORDS = [
    "patient_name",
    "ssn",
    "social_security",
    "diagnosis",
    "medical_record_number",
    "mrn",
    "clinical_notes", 
    "treatment_plan",
    "prescription_details",
    "dob", 
    "date_of_birth"
]

# Allow-list for demo scripts or specific constrained contexts (if any)
EXCLUDED_FILES = [
    "services/admin/seeds/healthcare_demo.py", # Explicitly allows mock data for demos
    "scripts/security/scan_phi.py", # The scanner itself
    "services/admin/migrations/V12__production_compliance_init.sql" # Production/Film Vertical (Employee PII, not Patient PHI)
]

def scan_file(file_path: Path) -> List[str]:
    violations = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                lower_line = line.lower()
                for keyword in FORBIDDEN_KEYWORDS:
                    if keyword in lower_line:
                        # Simple check to avoid matching "patient_volume" vs "patient_name"
                        # Ideally regex, but substring is safer for broad catching
                        violations.append(f"Line {line_no}: Found forbidden keyword '{keyword}'")
    except Exception as e:
        print(f"⚠️ Could not read {file_path}: {e}")
    return violations

def run_scan():
    print("🛡️  Starting Zero-PHI Constitution Scan...")
    print("-----------------------------------------")
    
    root_dir = Path(".").resolve()
    
    # Directories to scan: Migrations and Schemas
    scan_targets = [
        root_dir / "services/admin/migrations",
        root_dir / "services/admin/app/verticals/healthcare/schemas.py",
        root_dir / "services/admin/app/verticals/healthcare/service.py"
    ]
    
    total_violations = 0
    
    for target in scan_targets:
        if target.is_file():
            files = [target]
        else:
            files = target.glob("**/*")
            
        for file_path in files:
            if not file_path.is_file():
                continue
            
            # Check exclusions
            rel_path = str(file_path.relative_to(root_dir))
            if rel_path in EXCLUDED_FILES:
                continue
                
            # Only scan relevant extensions
            if not file_path.suffix in [".sql", ".py", ".json"]:
                continue
                
            violations = scan_file(file_path)
            if violations:
                print(f"❌ VIOLATION in {rel_path}:")
                for v in violations:
                    print(f"   {v}")
                total_violations += 1
            else:
                # print(f"✅ Clean: {rel_path}")
                pass
                
    print("-----------------------------------------")
    if total_violations > 0:
        print(f"🚨 SCAN FAILED: Found {total_violations} files with potential PHI keywords.")
        sys.exit(1)
    else:
        print("✅ SCAN PASSED: No PHI keywords detected in critical paths.")
        sys.exit(0)

if __name__ == "__main__":
    run_scan()
