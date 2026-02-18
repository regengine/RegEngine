-- Gaming Compliance Service - Initial Schema
-- Version: V001
-- Description: Create transaction_logs, self_exclusion_records, and responsible_gaming_alerts tables

-- Transaction logs table (immutable)
CREATE TABLE transaction_logs (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(255) NOT NULL,
    transaction_type VARCHAR(50) NOT NULL CHECK (transaction_type IN ('WAGER', 'PAYOUT', 'JACKPOT', 'DEPOSIT', 'WITHDRAWAL')),
    amount_cents BIGINT NOT NULL CHECK (amount_cents >= 0),
    game_id VARCHAR(255) NOT NULL,
    jurisdiction VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    content_hash VARCHAR(64) NOT NULL UNIQUE,
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for transaction_logs
CREATE INDEX idx_transaction_player_id ON transaction_logs(player_id);
CREATE INDEX idx_transaction_game_id ON transaction_logs(game_id);
CREATE INDEX idx_transaction_timestamp ON transaction_logs(timestamp);
CREATE INDEX idx_transaction_player_timestamp ON transaction_logs(player_id, timestamp);
CREATE INDEX idx_transaction_jurisdiction_timestamp ON transaction_logs(jurisdiction, timestamp);

-- Self-exclusion records table
CREATE TABLE self_exclusion_records (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(255) NOT NULL UNIQUE,
    duration_days INTEGER NOT NULL CHECK (duration_days >= 0),
    reason VARCHAR(500),
    effective_date TIMESTAMP NOT NULL,
    expiration_date TIMESTAMP,
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'EXPIRED', 'REVOKED')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for self_exclusion_records
CREATE INDEX idx_exclusion_player_id ON self_exclusion_records(player_id);
CREATE INDEX idx_exclusion_effective_date ON self_exclusion_records(effective_date);

-- Responsible gaming alerts table
CREATE TABLE responsible_gaming_alerts (
    id SERIAL PRIMARY KEY,
    player_id VARCHAR(255) NOT NULL,
    alert_type VARCHAR(100) NOT NULL,
    risk_score INTEGER NOT NULL CHECK (risk_score >= 0 AND risk_score <= 100),
    detection_data JSONB NOT NULL,
    triggered_at TIMESTAMP NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMP,
    reviewed_by VARCHAR(255),
    intervention_action VARCHAR(500),
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'REVIEWED', 'ESCALATED'))
);

-- Indexes for responsible_gaming_alerts
CREATE INDEX idx_alert_player_id ON responsible_gaming_alerts(player_id);
CREATE INDEX idx_alert_triggered_at ON responsible_gaming_alerts(triggered_at);
CREATE INDEX idx_alert_player_status ON responsible_gaming_alerts(player_id, status);

-- Comments for documentation
COMMENT ON TABLE transaction_logs IS 'Immutable transaction logs for Gaming Commission compliance';
COMMENT ON TABLE self_exclusion_records IS 'Player self-exclusion records for responsible gaming';
COMMENT ON TABLE responsible_gaming_alerts IS 'Automated problem gambling detection alerts';

COMMENT ON COLUMN transaction_logs.content_hash IS 'SHA-256 hash for cryptographic immutability verification';
COMMENT ON COLUMN transaction_logs.amount_cents IS 'Amount stored in cents to avoid floating point precision issues';
