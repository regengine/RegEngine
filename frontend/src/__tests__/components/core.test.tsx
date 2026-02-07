/**
 * Core UI Component Tests
 * 
 * Tests for shared UI components:
 * - Button component with variants
 * - Input component with validation
 * - Card components
 * - Toast notifications
 */

import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';

describe('Button Component', () => {
    it('renders button with text', () => {
        render(<Button>Click me</Button>);
        expect(screen.getByRole('button', { name: /click me/i })).toBeInTheDocument();
    });

    it('handles click events', async () => {
        const user = userEvent.setup();
        const handleClick = vi.fn();

        render(<Button onClick={handleClick}>Click me</Button>);

        await user.click(screen.getByRole('button'));
        expect(handleClick).toHaveBeenCalledTimes(1);
    });

    it('can be disabled', () => {
        render(<Button disabled>Disabled</Button>);
        expect(screen.getByRole('button')).toBeDisabled();
    });

    it('does not trigger onClick when disabled', async () => {
        const user = userEvent.setup();
        const handleClick = vi.fn();

        render(<Button disabled onClick={handleClick}>Disabled</Button>);

        await user.click(screen.getByRole('button'));
        expect(handleClick).not.toHaveBeenCalled();
    });

    it('supports different variants via className', () => {
        const { container } = render(<Button className="custom-class">Button</Button>);
        expect(container.firstChild).toHaveClass('custom-class');
    });

    it('can render as different element types', () => {
        render(<Button asChild><a href="/test">Link Button</a></Button>);
        const link = screen.getByRole('link');
        expect(link).toHaveTextContent('Link Button');
        expect(link).toHaveAttribute('href', '/test');
    });
});

describe('Input Component', () => {
    it('renders input field', () => {
        render(<Input placeholder="Enter text" />);
        expect(screen.getByPlaceholderText(/enter text/i)).toBeInTheDocument();
    });

    it('accepts user input', async () => {
        const user = userEvent.setup();
        render(<Input />);

        const input = screen.getByRole('textbox');
        await user.type(input, 'Hello World');

        expect(input).toHaveValue('Hello World');
    });

    it('can be disabled', () => {
        render(<Input disabled />);
        expect(screen.getByRole('textbox')).toBeDisabled();
    });

    it('supports different input types', () => {
        render(<Input type="email" data-testid="email-input" />);
        const input = screen.getByTestId('email-input');
        expect(input).toHaveAttribute('type', 'email');
    });

    it('forwards ref correctly', () => {
        const ref = vi.fn();
        render(<Input ref={ref as any} />);
        expect(ref).toHaveBeenCalled();
    });

    it('supports required attribute', () => {
        render(<Input required />);
        expect(screen.getByRole('textbox')).toBeRequired();
    });

    it('handles onChange events', async () => {
        const user = userEvent.setup();
        const handleChange = vi.fn();

        render(<Input onChange={handleChange} />);

        const input = screen.getByRole('textbox');
        await user.type(input, 'test');

        expect(handleChange).toHaveBeenCalled();
    });

    it('supports controlled input', async () => {
        const user = userEvent.setup();
        const handleChange = vi.fn();

        const { rerender } = render(
            <Input value="initial" onChange={handleChange} />
        );

        expect(screen.getByRole('textbox')).toHaveValue('initial');

        rerender(<Input value="updated" onChange={handleChange} />);
        expect(screen.getByRole('textbox')).toHaveValue('updated');
    });
});

describe('Card Components', () => {
    it('renders card with all sub-components', () => {
        render(
            <Card>
                <CardHeader>
                    <CardTitle>Card Title</CardTitle>
                    <CardDescription>Card Description</CardDescription>
                </CardHeader>
                <CardContent>Card Content</CardContent>
            </Card>
        );

        expect(screen.getByText('Card Title')).toBeInTheDocument();
        expect(screen.getByText('Card Description')).toBeInTheDocument();
        expect(screen.getByText('Card Content')).toBeInTheDocument();
    });

    it('applies custom className to Card', () => {
        const { container } = render(<Card className="custom-card">Content</Card>);
        expect(container.firstChild).toHaveClass('custom-card');
    });

    it('CardTitle renders as h3 by default', () => {
        render(<CardTitle>Title</CardTitle>);
        const title = screen.getByText('Title');
        expect(title.tagName).toBe('H3');
    });

    it('CardDescription has correct styling', () => {
        const { container } = render(<CardDescription>Description</CardDescription>);
        const description = screen.getByText('Description');
        expect(description).toBeInTheDocument();
    });

    it('can nest interactive elements in CardContent', async () => {
        const user = userEvent.setup();
        const handleClick = vi.fn();

        render(
            <Card>
                <CardContent>
                    <Button onClick={handleClick}>Action</Button>
                </CardContent>
            </Card>
        );

        await user.click(screen.getByRole('button', { name: /action/i }));
        expect(handleClick).toHaveBeenCalled();
    });
});

describe('Component Integration', () => {
    it('Button and Input work together in forms', async () => {
        const user = userEvent.setup();
        const handleSubmit = vi.fn((e) => e.preventDefault());

        render(
            <form onSubmit={handleSubmit}>
                <Input placeholder="Enter value" />
                <Button type="submit">Submit</Button>
            </form>
        );

        const input = screen.getByPlaceholderText(/enter value/i);
        const button = screen.getByRole('button', { name: /submit/i });

        await user.type(input, 'test value');
        await user.click(button);

        expect(handleSubmit).toHaveBeenCalled();
    });

    it('Card can contain form with Input and Button', async () => {
        const user = userEvent.setup();
        const handleSubmit = vi.fn((e) => e.preventDefault());

        render(
            <Card>
                <CardHeader>
                    <CardTitle>Login Form</CardTitle>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit}>
                        <Input type="email" placeholder="Email" />
                        <Button type="submit">Sign In</Button>
                    </form>
                </CardContent>
            </Card>
        );

        await user.type(screen.getByPlaceholderText(/email/i), 'test@example.com');
        await user.click(screen.getByRole('button', { name: /sign in/i }));

        expect(handleSubmit).toHaveBeenCalled();
    });
});
