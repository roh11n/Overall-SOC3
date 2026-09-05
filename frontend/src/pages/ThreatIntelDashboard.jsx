import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  AlertOctagon, Globe2, Fingerprint, Hash as HashIcon, Server,
  ShieldAlert, UploadCloud, Trash2, Sparkles, CalendarDays, Building2,
} from "lucide-react";
import KpiCard from "@/components/KpiCard";
import ChartCard from "@/components/ChartCard";
import TimeTabs from "@/components/TimeTabs";
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
const IOC_COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444", "#06b6d4"];
const HASH_COLORS = ["#0ea5e9", "#22c55e", "#eab308", "#ec4899", "#a855f7", "#64748b"];

function EmptyState({ onUpload, tenantName }) {
  return (
    <div
      className="rounded-xl border-2 border-dashed border-border/60 p-10 text-center bg-card/40"
      data-testid="ti-empty-state"
    >
      <div className="mx-auto h-14 w-14 rounded-full bg-primary/10 grid place-items-center mb-4">
        <UploadCloud className="h-7 w-7 text-primary" />
      </div>
      <h2 className="text-xl font-semibold tracking-tight">
        No threat-intel data uploaded yet
      </h2>
      <p className="text-sm text-muted-foreground mt-2 max-w-xl mx-auto">
        Upload an advisories export (CSV / XLSX) for <span className="font-semibold text-foreground">{tenantName}</span> to drive this dashboard.
        Expected columns:&nbsp;
        <span className="font-mono text-[11px]">Advisories Name, Industry, Date of Release, IPs, Domain, Hash, Hash Type</span>.
      </p>
      <Button className="mt-5 gap-2" onClick={onUpload} data-testid="ti-empty-upload-btn">
        <UploadCloud className="h-4 w-4" /> Upload Threat Intel File
      </Button>
    </div>
  );
}

export default function ThreatIntelDashboard() {
  const [period, setPeriod] = useState("monthly");
  const [uploadOpen, setUploadOpen] = useState(false);
  const { tenantId, tenant } = useTenant();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["ti", period, tenantId],
    queryFn: async () => (await api.get(`/dashboard/threat-intel?period=${period}&tenant_id=${tenantId || "all"}`)).data,
    keepPreviousData: true,
  });

  const clearData = async () => {
    if (!window.confirm(`Delete all uploaded threat-intel data for ${tenant?.name || "this tenant"}?`)) return;
    try {
      await api.delete(`/dashboard/threat-intel/data?tenant_id=${tenantId || "all"}`);
      toast.success("Threat-intel data cleared");
      qc.invalidateQueries({ queryKey: ["ti"] });
    } catch (e) {
      toast.error("Clear failed");
    }
  };

  const hasData = data?.data_status === "live";

  return (
    <motion.div {...fadeIn} className="p-6 md:p-8 space-y-6" data-testid="threat-intel-page">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold">Persona</div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mt-1" style={{ fontFamily: "var(--font-heading)" }}>
            Threat Intelligence
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Advisory-driven landscape awareness, IOC volumes and sector exposure — powered by your uploaded intel feed.
          </p>
          {data?.upload && (
            <div className="mt-3 flex items-center gap-2 text-[11px]" data-testid="ti-data-source-chip">
              <Badge variant="outline" className="gap-1 border-emerald-500/40 text-emerald-500">
                <Sparkles className="h-3 w-3" /> LIVE FROM UPLOAD
              </Badge>
              <span className="text-muted-foreground truncate">
                <span className="font-medium text-foreground">{data.upload.filename}</span>
                &nbsp;· {data.upload.row_count?.toLocaleString()} rows · {data.upload.uploaded_at?.slice(0, 10)}
              </span>
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline" size="sm"
            onClick={() => setUploadOpen(true)}
            data-testid="ti-upload-btn" className="gap-2"
          >
            <UploadCloud className="h-4 w-4" />
            {hasData ? "Re-upload" : "Upload"} Threat Intel
          </Button>
          {hasData && (
            <Button
              variant="ghost" size="sm"
              onClick={clearData}
              data-testid="ti-clear-btn"
              className="gap-2 text-rose-500 hover:text-rose-600"
            >
              <Trash2 className="h-4 w-4" /> Clear
            </Button>
          )}
          <ExportActions period={period} />
          <TimeTabs value={period} onChange={setPeriod} />
        </div>
      </div>

      {isLoading && !data && <div className="text-sm text-muted-foreground">Loading…</div>}

      {data && data.data_status === "empty" && (
        <EmptyState onUpload={() => setUploadOpen(true)} tenantName={tenant?.name || "All Tenants"} />
      )}

      {data && data.data_status === "live" && (
        <>
          {/* Summary KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <KpiCard label="Total Advisories" value={data.summary.total_advisories.toLocaleString()} icon={AlertOctagon} testid="kpi-total-advisories" />
            <KpiCard label="Total IOCs" value={data.summary.total_iocs.toLocaleString()} icon={ShieldAlert} testid="kpi-total-iocs" />
            <KpiCard label="Unique Domains" value={data.summary.unique_domains.toLocaleString()} icon={Globe2} testid="kpi-domains" />
            <KpiCard label="Unique Hashes" value={data.summary.unique_hashes.toLocaleString()} icon={HashIcon} testid="kpi-hashes" />
            <KpiCard label="Unique IPs" value={data.summary.unique_ips.toLocaleString()} icon={Server} testid="kpi-ips" />
            <KpiCard label="Industries Covered" value={data.summary.industries_covered.toLocaleString()} icon={Building2} testid="kpi-industries" />
          </div>

          {/* Row: Timeline + IOC types + Hash types */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <ChartCard
              title="Advisories Timeline"
              subtitle={data.advisories_timeline.length > 30 ? "Weekly buckets" : "Per publication day"}
              testid="chart-ti-timeline"
              action={<CalendarDays className="h-4 w-4 text-muted-foreground" />}
              className="lg:col-span-2"
            >
              <div className="h-64">
                {data.advisories_timeline.length === 0 ? (
                  <div className="h-full grid place-items-center text-sm text-muted-foreground">
                    No dated advisories in this period
                  </div>
                ) : (
                  <ResponsiveContainer>
                    <LineChart data={data.advisories_timeline}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                      <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={10} interval="preserveStartEnd" />
                      <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} allowDecimals={false} />
                      <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                      <Line type="monotone" dataKey="advisories" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </ChartCard>

            <ChartCard title="IOC Type Mix" subtitle="Unique per type" testid="chart-ioc-mix">
              <div className="h-64">
                <ResponsiveContainer>
                  <PieChart>
                    <Pie
                      data={data.ioc_type_distribution}
                      dataKey="count" nameKey="type"
                      innerRadius={50} outerRadius={85} paddingAngle={2}
                      labelLine={false}
                    >
                      {data.ioc_type_distribution.map((_, i) => (
                        <Cell key={i} fill={IOC_COLORS[i % IOC_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          </div>

          {/* Row: Industry breakdown + Hash-type breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ChartCard
              title="Sector Coverage"
              subtitle="Advisories tagged per industry (multi-tag expanded)"
              testid="chart-industries"
              action={<Building2 className="h-4 w-4 text-muted-foreground" />}
            >
              <div className="h-72">
                {data.industry_breakdown.length === 0 ? (
                  <div className="h-full grid place-items-center text-sm text-muted-foreground">
                    No industry tags found
                  </div>
                ) : (
                  <ResponsiveContainer>
                    <BarChart data={data.industry_breakdown} layout="vertical" margin={{ left: 40 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                      <XAxis type="number" stroke="hsl(var(--muted-foreground))" fontSize={11} allowDecimals={false} />
                      <YAxis type="category" dataKey="industry" stroke="hsl(var(--muted-foreground))" fontSize={10} width={150} />
                      <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                      <Bar dataKey="count" fill="hsl(var(--chart-3))" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </ChartCard>

            <ChartCard
              title="Hash Algorithm Mix"
              subtitle="Normalised across MD5 / SHA1 / SHA256 / SHA512"
              testid="chart-hash-mix"
              action={<Fingerprint className="h-4 w-4 text-muted-foreground" />}
            >
              <div className="h-72">
                {data.hash_type_breakdown.length === 0 ? (
                  <div className="h-full grid place-items-center text-sm text-muted-foreground">
                    No hash IOCs in this period
                  </div>
                ) : (
                  <ResponsiveContainer>
                    <BarChart data={data.hash_type_breakdown}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                      <XAxis dataKey="type" stroke="hsl(var(--muted-foreground))" fontSize={11} />
                      <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} allowDecimals={false} />
                      <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                      <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                        {data.hash_type_breakdown.map((_, i) => (
                          <Cell key={i} fill={HASH_COLORS[i % HASH_COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>
            </ChartCard>
          </div>

          {/* Top advisories by IOC weight */}
          <ChartCard
            title="Top Advisories by IOC Weight"
            subtitle="Ranked by unique IOC contribution across IP + Domain + Hash"
            testid="table-top-advisories"
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">#</TableHead>
                  <TableHead>Advisory</TableHead>
                  <TableHead>Industry</TableHead>
                  <TableHead>Hash Types</TableHead>
                  <TableHead className="text-right">IOCs</TableHead>
                  <TableHead className="text-right">Latest</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.top_advisories.map((a, i) => (
                  <TableRow key={a.advisory + i} data-testid={`top-advisory-${i}`}>
                    <TableCell className="text-xs text-muted-foreground">{String(i + 1).padStart(2, "0")}</TableCell>
                    <TableCell className="font-medium max-w-[380px]">
                      <div className="truncate" title={a.advisory}>{a.advisory}</div>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {a.industry || <span className="opacity-40">—</span>}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1 flex-wrap">
                        {(a.hash_types || []).map((h) => (
                          <Badge key={h} variant="secondary" className="text-[10px]">{h}</Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-mono font-semibold tabular-nums">{a.iocs}</TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground tabular-nums">
                      {a.date || "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ChartCard>

          {/* Recent advisories */}
          <ChartCard
            title="Recent Advisories"
            subtitle="Newest 10 unique advisories in this period"
            testid="table-recent-advisories"
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Advisory</TableHead>
                  <TableHead>Industry</TableHead>
                  <TableHead>Hash Type</TableHead>
                  <TableHead>First IOC</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.recent_advisories.map((a, i) => (
                  <TableRow key={a.advisory + i} data-testid={`recent-advisory-${i}`}>
                    <TableCell className="text-xs text-muted-foreground tabular-nums whitespace-nowrap">{a.date || "—"}</TableCell>
                    <TableCell className="font-medium max-w-[420px]">
                      <div className="truncate" title={a.advisory}>{a.advisory}</div>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {a.industry || <span className="opacity-40">—</span>}
                    </TableCell>
                    <TableCell>
                      {a.hash_type
                        ? <Badge variant="outline" className="text-[10px]">{a.hash_type}</Badge>
                        : <span className="opacity-40">—</span>}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] text-muted-foreground max-w-[240px]">
                      <div className="truncate" title={a.first_ioc}>{a.first_ioc}</div>
                    </TableCell>
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
