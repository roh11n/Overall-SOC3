import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Activity, ShieldAlert, Timer, Percent, Radar, Bot, FileText, Skull, Server, Sparkles, Brain,
} from "lucide-react";
import KpiCard from "@/components/KpiCard";
import ChartCard from "@/components/ChartCard";
import TimeTabs from "@/components/TimeTabs";
import ExportActions from "@/components/ExportActions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";
import {
  ResponsiveContainer, AreaChart, Area, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip,
  RadialBarChart, RadialBar, PolarAngleAxis,
} from "recharts";
import api from "@/api/client";
import { cn } from "@/lib/utils";
import { useTenant } from "@/contexts/TenantContext";

const fadeIn = { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 } };

function Gauge({ value, label, color = "hsl(var(--primary))", testid }) {
  return (
    <div className="relative flex flex-col items-center" data-testid={testid}>
      <div className="h-40 w-40">
        <ResponsiveContainer>
          <RadialBarChart innerRadius="70%" outerRadius="100%" data={[{ value }]} startAngle={90} endAngle={-270}>
            <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
            <RadialBar dataKey="value" cornerRadius={20} fill={color} background={{ fill: "hsl(var(--muted))" }} />
          </RadialBarChart>
        </ResponsiveContainer>
      </div>
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <div className="text-3xl font-bold tabular" style={{ fontFamily: "var(--font-heading)" }}>
          {value}
        </div>
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold mt-1">
          {label}
        </div>
      </div>
    </div>
  );
}

function RecPanel({ recs, onEnrich, aiLoading, aiEnriched }) {
  const priColor = {
    P1: "bg-rose-500/15 text-rose-500 border-rose-500/40",
    P2: "bg-amber-500/15 text-amber-500 border-amber-500/40",
    P3: "bg-primary/15 text-primary border-primary/40",
    P4: "bg-emerald-500/15 text-emerald-500 border-emerald-500/40",
  };
  return (
    <div className="rounded-xl ai-glow p-[1px]" data-testid="ai-recommendations">
      <div className="rounded-[11px] bg-card p-6">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <div className="text-[10px] uppercase tracking-[0.2em] font-bold text-muted-foreground">
              AI Executive Recommendations
            </div>
            {aiEnriched && (
              <Badge variant="default" className="text-[9px] gap-1">
                <Brain className="h-2.5 w-2.5" /> HF LLM
              </Badge>
            )}
          </div>
          <Button
            size="sm"
            variant={aiEnriched ? "outline" : "default"}
            onClick={onEnrich}
            disabled={aiLoading}
            className="gap-1.5 h-7 text-[11px]"
            data-testid="enrich-llm-btn"
          >
            <Brain className="h-3 w-3" />
            {aiLoading ? "Reasoning…" : aiEnriched ? "Regenerate with LLM" : "Deep reasoning (HF LLM)"}
          </Button>
        </div>
        <h3 className="text-xl font-bold tracking-tight mb-4" style={{ fontFamily: "var(--font-heading)" }}>
          What leadership should act on this cycle
        </h3>
        <div className="grid md:grid-cols-2 gap-3">
          {recs?.map((r, i) => (
            <div key={i} className="rounded-lg border border-border/60 p-4 hover:border-primary/40 transition-colors" data-testid={`rec-item-${i}`}>
              <div className="flex items-center gap-2 mb-2">
                <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded border", priColor[r.priority])}>
                  {r.priority}
                </span>
                <Badge variant="outline" className="text-[10px]">{r.area}</Badge>
                {r.reasoning_source === "hf-llm" && (
                  <Badge variant="secondary" className="text-[9px] gap-1 ml-auto">
                    <Brain className="h-2.5 w-2.5" /> HF LLM
                  </Badge>
                )}
              </div>
              <div className="font-semibold text-sm">{r.title}</div>
              <div className="text-xs text-muted-foreground mt-1 leading-relaxed">{r.insight}</div>
              <div className="text-xs mt-2 border-l-2 border-primary/50 pl-2">
                {r.reasoning || r.action}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function DashEmpty({ title = "No live data yet" }) {
  return (
    <div className="rounded-xl border-2 border-dashed border-border/60 p-10 text-center bg-card/40" data-testid="dashboard-empty-state">
      <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
      <p className="text-sm text-muted-foreground mt-2 max-w-xl mx-auto">
        This dashboard is driven entirely by your uploads. Upload XSOAR incident data
        (SOC Manager / SOAR pages) and Threat-Intel data (Threat Intel page) to populate it.
      </p>
    </div>
  );
}

export default function ExecutiveOverview() {
  const [period, setPeriod] = useState("monthly");
  const [aiEnriched, setAiEnriched] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [enrichedRecs, setEnrichedRecs] = useState(null);
  const { tenantId } = useTenant();
  const { data, isLoading } = useQuery({
    queryKey: ["executive", period, tenantId],
    queryFn: async () => (await api.get(`/dashboard/executive?period=${period}&tenant_id=${tenantId || "all"}`)).data,
    keepPreviousData: true,
  });

  // Reset enriched recs when period/tenant changes
  useEffect(() => {
    setEnrichedRecs(null);
    setAiEnriched(false);
  }, [period, tenantId]);

  const enrichWithLLM = async () => {
    setAiLoading(true);
    try {
      const { data: enriched } = await api.get(`/ai/insights?period=${period}&tenant_id=${tenantId || "all"}`);
      setEnrichedRecs(enriched.recommendations);
      setAiEnriched(true);
    } catch (e) { /* noop */ }
    finally { setAiLoading(false); }
  };

  const displayRecs = enrichedRecs || data?.recommendations;

  return (
    <motion.div {...fadeIn} className="p-6 md:p-8 space-y-6" data-testid="executive-overview">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold">
            Cross-Functional Executive Overview
          </div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mt-1" style={{ fontFamily: "var(--font-heading)" }}>
            SOC Command Center
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            One-glance posture across QRadar detection, XSOAR operations and Threat Intelligence.
          </p>
          {data?.xsoar_live && (
            <div className="mt-3 flex items-center gap-2 text-[11px]" data-testid="exec-xsoar-live-chip">
              <Badge variant="outline" className="gap-1 border-emerald-500/40 text-emerald-500">
                <Sparkles className="h-3 w-3" /> LIVE FROM XSOAR
              </Badge>
              {data.xsoar_upload && (
                <span className="text-muted-foreground truncate">
                  <span className="font-medium text-foreground">{data.xsoar_upload.filename}</span>
                  &nbsp;· {data.xsoar_upload.row_count?.toLocaleString()} incidents · {data.xsoar_upload.uploaded_at?.slice(0, 10)}
                </span>
              )}
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <ExportActions period={period} />
          <TimeTabs value={period} onChange={setPeriod} />
        </div>
      </div>

      {isLoading && <div className="text-sm text-muted-foreground">Loading dashboards…</div>}
      {data && data.data_status !== "live" && <DashEmpty title="No live data for this tenant yet" />}
      {data && data.data_status === "live" && (
        <>
          {/* Hero: two gauges + AI recs */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-4">
              <div className="rounded-xl border border-border/60 bg-card p-6 flex flex-col items-center justify-center gap-4 h-full">
                <div className="grid grid-cols-2 gap-6">
                  <Gauge value={data.health_score} label="SOC Health" color="hsl(var(--chart-2))" testid="gauge-health" />
                  <Gauge value={data.risk_score} label="Composite Risk" color="hsl(var(--chart-5))" testid="gauge-risk" />
                </div>
                <div className="flex flex-wrap gap-2 justify-center text-xs">
                  <Badge variant="outline" className="gap-1"><Skull className="h-3 w-3" /> {data.top_threat_actor}</Badge>
                  <Badge variant="outline" className="gap-1"><Server className="h-3 w-3" /> {data.top_targeted_asset}</Badge>
                </div>
              </div>
            </div>

            <div className="lg:col-span-8">
              <RecPanel recs={displayRecs} onEnrich={enrichWithLLM} aiLoading={aiLoading} aiEnriched={aiEnriched} />
            </div>
          </div>

          {/* KPI grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard label="Incidents (XSOAR)" value={data.incidents} icon={ShieldAlert} intent="negative" delta={-4.2} trend={data.incident_trend} testid="kpi-incidents" />
            <KpiCard label="Offenses (QRadar)" value={data.offenses} icon={Activity} intent="negative" delta={2.1} testid="kpi-offenses" />
            <KpiCard label="SLA Compliance" value={data.sla_compliance} suffix="%" icon={Percent} delta={0.8} trend={data.sla_trend} testid="kpi-sla" />
            <KpiCard label="MTTR" value={data.mttr_hours} suffix="h" icon={Timer} intent="negative" delta={-6.4} testid="kpi-mttr" />
            <KpiCard label="Detection Coverage" value={data.detection_coverage} suffix="%" icon={Radar} delta={1.9} testid="kpi-coverage" />
            <KpiCard label="Automation Rate" value={data.automation_rate} suffix="%" icon={Bot} delta={3.4} testid="kpi-automation" />
            <KpiCard label="Threat Advisories" value={data.advisories} icon={FileText} intent="neutral" delta={5.2} testid="kpi-advisories" />
            <KpiCard label="Top Threat Actor" value={data.top_threat_actor} icon={Skull} testid="kpi-actor" />
          </div>

          {/* Trend charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ChartCard title="Incident Volume" subtitle="Trend · XSOAR + QRadar" testid="chart-incident-trend">
              <div className="h-64">
                <ResponsiveContainer>
                  <AreaChart data={data.incident_trend}>
                    <defs>
                      <linearGradient id="incFill" x1="0" x2="0" y1="0" y2="1">
                        <stop offset="0%" stopColor="hsl(var(--chart-1))" stopOpacity={0.5} />
                        <stop offset="100%" stopColor="hsl(var(--chart-1))" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                    <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={11} />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} />
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                    <Area type="monotone" dataKey="value" stroke="hsl(var(--chart-1))" strokeWidth={2} fill="url(#incFill)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
            <ChartCard title="SLA Compliance" subtitle="Trend · XSOAR" testid="chart-sla-trend">
              <div className="h-64">
                <ResponsiveContainer>
                  <LineChart data={data.sla_trend}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                    <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={11} />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} domain={["dataMin - 2", 100]} />
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                    <Line type="monotone" dataKey="value" stroke="hsl(var(--chart-2))" strokeWidth={2.5} dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          </div>
        </>
      )}
    </motion.div>
  );
}
