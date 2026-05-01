"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Building2,
  MapPin,
  Package,
  Search,
  Factory,
  Truck,
  Store,
  Ship,
  Leaf,
  Fish,
} from "lucide-react";
import {
  ALL_TARGET_COMPANIES,
  LEAFY_GREENS_COMPANIES,
  SEAFOOD_COMPANIES,
  type TargetCompany,
  type SupplyChainRole,
  type ProductSegment,
} from "@/data/fsma-target-market";

const ROLE_ICONS: Record<
  SupplyChainRole,
  React.ComponentType<{ className?: string }>
> = {
  GROWER: Leaf,
  PROCESSOR: Factory,
  DISTRIBUTOR: Truck,
  RETAILER: Store,
  IMPORTER: Ship,
};

const ROLE_LABELS: Record<SupplyChainRole, string> = {
  GROWER: "Grower/Farmer",
  PROCESSOR: "Processor",
  DISTRIBUTOR: "Distributor",
  RETAILER: "Retailer",
  IMPORTER: "Importer",
};

const SCALE_BADGES: Record<
  TargetCompany["scale"],
  { label: string; className: string }
> = {
  MAJOR_NATIONAL: {
    label: "Major National",
    className:
      "border-re-border-default bg-re-surface-base text-re-text-primary",
  },
  REGIONAL_MAJOR: {
    label: "Regional Major",
    className:
      "border-re-border-default bg-re-surface-base text-re-text-secondary",
  },
  REGIONAL: {
    label: "Regional",
    className:
      "border-re-border-default bg-re-surface-base text-re-text-tertiary",
  },
  EMERGING: {
    label: "Emerging",
    className:
      "border-re-border-default bg-re-surface-base text-re-text-secondary",
  },
};

const SEGMENT_BADGES: Record<
  ProductSegment,
  { label: string; icon: React.ComponentType<{ className?: string }> }
> = {
  LEAFY_GREENS: { label: "Leafy Greens", icon: Leaf },
  FRESH_CUT: { label: "Fresh-Cut", icon: Package },
  TOMATOES: { label: "Tomatoes", icon: Package },
  PEPPERS: { label: "Peppers", icon: Package },
  FINFISH: { label: "Finfish", icon: Fish },
  SHELLFISH: { label: "Shellfish", icon: Fish },
  SMOKED_FISH: { label: "Smoked Fish", icon: Fish },
};

interface CompanyCardProps {
  company: TargetCompany;
  onClick?: () => void;
}

function CompanyCard({ company, onClick }: CompanyCardProps) {
  const RoleIcon = ROLE_ICONS[company.role];
  const scaleBadge = SCALE_BADGES[company.scale];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="h-full"
    >
      <button
        type="button"
        className="h-full w-full cursor-pointer border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 text-left transition-colors hover:border-[var(--re-brand)]"
        onClick={onClick}
      >
        <div className="flex items-start justify-between gap-3 border-b border-[var(--re-surface-border)] pb-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center border border-[var(--re-surface-border)] bg-[var(--re-surface-base)]">
              <RoleIcon className="h-4 w-4" />
            </div>
            <div>
              <h3 className="font-semibold text-sm">{company.name}</h3>
              {company.parentCompany && (
                <p className="text-xs text-muted-foreground">
                  {company.parentCompany}
                </p>
              )}
            </div>
          </div>
          <Badge
            variant="outline"
            className={`text-xs ${scaleBadge.className}`}
          >
            {scaleBadge.label}
          </Badge>
        </div>

        <div className="flex items-center gap-1 text-xs text-muted-foreground mb-3 mt-3">
          <MapPin className="h-3 w-3" />
          {company.headquarters}
        </div>

        <div className="flex flex-wrap gap-1 mb-3">
          {company.segment.slice(0, 2).map((seg) => {
            const segInfo = SEGMENT_BADGES[seg];
            return (
              <Badge key={seg} variant="outline" className="text-xs rounded-sm">
                {segInfo.label}
              </Badge>
            );
          })}
          {company.segment.length > 2 && (
            <Badge variant="outline" className="text-xs rounded-sm">
              +{company.segment.length - 2}
            </Badge>
          )}
        </div>

        <p className="text-xs text-muted-foreground line-clamp-2">
          {company.products.join(", ")}
        </p>

        {company.notes && (
          <p className="text-xs text-[var(--re-brand)] mt-2 font-medium">
            {company.notes}
          </p>
        )}
      </button>
    </motion.div>
  );
}

type SegmentFilter = "all" | "produce" | "seafood";

export function TargetMarketBrowser() {
  const [search, setSearch] = useState("");
  const [segmentFilter, setSegmentFilter] = useState<SegmentFilter>("all");
  const [roleFilter, setRoleFilter] = useState<SupplyChainRole | "all">("all");
  const [selectedCompany, setSelectedCompany] = useState<TargetCompany | null>(
    null,
  );

  const filteredCompanies = ALL_TARGET_COMPANIES.filter((company) => {
    // Search filter
    if (search) {
      const searchLower = search.toLowerCase();
      const matchesSearch =
        company.name.toLowerCase().includes(searchLower) ||
        company.headquarters.toLowerCase().includes(searchLower) ||
        company.products.some((p) => p.toLowerCase().includes(searchLower)) ||
        (company.parentCompany?.toLowerCase().includes(searchLower) ?? false);
      if (!matchesSearch) return false;
    }

    // Segment filter
    if (segmentFilter === "produce") {
      if (!LEAFY_GREENS_COMPANIES.some((c) => c.id === company.id))
        return false;
    } else if (segmentFilter === "seafood") {
      if (!SEAFOOD_COMPANIES.some((c) => c.id === company.id)) return false;
    }

    // Role filter
    if (roleFilter !== "all" && company.role !== roleFilter) return false;

    return true;
  });

  const stats = {
    total: ALL_TARGET_COMPANIES.length,
    produce: LEAFY_GREENS_COMPANIES.length,
    seafood: SEAFOOD_COMPANIES.length,
    majorNational: ALL_TARGET_COMPANIES.filter(
      (c) => c.scale === "MAJOR_NATIONAL",
    ).length,
  };

  return (
    <div className="space-y-6">
      {/* Stats Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 text-center">
          <p className="text-3xl font-bold text-[var(--re-text-primary)]">
            {stats.total}
          </p>
          <p className="text-sm text-muted-foreground">Total Companies</p>
        </div>
        <div className="border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 text-center">
          <p className="text-3xl font-bold text-[var(--re-text-primary)]">
            {stats.produce}
          </p>
          <p className="text-sm text-muted-foreground">Produce Segment</p>
        </div>
        <div className="border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 text-center">
          <p className="text-3xl font-bold text-[var(--re-text-primary)]">
            {stats.seafood}
          </p>
          <p className="text-sm text-muted-foreground">Seafood Segment</p>
        </div>
        <div className="border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 text-center">
          <p className="text-3xl font-bold text-[var(--re-text-primary)]">
            {stats.majorNational}
          </p>
          <p className="text-sm text-muted-foreground">Major National</p>
        </div>
      </div>

      {/* Filters */}
      <section className="border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 space-y-4">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search companies, locations, products..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10"
              />
            </div>
          </div>

          <div className="flex gap-2">
            <Button
              variant={segmentFilter === "all" ? "default" : "outline"}
              size="sm"
              onClick={() => setSegmentFilter("all")}
            >
              All
            </Button>
            <Button
              variant={segmentFilter === "produce" ? "default" : "outline"}
              size="sm"
              onClick={() => setSegmentFilter("produce")}
            >
              <Leaf className="h-4 w-4 mr-1" />
              Produce
            </Button>
            <Button
              variant={segmentFilter === "seafood" ? "default" : "outline"}
              size="sm"
              onClick={() => setSegmentFilter("seafood")}
            >
              <Fish className="h-4 w-4 mr-1" />
              Seafood
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <span className="text-sm text-muted-foreground self-center">
            Role:
          </span>
          <Button
            variant={roleFilter === "all" ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setRoleFilter("all")}
          >
            All Roles
          </Button>
          {Object.entries(ROLE_LABELS).map(([role, label]) => {
            const Icon = ROLE_ICONS[role as SupplyChainRole];
            return (
              <Button
                key={role}
                variant={roleFilter === role ? "secondary" : "ghost"}
                size="sm"
                onClick={() => setRoleFilter(role as SupplyChainRole)}
              >
                <Icon className="h-3 w-3 mr-1" />
                {label}
              </Button>
            );
          })}
        </div>
      </section>

      {/* Results */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Showing {filteredCompanies.length} of {stats.total} companies
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredCompanies.map((company) => (
          <CompanyCard
            key={company.id}
            company={company}
            onClick={() => setSelectedCompany(company)}
          />
        ))}
      </div>

      {filteredCompanies.length === 0 && (
        <div className="border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] py-12">
          <div className="text-center">
            <Building2 className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">No companies found</h3>
            <p className="text-muted-foreground">
              Try adjusting your search or filters
            </p>
          </div>
        </div>
      )}

      {/* Company Detail Modal would go here */}
    </div>
  );
}
