import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Container } from "@/components/layout/container";

export type RelatedLink = {
  href: string;
  label: string;
  description?: string;
};

/**
 * Additive SEO related links. Prefer this over rewriting ranking-page body copy.
 * Anchor text is the visible label; keep it exact to the internal-links plan.
 */
export function RelatedLinks({
  links,
  heading = "Related",
  width = "marketing",
}: {
  links: RelatedLink[];
  heading?: string;
  width?: "marketing" | "tool" | "prose";
}) {
  if (!links.length) return null;
  return (
    <Container as="section" width={width} className="pb-16 pt-4">
      <h2 className="mb-3 text-label uppercase text-re-text-muted">{heading}</h2>
      <ul className="list-none p-0">
        {links.map((link) => (
          <li key={`${link.href}:${link.label}`} className="border-b border-re-border-subtle last:border-b-0">
            <Link
              href={link.href}
              className="group flex items-center gap-4 py-3 no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring"
            >
              <span className="min-w-0 flex-1">
                <span className="block text-ui font-medium text-re-text-primary transition-colors duration-120 group-hover:text-re-brand motion-reduce:transition-none">
                  {link.label}
                </span>
                {link.description ? (
                  <span className="mt-0.5 block truncate text-small text-re-text-tertiary">
                    {link.description}
                  </span>
                ) : null}
              </span>
              <ChevronRight
                aria-hidden="true"
                size={16}
                strokeWidth={1.75}
                className="shrink-0 text-re-text-muted transition-colors duration-120 group-hover:text-re-text-secondary motion-reduce:transition-none"
              />
            </Link>
          </li>
        ))}
      </ul>
    </Container>
  );
}
