import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { AlertCircle, Building2, Fish, Globe2, ShieldAlert, TrendingUp } from "lucide-react";
import KpiCard from "@/components/KpiCard";
import ChartCard from "@/components/ChartCard";
import TimeTabs from "@/components/TimeTabs";
import ExportActions from "@/components/ExportActions";
import { useTenant } from "@/contexts/TenantContext";
import { Badge } from "@/components/ui/badge";
import {
  ResponsiveContainer, BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip,
  LineChart, Line, AreaChart, Area,
} from "recharts";
import api from "@/api/client";

const fadeIn = { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 } };

function DashEmpty({ title = "No live data for this tenant yet" }) {
  return (
    <div className="rounded-xl border-2 border-dashed border-border/60 p-10 text-center bg-card/40" data-testid="client-empty-state">
      <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
      <p className="text-sm text-muted-foreground mt-2 max-w-xl mx-auto">
        Upload XSOAR incident data for this tenant (SOC Manager page) to populate the client scorecard.
      </p>
    </div>
  );
}

export default function ClientDashboard() {
  const [period, setPeriod] = useState("monthly");
  const { tenantId } = useTenant();
  const { data, isLoading } = useQuery({
    queryKey: ["client", period, tenantId],
    queryFn: async () => (await api.get(`/dashboard/client?period=${period}&tenant_id=${tenantId || "all"}`)).data,
    keepPreviousData: true,
  });

  return (
    <motion.div {...fadeIn} className="p-6 md:p-8 space-y-6" data-testid="client-page">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold">Persona</div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mt-1" style={{ fontFamily: "var(--font-heading)" }}>
            Stakeholder · Client Executive
          </h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            High-level business risk and service outcomes for tenant leadership.
          </p>
        </div>
        <TimeTabs value={period} onChange={setPeriod} />
      </div>

      {isLoading && <div className="text-sm text-muted-foreground">Loading…</div>}
      {data && data.data_status !== "live" && <DashEmpty />}
      {data && data.data_status === "live" && (
        <>
          {/* Executive Scorecard */}
          <section>
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold mb-3">
              Executive Scorecard
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <KpiCard label="Composite Risk" value={data.scorecard.composite_risk_score} icon={ShieldAlert} intent="negative" delta={data.scorecard.yoy_incident_delta} testid="kpi-risk" />
              <KpiCard label="Client Risk Rank" value={`#${data.scorecard.client_risk_rank}`} icon={TrendingUp} testid="kpi-rank" />
              <KpiCard label="Quarterly SLA" value={data.scorecard.quarterly_sla} suffix="%" delta={data.scorecard.yoy_sla_delta} testid="kpi-quarterly-sla" />
              <KpiCard label="Major P1/P2" value={data.scorecard.major_p1_p2_incidents} icon={AlertCircle} intent="negative" testid="kpi-major" />
              <KpiCard label="YoY Incidents" value={`${data.scorecard.yoy_incident_delta > 0 ? "+" : ""}${data.scorecard.yoy_incident_delta}`} suffix="%" intent="negative" testid="kpi-yoy-inc" />
              <KpiCard label="YoY MTTR" value={`${data.scorecard.yoy_mttr_delta > 0 ? "+" : ""}${data.scorecard.yoy_mttr_delta}`} suffix="%" intent="negative" testid="kpi-yoy-mttr" />
              <KpiCard label="YoY SLA" value={`${data.scorecard.yoy_sla_delta > 0 ? "+" : ""}${data.scorecard.yoy_sla_delta}`} suffix="%" testid="kpi-yoy-sla" />
              <KpiCard label="Open Critical" value={data.business_risk.open_critical} intent="negative" testid="kpi-open-critical" />
            </div>
          </section>

          {/* Business Risk */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ChartCard title="Top Targeted Assets" subtitle="QRadar" testid="chart-top-assets" action={<Building2 className="h-4 w-4 text-muted-foreground" />}>
              <div className="h-64">
                <ResponsiveContainer>
                  <BarChart data={data.business_risk.top_assets} layout="vertical" margin={{ left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                    <XAxis type="number" stroke="hsl(var(--muted-foreground))" fontSize={11} />
                    <YAxis type="category" dataKey="asset" stroke="hsl(var(--muted-foreground))" fontSize={11} width={130} />
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                    <Bar dataKey="hits" fill="hsl(var(--chart-1))" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>

            <ChartCard title="Top Attacking Sources" subtitle="Geo · QRadar" testid="chart-top-sources" action={<Globe2 className="h-4 w-4 text-muted-foreground" />}>
              <div className="h-64">
                <ResponsiveContainer>
                  <BarChart data={data.business_risk.top_sources}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                    <XAxis dataKey="country" stroke="hsl(var(--muted-foreground))" fontSize={11} />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} />
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                    <Bar dataKey="count" fill="hsl(var(--chart-5))" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard label="Phishing Incidents" value={data.business_risk.phishing_incidents} icon={Fish} intent="negative" delta={-5.2} testid="kpi-phishing" />
            <KpiCard label="Avg Dwell Time" value={data.business_risk.avg_dwell_hours} suffix="h" intent="negative" testid="kpi-dwell" />
            <KpiCard label="Repeat Incidents" value={data.business_risk.repeat_incidents} intent="negative" testid="kpi-repeat-inc" />
            <KpiCard label="Advisories" value={data.threat_exposure.total_advisories} testid="kpi-advisories-tot" />
          </div>

          {/* Threat Exposure */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <ChartCard title="Threat Actor Activity" subtitle="Threat Intel" testid="chart-actors">
              <div className="space-y-2">
                {data.threat_exposure.threat_actors.map((a) => (
                  <div key={a.name} className="flex items-center justify-between text-sm">
                    <div className="font-medium">{a.name}</div>
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-24 bg-muted rounded-full overflow-hidden">
                        <div className="h-full bg-rose-500" style={{ width: `${a.activity}%` }} />
                      </div>
                      <span className="text-xs text-muted-foreground tabular w-8 text-right">{a.activity}</span>
                    </div>
                  </div>
                ))}
              </div>
            </ChartCard>

            <ChartCard title="Malware Families" subtitle="Threat Intel" testid="chart-malware">
              <div className="h-64">
                <ResponsiveContainer>
                  <BarChart data={data.threat_exposure.malware}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                    <XAxis dataKey="family" stroke="hsl(var(--muted-foreground))" fontSize={10} interval={0} angle={-30} height={60} textAnchor="end" />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} />
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                    <Bar dataKey="count" fill="hsl(var(--chart-4))" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>

            <ChartCard title="Advisory Trend" subtitle="Threat Intel" testid="chart-advisory-trend">
              <div className="h-64">
                <ResponsiveContainer>
                  <AreaChart data={data.threat_exposure.advisory_trend}>
                    <defs>
                      <linearGradient id="advFill" x1="0" x2="0" y1="0" y2="1">
                        <stop offset="0%" stopColor="hsl(var(--chart-3))" stopOpacity={0.5} />
                        <stop offset="100%" stopColor="hsl(var(--chart-3))" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                    <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={11} />
                    <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} />
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                    <Area type="monotone" dataKey="value" stroke="hsl(var(--chart-3))" strokeWidth={2} fill="url(#advFill)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </ChartCard>
          </div>

          {/* Executive Trends */}
          <ChartCard title="Executive Trends" subtitle="Multi-metric overlay" testid="chart-exec-trends">
            <div className="h-72">
              <ResponsiveContainer>
                <LineChart>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                  <XAxis dataKey="date" allowDuplicatedCategory={false} stroke="hsl(var(--muted-foreground))" fontSize={11} type="category" />
                  <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} />
                  <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8 }} />
                  <Line data={data.trends.sla} type="monotone" dataKey="value" name="SLA %" stroke="hsl(var(--chart-2))" strokeWidth={2} dot={false} />
                  <Line data={data.trends.automation} type="monotone" dataKey="value" name="Automation %" stroke="hsl(var(--chart-1))" strokeWidth={2} dot={false} />
                  <Line data={data.trends.coverage} type="monotone" dataKey="value" name="Coverage %" stroke="hsl(var(--chart-4))" strokeWidth={2} dot={false} />
                  <Line data={data.trends.fp} type="monotone" dataKey="value" name="FP %" stroke="hsl(var(--chart-5))" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <Badge variant="outline"><span className="h-2 w-2 rounded-full bg-emerald-500 mr-1.5" /> SLA</Badge>
              <Badge variant="outline"><span className="h-2 w-2 rounded-full bg-blue-500 mr-1.5" /> Automation</Badge>
              <Badge variant="outline"><span className="h-2 w-2 rounded-full bg-violet-500 mr-1.5" /> Coverage</Badge>
              <Badge variant="outline"><span className="h-2 w-2 rounded-full bg-rose-500 mr-1.5" /> False Positive</Badge>
            </div>
          </ChartCard>
        </>
      )}
    </motion.div>
  );
}
