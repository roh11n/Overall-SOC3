import { useState } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { Shield, Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const PERSONAS = [];

export default function LoginPage() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const submit = async (e) => {
    e?.preventDefault();
    setBusy(true);
    try {
      await login(email, password);
      toast.success("Signed in");
      nav("/");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Invalid credentials");
    } finally {
      setBusy(false);
    }
  };

  const quickLogin = async (p) => {
    setEmail(p.email);
    setPassword(p.pwd);
    setBusy(true);
    try {
      await login(p.email, p.pwd);
      nav("/");
    } catch (e) {
      toast.error("Quick login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground grid lg:grid-cols-2">
      {/* Left visual */}
      <div className="hidden lg:flex relative bg-gradient-to-br from-background via-background to-primary/5 border-r border-border/60 overflow-hidden">
        <div className="absolute inset-0 grid-backdrop opacity-40" />
        <div className="relative z-10 p-12 flex flex-col justify-between w-full">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-md bg-primary/15 border border-primary/40 grid place-items-center">
              <Shield className="h-5 w-5 text-primary" />
            </div>
            <div>
              <div className="font-bold tracking-tight text-lg" style={{ fontFamily: "var(--font-heading)" }}>
                MSSP SOC KPI Console
              </div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mt-1">
                Persona-first · Multi-tenant · Real-time
              </div>
            </div>
          </div>

          <div className="space-y-6 max-w-md">
            <h1 className="text-5xl font-bold tracking-tight leading-[1.05]" style={{ fontFamily: "var(--font-heading)" }}>
              Operate the SOC by <span className="text-primary">audience</span>, not by dashboard.
            </h1>
            <p className="text-muted-foreground leading-relaxed">
              Six persona-organized views wired to QRadar, XSOAR and Threat Intelligence.
              Every KPI slices to Weekly, Monthly or Quarterly on demand.
            </p>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">QRadar</Badge>
              <Badge variant="outline">XSOAR</Badge>
              <Badge variant="outline">MITRE ATT&CK</Badge>
              <Badge variant="outline">SLA Analytics</Badge>
              <Badge variant="outline">AI Recommendations</Badge>
            </div>
          </div>

          <div className="text-xs text-muted-foreground font-mono">
            v1.0 · Ops-grade telemetry
          </div>
        </div>
      </div>

      {/* Right form */}
      <div className="flex items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-md space-y-8">
          <div className="lg:hidden flex items-center gap-3">
            <div className="h-10 w-10 rounded-md bg-primary/15 border border-primary/40 grid place-items-center">
              <Shield className="h-5 w-5 text-primary" />
            </div>
            <div className="font-bold tracking-tight text-lg" style={{ fontFamily: "var(--font-heading)" }}>
              MSSP SOC
            </div>
          </div>

          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold">
              Secure sign in
            </div>
            <h2 className="text-3xl font-bold tracking-tight mt-2" style={{ fontFamily: "var(--font-heading)" }}>
              Welcome back
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              Enter your credentials to access the SOC console.
            </p>
          </div>

          <form onSubmit={submit} className="space-y-4" data-testid="login-form">
            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="mt-1.5"
                data-testid="login-email"
              />
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <div className="relative mt-1.5">
                <Input
                  id="password"
                  type={showPwd ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  data-testid="login-password"
                />
                <button
                  type="button"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  onClick={() => setShowPwd((v) => !v)}
                  data-testid="login-toggle-password"
                >
                  {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <Button
              type="submit"
              className="w-full"
              size="lg"
              disabled={busy}
              data-testid="login-submit"
            >
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
