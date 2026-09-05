import { cn } from "@/lib/utils";
import {
  Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from "@/components/ui/tooltip";

/**
 * MITRE ATT&CK Heatmap - tactics as columns, techniques as cells.
 * data: [{ tactic, coverage, techniques: [{name, covered, hits}] }]
 */
export default function MitreHeatmap({ data }) {
  const maxHits = Math.max(1, ...data.flatMap((t) => t.techniques.map((x) => x.hits)));

  const cellColor = (technique) => {
    if (!technique.covered) return "bg-muted/40 text-muted-foreground";
    const pct = technique.hits / maxHits;
    if (pct > 0.66) return "bg-rose-500/70 text-white border-rose-500/70";
    if (pct > 0.33) return "bg-amber-500/60 text-white border-amber-500/60";
    return "bg-emerald-500/50 text-white border-emerald-500/50";
  };

  return (
    <TooltipProvider>
      <div className="overflow-x-auto pb-2" data-testid="mitre-heatmap">
        <div className="min-w-[1000px] grid gap-2" style={{ gridTemplateColumns: `repeat(${data.length}, minmax(0, 1fr))` }}>
          {data.map((tactic) => (
            <div key={tactic.tactic} className="flex flex-col gap-1">
              <div className="mb-2 px-2 py-2 rounded-md border border-border/60 bg-muted/30">
                <div className="text-[10px] uppercase tracking-[0.15em] font-bold text-muted-foreground truncate">
                  {tactic.tactic}
                </div>
                <div className="text-sm font-bold mt-1 tabular">{tactic.coverage}%</div>
              </div>
              {tactic.techniques.map((tech) => (
                <Tooltip key={tech.name}>
                  <TooltipTrigger asChild>
                    <div
                      className={cn(
                        "px-2 py-2 rounded border text-[11px] leading-tight cursor-default transition-transform hover:scale-[1.02]",
                        cellColor(tech),
                      )}
                    >
                      <div className="truncate">{tech.name}</div>
                      <div className="text-[10px] opacity-80 tabular mt-0.5">{tech.hits} hits</div>
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>
                    <div className="text-xs">
                      <div className="font-semibold">{tactic.tactic} · {tech.name}</div>
                      <div>{tech.covered ? "Covered" : "Not covered"} — {tech.hits} hits</div>
                    </div>
                  </TooltipContent>
                </Tooltip>
              ))}
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-2"><span className="h-3 w-3 rounded bg-muted/40 border" /> No coverage</div>
          <div className="flex items-center gap-2"><span className="h-3 w-3 rounded bg-emerald-500/50" /> Low activity</div>
          <div className="flex items-center gap-2"><span className="h-3 w-3 rounded bg-amber-500/60" /> Medium</div>
          <div className="flex items-center gap-2"><span className="h-3 w-3 rounded bg-rose-500/70" /> High activity</div>
        </div>
      </div>
    </TooltipProvider>
  );
}
