// FSMA 204 Types for frontend

// Facility types as defined in FSMA 204
export type FacilityType = 'FARM' | 'PROCESSOR' | 'DISTRIBUTOR' | 'RETAILER' | 'RESTAURANT';

// Trace event types
export type TraceEventType = 'CREATION' | 'SHIPPING' | 'RECEIVING' | 'TRANSFORMATION';

// Recall status
export type RecallStatus = 'PENDING' | 'IN_PROGRESS' | 'MET' | 'AT_RISK' | 'BREACHED' | 'COMPLETED' | 'CANCELLED';

// Recall drill types
export type RecallDrillType = 'FORWARD' | 'BACKWARD' | 'MASS_BALANCE';

// Risk levels for compliance
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

// Drift alert severity
export type DriftSeverity = 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';

// Facility in the supply chain
export interface Facility {
  gln: string;
  name: string;
  type: FacilityType;
  address?: string;
  fda_registration?: string;
  contact_name?: string;
  contact_email?: string;
  contact_phone?: string;
}

// Lot/product being traced
export interface Lot {
  tlc: string;
  gtin?: string;
  product_description: string;
  quantity: number;
  unit: string;
  harvest_date?: string;
  expiry_date?: string;
  source_facility?: string;
}

// Trace event in the supply chain
export interface TraceEvent {
  id: string;
  type: TraceEventType;
  timestamp: string;
  facility_gln: string;
  facility_name: string;
  facility_type: FacilityType;
  lot_tlc: string;
  quantity?: number;
  unit?: string;
  reference_document?: string;
  kdes_complete: boolean;
  missing_kdes?: string[];
}

// Forward/Backward trace result
export interface TraceResult {
  lot_id: string;
  direction: 'forward' | 'backward';
  query_time_ms: number;
  total_facilities: number;
  total_events: number;
  total_quantity: number;
  facilities: Facility[];
  events: TraceEvent[];
  path: TracePath[];
  gaps?: TraceGap[];
}

// A single step in the trace path
export interface TracePath {
  from_facility: Facility;
  to_facility: Facility;
  event_type: TraceEventType;
  timestamp: string;
  lot_tlc: string;
  quantity: number;
}

// Gap/missing data in trace
export interface TraceGap {
  event_id: string;
  missing_kdes: string[];
  severity: DriftSeverity;
  facility: string;
}

// Mass balance check result
export interface MassBalanceResult {
  lot_tlc: string;
  is_balanced: boolean;
  input_quantity: number;
  output_quantity: number;
  variance: number;
  variance_percent: number;
  tolerance_percent: number;
  status: 'BALANCED' | 'WITHIN_TOLERANCE' | 'MASS_IMBALANCE';
  events: MassBalanceEvent[];
  time_violations?: TimeViolation[];
}

export interface MassBalanceEvent {
  event_id: string;
  type: TraceEventType;
  facility: string;
  timestamp: string;
  quantity: number;
  direction: 'IN' | 'OUT';
}

export interface TimeViolation {
  source_event: string;
  target_event: string;
  source_time: string;
  target_time: string;
  violation_type: 'TIME_REVERSAL' | 'IMPOSSIBLE_TRANSIT';
}

// Recall drill
export interface RecallDrill {
  id: string;
  type: RecallDrillType;
  status: RecallStatus;
  target_tlc: string;
  target_product?: string;
  initiated_at: string;
  completed_at?: string;
  deadline: string; // 24-hour SLA deadline
  elapsed_seconds: number;
  remaining_seconds: number;
  facilities_contacted: number;
  total_facilities: number;
  lots_traced: number;
  total_quantity_affected: number;
  created_by: string;
  notes?: string;
}

// Recall readiness report
export interface RecallReadiness {
  overall_score: number; // 0-100
  sla_compliance: number; // % of drills meeting 24hr SLA
  average_response_time_hours: number;
  last_drill_date?: string;
  total_drills: number;
  drills_met: number;
  drills_breached: number;
  recommendations: string[];
  control_scores: {
    traceability_plan: number;
    kde_capture: number;
    cte_coverage: number;
    recordkeeping: number;
    technology: number;
  };
}

// Drift alert
export interface DriftAlert {
  id: string;
  severity: DriftSeverity;
  type?: string;
  metric?: string; // Added from backend
  current_value?: number; // Added from backend
  threshold?: number; // Added from backend
  message: string;
  source: string;
  created_at?: string; // backend sends timestamp
  acknowledged_at?: string;
  resolved_at?: string;
  metadata?: Record<string, unknown>;
}

// Supplier health status
export interface SupplierHealth {
  gln: string;
  name: string;
  type: FacilityType;
  health_score: number; // 0-100
  kde_completeness: number;
  avg_response_time_hours: number;
  last_event_date: string;
  active_alerts: number;
  status: 'HEALTHY' | 'DEGRADED' | 'CRITICAL' | 'UNKNOWN';
}

// FSMA Dashboard summary
export interface FSMADashboard {
  system_health: 'HEALTHY' | 'DEGRADED' | 'DOWN';
  total_lots: number;
  total_events: number;
  total_facilities: number;
  kde_completeness_percent: number;
  active_recalls: number;
  pending_reviews: number;
  recent_alerts: DriftAlert[];
  recall_readiness: RecallReadiness;
  supplier_health: SupplierHealth[];
}

// Recall drill creation request
export interface CreateRecallDrillRequest {
  type: RecallDrillType;
  target_tlc: string;
  reason?: string;
  notify_contacts?: boolean;
}

// Schedule for recurring drills
export interface RecallSchedule {
  id: string;
  name: string;
  drill_type: RecallDrillType;
  frequency: 'DAILY' | 'WEEKLY' | 'MONTHLY' | 'QUARTERLY';
  next_run: string;
  last_run?: string;
  enabled: boolean;
  target_products?: string[];
}

// KDE Quality metrics
export interface KDEQualityMetrics {
  overall_completeness: number;
  by_event_type: Record<TraceEventType, number>;
  by_facility_type: Record<FacilityType, number>;
  trend: 'IMPROVING' | 'STABLE' | 'DEGRADING';
  missing_kde_counts: Record<string, number>;
}
