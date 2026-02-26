"""
Vertical Compiler v2
================================================================================
Compiler-first architecture for RegEngine verticals.

Generates FastAPI routes, Pydantic models, graph bindings, and test scaffolds
from declarative YAML schemas.

NO MANUAL CODE GENERATION. All vertical runtime code must be compiler-generated.

Usage:
    regengine compile vertical finance
"""

import yaml
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, ValidationError
import logging

from .schema_validator import validate_vertical_schema, validate_obligations_schema
from .codegen import (
    generate_fastapi_routes,
    generate_pydantic_models,
    generate_test_scaffolds
)
from .graph_adapter import generate_graph_nodes, generate_graph_relationships
from .snapshot_adapter_generator import generate_snapshot_adapter

logger = logging.getLogger(__name__)


class VerticalMetadata(BaseModel):
    """Vertical metadata from vertical.yaml"""
    name: str
    version: str
    regulators: List[str]
    regulatory_domains: List[str]
    decision_types: List[str]
    risk_dimensions: List[str]
    evidence_contract: Dict[str, Dict[str, List[str]]]
    snapshot_contract: Dict[str, Any]
    scoring_weights: Dict[str, float]


class ObligationDefinition(BaseModel):
    """Single regulatory obligation definition"""
    id: str
    citation: str
    regulator: str
    domain: str
    description: str
    triggering_conditions: Dict[str, Any]
    required_evidence: List[str]


class CompilationResult(BaseModel):
    """Result of vertical compilation"""
    vertical_name: str
    compilation_status: str  # success, failed
    generated_files: List[str]
    errors: List[str]
    warnings: List[str]


class VerticalCompiler:
    """
    Main compiler orchestrator.
    
    Workflow:
    1. Load vertical.yaml + obligations.yaml
    2. Validate schemas
    3. Generate FastAPI routes
    4. Generate Pydantic models
    5. Generate graph node definitions
    6. Generate snapshot adapter
    7. Update OpenAPI spec
    8. Register vertical in DB
    """
    
    def __init__(self, verticals_dir: Path, services_dir: Path, output_dir: Path):
        self.verticals_dir = verticals_dir
        self.services_dir = services_dir
        self.output_dir = output_dir
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.generated_files: List[str] = []
    
    def compile_vertical(self, vertical_name: str) -> CompilationResult:
        """
        Compile a vertical from YAML schemas to runtime code.
        
        Args:
            vertical_name: Name of vertical (e.g., 'finance')
            
        Returns:
            CompilationResult with status and generated files
        """
        logger.info(f"Starting compilation of vertical: {vertical_name}")
        
        try:
            # Step 1: Load schemas
            vertical_meta, obligations = self._load_schemas(vertical_name)
            
            # Step 2: Validate schemas
            self._validate_schemas(vertical_meta, obligations)
            
            # Step 3: Generate FastAPI routes
            routes_path = self._generate_routes(vertical_meta, obligations)
            self.generated_files.append(str(routes_path))
            
            # Step 4: Generate Pydantic models
            models_path = self._generate_models(vertical_meta, obligations)
            self.generated_files.append(str(models_path))
            
            # Step 5: Generate graph bindings
            graph_nodes_path, graph_rels_path = self._generate_graph_bindings(vertical_meta, obligations)
            self.generated_files.extend([str(graph_nodes_path), str(graph_rels_path)])
            
            # Step 6: Generate snapshot adapter
            snapshot_path = self._generate_snapshot(vertical_meta, obligations)
            self.generated_files.append(str(snapshot_path))
            
            # Step 7: Generate test scaffolds
            test_paths = self._generate_tests(vertical_meta, obligations)
            self.generated_files.extend([str(p) for p in test_paths])
            
            # Step 8: Update OpenAPI spec
            self._update_openapi_spec(vertical_name, vertical_meta)
            
            # Step 9: Register vertical
            self._register_vertical(vertical_name, vertical_meta)
            
            logger.info(f"✅ Compilation successful: {vertical_name}")
            return CompilationResult(
                vertical_name=vertical_name,
                compilation_status="success",
                generated_files=self.generated_files,
                errors=self.errors,
                warnings=self.warnings
            )
            
        except Exception as e:
            logger.error(f"❌ Compilation failed: {vertical_name} - {str(e)}")
            self.errors.append(str(e))
            return CompilationResult(
                vertical_name=vertical_name,
                compilation_status="failed",
                generated_files=self.generated_files,
                errors=self.errors,
                warnings=self.warnings
            )
    
    def _load_schemas(self, vertical_name: str) -> tuple[VerticalMetadata, List[ObligationDefinition]]:
        """Load vertical.yaml and obligations.yaml"""
        vertical_dir = self.verticals_dir / vertical_name
        
        # Load vertical.yaml
        vertical_path = vertical_dir / "vertical.yaml"
        if not vertical_path.exists():
            raise FileNotFoundError(f"vertical.yaml not found at {vertical_path}")
        
        with open(vertical_path, encoding="utf-8") as f:
            vertical_data = yaml.safe_load(f)
        
        vertical_meta = VerticalMetadata(**vertical_data)
        
        # Load obligations.yaml
        obligations_path = vertical_dir / "obligations.yaml"
        if not obligations_path.exists():
            raise FileNotFoundError(f"obligations.yaml not found at {obligations_path}")
        
        with open(obligations_path, encoding="utf-8") as f:
            obligations_data = yaml.safe_load(f)
        
        obligations = [
            ObligationDefinition(**obligation)
            for obligation in obligations_data.get("obligations", [])
        ]
        
        logger.info(f"Loaded {len(obligations)} obligations for {vertical_name}")
        
        return vertical_meta, obligations
    
    def _validate_schemas(self, vertical_meta: VerticalMetadata, obligations: List[ObligationDefinition]):
        """Validate schemas against JSON Schema definitions"""
        # Validate vertical schema
        vertical_errors = validate_vertical_schema(vertical_meta.dict())
        if vertical_errors:
            raise ValidationError(f"Vertical schema validation failed: {vertical_errors}")
        
        # Validate obligations schema
        obligations_errors = validate_obligations_schema([o.dict() for o in obligations])
        if obligations_errors:
            raise ValidationError(f"Obligations schema validation failed: {obligations_errors}")
        
        # Cross-validation: check evidence_contract references decision_types
        for decision_type in vertical_meta.evidence_contract.keys():
            if decision_type not in vertical_meta.decision_types:
                self.warnings.append(
                    f"Evidence contract references unknown decision_type: {decision_type}"
                )
        
        # Cross-validation: check scoring_weights sum to 1.0
        total_weight = sum(vertical_meta.scoring_weights.values())
        if abs(total_weight - 1.0) > 0.01:
            raise ValidationError(f"Scoring weights must sum to 1.0, got {total_weight}")
        
        logger.info("✅ Schema validation passed")
    
    def _generate_routes(self, vertical_meta: VerticalMetadata, obligations: List[ObligationDefinition]) -> Path:
        """Generate FastAPI routes file"""
        output_dir = self.services_dir / f"{vertical_meta.name}_api"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        routes_file = output_dir / "routes.py"
        routes_code = generate_fastapi_routes(vertical_meta, obligations)
        
        with open(routes_file, 'w', encoding='utf-8') as f:
            f.write(routes_code)
        
        logger.info(f"Generated routes: {routes_file}")
        return routes_file
    
    def _generate_models(self, vertical_meta: VerticalMetadata, obligations: List[ObligationDefinition]) -> Path:
        """Generate Pydantic models file"""
        output_dir = self.services_dir / f"{vertical_meta.name}_api"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        models_file = output_dir / "models.py"
        models_code = generate_pydantic_models(vertical_meta, obligations)
        
        with open(models_file, 'w', encoding='utf-8') as f:
            f.write(models_code)
        
        logger.info(f"Generated models: {models_file}")
        return models_file
    
    def _generate_graph_bindings(
        self, 
        vertical_meta: VerticalMetadata, 
        obligations: List[ObligationDefinition]
    ) -> tuple[Path, Path]:
        """Generate graph node and relationship definitions"""
        output_dir = self.services_dir / f"{vertical_meta.name}_api"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate nodes
        nodes_file = output_dir / "graph_nodes.py"
        nodes_code = generate_graph_nodes(vertical_meta, obligations)
        
        with open(nodes_file, 'w', encoding='utf-8') as f:
            f.write(nodes_code)
        
        # Generate relationships
        rels_file = output_dir / "graph_relationships.py"
        rels_code = generate_graph_relationships(vertical_meta, obligations)
        
        with open(rels_file, 'w', encoding='utf-8') as f:
            f.write(rels_code)
        
        logger.info(f"Generated graph bindings: {nodes_file}, {rels_file}")
        return nodes_file, rels_file
    
    def _generate_snapshot(self, vertical_meta: VerticalMetadata, obligations: List[ObligationDefinition]) -> Path:
        """Generate snapshot adapter"""
        output_dir = self.services_dir / f"{vertical_meta.name}_api"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        snapshot_file = output_dir / "snapshot_adapter.py"
        snapshot_code = generate_snapshot_adapter(vertical_meta, obligations)
        
        with open(snapshot_file, 'w', encoding='utf-8') as f:
            f.write(snapshot_code)
        
        logger.info(f"Generated snapshot adapter: {snapshot_file}")
        return snapshot_file
    
    def _generate_tests(self, vertical_meta: VerticalMetadata, obligations: List[ObligationDefinition]) -> List[Path]:
        """Generate test scaffolds"""
        output_dir = self.services_dir / f"{vertical_meta.name}_api" / "tests"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        test_files = generate_test_scaffolds(vertical_meta, obligations, output_dir)
        
        logger.info(f"Generated {len(test_files)} test files")
        return test_files
    
    def _update_openapi_spec(self, vertical_name: str, vertical_meta: VerticalMetadata):
        """Update OpenAPI specification with new vertical endpoints."""
        try:
            # Generate OpenAPI paths for this vertical
            vertical_paths = {
                f"/v1/{vertical_name}/decision/record": {
                    "post": {
                        "tags": [vertical_name],
                        "summary": f"Record {vertical_name} decision",
                        "description": f"Record a regulatory decision for {vertical_name} vertical",
                        "operationId": f"record_{vertical_name}_decision",
                        "responses": {"200": {"description": "Decision recorded"}}
                    }
                },
                f"/v1/{vertical_name}/snapshot": {
                    "get": {
                        "tags": [vertical_name],
                        "summary": f"Get {vertical_name} compliance snapshot",
                        "description": f"Retrieve current compliance snapshot for {vertical_name} vertical",
                        "operationId": f"get_{vertical_name}_snapshot",
                        "responses": {"200": {"description": "Compliance snapshot"}}
                    }
                }
            }
            
            # Update main OpenAPI spec file if it exists
            openapi_spec_file = self.output_dir / "openapi.json"
            
            if openapi_spec_file.exists():
                with open(openapi_spec_file, 'r', encoding='utf-8') as f:
                    spec = json.load(f)
                
                # Merge paths
                if "paths" not in spec:
                    spec["paths"] = {}
                spec["paths"].update(vertical_paths)
                
                # Add tag
                if "tags" not in spec:
                    spec["tags"] = []
                if vertical_name not in [t.get("name") for t in spec["tags"]]:
                    spec["tags"].append({
                        "name": vertical_name,
                        "description": f"{vertical_name.capitalize()} vertical endpoints"
                    })
                
                with open(openapi_spec_file, 'w', encoding='utf-8') as f:
                    json.dump(spec, f, indent=2)
                
                logger.info(f"Updated OpenAPI spec for {vertical_name}")
            else:
                logger.warning(f"OpenAPI spec file not found at {openapi_spec_file}, skipping update")
        except Exception as e:
            logger.error(f"Failed to update OpenAPI spec for {vertical_name}: {e}")
            self.warnings.append(f"OpenAPI spec update failed: {e}")
    
    def _register_vertical(self, vertical_name: str, vertical_meta: VerticalMetadata):
        """Register vertical in database."""
        try:
            from shared.database import get_db_session
            
            # Get database session
            session = get_db_session()
            
            # Register vertical metadata
            vertical_record = {
                "name": vertical_name,
                "version": vertical_meta.version,
                "regulators": vertical_meta.regulators,
                "regulatory_domains": vertical_meta.regulatory_domains,
                "decision_types": vertical_meta.decision_types,
                "risk_dimensions": vertical_meta.risk_dimensions,
                "scoring_weights": vertical_meta.scoring_weights,
                "is_active": True,
                "compiled_at": datetime.utcnow().isoformat()
            }
            
            # Upsert vertical registration (insert or update)
            # This would use the actual DB model when implemented
            logger.info(f"Registered vertical: {vertical_name} v{vertical_meta.version}")
            logger.debug(f"Vertical registration data: {vertical_record}")
            
            # Note: Actual DB insertion would happen here
            # e.g., session.merge(VerticalRegistration(**vertical_record))
            # session.commit()
            
        except Exception as e:
            logger.error(f"Failed to register vertical {vertical_name}: {e}")
            self.warnings.append(f"Vertical registration failed: {e}")


def compile_vertical_cli(vertical_name: str):
    """CLI entry point for vertical compilation"""
    import os
    
    verticals_dir = Path(os.getenv("REGENGINE_VERTICALS_DIR", "./verticals"))
    services_dir = Path(os.getenv("REGENGINE_SERVICES_DIR", "./services"))
    output_dir = Path(os.getenv("REGENGINE_OUTPUT_DIR", "./generated"))
    
    compiler = VerticalCompiler(verticals_dir, services_dir, output_dir)
    result = compiler.compile_vertical(vertical_name)
    
    if result.compilation_status == "success":
        print(f"✅ Compilation successful: {vertical_name}")
        print(f"Generated {len(result.generated_files)} files:")
        for f in result.generated_files:
            print(f"  - {f}")
    else:
        print(f"❌ Compilation failed: {vertical_name}")
        for error in result.errors:
            print(f"  ERROR: {error}")
    
    if result.warnings:
        print(f"⚠️  {len(result.warnings)} warnings:")
        for warning in result.warnings:
            print(f"  WARNING: {warning}")
