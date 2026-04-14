"""
Tests for FSMA 204 Traceability Plan Builder.
"""

import pytest
from shared.fsma_plan_builder import (
    FIRM_TYPE_PROCEDURES,
    FirmInfo,
    FirmType,
    FTLCommodity,
    RecordLocation,
    RecordRetentionPeriod,
    TraceabilityPlanBuilder,
    export_plan_json,
    export_plan_markdown,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_firm():
    """Create a sample firm for testing."""
    return FirmInfo(
        name="Fresh Foods Processing Co",
        address="123 Industrial Blvd, Salinas, CA 93901",
        firm_type=FirmType.PROCESSOR,
        gln="1234567890123",
        fda_registration="12345678901",
        contact_name="John Smith",
        contact_email="john.smith@freshfoods.com",
        contact_phone="831-555-1234",
    )


@pytest.fixture
def sample_commodities():
    """Create sample commodities."""
    return [
        FTLCommodity(
            name="Romaine Lettuce",
            category="Leafy Greens",
            cte_types=["RECEIVING", "TRANSFORMATION", "SHIPPING"],
            tlc_assignment_method="Date-based sequential",
        ),
        FTLCommodity(
            name="Spinach",
            category="Leafy Greens",
            cte_types=["RECEIVING", "TRANSFORMATION", "SHIPPING"],
            tlc_assignment_method="Date-based sequential",
        ),
    ]


@pytest.fixture
def sample_record_location():
    """Create a sample record location."""
    return RecordLocation(
        location_type="electronic",
        system_name="RegEngine",
        backup_procedure="Daily cloud backup",
        retention_period=RecordRetentionPeriod.TWO_YEARS,
    )


# =============================================================================
# FIRM INFO TESTS
# =============================================================================

class TestFirmInfo:
    """Tests for FirmInfo dataclass."""

    def test_firm_to_dict(self, sample_firm):
        """Test firm serialization to dict."""
        result = sample_firm.to_dict()
        
        assert result["name"] == "Fresh Foods Processing Co"
        assert result["firm_type"] == "processor"
        assert result["gln"] == "1234567890123"
        assert result["contact_email"] == "john.smith@freshfoods.com"

    def test_firm_optional_fields(self):
        """Test firm with minimal required fields."""
        firm = FirmInfo(
            name="Simple Farm",
            address="456 Farm Road",
            firm_type=FirmType.GROWER,
        )
        
        assert firm.gln is None
        assert firm.contact_name == ""


class TestFirmType:
    """Tests for FirmType enum."""

    def test_all_firm_types(self):
        """Test all firm types are defined."""
        expected_types = [
            "grower", "manufacturer", "processor", "packer",
            "holder", "distributor", "retailer", "restaurant"
        ]
        
        for ft in expected_types:
            assert FirmType(ft)


# =============================================================================
# COMMODITY TESTS
# =============================================================================

class TestFTLCommodity:
    """Tests for FTLCommodity dataclass."""

    def test_commodity_to_dict(self, sample_commodities):
        """Test commodity serialization."""
        result = sample_commodities[0].to_dict()
        
        assert result["name"] == "Romaine Lettuce"
        assert result["category"] == "Leafy Greens"
        assert "RECEIVING" in result["cte_types"]

    def test_commodity_default_values(self):
        """Test commodity with minimal fields."""
        commodity = FTLCommodity(
            name="Test Product",
            category="Test Category",
        )
        
        assert commodity.cte_types == []
        assert commodity.tlc_assignment_method == ""


# =============================================================================
# PLAN BUILDER TESTS
# =============================================================================

class TestTraceabilityPlanBuilder:
    """Tests for TraceabilityPlanBuilder."""

    def test_build_minimal_plan(self, sample_firm):
        """Test building a plan with minimal configuration."""
        builder = TraceabilityPlanBuilder(sample_firm)
        plan = builder.build()
        
        assert plan.plan_id is not None
        assert plan.firm.name == "Fresh Foods Processing Co"
        assert plan.version == "1.0"
        assert plan.created_date is not None

    def test_build_full_plan(self, sample_firm, sample_commodities, sample_record_location):
        """Test building a complete plan."""
        builder = TraceabilityPlanBuilder(sample_firm)
        
        for commodity in sample_commodities:
            builder.add_commodity(commodity)
        
        builder.add_record_location(sample_record_location)
        builder.set_tlc_format("FFC-{YYYYMMDD}-{SEQ}")
        
        plan = builder.build()
        
        assert len(plan.commodities) == 2
        assert len(plan.record_locations) == 1
        assert plan.tlc_format == "FFC-{YYYYMMDD}-{SEQ}"

    def test_generated_procedures_contain_firm_name(self, sample_firm):
        """Test that generated procedures reference the firm."""
        builder = TraceabilityPlanBuilder(sample_firm)
        plan = builder.build()
        
        assert "Fresh Foods Processing Co" in plan.receiving_procedure
        assert "Fresh Foods Processing Co" in plan.shipping_procedure
        assert "Fresh Foods Processing Co" in plan.recall_procedure

    def test_generated_procedures_contain_address(self, sample_firm):
        """Test that generated procedures reference the address."""
        builder = TraceabilityPlanBuilder(sample_firm)
        plan = builder.build()
        
        assert "Salinas" in plan.receiving_procedure

    def test_recall_procedure_has_contact_info(self, sample_firm):
        """Test that recall procedure includes contact information."""
        builder = TraceabilityPlanBuilder(sample_firm)
        plan = builder.build()
        
        assert "John Smith" in plan.recall_procedure
        assert "john.smith@freshfoods.com" in plan.recall_procedure

    def test_builder_chaining(self, sample_firm):
        """Test that builder methods return self for chaining."""
        builder = TraceabilityPlanBuilder(sample_firm)
        
        result = (
            builder
            .add_commodity(FTLCommodity(name="Test", category="Test"))
            .set_tlc_format("TEST-{SEQ}")
        )
        
        assert result is builder

    def test_record_system_updates_procedures(self, sample_firm):
        """Test that record system name appears in procedures."""
        builder = TraceabilityPlanBuilder(sample_firm)
        builder.add_record_location(RecordLocation(
            location_type="electronic",
            system_name="CustomERP System",
        ))
        
        plan = builder.build()
        
        assert "CustomERP System" in plan.receiving_procedure


# =============================================================================
# PLAN EXPORT TESTS
# =============================================================================

class TestPlanExport:
    """Tests for plan export functions."""

    def test_export_json(self, sample_firm):
        """Test JSON export contains required fields."""
        builder = TraceabilityPlanBuilder(sample_firm)
        plan = builder.build()
        
        result = export_plan_json(plan)
        
        assert "plan_id" in result
        assert "firm" in result
        assert "version" in result
        assert "procedures" in result
        assert result["firm"]["name"] == "Fresh Foods Processing Co"

    def test_export_markdown(self, sample_firm):
        """Test Markdown export is formatted correctly."""
        builder = TraceabilityPlanBuilder(sample_firm)
        builder.add_commodity(FTLCommodity(
            name="Lettuce",
            category="Leafy Greens",
        ))
        plan = builder.build()
        
        md = export_plan_markdown(plan)
        
        # Check structure
        assert "# FSMA 204 Traceability Plan" in md
        assert "**Company:** Fresh Foods Processing Co" in md
        assert "## Food Traceability List (FTL) Commodities" in md
        assert "Lettuce" in md
        assert "## Certification" in md

    def test_export_markdown_has_all_sections(self, sample_firm):
        """Test Markdown export includes all required sections for a processor."""
        builder = TraceabilityPlanBuilder(sample_firm)
        plan = builder.build()

        md = export_plan_markdown(plan)

        # Universal sections (always present)
        for section in [
            "Traceability Contact",
            "Record Storage",
            "TLC Format",
            "24-Hour Recall Response",
            "Training Procedure",
        ]:
            assert section in md, f"Missing universal section: {section}"

        # Processor-specific CTE sections
        for section in [
            "Receiving Procedure",
            "Shipping Procedure",
            "Transformation Procedure",
            "Cooling Procedure",
            "Initial Packing Procedure",
        ]:
            assert section in md, f"Missing processor section: {section}"

        # Processor should NOT have these
        assert "Harvesting Procedure" not in md
        assert "Holding & Storage Procedure" not in md


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestPlanBuilderIntegration:
    """Integration tests for complete plan generation flow."""

    def test_complete_processor_plan(self):
        """Test generating a complete plan for a food processor."""
        firm = FirmInfo(
            name="Valley Fresh Produce",
            address="789 Processing Way, Fresno, CA 93721",
            firm_type=FirmType.PROCESSOR,
            gln="9876543210123",
            fda_registration="98765432101",
            contact_name="Maria Garcia",
            contact_email="mgarcia@valleyfresh.com",
            contact_phone="559-555-9876",
        )
        
        builder = TraceabilityPlanBuilder(firm)
        
        # Add FTL commodities
        builder.add_commodity(FTLCommodity(
            name="Bagged Salad Mix",
            category="Leafy Greens",
            cte_types=["RECEIVING", "TRANSFORMATION", "PACKING", "SHIPPING"],
            tlc_assignment_method="Date + Production Line",
        ))
        
        builder.add_commodity(FTLCommodity(
            name="Fresh-cut Melons",
            category="Fresh-cut Fruits",
            cte_types=["RECEIVING", "TRANSFORMATION", "PACKING", "SHIPPING"],
        ))
        
        # Add record system
        builder.add_record_location(RecordLocation(
            location_type="electronic",
            system_name="RegEngine Traceability",
            backup_procedure="Continuous cloud sync with daily backup",
            retention_period=RecordRetentionPeriod.TWO_YEARS,
        ))
        
        builder.set_tlc_format("VFP-{YYYYMMDD}-{LINE}-{SEQ}")
        
        plan = builder.build()
        
        # Verify plan completeness
        assert plan.firm.name == "Valley Fresh Produce"
        assert len(plan.commodities) == 2
        assert "VFP-{YYYYMMDD}-{LINE}-{SEQ}" in plan.tlc_assignment_procedure
        assert "Maria Garcia" in plan.recall_procedure
        
        # Verify JSON export
        json_export = export_plan_json(plan)
        assert json_export["firm"]["gln"] == "9876543210123"
        
        # Verify Markdown export
        md_export = export_plan_markdown(plan)
        assert "Valley Fresh Produce" in md_export
        assert "Bagged Salad Mix" in md_export

    def test_minimal_grower_plan(self):
        """Test generating a minimal plan for a grower."""
        firm = FirmInfo(
            name="Small Family Farm",
            address="1 Country Road, Rural, CA 95000",
            firm_type=FirmType.GROWER,
        )

        builder = TraceabilityPlanBuilder(firm)
        plan = builder.build()

        # Grower gets harvesting, cooling, initial packing, shipping
        assert "Small Family Farm" in plan.harvesting_procedure
        assert "Small Family Farm" in plan.shipping_procedure
        assert plan.cooling_procedure  # growers cool produce
        assert plan.initial_packing_procedure  # growers pack

        # Grower should NOT get receiving or transformation
        assert plan.receiving_procedure == ""
        assert plan.transformation_procedure == ""
        assert plan.holding_procedure == ""

        # Universal procedures always present
        assert plan.recall_contact is not None
        assert plan.tlc_assignment_procedure

    def test_distributor_plan_no_transformation(self):
        """Test that distributors get holding but not transformation."""
        firm = FirmInfo(
            name="Metro Cold Storage",
            address="500 Logistics Ave, Newark, NJ 07105",
            firm_type=FirmType.DISTRIBUTOR,
            contact_name="Pat Chen",
            contact_email="pchen@metrocold.com",
            contact_phone="973-555-4000",
        )

        builder = TraceabilityPlanBuilder(firm)
        plan = builder.build()

        # Distributor gets receiving, holding, shipping
        assert "Metro Cold Storage" in plan.receiving_procedure
        assert "Metro Cold Storage" in plan.holding_procedure
        assert "Metro Cold Storage" in plan.shipping_procedure

        # Distributor should NOT get transformation or harvesting
        assert plan.transformation_procedure == ""
        assert plan.harvesting_procedure == ""
        assert plan.cooling_procedure == ""
        assert plan.initial_packing_procedure == ""

    def test_retailer_plan_receiving_only(self):
        """Test that retailers only get receiving procedure."""
        firm = FirmInfo(
            name="Corner Market",
            address="100 Main St, Anytown, USA",
            firm_type=FirmType.RETAILER,
        )

        builder = TraceabilityPlanBuilder(firm)
        plan = builder.build()

        assert "Corner Market" in plan.receiving_procedure
        assert plan.shipping_procedure == ""
        assert plan.transformation_procedure == ""
        assert plan.holding_procedure == ""

    def test_firm_type_procedures_covers_all_types(self):
        """Every FirmType has an entry in FIRM_TYPE_PROCEDURES."""
        for ft in FirmType:
            assert ft in FIRM_TYPE_PROCEDURES, f"Missing mapping for {ft}"

    def test_to_dict_omits_empty_procedures(self):
        """to_dict should not include CTE procedures that are empty."""
        firm = FirmInfo(
            name="Test Retailer",
            address="123 Test",
            firm_type=FirmType.RETAILER,
        )
        builder = TraceabilityPlanBuilder(firm)
        plan = builder.build()
        result = export_plan_json(plan)

        procedures = result["procedures"]
        assert "receiving" in procedures
        assert "transformation" not in procedures
        assert "shipping" not in procedures
        assert "holding" not in procedures
        # Universal procedures always present
        assert "tlc_assignment" in procedures
        assert "recall" in procedures
