/**
 * The shared control recipe — SPEC §4. Input, Textarea, Select and any native
 * control render it, so a select and a text field on one row are identical
 * apart from the chevron.
 *
 * In dark mode fields sit on `surface-inset`, i.e. *below* the card, so they
 * read as wells rather than slabs. `border-default` at rest is a decorative
 * boundary; hover and focus promote it to `border-strong` plus a 2px ring, so
 * the control's edge is always identifiable at 3:1 when it matters.
 *
 * This lives in its own module rather than in `input.tsx` because several test
 * suites replace `@/components/ui/input` with a partial `vi.mock`. When Select
 * imported the recipe from there, those mocks made Select throw at import time
 * for a constant that has nothing to do with the Input component. `input.tsx`
 * re-exports it, so every existing import path keeps working.
 */
export const fieldControlClasses =
  "flex h-9 w-full rounded-md border border-re-border bg-re-surface-card px-3 text-ui text-re-text-primary placeholder:text-re-text-muted transition-colors duration-120 hover:border-re-border-strong focus-visible:outline-none focus-visible:border-re-brand focus-visible:ring-2 focus-visible:ring-re-focus-ring/25 disabled:cursor-not-allowed disabled:bg-re-surface-inset disabled:text-re-text-disabled aria-[invalid=true]:border-re-danger aria-[invalid=true]:focus-visible:ring-re-danger/25 motion-reduce:transition-none dark:bg-re-surface-inset"
