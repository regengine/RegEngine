import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { SnapshotIntegrityCoverage } from '@/components/compliance/snapshot-integrity-coverage';
it('limits a legacy hash match to its exact backend coverage', () => {
 render(<SnapshotIntegrityCoverage version={1} coverage="identity fields only; compliance posture and attestation are NOT sealed (legacy v1 seal)"/>);
 expect(screen.getByText(/identity fields only/)).toHaveTextContent('compliance posture and attestation are NOT sealed');
 expect(screen.queryByText(/data has not been modified/)).not.toBeInTheDocument();
});
it('does not infer full coverage when metadata is absent', () => {
 render(<SnapshotIntegrityCoverage/>);
 expect(screen.getByText(/full snapshot integrity is not established/)).toBeInTheDocument();
});
