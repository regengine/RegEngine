import type * as React from "react"

/**
 * The type of an icon passed into a primitive's `icon` slot.
 *
 * Hand-rolling `React.ComponentType<{ className?: string }>` looks harmless and
 * is not: it rejects `strokeWidth`, which SPEC §5 requires on every icon, and
 * it is not a supertype of lucide's own component type — lucide types
 * `strokeWidth` as `string | number`, so narrowing it to `number` makes every
 * lucide icon un-assignable. Three separate migrations hit one side or the
 * other of that before this type existed.
 *
 * `SVGProps<SVGSVGElement>` is exactly the surface a lucide icon accepts, so
 * both directions type-check.
 */
export type IconComponent = React.ComponentType<React.SVGProps<SVGSVGElement>>
