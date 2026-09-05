import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  ShieldAlert, Timer, Zap, Users2, UploadCloud, Trash2, Sparkles,
  AlertOctagon, CheckCircle2, XCircle, Layers,
} from "lucide-react";
import KpiCard from "@/components/KpiCard";
import ChartCard from "@/components/ChartCard";
import ExportActions from "@/components/ExportActions";
import UploadModal from "@/components/UploadModal";
import { useTenant } from "@/contexts/TenantContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  ResponsiveContainer, BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip,
  PieChart, Pie, Cell, Legend, LineChart, Line,
} from "recharts";
import { toast } from "sonner";
import api from "@/api/client";

const fadeIn = { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 } };
const SEV_COLORS = { Critical: "#ef4444", High: "#f59e0b", Medium: "#3b82f6", Low: "#10b981", Informational: "#64748b", Unknown: "#94a3b8" };
const CR_COLORS = ["#10b981", "#ef4444", "#f59e0b", "#3b82f6", "#8b5cf6", "#64748b"];

function EmptyState({ onUpload, tenantName }) {
  return (
    <div className="rounded-xl border-2 border-dashed border-border/60 p-10 text-center bg-card/40" data-testid="soc-empty-state">
      <div className="mx-auto h-14 w-14 rounded-full bg-primary/10 grid place-items-center mb-4">
        <UploadCloud className="h-7 w-7 text-primary" />
      </div>
      <h2 className="text-xl font-semibold tracking-tight">No XSOAR incident data uploaded</h2>
      <p className="text-sm text-muted-foreground mt-2 max-w-xl mx-auto">
        Upload an XSOAR incident export (CSV / XLSX) for <span className="font-semibold text-foreground">{tenantName}</span>.
        Expected columns include:&nbsp;
        <span className="font-mono text-[11px]">id, name, severity, owner, playbookId, occurred, closed, closeReason, Rule Name, MITRE Tactic Name, SLA Breached, Auto Close</span>.
      </p>
      <Button className="mt-5 gap-2" onClick={onUpload} data-testid="soc-empty-upload-btn">
        <UploadCloud className="h-4 w-4" /> Upload XSOAR File
      </Button>
    </div>
  );
}

export default function SocManagerDashboard() {
  const { tenantId, tenant } = useTenant();
  const [uploadOpen, setUploadOpen] = useState(false);
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["soc-manager", tenantId],
    queryFn: async () => (await api.get(`/dashboard/soc-manager?tenant_id=${tenantId || "all"}`)).data,
    keepPreviousData: true,
  });

  const clearData = async () => {
    if (!window.confirm(`Delete all uploaded XSOAR data for ${tenant?.name || "this tenant"}?`)) return;
    try {
      await api.delete(`/dashboard/soc-manager/data?tenant_id=${tenantId || "all"}`);
      toast.success("XSOAR data cleared");
      qc.invalidateQueries();
    } catch { toast.error("Clear failed"); }
  };

  const hasData = data?.data_status === "live";

  return (
    <motion.div {...fadeIn} className="p-6 md:p-8 space-y-6" data-testid="soc-manager-page">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold">Persona</div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mt-1" style={{ fontFamily: "var(--font-heading)" }}>
            SOC Manager · Operations
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Live incident operations, SLA and analyst load driven by your XSOAR feed.
          </p>
          {data?.upload && (
            <div className="mt-3 flex items-center gap-2 text-[11px]" data-testid="soc-data-source-chip">
              <Badge variant="outline" className="gap-1 border-emerald-500/40 text-emerald-500">
                <Sparkles className="h-3 w-3" /> LIVE FROM XSOAR
              </Badge>
              <span className="text-muted-foreground truncate">
                <span className="font-medium text-foreground">{data.upload.filename}</span>
                &nbsp;· {data.upload.row_count?.toLocaleString()} incidents · {data.upload.uploaded_at?.slice(0, 10)}
              </span>
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setUploadOpen(true)} data-testid="soc-upload-btn" className="gap-2">
            <UploadCloud className="h-4 w-4" /> {hasData ? "Re-upload" : "Upload"} XSOAR
          </Button>
          {hasData && (
            <Button variant="ghost" size="sm" onClick={clearData} data-testid="soc-clear-btn" className="gap-2 text-rose-500 hover:text-rose-600">
              <Trash2 className="h-4 w-4" /> Clear
            </Button>
          )}
          <ExportActions period="monthly" />
        </div>
      </div>

      {isLoading && !data && <div className="text-sm text-muted-foreground">Loading…</div>}
      {data && data.data_status === "empty" && (
        <EmptyState onUpload={() => setUploadOpen(true)} tenantName={tenant?.name || "All Tenants"} />
      )}

      {hasData && (
        <>
          {/* Summary KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <KpiCard label="Total Incidents" value={data.summary.total_incidents.toLocaleString()} icon={ShieldAlert} testid="kpi-total-incidents" />
            <KpiCard label="Closed" value={data.summary.closed.toLocaleString()} icon={CheckCircle2} testid="kpi-closed" />
            <KpiCard label="Open Backlog" value={data.summary.backlog_open.toLocaleString()} icon={Layers} intent="negative" testid="kpi-open" />
            <KpiCard label="MTTR" value={data.summary.mttr_hours} suffix="h" icon={Timer} intent="negative" testid="kpi-mttr" />
            <KpiCard label="MTTD" value={data.summary.mttd_minutes} suffix="m" icon={Timer} intent="negative" testid="kpi-mttd" />
            <KpiCard label="SLA Compliance" value={data.summary.sla_compliance_pct} suffix="%" testid="kpi-sla" />
            <KpiCard label="False Positive Rate" value={data.summary.false_positive_rate} suffix="%" icon={XCircle} intent="negative" testid="kpi-fp" />
            <KpiCard label="True Positive Rate" value={data.summary.true_positive_rate} suffix="%" icon={CheckCircle2} testid="kpi-tp" />
            <KpiCard label="SLA Breach Rate" value={data.summary.sla_breach_rate} suffix="%" icon={AlertOctagon} intent="negative" testid="kpi-breach" />
            <KpiCard label="Avg Handling Time" value={data.summary.avg_time_taken_min} suffix="m" testid="kpi-aht" />
            <KpiCard label="Backlog Aging" value={data.summary.backlog_aging_hours} suffix="h" intent="negative" testid="kpi-aging" />
          </div>

          {/* Incidents timeline + Severity + Close-reason */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <ChartCard title="Incident Volume" subtitle="Occurrences over time" testid="chart-inc-vol" className="lg:col-span-2">
              <div className="h-64">
                {data.incidents_timeline.length === 0 ? (
                  <div className="h-full grid place-items-center text-sm text-muted-foreground">No dated incidents</div>
                ) : (
                  <ResponsiveContainer>
                    <LineChart data={data.incidents_timeline}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                      <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={10} interval="preserveStartEnd" />
                      <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} allowDecimals={false} />
                      <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                      <Line type="monotone" dataKey="value" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </ChartCard>

            <ChartCard title="Severity Mix" testid="chart-severity">
              <div className="h-64">
                <ResponsiveContainer>
                  <PieChart>
                    <Pie data={data.severity_distribution} dataKey="count" nameKey="severity" innerRadius={50} outerRadius={85} paddingAngle={2}>
                      {data.severity_distribution.map((e) => <Cell key={e.severity} fill={SEV_COLORS[e.severity] || "#94a3b8"} />)}
                    </Pie>
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          </div>

          {/* Close reasons + MTTR trend */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <ChartCard title="Close Reasons" subtitle="Resolution mix" testid="chart-close-reasons">
              <div className="h-64">
                {data.close_reason_mix.length === 0 ? (
                  <div className="h-full grid place-items-center text-sm text-muted-foreground">No closed incidents</div>
                ) : (
                  <ResponsiveContainer>
                    <PieChart>
                      <Pie data={data.close_reason_mix} dataKey="count" nameKey="reason" innerRadius={40} outerRadius={80} paddingAngle={2}>
                        {data.close_reason_mix.map((_, i) => <Cell key={i} fill={CR_COLORS[i % CR_COLORS.length]} />)}
                      </Pie>
                      <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                      <Legend wrapperStyle={{ fontSize: 10 }} />
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </div>
            </ChartCard>

            <ChartCard title="MTTR Trend" subtitle="Avg hours to resolve per day" testid="chart-mttr-trend" className="lg:col-span-2">
              <div className="h-64">
                {data.mttr_trend.length === 0 ? (
                  <div className="h-full grid place-items-center text-sm text-muted-foreground">No resolved incidents in range</div>
                ) : (
                  <ResponsiveContainer>
                    <LineChart data={data.mttr_trend}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                      <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={10} interval="preserveStartEnd" />
                      <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} />
                      <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                      <Line type="monotone" dataKey="value" stroke="hsl(var(--chart-2))" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </ChartCard>
          </div>

          {/* Top rules + Noisy rules */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ChartCard title="Top Rules by Volume" subtitle="Most frequent triggers" testid="chart-top-rules" action={<Zap className="h-4 w-4 text-muted-foreground" />}>
              <div className="h-72">
                <ResponsiveContainer>
                  <BarChart data={data.top_rules} layout="vertical" margin={{ left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                    <XAxis type="number" stroke="hsl(var(--muted-foreground))" fontSize={10} />
                    <YAxis type="category" dataKey="rule" stroke="hsl(var(--muted-foreground))" fontSize={9} width={200} />
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                    <Bar dataKey="triggers" fill="hsl(var(--chart-1))" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>

            <ChartCard title="Noisiest Rules" subtitle="Highest false-positive rate (≥3 incidents)" testid="table-noisy-rules">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Rule</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                    <TableHead className="text-right">FP</TableHead>
                    <TableHead className="text-right">FP %</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.noisy_rules.length === 0 ? (
                    <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground text-sm">Not enough data</TableCell></TableRow>
                  ) : data.noisy_rules.map((r, i) => (
                    <TableRow key={i}>
                      <TableCell className="text-xs font-medium max-w-[280px]"><div className="truncate" title={r.rule}>{r.rule}</div></TableCell>
                      <TableCell className="text-right tabular text-xs">{r.total}</TableCell>
                      <TableCell className="text-right tabular text-xs">{r.fp}</TableCell>
                      <TableCell className="text-right">
                        <Badge variant={r.fp_pct >= 80 ? "destructive" : r.fp_pct >= 50 ? "secondary" : "outline"} className="text-[10px]">
                          {r.fp_pct}%
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </ChartCard>
          </div>

          {/* Categories + Analyst load */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ChartCard title="Incident Categories" testid="chart-categories">
              <div className="h-64">
                {data.categories.length === 0 ? (
                  <div className="h-full grid place-items-center text-sm text-muted-foreground">No categories</div>
                ) : (
                  <ResponsiveContainer>
                    <BarChart data={data.categories}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                      <XAxis dataKey="category" stroke="hsl(var(--muted-foreground))" fontSize={9} angle={-15} textAnchor="end" height={70} />
                      <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} allowDecimals={false} />
                      <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                      <Bar dataKey="count" fill="hsl(var(--chart-3))" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </ChartCard>

            <ChartCard title="Analyst Load" subtitle="Incidents per owner" testid="table-analyst-load" action={<Users2 className="h-4 w-4 text-muted-foreground" />}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Analyst</TableHead>
                    <TableHead className="text-right">Incidents</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.analyst_load.length === 0 ? (
                    <TableRow><TableCell colSpan={2} className="text-center text-muted-foreground text-sm">No owner data</TableCell></TableRow>
                  ) : data.analyst_load.map((a) => (
                    <TableRow key={a.analyst}>
                      <TableCell className="font-medium">{a.analyst}</TableCell>
                      <TableCell className="text-right tabular">{a.incidents}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </ChartCard>
          </div>
        </>
      )}

      <UploadModal open={uploadOpen} onOpenChange={setUploadOpen} />
    </motion.div>
  );
}
