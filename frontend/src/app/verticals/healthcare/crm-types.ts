
export interface DepartmentRisk {
    dept: string
    risk: number
    detail: string
}

export interface AccessLog {
    time: string
    user: string
    action: string
    status: "NORMAL" | "FLAGGED" | "CRITICAL"
}

export interface EnterpriseRiskStatus {
    overall_risk_score: number
    monitored_users: number
    active_alerts: number
    critical_breaches: number
}
