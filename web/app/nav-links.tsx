"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const links = [
  { href: "/",          label: "Ingest"    },
  { href: "/tutorials", label: "Library"   },
  { href: "/watchers",  label: "Watchers"  },
  { href: "/gaps",      label: "Gaps"      },
  { href: "/query",     label: "Query"     },
];

export function NavLinks() {
  const path = usePathname();

  return (
    <nav className="flex items-center gap-1">
      {links.map(({ href, label }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "px-3 py-1.5 rounded-md text-sm transition-colors",
              active
                ? "text-foreground bg-white/[0.06] font-medium"
                : "text-muted-foreground hover:text-foreground hover:bg-white/[0.04]"
            )}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
