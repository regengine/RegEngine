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
import { Button } from '@/components/ui/button';

// Facility type icons and colors
const facilityConfig: Record<FacilityType, { icon: React.ElementType; color: string; bgColor: string }> = {
  FARM: { icon: Leaf, color: 'text-re-success', bgColor: 'bg-re-success-muted dark:bg-green-900' },
  PROCESSOR: { icon: Factory, color: 'text-re-info', bgColor: 'bg-re-info-muted dark:bg-blue-900' },
  DISTRIBUTOR: { icon: Truck, color: 'text-purple-600', bgColor: 'bg-purple-100 dark:bg-purple-900' },
  RETAILER: { icon: Store, color: 'text-orange-600', bgColor: 'bg-orange-100 dark:bg-orange-900' },
  RESTAURANT: { icon: ChefHat, color: 'text-re-danger', bgColor: 'bg-re-danger-muted dark:bg-re-danger' },
};

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
          <Button variant="outline" size="sm" onClick={onExport}>
            <Download className="w-4 h-4 mr-2" />
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
                'relative flex flex-col items-center cursor-pointer transition-all',
                isHighlighted && 'scale-110',
                isAffected && 'ring-2 ring-re-danger ring-offset-2 rounded-xl'
              )}
              onClick={() => onFacilityClick?.(facility)}
            >
              {/* Node Circle */}
              <div
                className={cn(
                  'relative w-16 h-16 rounded-xl flex items-center justify-center transition-all',
                  config.bgColor,
                  isHighlighted && 'shadow-lg',
                  isAffected && 'animate-pulse'
                )}
              >
                <Icon className={cn('w-8 h-8', config.color)} />

                {/* Event count badge */}
                {facilityEvents.length > 0 && (
                  <span className="absolute -top-1 -right-1 w-5 h-5 flex items-center justify-center text-xs font-bold bg-primary text-primary-foreground rounded-full">
                    {facilityEvents.length}
                  </span>
                )}

                {/* Affected indicator */}
                {isAffected && (
                  <span className="absolute -bottom-1 -right-1 w-5 h-5 flex items-center justify-center bg-re-danger-muted0 text-white rounded-full">
                    <AlertTriangle className="w-3 h-3" />
                  </span>
                )}
              </div>

              {/* Labels */}
              {showLabels && (
                <div className="mt-2 text-center max-w-[100px]">
                  <p className="text-xs font-medium truncate">{facility.name}</p>
                  <p className="text-xs text-muted-foreground">{facility.type}</p>
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
                <div className={cn(
                  'h-0.5 bg-muted-foreground/30',
                  isHorizontal ? 'w-8' : 'w-8'
                )} />
                <ArrowRight className="w-4 h-4 text-muted-foreground/50 -mx-1" />
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
                'w-8 h-8 rounded-md flex items-center justify-center',
                config.bgColor,
                isAffected && 'ring-2 ring-re-danger'
              )}
              title={`${facility.name} (${facility.type})`}
            >
              <Icon className={cn('w-4 h-4', config.color)} />
            </div>
            {index < sortedFacilities.length - 1 && (
              <ArrowRight className="w-3 h-3 text-muted-foreground/50" />
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
    <motion.div
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      className={cn(
        'p-4 rounded-lg border cursor-pointer transition-all',
        isSelected && 'ring-2 ring-primary',
        isAffected && 'border-re-danger bg-re-danger-muted dark:bg-re-danger/20',
        !isAffected && !isSelected && 'hover:shadow-md',
        className
      )}
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        <div className={cn('p-2 rounded-lg', config.bgColor)}>
          <Icon className={cn('w-6 h-6', config.color)} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="font-medium truncate">{facility.name}</h4>
            {isAffected && (
              <AlertTriangle className="w-4 h-4 text-re-danger flex-shrink-0" />
            )}
          </div>
          <p className="text-sm text-muted-foreground">{facility.type}</p>
          <p className="text-xs text-muted-foreground font-mono mt-1">GLN: {facility.gln}</p>
          {events.length > 0 && (
            <p className="text-xs text-muted-foreground mt-1">
              {events.length} event{events.length !== 1 ? 's' : ''}
            </p>
          )}
        </div>
      </div>

      {/* Contact info if available */}
      {facility.contact_name && (
        <div className="mt-3 pt-3 border-t text-sm">
          <p className="font-medium">{facility.contact_name}</p>
          {facility.contact_email && (
            <p className="text-muted-foreground">{facility.contact_email}</p>
          )}
          {facility.contact_phone && (
            <p className="text-muted-foreground">{facility.contact_phone}</p>
          )}
        </div>
      )}
    </motion.div>
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
        'p-3 rounded-lg border',
        isAffected && 'border-re-danger bg-re-danger-muted dark:bg-re-danger/20',
        className
      )}
    >
      <div className="flex items-center gap-2">
        <Package className={cn('w-5 h-5', isAffected ? 'text-re-danger' : 'text-muted-foreground')} />
        <div className="flex-1 min-w-0">
          <p className="font-mono text-sm truncate">{tlc}</p>
          {productDescription && (
            <p className="text-xs text-muted-foreground truncate">{productDescription}</p>
          )}
        </div>
        {quantity && (
          <span className="text-sm font-medium">
            {quantity} {unit || 'units'}
          </span>
        )}
        {isAffected && <AlertTriangle className="w-4 h-4 text-re-danger" />}
      </div>
    </div>
  );
}
