import { ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { LineChart, Line, ResponsiveContainer, YAxis } from "recharts";

/**
 * KPI Card with big value, delta indicator and optional mini sparkline.
 * Props: label, value, suffix, delta (number - percent), trend (array of {value})
 * intent: 'positive' | 'negative' | 'neutral' — controls delta color polarity
 */
export default function KpiCard({
  label,
  value,
  suffix,
  delta,
  trend,
  intent = "positive",
  icon: Icon,
  testid,
}) {
  const isUp = typeof delta === "number" ? delta > 0 : null;
  const isFlat = delta === 0;
  const good =
    isUp === null
      ? true
      : intent === "positive"
        ? isUp
        : intent === "negative"
          ? !isUp
          : true;
  const deltaColor = isFlat
    ? "text-muted-foreground"
    : good
      ? "text-emerald-500"
      : "text-rose-500";

  return (
    <Card className="p-5 flex flex-col gap-4 hover:-translate-y-0.5 transition-transform duration-200" data-testid={testid}>
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold">
          {label}
        </div>
        {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
      </div>
      <div className="flex items-baseline gap-2">
        <div className="text-3xl font-bold tabular tracking-tight" style={{ fontFamily: "var(--font-heading)" }}>
          {value}
          {suffix && <span className="text-lg text-muted-foreground ml-1">{suffix}</span>}
        </div>
      </div>
      <div className="flex items-center justify-between">
        {typeof delta === "number" ? (
          <div className={cn("flex items-center gap-1 text-xs font-semibold", deltaColor)}>
            {isFlat ? (
              <Minus className="h-3 w-3" />
            ) : isUp ? (
              <ArrowUpRight className="h-3 w-3" />
            ) : (
              <ArrowDownRight className="h-3 w-3" />
            )}
            <span>{Math.abs(delta).toFixed(1)}%</span>
            <span className="text-muted-foreground font-normal">vs prev</span>
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">Live</div>
        )}
        {trend?.length ? (
          <div className="h-8 w-24">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trend}>
                <YAxis hide domain={["dataMin", "dataMax"]} />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke={good ? "hsl(var(--chart-2))" : "hsl(var(--chart-5))"}
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
