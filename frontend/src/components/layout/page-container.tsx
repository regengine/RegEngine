'use client';

import { ReactNode } from 'react';
import { Container, type ContainerWidth } from '@/components/layout/container';
import { cn } from '@/lib/utils';

/**
 * PageContainer — the app-surface width wrapper.
 *
 * Kept as the default export name because 31 pages import it (and five page
 * tests mock this module path). It is now a thin wrapper over `Container`, so
 * the app has one width scale instead of the container zoo the inventory found.
 */
interface PageContainerProps {
  children: ReactNode;
  width?: ContainerWidth;
  className?: string;
}

export function PageContainer({ children, width = 'app', className }: PageContainerProps) {
  return (
    <Container width={width} className={cn('py-5 sm:py-6', className)}>
      {children}
    </Container>
  );
}
