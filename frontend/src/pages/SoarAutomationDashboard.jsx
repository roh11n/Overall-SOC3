import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Bot, CheckCircle2, Cpu, PlayCircle, Wallet,
  UploadCloud, Trash2, Sparkles, TrendingUp,
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
  ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip,
  AreaChart, Area,
} from "recharts";
import { toast } from "sonner";
import api from "@/api/client";

const fadeIn = { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 } };

function EmptyState({ onUpload, tenantName }) {
  return (
    <div className="rounded-xl border-2 border-dashed border-border/60 p-10 text-center bg-card/40" data-testid="soar-empty-state">
      <div className="mx-auto h-14 w-14 rounded-full bg-primary/10 grid place-items-center mb-4">
        <UploadCloud className="h-7 w-7 text-primary" />
      </div>
      <h2 className="text-xl font-semibold tracking-tight">No XSOAR playbook data uploaded</h2>
      <p className="text-sm text-muted-foreground mt-2 max-w-xl mx-auto">
        Upload an XSOAR incident export for <span className="font-semibold text-foreground">{tenantName}</span> to see live playbook health, automation ROI and hours saved.
      </p>
      <Button className="mt-5 gap-2" onClick={onUpload} data-testid="soar-empty-upload-btn">
        <UploadCloud className="h-4 w-4" /> Upload XSOAR File
      </Button>
    </div>
  );
}

export default function SoarAutomationDashboard() {
  const { tenantId, tenant } = useTenant();
  const [uploadOpen, setUploadOpen] = useState(false);
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["soar", tenantId],
    queryFn: async () => (await api.get(`/dashboard/soar-automation?tenant_id=${tenantId || "all"}`)).data,
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
    <motion.div {...fadeIn} className="p-6 md:p-8 space-y-6" data-testid="soar-page">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold">Persona</div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mt-1" style={{ fontFamily: "var(--font-heading)" }}>
            SOAR · Automation
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Playbook health, automation ROI and hours saved — computed live from your XSOAR feed.
          </p>
          {data?.upload && (
            <div className="mt-3 flex items-center gap-2 text-[11px]" data-testid="soar-data-source-chip">
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
          <Button variant="outline" size="sm" onClick={() => setUploadOpen(true)} data-testid="soar-upload-btn" className="gap-2">
            <UploadCloud className="h-4 w-4" /> {hasData ? "Re-upload" : "Upload"} XSOAR
          </Button>
          {hasData && (
            <Button variant="ghost" size="sm" onClick={clearData} data-testid="soar-clear-btn" className="gap-2 text-rose-500 hover:text-rose-600">
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
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard label="Automation Rate" value={data.health.automation_rate} suffix="%" icon={Bot} testid="kpi-auto-rate" />
            <KpiCard label="Success Rate" value={data.health.success_rate} suffix="%" icon={CheckCircle2} testid="kpi-success" />
            <KpiCard label="Playbooks Executed" value={data.health.playbooks_executed.toLocaleString()} icon={PlayCircle} testid="kpi-execs" />
            <KpiCard label="Unique Playbooks" value={data.health.unique_playbooks} icon={PlayCircle} testid="kpi-unique-pb" />
            <KpiCard label="Failed Automations" value={data.health.failed_automations} intent="negative" testid="kpi-failed" />
            <KpiCard label="Auto Closures" value={data.efficiency.auto_closures} icon={CheckCircle2} testid="kpi-auto-close" />
            <KpiCard label="Manual Closures" value={data.efficiency.manual_closures} intent="negative" testid="kpi-manual-close" />
            <KpiCard label="Hours Saved" value={data.efficiency.hours_saved.toLocaleString()} icon={Cpu} testid="kpi-hours-saved" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ChartCard title="Automation Rate Trend" subtitle="Daily auto-close %" testid="chart-auto-trend" action={<TrendingUp className="h-4 w-4 text-muted-foreground" />}>
              <div className="h-64">
                {data.automation_trend.length === 0 ? (
                  <div className="h-full grid place-items-center text-sm text-muted-foreground">No trend data</div>
                ) : (
                  <ResponsiveContainer>
                    <LineChart data={data.automation_trend}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                      <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={10} interval="preserveStartEnd" />
                      <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} />
                      <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                      <Line type="monotone" dataKey="value" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </ChartCard>

            <ChartCard title="Playbook Executions" subtitle="Volume over time" testid="chart-execs">
              <div className="h-64">
                {data.executions_timeline.length === 0 ? (
                  <div className="h-full grid place-items-center text-sm text-muted-foreground">No executions yet</div>
                ) : (
                  <ResponsiveContainer>
                    <AreaChart data={data.executions_timeline}>
                      <defs>
                        <linearGradient id="execFill" x1="0" x2="0" y1="0" y2="1">
                          <stop offset="0%" stopColor="hsl(var(--chart-4))" stopOpacity={0.5} />
                          <stop offset="100%" stopColor="hsl(var(--chart-4))" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                      <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={10} interval="preserveStartEnd" />
                      <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} allowDecimals={false} />
                      <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                      <Area type="monotone" dataKey="value" stroke="hsl(var(--chart-4))" strokeWidth={2} fill="url(#execFill)" />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </div>
            </ChartCard>
          </div>

          <ChartCard title="Playbook Performance" subtitle={`Baseline manual time: ${data.health.avg_manual_min_baseline} min/incident`} testid="table-playbooks" action={<Wallet className="h-4 w-4 text-muted-foreground" />}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Playbook</TableHead>
                  <TableHead className="text-right">Executions</TableHead>
                  <TableHead className="text-right">Closed</TableHead>
                  <TableHead className="text-right">Auto-Closed</TableHead>
                  <TableHead className="text-right">Success %</TableHead>
                  <TableHead className="text-right">Auto-Close %</TableHead>
                  <TableHead className="text-right">Avg Runtime</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.playbooks.length === 0 ? (
                  <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground text-sm">No playbook data</TableCell></TableRow>
                ) : data.playbooks.map((p, i) => (
                  <TableRow key={p.name + i}>
                    <TableCell className="font-medium max-w-[380px]"><div className="truncate" title={p.name}>{p.name}</div></TableCell>
                    <TableCell className="text-right tabular">{p.executions}</TableCell>
                    <TableCell className="text-right tabular">{p.closed}</TableCell>
                    <TableCell className="text-right tabular">{p.auto_closed}</TableCell>
                    <TableCell className="text-right">
                      <Badge variant={p.success_rate >= 95 ? "default" : p.success_rate >= 85 ? "secondary" : "destructive"} className="text-[10px]">
                        {p.success_rate}%
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right tabular text-xs">{p.auto_close_rate}%</TableCell>
                    <TableCell className="text-right tabular text-xs">{p.avg_runtime_sec}s</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ChartCard>
        </>
      )}

      <UploadModal open={uploadOpen} onOpenChange={setUploadOpen} />
    </motion.div>
  );
}
