import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PasskeyRequiredNotice } from '@/components/auth/PasskeyRequiredNotice';

describe('PasskeyRequiredNotice', () => {
    it('announces that a passkey is required, with the reason', () => {
        render(<PasskeyRequiredNotice>This action remains blocked.</PasskeyRequiredNotice>);
        const alert = screen.getByRole('alert');
        expect(alert).toHaveTextContent('Passkey required');
        expect(alert).toHaveTextContent('This action remains blocked.');
    });
});
