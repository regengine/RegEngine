-- Migration: V5__create_compliance_status.sql
-- Purpose: Create compliance state machine for the "2am Alert" feature
-- This enables binary compliance status + countdown timers + external alerts

-- Compliance status enum
CREATE TYPE compliance_status_type AS ENUM ('COMPLIANT', 'AT_RISK', 'NON_COMPLIANT');

-- Compliance alert severity
CREATE TYPE alert_severity_type AS ENUM ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW');

-- Compliance alert source type
CREATE TYPE alert_source_type AS ENUM (
    'FDA_RECALL',
    'FDA_WARNING_LETTER',
    'FDA_IMPORT_ALERT',
    'RETAILER_REQUEST',
    'INTERNAL_AUDIT',
    'MANUAL'
);

-- Main compliance status table (one row per tenant)
CREATE TABLE IF NOT EXISTS tenant_compliance_status (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL UNIQUE,
    status compliance_status_type NOT NULL DEFAULT 'COMPLIANT',
    last_status_change TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active_alert_count INTEGER NOT NULL DEFAULT 0,
    critical_alert_count INTEGER NOT NULL DEFAULT 0,
    -- Compliance score (0.0 - 1.0) based on completeness of data
    completeness_score FLOAT DEFAULT 1.0,
    -- Next required action deadline (NULL if compliant)
    next_deadline TIMESTAMP WITH TIME ZONE,
    next_deadline_description TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Compliance alerts table (triggered by external events)
CREATE TABLE IF NOT EXISTS compliance_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    
    -- Alert identification
    source_type alert_source_type NOT NULL,
    source_id VARCHAR(255) NOT NULL,  -- External reference (recall number, etc.)
    
    -- Alert details
    title TEXT NOT NULL,
    summary TEXT,
    severity alert_severity_type NOT NULL DEFAULT 'MEDIUM',
    
    -- Countdown timer (the "2am" part)
    countdown_start TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    countdown_end TIMESTAMP WITH TIME ZONE NOT NULL,  -- When action is required by
    countdown_hours INTEGER NOT NULL DEFAULT 24,  -- For display purposes
    
    -- Required actions
    required_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Example: [{"action": "Upload lot data", "completed": false}, {"action": "Run trace", "completed": false}]
    
    -- Status tracking
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE, ACKNOWLEDGED, RESOLVED, EXPIRED
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    acknowledged_by VARCHAR(255),
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by VARCHAR(255),
    resolution_notes TEXT,
    
    -- Matching criteria (why this alert applies to this tenant)
    match_reason JSONB,
    -- Example: {"matched_products": ["romaine"], "matched_regions": ["CA", "AZ"]}
    
    -- Raw data from source
    raw_data JSONB,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Prevent duplicate alerts for same source event
    UNIQUE(tenant_id, source_type, source_id)
);

-- Compliance status transition log (audit trail)
CREATE TABLE IF NOT EXISTS compliance_status_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    
    -- Status transition
    previous_status compliance_status_type,
    new_status compliance_status_type NOT NULL,
    
    -- Trigger information
    trigger_type VARCHAR(100) NOT NULL,  -- 'alert_created', 'alert_resolved', 'manual', 'system'
    trigger_alert_id UUID,  -- Reference to the alert that caused this transition
    trigger_description TEXT,
    
    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Notification log (track what was sent)
CREATE TABLE IF NOT EXISTS compliance_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    alert_id UUID REFERENCES compliance_alerts(id),
    
    -- Notification details
    notification_type VARCHAR(50) NOT NULL,  -- 'email', 'webhook', 'sms'
    recipient VARCHAR(255) NOT NULL,
    subject TEXT,
    
    -- Status
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',  -- PENDING, SENT, FAILED
    sent_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Tenant product profile (for matching alerts)
CREATE TABLE IF NOT EXISTS tenant_product_profile (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    
    -- Product categories (for FDA matching)
    product_categories JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Example: ["leafy_greens", "romaine_lettuce", "sprouts"]
    
    -- Geographic regions
    supply_regions JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Example: ["CA", "AZ", "FL"]
    
    -- Suppliers (GTINs, company names)
    supplier_identifiers JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Example: ["1234567890123", "Fresh Farms Inc"]
    
    -- FDA categories
    fda_product_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Example: ["54C21", "54E20"] -- FDA product codes
    
    -- Retailer relationships
    retailer_relationships JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Example: ["walmart", "costco", "kroger"]
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(tenant_id)
);

-- Indexes for performance
CREATE INDEX idx_compliance_alerts_tenant_status ON compliance_alerts(tenant_id, status);
CREATE INDEX idx_compliance_alerts_countdown ON compliance_alerts(countdown_end) WHERE status = 'ACTIVE';
CREATE INDEX idx_compliance_alerts_severity ON compliance_alerts(severity, status);
CREATE INDEX idx_compliance_status_log_tenant ON compliance_status_log(tenant_id, created_at);
CREATE INDEX idx_compliance_notifications_alert ON compliance_notifications(alert_id);

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_tenant_compliance_status_updated_at
    BEFORE UPDATE ON tenant_compliance_status
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_compliance_alerts_updated_at
    BEFORE UPDATE ON compliance_alerts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_tenant_product_profile_updated_at
    BEFORE UPDATE ON tenant_product_profile
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to calculate current compliance status based on active alerts
CREATE OR REPLACE FUNCTION calculate_compliance_status(p_tenant_id UUID)
RETURNS compliance_status_type AS $$
DECLARE
    v_critical_count INTEGER;
    v_high_count INTEGER;
    v_total_active INTEGER;
BEGIN
    SELECT 
        COUNT(*) FILTER (WHERE severity = 'CRITICAL' AND status = 'ACTIVE'),
        COUNT(*) FILTER (WHERE severity = 'HIGH' AND status = 'ACTIVE'),
        COUNT(*) FILTER (WHERE status = 'ACTIVE')
    INTO v_critical_count, v_high_count, v_total_active
    FROM compliance_alerts
    WHERE tenant_id = p_tenant_id;
    
    IF v_critical_count > 0 THEN
        RETURN 'NON_COMPLIANT';
    ELSIF v_high_count > 0 OR v_total_active > 0 THEN
        RETURN 'AT_RISK';
    ELSE
        RETURN 'COMPLIANT';
    END IF;
END;
$$ LANGUAGE plpgsql;
