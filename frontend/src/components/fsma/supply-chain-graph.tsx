'use client';

import React, { useMemo } from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import type { Facility, FacilityType, TraceEvent, TracePath } from '@/types/fsma';
import {
  Factory,
  Store,
  Truck,
  Warehouse,
  Leaf,
  ChefHat,
  ArrowRight,
  AlertTriangle,
  CheckCircle,
  Package,
  Download,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

// Facility type is *categorical*, not a status: it uses the --re-cat-* ramp and
// never a status colour. The node itself is a neutral inset well with a hairline
// — icons are never set in a tinted disc (SPEC §5.4).
const facilityConfig: Record<FacilityType, { icon: React.ElementType; color: string }> = {
  FARM: { icon: Leaf, color: 'text-re-cat-3' },
  PROCESSOR: { icon: Factory, color: 'text-re-cat-1' },
  DISTRIBUTOR: { icon: Truck, color: 'text-re-cat-4' },
  RETAILER: { icon: Store, color: 'text-re-cat-2' },
  RESTAURANT: { icon: ChefHat, color: 'text-re-cat-6' },
};

const NODE_SURFACE = 'border border-re-border bg-re-surface-inset';

interface SupplyChainGraphProps {
  facilities: Facility[];
  events?: TraceEvent[];
  paths?: TracePath[];
  highlightedFacility?: string;
  affectedFacilities?: string[];
  onFacilityClick?: (facility: Facility) => void;
  onExport?: () => void;
  className?: string;
  direction?: 'horizontal' | 'vertical';
  showLabels?: boolean;
  animated?: boolean;
}

export function SupplyChainGraph({
  facilities,
  events = [],
  paths = [],
  highlightedFacility,
  affectedFacilities = [],
  onFacilityClick,
  onExport,
  className,
  direction = 'horizontal',
  showLabels = true,
  animated = true,
}: SupplyChainGraphProps) {
  // Sort facilities by type to ensure logical flow
  const sortedFacilities = useMemo(() => {
    const typeOrder: Record<FacilityType, number> = {
      FARM: 0,
      PROCESSOR: 1,
      DISTRIBUTOR: 2,
      RETAILER: 3,
      RESTAURANT: 4,
    };
    return [...facilities].sort((a, b) => typeOrder[a.type] - typeOrder[b.type]);
  }, [facilities]);

  const isHorizontal = direction === 'horizontal';

  return (
    <div
      className={cn(
        'relative p-4',
        isHorizontal ? 'flex items-center gap-2 overflow-x-auto' : 'flex flex-col gap-4',
        className
      )}
    >
      {onExport && (
        <div className="absolute top-0 right-0 z-10">
          <Button variant="secondary" size="sm" onClick={onExport}>
            <Download className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            Export CSV
          </Button>
        </div>
      )}
      {sortedFacilities.map((facility, index) => {
        const config = facilityConfig[facility.type];
        const Icon = config.icon;
        const isAffected = affectedFacilities.includes(facility.gln);
        const isHighlighted = highlightedFacility === facility.gln;
        const facilityEvents = events.filter(e => e.facility_gln === facility.gln);

        return (
          <React.Fragment key={facility.gln}>
            {/* Facility Node */}
            <motion.div
              initial={animated ? { opacity: 0, scale: 0.8 } : undefined}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: index * 0.1 }}
              className={cn(
                'relative flex cursor-pointer flex-col items-center rounded-lg transition-colors duration-120 motion-reduce:transition-none',
                isAffected && 'ring-2 ring-re-danger ring-offset-2 ring-offset-re-surface-card'
              )}
              onClick={() => onFacilityClick?.(facility)}
            >
              {/* Node Circle */}
              <div
                className={cn(
                  'relative flex h-16 w-16 items-center justify-center rounded-lg transition-colors duration-120 motion-reduce:transition-none',
                  NODE_SURFACE,
                  isHighlighted && 'border-re-border-strong bg-re-surface-card',
                  isAffected && 'animate-pulse motion-reduce:animate-none'
                )}
              >
                <Icon className={cn('h-6 w-6', config.color)} strokeWidth={1.75} aria-hidden="true" />

                {/* Event count badge */}
                {facilityEvents.length > 0 && (
                  <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full border border-re-border bg-re-surface-card font-mono text-label tabular-nums text-re-text-primary">
                    {facilityEvents.length}
                  </span>
                )}

                {/* Affected indicator */}
                {isAffected && (
                  <span className="absolute -bottom-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-re-danger text-re-danger-foreground">
                    <AlertTriangle className="h-3 w-3" strokeWidth={1.75} aria-hidden="true" />
                  </span>
                )}
              </div>

              {/* Labels */}
              {showLabels && (
                <div className="mt-2 max-w-[100px] text-center">
                  <p className="truncate text-small font-medium text-re-text-primary">{facility.name}</p>
                  <p className="text-label text-re-text-muted">{facility.type}</p>
                </div>
              )}
            </motion.div>

            {/* Connector Arrow */}
            {index < sortedFacilities.length - 1 && (
              <motion.div
                initial={animated ? { opacity: 0, scaleX: 0 } : undefined}
                animate={{ opacity: 1, scaleX: 1 }}
                transition={{ delay: index * 0.1 + 0.05 }}
                className={cn(
                  'flex items-center',
                  isHorizontal ? 'flex-row px-2' : 'flex-col py-2 rotate-90'
                )}
              >
                <div className="h-px w-8 bg-re-border" />
                <ArrowRight className="-mx-1 h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
              </motion.div>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// Mini version for cards/compact display
interface MiniSupplyChainProps {
  facilities: Facility[];
  affectedFacilities?: string[];
  className?: string;
}

export function MiniSupplyChain({ facilities, affectedFacilities = [], className }: MiniSupplyChainProps) {
  const sortedFacilities = useMemo(() => {
    const typeOrder: Record<FacilityType, number> = {
      FARM: 0,
      PROCESSOR: 1,
      DISTRIBUTOR: 2,
      RETAILER: 3,
      RESTAURANT: 4,
    };
    return [...facilities].sort((a, b) => typeOrder[a.type] - typeOrder[b.type]);
  }, [facilities]);

  return (
    <div className={cn('flex items-center gap-1', className)}>
      {sortedFacilities.map((facility, index) => {
        const config = facilityConfig[facility.type];
        const Icon = config.icon;
        const isAffected = affectedFacilities.includes(facility.gln);

        return (
          <React.Fragment key={facility.gln}>
            <div
              className={cn(
                'flex h-8 w-8 items-center justify-center rounded-md',
                NODE_SURFACE,
                isAffected && 'ring-2 ring-re-danger'
              )}
              title={`${facility.name} (${facility.type})`}
            >
              <Icon className={cn('h-4 w-4', config.color)} strokeWidth={1.75} aria-hidden="true" />
            </div>
            {index < sortedFacilities.length - 1 && (
              <ArrowRight className="h-3 w-3 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// Facility card with details
interface FacilityCardProps {
  facility: Facility;
  events?: TraceEvent[];
  isAffected?: boolean;
  isSelected?: boolean;
  onClick?: () => void;
  className?: string;
}

export function FacilityCard({
  facility,
  events = [],
  isAffected,
  isSelected,
  onClick,
  className,
}: FacilityCardProps) {
  const config = facilityConfig[facility.type];
  const Icon = config.icon;

  return (
    <div
      className={cn(
        'cursor-pointer rounded-lg border bg-re-surface-card p-4 transition-colors duration-120 hover:border-re-border-strong motion-reduce:transition-none',
        isSelected ? 'border-re-border-strong' : 'border-re-border',
        className
      )}
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        <div className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-md', NODE_SURFACE)}>
          <Icon className={cn('h-5 w-5', config.color)} strokeWidth={1.75} aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h4 className="truncate text-subheading text-re-text-primary">{facility.name}</h4>
            {isAffected && (
              <Badge tone="danger" size="sm">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                Affected
              </Badge>
            )}
          </div>
          <p className="text-ui text-re-text-secondary">{facility.type}</p>
          <p className="mt-1 font-mono text-[0.8125rem] text-re-text-tertiary">GLN: {facility.gln}</p>
          {events.length > 0 && (
            <p className="mt-1 text-small text-re-text-tertiary">
              {events.length} event{events.length !== 1 ? 's' : ''}
            </p>
          )}
        </div>
      </div>

      {/* Contact info if available */}
      {facility.contact_name && (
        <div className="mt-3 border-t border-re-border-subtle pt-3 text-ui">
          <p className="font-medium text-re-text-primary">{facility.contact_name}</p>
          {facility.contact_email && (
            <p className="text-re-text-secondary">{facility.contact_email}</p>
          )}
          {facility.contact_phone && (
            <p className="text-re-text-secondary">{facility.contact_phone}</p>
          )}
        </div>
      )}
    </div>
  );
}

// Lot/Product card
interface LotCardProps {
  tlc: string;
  productDescription?: string;
  quantity?: number;
  unit?: string;
  isAffected?: boolean;
  className?: string;
}

export function LotCard({ tlc, productDescription, quantity, unit, isAffected, className }: LotCardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border bg-re-surface-card p-3',
        isAffected ? 'border-re-danger-border' : 'border-re-border',
        className
      )}
    >
      <div className="flex items-center gap-2">
        <Package className={cn('h-4 w-4 shrink-0', isAffected ? 'text-re-danger' : 'text-re-text-tertiary')} strokeWidth={1.75} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-[0.8125rem] text-re-text-primary">{tlc}</p>
          {productDescription && (
            <p className="truncate text-small text-re-text-tertiary">{productDescription}</p>
          )}
        </div>
        {quantity && (
          <span className="text-ui font-medium tabular-nums text-re-text-primary">
            {quantity} {unit || 'units'}
          </span>
        )}
        {isAffected && <AlertTriangle className="h-4 w-4 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />}
      </div>
    </div>
  );
}
