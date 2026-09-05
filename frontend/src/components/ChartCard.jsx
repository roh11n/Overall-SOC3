import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export default function ChartCard({ title, subtitle, children, className, testid, action }) {
  return (
    <Card className={cn("p-5 flex flex-col gap-4", className)} data-testid={testid}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold">
            {subtitle}
          </div>
          <h3 className="text-base font-semibold mt-1 tracking-tight" style={{ fontFamily: "var(--font-heading)" }}>
            {title}
          </h3>
        </div>
        {action}
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </Card>
  );
}
