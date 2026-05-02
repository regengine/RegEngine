import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  CommitGate,
  ComplianceStateBadge,
  EvidenceCard,
  EvidencePackagePreview,
  HashVerificationStrip,
  ReadinessScore,
  RegulatoryCitationBlock,
} from "@/components/compliance";

describe("Compliance primitives", () => {
  it("renders object-state badges with the compliance state label", () => {
    render(<ComplianceStateBadge state="needs-correction" />);

    expect(screen.getByText("Needs correction")).toBeInTheDocument();
  });

  it("renders evidence cards with metadata and state", () => {
    render(
      <EvidenceCard
        title="Supplier Gap Radar"
        description="Owner and blocker visibility for supplier files."
        state="blocked"
        meta="Readiness workbench"
      />,
    );

    expect(screen.getByText("Supplier Gap Radar")).toBeInTheDocument();
    expect(screen.getByText("Readiness workbench")).toBeInTheDocument();
    expect(screen.getByText("Blocked")).toBeInTheDocument();
  });

  it("renders readiness scores as an accessible percentage", () => {
    render(<ReadinessScore score={86} label="Traceability readiness" description="Ready with three blockers." blockers={3} />);

    expect(screen.getByLabelText("Traceability readiness: 86% ready")).toBeInTheDocument();
    expect(screen.getByText("3 blockers")).toBeInTheDocument();
  });

  it("renders hash verification details without dropping long hashes", () => {
    render(<HashVerificationStrip hash="abc123def456" verifiedAt="verified today" state="signed" />);

    expect(screen.getByText(/SHA-256:abc123def456/)).toBeInTheDocument();
    expect(screen.getByText("Signed")).toBeInTheDocument();
  });

  it("renders commit gate criteria and blocked state", () => {
    render(
      <CommitGate
        status="blocked"
        title="Export eligibility gate"
        description="The package has unresolved gaps."
        criteria={[
          { label: "Tenant identity resolved", passed: true },
          { label: "Supplier gaps cleared", passed: false, detail: "3 lots still need ship-to values." },
        ]}
      />,
    );

    expect(screen.getByText("Export eligibility gate")).toBeInTheDocument();
    expect(screen.getByText("Supplier gaps cleared")).toBeInTheDocument();
    expect(screen.getByText("3 lots still need ship-to values.")).toBeInTheDocument();
  });

  it("renders evidence package and regulatory citation blocks", () => {
    render(
      <>
        <EvidencePackagePreview
          packageId="FDA-204-PKG-0427"
          status="building"
          records={1284}
          kdeCoverage={94}
          generatedAt="04:12"
          items={["Facility scope manifest", "Committed CTE/KDE records"]}
        />
        <RegulatoryCitationBlock citation="21 CFR 1.1455" title="Records within 24 hours">
          Response posture stays visible.
        </RegulatoryCitationBlock>
      </>,
    );

    expect(screen.getByText("FDA-204-PKG-0427")).toBeInTheDocument();
    expect(screen.getByText("1,284")).toBeInTheDocument();
    expect(screen.getByText("21 CFR 1.1455")).toBeInTheDocument();
  });
});
