import { useState } from "react";
import { Building2, Check } from "lucide-react";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useTenant } from "@/contexts/TenantContext";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";

export default function TenantSelector() {
  const { tenants, tenant, setTenant } = useTenant();
  const [open, setOpen] = useState(false);

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2 max-w-[220px]" data-testid="tenant-selector">
          <span
            className="h-2 w-2 rounded-full shrink-0"
            style={{ background: tenant?.primary_color || "#3B82F6" }}
          />
          <Building2 className="h-3.5 w-3.5" />
          <span className="truncate text-xs font-semibold">{tenant?.name || "All Tenants"}</span>
          <Badge variant="secondary" className="text-[9px] font-mono ml-1">{tenant?.domain || "ALL"}</Badge>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel className="text-[10px] uppercase tracking-[0.2em] font-bold text-muted-foreground">
          QRadar Domain
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {tenants.map((t) => (
          <DropdownMenuItem
            key={t.id}
            onClick={() => setTenant(t.id)}
            className={cn("gap-2 py-2", tenant?.id === t.id && "bg-accent")}
            data-testid={`tenant-option-${t.id}`}
          >
            <span
              className="h-2 w-2 rounded-full"
              style={{ background: t.primary_color || "#3B82F6" }}
            />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate">{t.name}</div>
              <div className="text-[10px] font-mono text-muted-foreground truncate">{t.domain}</div>
            </div>
            {tenant?.id === t.id && <Check className="h-3.5 w-3.5 text-primary" />}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild data-testid="tenant-manage-link">
          <Link to="/settings" className="text-xs text-muted-foreground">Manage tenants & branding →</Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
