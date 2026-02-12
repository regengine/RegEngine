# Finance Vertical Dashboard Specification

## Phase 7: Frontend Dashboard

### Overview
Build comprehensive Finance vertical dashboard for compliance visualization and monitoring.

---

## Component Specifications

### 1. Dashboard Overview Page (`/finance`)

**Purpose**: At-a-glance compliance view

**Metrics Cards**:
- Total Decisions (last 30 days)
- Obligation Coverage % (gauge)
- Risk Level (low/medium/high/critical badge)
- Open Violations count

**Charts**:
- Decision volume timeline (line chart, 30 days)
- Risk distribution (pie chart: low/medium/high/critical)
- Top 5 violated obligations (horizontal bar)

**Real-time Updates**:
- Poll `/v1/finance/stats` every 30 seconds
- Poll `/v1/finance/snapshot` every 60 seconds

---

### 2. Bias Analytics Page (`/finance/bias`)

**Purpose**: Protected class bias monitoring

**Bias Heatmap**:
- **Rows**: Protected classes (race, sex, marital_status, age, etc.)
- **Columns**: Decision types (credit_approval, credit_denial, etc.)
- **Colors**: 
  - Green: DIR >= 0.80 (passes 80% rule)
  - Yellow: 0.50 <= DIR < 0.80 (moderate concern)
  - Red: DIR < 0.50 (severe bias)
- **Tooltip**: Shows exact DIR, statistical significance

**Filter Controls**:
- Date range picker
- Model selector
- Protected class selector

**Detail Table**:
- Protected class
- Reference group approval rate
- Protected group approval rate
- DIR
- Statistical significance (p-value)
- Severity

---

### 3. Drift Monitoring Page (`/finance/drift`)

**Purpose**: Model feature drift tracking

**Drift Timeline**:
- **X-axis**: Time
- **Y-axis**: PSI value
- **Threshold lines**:
  - PSI = 0.10 (minor drift, dotted yellow)
  - PSI = 0.25 (moderate drift, dashed orange)
  - PSI = 0.50 (severe drift, solid red)
- **Multiple features**: Different colored lines per feature

**Feature Cards**:
- Feature name
- Current PSI
- Severity badge
- KL divergence
- JS divergence
- Mean shift %
- Variance shift %

**Alert Panel**:
- Active drift alerts (PSI >= 0.25)
- Recommended actions
- Acknowledge/dismiss controls

---

### 4. Obligation Compliance Page (`/finance/compliance`)

**Purpose**: Regulatory obligation tracking

**Coverage Gauge**:
- Circular progress gauge showing % met
- Color-coded:
  - >= 90%: Green
  - 70-89%: Yellow
  - 50-69%: Orange
  - < 50%: Red

**Obligation List**:
- Columns:
  - Obligation ID
  - Citation
  - Regulator
  - Domain (ECOA, TILA, FCRA, etc.)
  - Status (met/violated)
  - Evidence completeness
  - Last evaluation

**Filters**:
- Regulator dropdown (OCC, CFPB, FRB, FDIC, NCUA)
- Domain dropdown
- Status filter (all/met/violated)

**Detail Modal**:
- Full obligation description
- Required evidence list
- Triggering conditions
- Recent evaluations timeline

---

### 5. Decision Explorer Page (`/finance/decisions`)

**Purpose**: Decision record search and analysis

**Search/Filter**:
- Decision ID search
- Date range
- Decision type selector
- Risk level filter
- Model selector

**Decision Table**:
- Columns:
  - Decision ID
  - Type
  - Date
  - Model
  - Coverage %
  - Risk level
  - Open violations count
  - Actions (view details)

**Detail Panel** (slide-out):
- Decision metadata
- Evidence payload (JSON viewer)
- Obligation evaluation results
- Evidence envelope status
- Chain position in envelope graph

---

### 6. Evidence Chain Explorer (`/finance/evidence`)

**Purpose**: Cryptographic integrity verification

**Chain Visualization**:
- **Graph view**: Nodes = envelopes, edges = ENVELOPE_CHAINS_TO
- **Timeline view**: Linear chain from genesis to head
- **Color coding**:
  - Green: No tamper detected
  - Red: Tamper detected
  - Gray: Not yet verified

**Verification Panel**:
- Envelope ID input
- "Verify Integrity" button
- Results:
  - ✅ Payload hash valid
  - ✅ Current hash valid
  - ✅ Chain continuity valid
  - ✅ Merkle proof valid
- Verification timestamp

**Chain Statistics**:
- Total envelopes
- Chain length
- Genesis hash
- Head hash
- Last envelope timestamp

---

## API Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/finance/stats` | Service statistics |
| `GET /v1/finance/snapshot` | Compliance snapshot |
| `GET /v1/finance/decision/{id}` | Decision details |
| `POST /v1/finance/decision/record` | Record decision |
| `GET /v1/obligations/coverage/finance` | Obligation coverage |
| `POST /v1/evidence/verify` | Verify envelope |
| `GET /v1/evidence/chain/{id}` | Chain traversal |

---

## Technology Stack

**Frontend Framework**: Next.js 14 (App Router)

**UI Libraries**:
- **Charts**: Recharts (for line, bar, pie charts)
- **Heatmap**: react-heatmap-grid or custom D3
- **Gauge**: recharts RadialBarChart
- **Graph Visualization**: react-force-graph (for chain explorer)
- **Data Tables**: TanStack Table
- **Date Pickers**: react-datepicker
- **Styling**: Tailwind CSS (or existing RegEngine design system)

**State Management**:
- React Query (for API data fetching + caching)

**Real-time**:
- Polling strategy (30-60 second intervals)
- Or WebSocket (if backend supports)

---

## Design System

### Colors

**Risk Levels**:
- Low: `#10b981` (green-500)
- Medium: `#f59e0b` (amber-500)
- High: `#f97316` (orange-500)
- Critical: `#ef4444` (red-500)

**Bias Severity**:
- Pass (DIR >= 0.80): `#22c55e` (green-500)
- Moderate (0.50-0.79): `#eab308` (yellow-500)
- Severe (< 0.50): `#dc2626` (red-600)

**Drift Severity**:
- None (PSI < 0.10): `#6b7280` (gray-500)
- Minor (0.10-0.24): `#fbbf24` (yellow-400)
- Moderate (0.25-0.49): `#fb923c` (orange-400)
- Severe (>= 0.50): `#e11d48` (rose-600)

### Typography

**Headers**: Inter, system-ui (bold, 600-700 weight)
**Body**: Inter, system-ui (regular, 400 weight)
**Monospace** (hashes, IDs): `font-mono`

---

## Implementation Priority

1. **Dashboard Overview** (highest priority)
   - Quick win, shows immediate value
   - Uses `/v1/finance/stats` and `/v1/finance/snapshot`

2. **Obligation Compliance**
   - Core RegEngine value prop
   - Uses `/v1/obligations/coverage/finance`

3. **Decision Explorer**
   - Essential for investigation
   - Uses `/v1/finance/decision/{id}`

4. **Bias Analytics**
   - High compliance value
   - Requires bias engine integration

5. **Drift Monitoring**
   - Important for model governance
   - Requires drift engine integration

6. **Evidence Chain Explorer**
   - Advanced feature
   - Demonstrates cryptographic integrity

---

## Sample Wireframes (Textual)

### Dashboard Overview
```
+--------------------------------------------------+
| Finance Vertical Dashboard                   🔄  |
+--------------------------------------------------+
| [Total Decisions]  [Coverage %]  [Risk]  [Violations] |
|     1,234           85.2%       Medium      12         |
+--------------------------------------------------+
| Decision Volume (Last 30 Days)                   |
| [Line chart showing daily decision counts]       |
+--------------------------------------------------+
| Risk Distribution        Top Violated Obligations|
| [Pie chart]              [Horizontal bar chart]  |
+--------------------------------------------------+
```

### Bias Heatmap
```
+--------------------------------------------------+
| Bias Analytics - Protected Class Analysis        |
+--------------------------------------------------+
| Filters: [Date Range] [Model] [Protected Class]  |
+--------------------------------------------------+
|               credit_  credit_  limit_  fraud_   |
|               approval denial   adjust  flag     |
| race          [0.85🟢] [0.72🟡] [0.91🟢] [0.88🟢]|
| sex           [0.79🟡] [0.45🔴] [0.82🟢] [0.75🟡]|
| age           [0.92🟢] [0.88🟢] [0.94🟢] [0.90🟢]|
| marital_stat  [0.81🟢] [0.68🟡] [0.85🟢] [0.77🟡]|
+--------------------------------------------------+
| 🔴 Severe (< 0.50)  🟡 Moderate (0.50-0.79)  🟢 Pass (>= 0.80) |
+--------------------------------------------------+
```

---

## Testing Strategy

**Component Tests**:
- Snapshot renders correctly
- Charts display data properly
- Filters update state
- Modal interactions work

**Integration Tests**:
- API calls succeed
- Data transformation correct
- Real-time polling works
- Error states handled

**E2E Tests** (Playwright):
- Navigate to dashboard
- Filter decisions
- View decision details
- Verify evidence envelope
- Export data

---

## Future Enhancements

- **Alerts**: Email/Slack notifications for violations
- **Exports**: CSV/JSON download for all views
- **Compare**: Side-by-side model comparison
- **Forecasting**: Predict future drift/bias trends
- **Custom Dashboards**: User-defined widget layouts
- **Mobile**: Responsive design for tablet/phone
