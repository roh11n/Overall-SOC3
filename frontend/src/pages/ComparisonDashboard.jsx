import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Camera, Trash2, ArrowUp, ArrowDown, Minus, History, GitCompare } from "lucide-react";
import { toast } from "sonner";
import api from "@/api/client";
import { useTenant } from "@/contexts/TenantContext";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const PERIODS = [
  { key: "weekly", label: "Weekly" },
  { key: "monthly", label: "Monthly" },
  { key: "quarterly", label: "Quarterly" },
];

// label + whether an increase is good, and the value suffix
const KPI_META = {
  incidents: { label: "Incidents", up: false, suffix: "" },
  sla_compliance: { label: "SLA Compliance", up: true, suffix: "%" },
  mttr_hours: { label: "MTTR", up: false, suffix: "h" },
  automation_rate: { label: "Automation Rate", up: true, suffix: "%" },
  risk_score: { label: "Risk Score", up: false, suffix: "" },
  health_score: { label: "Health Score", up: true, suffix: "" },
  false_positive_rate: { label: "False Positive Rate", up: false, suffix: "%" },
  advisories: { label: "TI Advisories", up: false, suffix: "" },
  mitre_coverage: { label: "MITRE Coverage", up: true, suffix: "%" },
  detection_coverage: { label: "Detection Coverage", up: true, suffix: "%" },
  quality_score: { label: "Quality Score", up: true, suffix: "" },
  rules_triggered: { label: "Rules Triggered", up: true, suffix: "" },
  total_rules: { label: "Total Rules", up: true, suffix: "" },
};

const fmtDate = (s) => (s ? new Date(s).toLocaleString() : "—");

function DeltaBadge({ meta, delta, pct }) {
  if (delta === null || delta === undefined) {
    return <Badge variant="outline" className="text-[10px] text-muted-foreground">baseline</Badge>;
  }
  const flat = delta === 0;
  const good = flat ? null : (delta > 0) === meta.up;
  const Icon = flat ? Minus : delta > 0 ? ArrowUp : ArrowDown;
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-semibold",
      flat ? "text-muted-foreground" : good ? "text-emerald-500" : "text-rose-500")}>
      <Icon className="h-3.5 w-3.5" />
      {delta > 0 ? "+" : ""}{delta}{meta.suffix}
      {pct !== null && pct !== undefined ? ` (${pct > 0 ? "+" : ""}${pct}%)` : ""}
    </span>
  );
}

function ComparisonPanel({ period }) {
  const { tenantId, tenant } = useTenant();
  const qc = useQueryClient();

  const compareKey = ["compare", period, tenantId];
  const listKey = ["snapshots", period, tenantId];

  const { data: cmp, isLoading } = useQuery({
    queryKey: compareKey,
    queryFn: async () => (await api.get(`/comparison/compare?period=${period}&tenant_id=${tenantId}`)).data,
  });
  const { data: history = [] } = useQuery({
    queryKey: listKey,
    queryFn: async () => (await api.get(`/comparison/snapshots?period=${period}&tenant_id=${tenantId}`)).data,
  });

  const snap = useMutation({
    mutationFn: async () => (await api.post(`/comparison/snapshot?period=${period}&tenant_id=${tenantId}`)).data,
    onSuccess: () => {
      toast.success(`${period[0].toUpperCase() + period.slice(1)} snapshot captured for ${tenant?.name || "All Tenants"}`);
      qc.invalidateQueries({ queryKey: compareKey });
      qc.invalidateQueries({ queryKey: listKey });
    },
    onError: () => toast.error("Failed to capture snapshot"),
  });

  const del = useMutation({
    mutationFn: async (id) => (await api.delete(`/comparison/snapshot/${id}`)).data,
    onSuccess: () => {
      toast.success("Snapshot deleted");
      qc.invalidateQueries({ queryKey: compareKey });
      qc.invalidateQueries({ queryKey: listKey });
    },
  });

  const hasCurrent = cmp && cmp.current;
  const hasPrev = cmp && cmp.previous;
  const deltas = cmp?.deltas || {};

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-muted-foreground">
          Capture a snapshot of the whole dashboard now; each new snapshot is auto-compared with the previous {period} one.
        </div>
        <Button onClick={() => snap.mutate()} disabled={snap.isPending} className="gap-2" data-testid={`snapshot-btn-${period}`}>
          <Camera className="h-4 w-4" /> {snap.isPending ? "Capturing…" : "Take Snapshot"}
        </Button>
      </div>

      {isLoading && <div className="text-sm text-muted-foreground">Loading…</div>}

      {!isLoading && !hasCurrent && (
        <div className="rounded-xl border-2 border-dashed border-border/60 p-10 text-center bg-card/40" data-testid={`compare-empty-${period}`}>
          <GitCompare className="h-8 w-8 mx-auto text-muted-foreground mb-2" />
          <h3 className="text-lg font-semibold">No {period} snapshots yet</h3>
          <p className="text-sm text-muted-foreground mt-1">Take your first snapshot to start tracking {period} changes.</p>
        </div>
      )}

      {hasCurrent && (
        <>
          <Card className="p-4" data-testid={`compare-summary-${period}`}>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
              <span className="font-semibold flex items-center gap-2"><GitCompare className="h-4 w-4 text-primary" /> Comparison</span>
              <span className="text-muted-foreground">Current: <b className="text-foreground">{fmtDate(cmp.current.created_at)}</b></span>
              <span className="text-muted-foreground">Previous: <b className="text-foreground">{hasPrev ? fmtDate(cmp.previous.created_at) : "— (baseline)"}</b></span>
            </div>
          </Card>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid={`compare-grid-${period}`}>
            {Object.entries(KPI_META).map(([key, meta]) => {
              const d = deltas[key] || {};
              return (
                <Card key={key} className="p-4" data-testid={`compare-kpi-${period}-${key}`}>
                  <div className="text-[11px] uppercase tracking-wide text-muted-foreground font-bold">{meta.label}</div>
                  <div className="mt-1 flex items-end justify-between">
                    <div>
                      <div className="text-2xl font-bold tabular">{d.current ?? 0}{meta.suffix}</div>
                      <div className="text-[11px] text-muted-foreground mt-0.5">was {hasPrev ? `${d.previous ?? 0}${meta.suffix}` : "—"}</div>
                    </div>
                    <DeltaBadge meta={meta} delta={d.delta} pct={d.pct} />
                  </div>
                </Card>
              );
            })}
          </div>
        </>
      )}

      <Card className="p-5">
        <div className="flex items-center gap-2 mb-3">
          <History className="h-4 w-4 text-primary" />
          <h3 className="font-semibold tracking-tight">Snapshot History</h3>
          <Badge variant="secondary" className="text-[10px]">{history.length}</Badge>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Captured</TableHead>
              <TableHead>By</TableHead>
              <TableHead className="text-right">Incidents</TableHead>
              <TableHead className="text-right">SLA %</TableHead>
              <TableHead className="text-right">MTTR</TableHead>
              <TableHead className="text-right">MITRE %</TableHead>
              <TableHead className="text-right">Rules Trig.</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {history.length === 0 && (
              <TableRow><TableCell colSpan={8} className="text-center text-sm text-muted-foreground">No snapshots captured yet.</TableCell></TableRow>
            )}
            {history.map((s, i) => (
              <TableRow key={s.id} data-testid={`history-row-${period}-${i}`}>
                <TableCell className="text-xs">{fmtDate(s.created_at)} {i === 0 && <Badge variant="outline" className="ml-1 text-[9px]">latest</Badge>}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{s.created_by}</TableCell>
                <TableCell className="text-right tabular">{s.kpis.incidents}</TableCell>
                <TableCell className="text-right tabular">{s.kpis.sla_compliance}</TableCell>
                <TableCell className="text-right tabular">{s.kpis.mttr_hours}</TableCell>
                <TableCell className="text-right tabular">{s.kpis.mitre_coverage}</TableCell>
                <TableCell className="text-right tabular">{s.kpis.rules_triggered}</TableCell>
                <TableCell className="text-right">
                  <Button variant="ghost" size="sm" onClick={() => del.mutate(s.id)} data-testid={`history-delete-${period}-${i}`}>
                    <Trash2 className="h-4 w-4 text-rose-500" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

export default function ComparisonDashboard() {
  const [tab, setTab] = useState("weekly");
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="p-6 md:p-8 pb-28 space-y-6" data-testid="comparison-page">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight" style={{ fontFamily: "var(--font-heading)" }}>
          Comparison
        </h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
          Snapshot the entire console and track how KPIs move week-over-week, month-over-month and quarter-over-quarter.
        </p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList data-testid="comparison-tabs">
          {PERIODS.map((p) => (
            <TabsTrigger key={p.key} value={p.key} data-testid={`comparison-tab-${p.key}`}>{p.label}</TabsTrigger>
          ))}
        </TabsList>
        {PERIODS.map((p) => (
          <TabsContent key={p.key} value={p.key} className="mt-6">
            <ComparisonPanel period={p.key} />
          </TabsContent>
        ))}
      </Tabs>
    </motion.div>
  );
}
