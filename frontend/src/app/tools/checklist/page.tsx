import { permanentRedirect } from "next/navigation";

/**
 * Soft-404 cleanup: /tools/checklist has index residue but no page. Prefer the
 * live self-reported checklist over inventing a third checklist surface.
 */
export default function ToolsChecklistRedirect() {
  permanentRedirect("/tools/self-reported-checklist");
}
