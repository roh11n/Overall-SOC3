import { useEffect, useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Mail, Info, Send, X } from "lucide-react";
import { toast } from "sonner";
import api from "@/api/client";

export default function EmailModal({ open, onOpenChange, period, tenant }) {
  const [recipients, setRecipients] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [attach, setAttach] = useState(true);
  const [sending, setSending] = useState(false);
  const [history, setHistory] = useState([]);
  const [mode, setMode] = useState("compose"); // 'compose' | 'history'

  useEffect(() => {
    if (open) {
      setSubject(`MSSP SOC ${period ? period.charAt(0).toUpperCase() + period.slice(1) : "Monthly"} Report · ${tenant?.name || "All Tenants"}`);
      setBody(
        `<p>Hi team,</p><p>Please find attached the MSSP SOC KPI report for <b>${tenant?.name || "All Tenants"}</b> (${tenant?.domain || "ALL"}) for the ${period} cycle.</p><p>Highlights and AI-generated recommendations are included in the deck.</p><p>— SOC Ops</p>`
      );
    }
  }, [open, period, tenant]);

  const loadHistory = async () => {
    try {
      const { data } = await api.get("/email/history");
      setHistory(data);
    } catch { /* noop */ }
  };

  useEffect(() => { if (open && mode === "history") loadHistory(); }, [open, mode]);

  const send = async () => {
    const to = recipients.split(/[,;\s]+/).map((s) => s.trim()).filter(Boolean);
    if (!to.length) { toast.error("Add at least one recipient"); return; }
    setSending(true);
    try {
      const { data } = await api.post("/email/send", {
        to, subject, html: body,
        tenant_id: tenant?.id || "all",
        period: period || "monthly",
        attach_pptx: attach,
      });
      toast.success(data.mode === "smtp"
        ? `Email delivered to ${to.length} recipient(s)`
        : `Console-mock email logged (attachment ${data.attachments?.[0]?.size ? Math.round(data.attachments[0].size / 1024) + " KB" : "none"})`);
      setRecipients("");
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Send failed");
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="email-modal">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail className="h-4 w-4 text-primary" />
            Email SOC Report
          </DialogTitle>
          <DialogDescription>
            Send the current dashboard as a branded PPTX attachment. Mode: SMTP if configured, else console-mock (logged + previewable in history).
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-1 border-b border-border/60 -mt-2">
          <button
            className={`px-3 py-2 text-xs font-medium ${mode === "compose" ? "border-b-2 border-primary text-foreground" : "text-muted-foreground"}`}
            onClick={() => setMode("compose")}
            data-testid="email-mode-compose"
          >
            Compose
          </button>
          <button
            className={`px-3 py-2 text-xs font-medium ${mode === "history" ? "border-b-2 border-primary text-foreground" : "text-muted-foreground"}`}
            onClick={() => setMode("history")}
            data-testid="email-mode-history"
          >
            History
          </button>
        </div>

        {mode === "compose" ? (
          <div className="space-y-4">
            <div>
              <Label htmlFor="email-to">Recipients</Label>
              <Input
                id="email-to"
                value={recipients}
                onChange={(e) => setRecipients(e.target.value)}
                placeholder="ciso@client.com, cto@client.com"
                className="mt-1.5"
                data-testid="email-recipients"
              />
              <p className="text-[10px] text-muted-foreground mt-1">Comma, space or semicolon separated</p>
            </div>
            <div>
              <Label htmlFor="email-subject">Subject</Label>
              <Input
                id="email-subject"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="mt-1.5"
                data-testid="email-subject"
              />
            </div>
            <div>
              <Label htmlFor="email-body">Body (HTML supported)</Label>
              <Textarea
                id="email-body"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={5}
                className="mt-1.5 font-mono text-xs"
                data-testid="email-body"
              />
            </div>
            <div className="flex items-center justify-between rounded-md border border-border/60 p-3">
              <div>
                <div className="text-sm font-medium">Attach PPTX report</div>
                <div className="text-xs text-muted-foreground">Multi-slide client-ready deck (~250 KB)</div>
              </div>
              <Switch checked={attach} onCheckedChange={setAttach} data-testid="email-attach-toggle" />
            </div>
            <div className="flex items-start gap-2 text-xs text-muted-foreground rounded-md border border-border/60 bg-muted/30 p-3">
              <Info className="h-3.5 w-3.5 mt-0.5 shrink-0 text-primary" />
              <div>
                <span className="font-medium text-foreground">MOCKED mode:</span> No SMTP credentials configured — the email + attachment are logged to backend console and stored in <code className="font-mono">db.emails</code> for preview. To go live, set <code className="font-mono">SMTP_HOST/PORT/USER/PASS</code> in <code className="font-mono">backend/.env</code>.
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="email-cancel">Cancel</Button>
              <Button onClick={send} disabled={sending} className="gap-2" data-testid="email-send-btn">
                <Send className="h-4 w-4" />
                {sending ? "Sending…" : "Send"}
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-2 max-h-96 overflow-y-auto" data-testid="email-history-list">
            {history.length === 0 && <div className="text-sm text-muted-foreground text-center py-8">No emails sent yet.</div>}
            {history.map((e) => (
              <div key={e._id} className="rounded-md border border-border/60 p-3 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <div className="font-semibold">{e.subject}</div>
                  <Badge variant={e.mode === "smtp" ? "default" : "secondary"} className="text-[10px]">
                    {e.mode === "smtp" ? "SMTP" : "MOCKED"}
                  </Badge>
                </div>
                <div className="text-muted-foreground">To: {e.to?.join(", ")}</div>
                <div className="flex justify-between text-muted-foreground">
                  <span>{new Date(e.sent_at).toLocaleString()}</span>
                  {e.attachments?.length ? (
                    <span>{e.attachments[0].filename} · {Math.round(e.attachments[0].size / 1024)} KB</span>
                  ) : <span>no attachment</span>}
                </div>
                {e.error && <div className="text-rose-500">Error: {e.error}</div>}
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
