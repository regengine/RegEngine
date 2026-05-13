'use client';

import { ReactNode } from 'react';

interface PageContainerProps {
  children: ReactNode;
}

export function PageContainer({ children }: PageContainerProps) {
  return (
    <div className="container mx-auto px-4 sm:px-6 py-6 sm:py-8">
      {children}
    </div>
  );
}
