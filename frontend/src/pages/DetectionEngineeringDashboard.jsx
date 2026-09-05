import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Crosshair, GitBranch, Target, TrendingDown, Upload } from "lucide-react";
import KpiCard from "@/components/KpiCard";
import ChartCard from "@/components/ChartCard";
import TimeTabs from "@/components/TimeTabs";
import ExportActions from "@/components/ExportActions";
import UploadModal from "@/components/UploadModal";
import { Button } from "@/components/ui/button";
import { useTenant } from "@/contexts/TenantContext";
import MitreHeatmap from "@/components/MitreHeatmap";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import api from "@/api/client";
import { cn } from "@/lib/utils";

const fadeIn = { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 } };

const PALETTE = ["#3B82F6", "#8B5CF6", "#10B981", "#F59E0B", "#EF4444", "#06B6D4"];
const PRIORITY_COLORS = { Essential: "#10B981", Selective: "#3B82F6", Redundant: "#F59E0B", Undefined: "#94A3B8" };
const BAND_LABEL = { above_avg: "Above avg", near_avg: "Near avg", below_avg: "Below avg", not_triggered: "Not triggered" };
const BAND_STYLE = {
  above_avg: "border-rose-500/40 text-rose-500",
  near_avg: "border-amber-500/40 text-amber-500",
  below_avg: "border-sky-500/40 text-sky-500",
  not_triggered: "border-slate-500/40 text-muted-foreground",
};

function StatChip({ label, value, tone, testid }) {
  const tones = {
    emerald: "text-emerald-500", rose: "text-rose-500", amber: "text-amber-500", slate: "text-muted-foreground",
  };
  return (
    <div className="rounded-lg border border-border/60 bg-card/40 px-3 py-2" data-testid={testid}>
      <div className={cn("text-2xl font-bold tabular", tones[tone])}>{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
    </div>
  );
}

function DashEmpty() {
  return (
    <div className="rounded-xl border-2 border-dashed border-border/60 p-10 text-center bg-card/40" data-testid="detection-empty-state">
      <h2 className="text-xl font-semibold tracking-tight">No live detection data for this tenant yet</h2>
      <p className="text-sm text-muted-foreground mt-2 max-w-xl mx-auto">
        Upload a <span className="font-semibold text-foreground">Rule Catalog</span> (MITRE coverage + rule effectiveness),
        an <span className="font-semibold text-foreground">XSOAR</span> export (rule triggers), and/or a
        <span className="font-semibold text-foreground"> Log Validation</span> file (priority pie) via the Upload button.
      </p>
    </div>
  );
}

export default function DetectionEngineeringDashboard() {
  const [period, setPeriod] = useState("monthly");
  const [uploadOpen, setUploadOpen] = useState(false);
  const { tenantId } = useTenant();
  const { data, isLoading } = useQuery({
    queryKey: ["det-eng", period, tenantId],
    queryFn: async () => (await api.get(`/dashboard/detection-engineering?period=${period}&tenant_id=${tenantId || "all"}`)).data,
    keepPreviousData: true,
  });

  return (
    <motion.div {...fadeIn} className="p-6 md:p-8 space-y-6" data-testid="detection-page">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold">Persona</div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mt-1" style={{ fontFamily: "var(--font-heading)" }}>
            Detection Engineering
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Detection quality, rule effectiveness and MITRE ATT&CK coverage.
          </p>
          {data?.xsoar_live && (
            <Badge variant="outline" className="mt-2 gap-1.5" data-testid="det-xsoar-live">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Live · XSOAR{data.xsoar_upload?.filename ? ` · ${data.xsoar_upload.filename}` : ""}
            </Badge>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="outline" size="sm" className="gap-2" onClick={() => setUploadOpen(true)} data-testid="det-upload-btn">
            <Upload className="h-4 w-4" /> Upload
          </Button>
          <ExportActions period={period} />
          <TimeTabs value={period} onChange={setPeriod} />
        </div>
      </div>

      <UploadModal open={uploadOpen} onOpenChange={setUploadOpen} />

      {isLoading && <div className="text-sm text-muted-foreground">Loading…</div>}
      {data && data.data_status !== "live" && <DashEmpty />}
      {data && data.data_status === "live" && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <KpiCard label="Detection Coverage" value={data.quality.detection_coverage} suffix="%" icon={Target} delta={2.4} testid="kpi-detection-cov" />
            <KpiCard label="Use Case Coverage" value={data.quality.use_case_coverage} suffix="%" delta={1.1} testid="kpi-usecase-cov" />
            <KpiCard label="MITRE Coverage" value={data.quality.mitre_coverage} suffix="%" testid="kpi-mitre-cov" />
            <KpiCard label="ATLAS Coverage" value={data.quality.atlas_coverage ?? "N/A"} suffix={data.quality.atlas_coverage == null ? "" : "%"} testid="kpi-atlas" />
            <KpiCard label="Quality Score" value={data.quality.quality_score} testid="kpi-quality-score" />
          </div>

          <ChartCard
            title="MITRE ATT&CK Coverage Heatmap"
            subtitle="Tactics × Techniques"
            testid="chart-mitre-heatmap"
            action={<Badge variant="outline">{data.gap_analysis.techniques_covered} / {data.gap_analysis.techniques_covered + data.gap_analysis.techniques_missing} techniques</Badge>}
          >
            <MitreHeatmap data={data.mitre_heatmap} />
          </ChartCard>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <ChartCard title="Detection Gap Analysis" subtitle="TI + QRadar" testid="chart-gaps" action={<Crosshair className="h-4 w-4 text-muted-foreground" />}>
              <div className="space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Techniques Covered</span>
                  <span className="font-semibold tabular">{data.gap_analysis.techniques_covered}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Techniques Missing</span>
                  <span className="font-semibold tabular text-rose-500">{data.gap_analysis.techniques_missing}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">ATLAS Covered</span>
                  <span className="font-semibold tabular">{data.gap_analysis.atlas_covered}</span>
                </div>
                <div className="pt-3 border-t border-border/60">
                  <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold mb-2">
                    New Detection Opportunities
                  </div>
                  <ul className="space-y-1.5 text-xs">
                    {data.gap_analysis.new_opportunities.map((o) => (
                      <li key={o} className="flex items-start gap-2">
                        <span className="mt-1 h-1 w-1 rounded-full bg-primary shrink-0" />
                        <span>{o}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </ChartCard>

            <ChartCard title="Detection Trends" subtitle="Rules · FP · Coverage" className="lg:col-span-2" testid="chart-det-trends" action={<GitBranch className="h-4 w-4 text-muted-foreground" />}>
              <div className="h-64">
                <ResponsiveContainer>
                  <LineChart>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                    <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={11} allowDuplicatedCategory={false} type="category" />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} />
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                    <Line data={data.trends.new_rules} type="monotone" dataKey="value" name="New Rules" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={false} />
                    <Line data={data.trends.rules_tuned} type="monotone" dataKey="value" name="Rules Tuned" stroke="hsl(var(--chart-2))" strokeWidth={2} dot={false} />
                    <Line data={data.trends.fp_reduction} type="monotone" dataKey="value" name="FP %" stroke="hsl(var(--chart-5))" strokeWidth={2} dot={false} />
                    <Line data={data.trends.coverage_qoq} type="monotone" dataKey="value" name="Coverage %" stroke="hsl(var(--chart-4))" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                <Badge variant="outline"><span className="h-2 w-2 rounded-full bg-blue-500 mr-1.5" /> New Rules</Badge>
                <Badge variant="outline"><span className="h-2 w-2 rounded-full bg-emerald-500 mr-1.5" /> Tuned</Badge>
                <Badge variant="outline"><span className="h-2 w-2 rounded-full bg-rose-500 mr-1.5" /> FP</Badge>
                <Badge variant="outline"><span className="h-2 w-2 rounded-full bg-violet-500 mr-1.5" /> Coverage</Badge>
              </div>
            </ChartCard>
          </div>

          {data.priority_breakdown && (
            <ChartCard title="Log Source Priority" subtitle={`Log validation · ${data.logval_total} sources`} testid="chart-log-priority">
              <div className="h-[300px]" data-testid="log-priority-pie">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={data.priority_breakdown} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} label={(e) => `${e.name}: ${e.value}`}>
                      {data.priority_breakdown.map((entry, i) => (
                        <Cell key={entry.name} fill={PRIORITY_COLORS[entry.name] || PALETTE[i % PALETTE.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          )}

          {data.rule_effectiveness ? (
            <ChartCard
              title="Rule Effectiveness"
              subtitle={`${data.rule_effectiveness.total_rules} rules · avg ${data.rule_effectiveness.avg_triggers} triggers`}
              testid="table-rules"
            >
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <StatChip label="Triggered" value={data.rule_effectiveness.triggered_rules} tone="emerald" testid="re-triggered" />
                <StatChip label="Above Avg" value={data.rule_effectiveness.bands.above_avg} tone="rose" testid="re-above" />
                <StatChip label="Near Avg" value={data.rule_effectiveness.bands.near_avg} tone="amber" testid="re-near" />
                <StatChip label="Not Triggered" value={data.rule_effectiveness.not_triggered_rules} tone="slate" testid="re-nottriggered" />
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Rule</TableHead>
                    <TableHead>Rule ID</TableHead>
                    <TableHead className="text-right">Triggers</TableHead>
                    <TableHead>Vs Avg</TableHead>
                    <TableHead>ATT&CK Tactics</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.rule_effectiveness.rules.map((r, i) => (
                    <TableRow key={`${r.rule_id}-${i}`} data-testid={`re-row-${i}`}>
                      <TableCell className="font-medium max-w-[340px] truncate">{r.name}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{r.rule_id}</TableCell>
                      <TableCell className="text-right tabular">{r.triggers}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={cn("text-[10px]", BAND_STYLE[r.band])}>{BAND_LABEL[r.band]}</Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground truncate max-w-[220px]">{(r.tactics || []).join(", ") || "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </ChartCard>
          ) : (
          <ChartCard title="Rule Effectiveness" subtitle="Precision · Recall · FP" testid="table-rules">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Rule</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Triggers</TableHead>
                  <TableHead className="text-right">TP</TableHead>
                  <TableHead className="text-right">FP %</TableHead>
                  <TableHead className="text-right">Precision</TableHead>
                  <TableHead className="text-right">Recall</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.rules.map((r) => (
                  <TableRow key={r.name}>
                    <TableCell className="font-medium">{r.name}</TableCell>
                    <TableCell>
                      <Badge variant={r.status === "active" ? "default" : r.status === "tuning" ? "secondary" : "outline"} className="text-[10px]">
                        {r.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right tabular">{r.triggers}</TableCell>
                    <TableCell className="text-right tabular">{r.true_positives}</TableCell>
                    <TableCell className={cn("text-right tabular", r.fp_rate > 40 && "text-rose-500 font-semibold")}>
                      {r.fp_rate}%
                    </TableCell>
                    <TableCell className="text-right tabular">{r.precision}</TableCell>
                    <TableCell className="text-right tabular">{r.recall}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ChartCard>
          )}
        </>
      )}
    </motion.div>
  );
}
