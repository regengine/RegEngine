"""
Code Generation Module
======================
Generates FastAPI routes and Pydantic models from vertical schemas.

Uses Jinja2 templates for clean, maintainable code generation.
"""

from pathlib import Path
from typing import List, Dict, Any
from jinja2 import Environment, PackageLoader, select_autoescape
import black

# Initialize Jinja2 environment
env = Environment(
    loader=PackageLoader('vertical_compiler'),
    autoescape=select_autoescape(),
    trim_blocks=True,
    lstrip_blocks=True
)


def generate_fastapi_routes(vertical_meta, obligations: List) -> str:
    """
    Generate FastAPI routes file.
    
    Generates:
    - POST /v1/{vertical}/decision/record
    - POST /v1/{vertical}/decision/replay
    - GET /v1/{vertical}/snapshot
    - GET /v1/{vertical}/export
    """
    template = env.get_template('routes.py.j2')
    
    code = template.render(
        vertical_name=vertical_meta.name,
        decision_types=vertical_meta.decision_types,
        regulators=vertical_meta.regulators,
        domains=vertical_meta.regulatory_domains
    )
    
    # Format with black
    formatted = black.format_str(code, mode=black.Mode())
    
    return formatted


def generate_pydantic_models(vertical_meta, obligations: List) -> str:
    """
    Generate Pydantic models file.
    
    Generates:
    - DecisionRequest
    - DecisionResponse
    - SnapshotResponse
    - ExportRequest
    """
    template = env.get_template('models.py.j2')
    
    code = template.render(
        vertical_name=vertical_meta.name,
        decision_types=vertical_meta.decision_types,
        evidence_contract=vertical_meta.evidence_contract,
        risk_dimensions=vertical_meta.risk_dimensions
    )
    
    # Format with black
    formatted = black.format_str(code, mode=black.Mode())
    
    return formatted


def generate_test_scaffolds(vertical_meta, obligations: List, output_dir: Path) -> List[Path]:
    """
    Generate test scaffold files.
    
    Generates:
    - test_routes.py
    - test_models.py
    - test_snapshot.py
    """
    template_routes = env.get_template('test_routes.py.j2')
    template_models = env.get_template('test_models.py.j2')
    template_snapshot = env.get_template('test_snapshot.py.j2')
    
    generated_files = []
    
    # Generate test_routes.py
    routes_test = template_routes.render(
        vertical_name=vertical_meta.name,
        decision_types=vertical_meta.decision_types
    )
    routes_test_file = output_dir / "test_routes.py"
    with open(routes_test_file, 'w') as f:
        f.write(black.format_str(routes_test, mode=black.Mode()))
    generated_files.append(routes_test_file)
    
    # Generate test_models.py
    models_test = template_models.render(
        vertical_name=vertical_meta.name,
        decision_types=vertical_meta.decision_types
    )
    models_test_file = output_dir / "test_models.py"
    with open(models_test_file, 'w') as f:
        f.write(black.format_str(models_test, mode=black.Mode()))
    generated_files.append(models_test_file)
    
    # Generate test_snapshot.py
    snapshot_test = template_snapshot.render(
        vertical_name=vertical_meta.name,
        scoring_weights=vertical_meta.scoring_weights
    )
    snapshot_test_file = output_dir / "test_snapshot.py"
    with open(snapshot_test_file, 'w') as f:
        f.write(black.format_str(snapshot_test, mode=black.Mode()))
    generated_files.append(snapshot_test_file)
    
    return generated_files
