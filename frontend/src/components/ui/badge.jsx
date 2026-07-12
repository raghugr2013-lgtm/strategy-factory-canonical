import * as React from "react"
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

/**
 * shadcn Badge — extended in Phase U-1 with ASF verdict variants.
 *
 * Variants:
 *   - default | secondary | destructive | outline   (legacy, untouched)
 *   - verdict-success | verdict-warn | verdict-danger
 *     | verdict-neutral | verdict-info               (NEW — Phase U-1, C-03)
 *
 * The verdict-* variants resolve to the canonical ASF tokens (see
 * src/styles/asf-design-tokens.css). They are equivalent to using the
 * <VerdictBadge/> primitive from /components/ui-asf — the shadcn flavour
 * exists so existing badge call-sites can migrate by changing only the
 * `variant` prop, without swapping component types.
 *
 * Letter prefix (P/W/F/A/I) for colour-blind safety is NOT applied here —
 * use <VerdictBadge density="compact"/> when you need the letter prefix.
 */
const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground shadow hover:bg-primary/80",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground shadow hover:bg-destructive/80",
        outline: "text-foreground",
        "verdict-success":
          "border-[color:var(--asf-accent-success)] bg-[color:var(--asf-accent-success-fill)] text-[color:var(--asf-accent-success)]",
        "verdict-warn":
          "border-[color:var(--asf-accent-warn)] bg-[color:var(--asf-accent-warn-fill)] text-[color:var(--asf-accent-warn)]",
        "verdict-danger":
          "border-[color:var(--asf-accent-danger)] bg-[color:var(--asf-accent-danger-fill)] text-[color:var(--asf-accent-danger)]",
        "verdict-neutral":
          "border-[color:var(--asf-accent-neutral)] bg-[color:var(--asf-accent-neutral-fill)] text-[color:var(--asf-accent-neutral)]",
        "verdict-info":
          "border-[color:var(--asf-accent-info)] bg-[color:var(--asf-accent-info-fill)] text-[color:var(--asf-accent-info)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant,
  ...props
}) {
  return (<div className={cn(badgeVariants({ variant }), className)} {...props} />);
}

export { Badge, badgeVariants }
