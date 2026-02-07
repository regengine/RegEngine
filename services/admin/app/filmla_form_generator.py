"""
FilmLA Permit Form Generator

Generates pre-filled FilmLA permit applications from PCOS project data.
Uses field mappings to extract data and produce JSON output for PDF generation.
"""

import structlog
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, List, Any
import json
import re

logger = structlog.get_logger(__name__)


@dataclass 
class FieldValue:
    """A filled form field with source tracking."""
    field_name: str
    field_type: str
    value: Any
    data_path: str
    is_required: bool
    is_filled: bool
    source_value: Any = None  # Original value before transform


@dataclass
class FormFillResult:
    """Result of filling a form template."""
    template_code: str
    template_name: str
    template_version: str
    fields: List[FieldValue]
    filled_count: int
    required_count: int
    missing_required: List[str]
    is_complete: bool
    warnings: List[str]
    source_data_snapshot: Dict[str, Any]


class FilmLAFormGenerator:
    """
    Generates FilmLA permit application data from PCOS project/location data.
    
    This generator does not produce the actual PDF (that requires pdf-lib on client
    or a PDF service), but produces the JSON data needed to fill the form fields.
    """
    
    TEMPLATE_CODE = "FILMLA_PERMIT"
    
    # Default field mappings (matches V15 migration seed data)
    DEFAULT_FIELD_MAPPINGS = [
        {"field_name": "production_company", "field_type": "text", "pdf_field_id": "company_name", "data_path": "company.name", "required": True},
        {"field_name": "production_title", "field_type": "text", "pdf_field_id": "project_title", "data_path": "project.name", "required": True},
        {"field_name": "project_type", "field_type": "select", "pdf_field_id": "production_type", "data_path": "project.project_type", "required": True},
        {"field_name": "contact_name", "field_type": "text", "pdf_field_id": "contact_person", "data_path": "company.primary_contact_name", "required": True},
        {"field_name": "contact_phone", "field_type": "text", "pdf_field_id": "contact_phone", "data_path": "company.primary_contact_phone", "required": True},
        {"field_name": "contact_email", "field_type": "text", "pdf_field_id": "contact_email", "data_path": "company.primary_contact_email", "required": True},
        {"field_name": "company_address", "field_type": "text", "pdf_field_id": "company_address", "data_path": "company.address_line1", "required": True},
        {"field_name": "company_city", "field_type": "text", "pdf_field_id": "company_city", "data_path": "company.city", "required": True},
        {"field_name": "company_state", "field_type": "text", "pdf_field_id": "company_state", "data_path": "company.state", "required": True},
        {"field_name": "company_zip", "field_type": "text", "pdf_field_id": "company_zip", "data_path": "company.zip", "required": True},
        {"field_name": "location_address", "field_type": "text", "pdf_field_id": "filming_address", "data_path": "location.address_line1", "required": True},
        {"field_name": "location_city", "field_type": "text", "pdf_field_id": "filming_city", "data_path": "location.city", "required": True},
        {"field_name": "filming_date_start", "field_type": "date", "pdf_field_id": "start_date", "data_path": "location.shoot_dates[0]", "required": True},
        {"field_name": "filming_date_end", "field_type": "date", "pdf_field_id": "end_date", "data_path": "location.shoot_dates[-1]", "required": False},
        {"field_name": "crew_size", "field_type": "number", "pdf_field_id": "crew_count", "data_path": "location.estimated_crew_size", "required": True},
        {"field_name": "vehicles_count", "field_type": "number", "pdf_field_id": "vehicles", "data_path": "location.parking_spaces_needed", "required": True},
        {"field_name": "has_generator", "field_type": "checkbox", "pdf_field_id": "generator_yn", "data_path": "location.has_generator", "required": False},
        {"field_name": "has_special_effects", "field_type": "checkbox", "pdf_field_id": "sfx_yn", "data_path": "location.has_special_effects", "required": False},
        {"field_name": "insurance_carrier", "field_type": "text", "pdf_field_id": "insurance_company", "data_path": "insurance.carrier_name", "required": True},
        {"field_name": "insurance_policy_number", "field_type": "text", "pdf_field_id": "policy_number", "data_path": "insurance.policy_number", "required": True},
        {"field_name": "coi_expiration", "field_type": "date", "pdf_field_id": "coi_exp", "data_path": "insurance.expiration_date", "required": True},
    ]
    
    def __init__(self, field_mappings: Optional[List[Dict]] = None):
        """
        Initialize the form generator.
        
        Args:
            field_mappings: Custom field mappings. If not provided, uses defaults.
        """
        self.field_mappings = field_mappings or self.DEFAULT_FIELD_MAPPINGS
        logger.info(
            "filmla_form_generator_initialized",
            field_count=len(self.field_mappings)
        )
    
    def generate(
        self,
        project: Dict,
        company: Dict,
        location: Dict,
        insurance: Optional[Dict] = None
    ) -> FormFillResult:
        """
        Generate form data from project/company/location data.
        
        Args:
            project: Project data dict
            company: Company data dict  
            location: Location data dict
            insurance: Optional insurance policy data dict
            
        Returns:
            FormFillResult with all field values and completeness info
        """
        # Build source data structure
        source_data = {
            "project": project,
            "company": company,
            "location": location,
            "insurance": insurance or {}
        }
        
        # Fill each field
        fields: List[FieldValue] = []
        missing_required: List[str] = []
        warnings: List[str] = []
        
        for mapping in self.field_mappings:
            field_name = mapping["field_name"]
            field_type = mapping["field_type"]
            data_path = mapping["data_path"]
            is_required = mapping.get("required", False)
            
            # Extract value from source data
            raw_value = self._extract_value(source_data, data_path)
            
            # Transform value based on field type
            transformed_value = self._transform_value(raw_value, field_type)
            
            is_filled = transformed_value is not None and transformed_value != ""
            
            field = FieldValue(
                field_name=field_name,
                field_type=field_type,
                value=transformed_value,
                data_path=data_path,
                is_required=is_required,
                is_filled=is_filled,
                source_value=raw_value
            )
            fields.append(field)
            
            if is_required and not is_filled:
                missing_required.append(field_name)
        
        # Generate warnings
        if not insurance:
            warnings.append("No insurance data provided. COI fields will be empty.")
        
        if location.get("shoot_dates") and len(location.get("shoot_dates", [])) == 0:
            warnings.append("No shoot dates specified for location.")
        
        # Check if location is in LA
        location_city = (location.get("city") or "").lower()
        if location_city and "los angeles" not in location_city and location_city != "la":
            warnings.append(f"Location city '{location.get('city')}' may not require FilmLA permit.")
        
        filled_count = sum(1 for f in fields if f.is_filled)
        required_count = sum(1 for f in fields if f.is_required)
        
        return FormFillResult(
            template_code=self.TEMPLATE_CODE,
            template_name="FilmL.A. Film Permit Application",
            template_version="2024.1",
            fields=fields,
            filled_count=filled_count,
            required_count=required_count,
            missing_required=missing_required,
            is_complete=len(missing_required) == 0,
            warnings=warnings,
            source_data_snapshot=source_data
        )
    
    def _extract_value(self, data: Dict, path: str) -> Any:
        """
        Extract a value from nested dict using dot notation path.
        
        Supports:
        - Dot notation: "company.name"
        - Array indexing: "location.shoot_dates[0]"
        - Negative indexing: "location.shoot_dates[-1]"
        """
        try:
            parts = self._parse_path(path)
            current = data
            
            for part in parts:
                if isinstance(part, str):
                    if isinstance(current, dict):
                        current = current.get(part)
                    else:
                        return None
                elif isinstance(part, int):
                    if isinstance(current, (list, tuple)) and len(current) > abs(part):
                        current = current[part]
                    else:
                        return None
                
                if current is None:
                    return None
            
            return current
        except Exception as e:
            logger.warning("value_extraction_failed", path=path, error=str(e))
            return None
    
    def _parse_path(self, path: str) -> List:
        """Parse a data path into parts (strings and indices)."""
        parts = []
        # Split on dots, but handle array brackets
        tokens = re.split(r'\.(?![^\[]*\])', path)
        
        for token in tokens:
            # Check for array index
            match = re.match(r'^(\w+)\[(-?\d+)\]$', token)
            if match:
                parts.append(match.group(1))
                parts.append(int(match.group(2)))
            else:
                parts.append(token)
        
        return parts
    
    def _transform_value(self, value: Any, field_type: str) -> Any:
        """Transform a raw value to the appropriate field type."""
        if value is None:
            return None
        
        if field_type == "text":
            return str(value) if value else ""
        
        elif field_type == "number":
            if isinstance(value, (int, float, Decimal)):
                return int(value)
            try:
                return int(float(str(value)))
            except (ValueError, TypeError):
                return None
        
        elif field_type == "date":
            if isinstance(value, date):
                return value.isoformat()
            if isinstance(value, datetime):
                return value.date().isoformat()
            if isinstance(value, str):
                # Try to parse common date formats
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                    try:
                        return datetime.strptime(value, fmt).date().isoformat()
                    except ValueError:
                        continue
            return str(value) if value else None
        
        elif field_type == "checkbox":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "yes", "1", "y")
            return bool(value)
        
        elif field_type == "select":
            return str(value) if value else ""
        
        return str(value) if value else None


def generate_filmla_form(
    project: Dict,
    company: Dict,
    location: Dict,
    insurance: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Convenience function to generate FilmLA form data.
    
    Returns a dictionary suitable for JSON serialization and API response.
    """
    generator = FilmLAFormGenerator()
    result = generator.generate(project, company, location, insurance)
    
    return {
        "template_code": result.template_code,
        "template_name": result.template_name,
        "template_version": result.template_version,
        "is_complete": result.is_complete,
        "filled_count": result.filled_count,
        "required_count": result.required_count,
        "completion_pct": round(result.filled_count / len(result.fields) * 100, 1) if result.fields else 0,
        "missing_required": result.missing_required,
        "warnings": result.warnings,
        "fields": [
            {
                "field_name": f.field_name,
                "field_type": f.field_type,
                "value": f.value,
                "is_filled": f.is_filled,
                "is_required": f.is_required,
            }
            for f in result.fields
        ],
        "pdf_fields": {
            f.field_name: f.value
            for f in result.fields
            if f.is_filled
        },
        "source_data_snapshot": result.source_data_snapshot
    }
