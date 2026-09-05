import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Send, X, RotateCw, Loader2, ShieldCheck, Cpu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import api from "@/api/client";
import { useTenant } from "@/contexts/TenantContext";
import { useAuth } from "@/contexts/AuthContext";

const STORAGE_SESSION = "iris_session_id";

export default function IrisCopilot() {
  const { user } = useAuth();
  const { tenantId, tenant } = useTenant();
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState(() => localStorage.getItem(STORAGE_SESSION) || null);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  // Fetch status once when opened
  useEffect(() => {
    if (!open || status) return;
    api.get("/copilot/status").then((res) => setStatus(res.data)).catch(() => setStatus(null));
  }, [open, status]);

  // Load session history when opening
  useEffect(() => {
    if (!open || !sessionId || messages.length > 0) return;
    api.get(`/copilot/history?session_id=${sessionId}`)
      .then((res) => setMessages(res.data || []))
      .catch(() => {});
  }, [open, sessionId, messages.length]);

  // Auto scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, sending]);

  // Focus input when opened
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 200);
  }, [open]);

  if (!user) return null;

  const send = async (text) => {
    const question = (text ?? input).trim();
    if (!question || sending) return;
    setInput("");
    setSending(true);
    const optimistic = { role: "user", content: question, created_at: new Date().toISOString() };
    setMessages((m) => [...m, optimistic]);
    try {
      const res = await api.post("/copilot/chat", {
        message: question,
        session_id: sessionId,
        tenant_id: tenantId,
        period: "monthly",
      });
      const { session_id, answer, source, created_at } = res.data;
      if (session_id && session_id !== sessionId) {
        setSessionId(session_id);
        localStorage.setItem(STORAGE_SESSION, session_id);
      }
      setMessages((m) => [...m, {
        role: "assistant",
        content: answer,
        source,
        created_at,
      }]);
    } catch {
      setMessages((m) => [...m, {
        role: "assistant",
        content: "IRIS is temporarily unavailable. Please retry.",
        source: "error",
      }]);
    } finally {
      setSending(false);
    }
  };

  const resetSession = () => {
    localStorage.removeItem(STORAGE_SESSION);
    setSessionId(null);
    setMessages([]);
  };

  const modelReady = status?.ready;

  return (
    <>
      {/* Floating Launcher */}
      <AnimatePresence>
        {!open && (
          <motion.button
            key="iris-launcher"
            initial={{ opacity: 0, y: 12, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.9 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            onClick={() => setOpen(true)}
            data-testid="iris-copilot-launcher"
            className={cn(
              "fixed bottom-20 right-6 md:bottom-24 md:right-8 z-40 group",
              "flex items-center gap-2 pl-3 pr-4 py-2.5 rounded-full",
              "bg-primary text-primary-foreground shadow-lg shadow-primary/30",
              "hover:shadow-xl hover:shadow-primary/40 hover:-translate-y-0.5",
              "transition-all duration-200 border border-primary/60",
            )}
            aria-label="Open IRIS copilot"
          >
            <span className="relative flex h-7 w-7 items-center justify-center rounded-full bg-primary-foreground/15">
              <Sparkles className="h-4 w-4" />
              <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-emerald-400 ring-2 ring-primary animate-pulse" />
            </span>
            <div className="flex flex-col items-start leading-tight">
              <span className="text-[10px] uppercase tracking-[0.2em] opacity-70">Ask</span>
              <span className="text-sm font-bold tracking-tight">IRIS</span>
            </div>
          </motion.button>
        )}
      </AnimatePresence>

      {/* Chat Panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            key="iris-panel"
            initial={{ opacity: 0, y: 24, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.98 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className={cn(
              "fixed bottom-20 right-4 md:bottom-24 md:right-6 z-50",
              "w-[92vw] sm:w-[420px] h-[70vh] max-h-[640px]",
              "rounded-2xl overflow-hidden flex flex-col",
              "bg-card/95 backdrop-blur-xl border border-border shadow-2xl",
            )}
            data-testid="iris-copilot-panel"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-primary text-primary-foreground">
              <div className="flex items-center gap-3">
                <div className="relative flex h-9 w-9 items-center justify-center rounded-lg bg-primary-foreground/15 border border-primary-foreground/20">
                  <Sparkles className="h-4 w-4" />
                  <span className={cn(
                    "absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-primary",
                    modelReady ? "bg-emerald-400" : "bg-amber-400 animate-pulse",
                  )} />
                </div>
                <div>
                  <div className="text-sm font-bold tracking-tight leading-none">IRIS</div>
                  <div className="text-[10px] uppercase tracking-[0.2em] opacity-75 mt-1 flex items-center gap-1">
                    <Cpu className="h-3 w-3" />
                    {modelReady ? "HF LLM · Ready" : status?.loading ? "Warming up…" : "Rule-based fallback"}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 hover:bg-primary-foreground/10 text-primary-foreground"
                  onClick={resetSession}
                  data-testid="iris-reset-btn"
                  title="New session"
                >
                  <RotateCw className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 hover:bg-primary-foreground/10 text-primary-foreground"
                  onClick={() => setOpen(false)}
                  data-testid="iris-close-btn"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Grounding chip */}
            <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-muted/40 text-[11px] text-muted-foreground">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
              <span>Grounded on&nbsp;</span>
              <Badge variant="outline" className="text-[10px] py-0 px-1.5">
                {tenant?.name || "All Tenants"}
              </Badge>
              <span className="opacity-60">·&nbsp;monthly snapshot</span>
            </div>

            {/* Messages */}
            <div
              ref={scrollRef}
              className="flex-1 overflow-y-auto px-4 py-4 space-y-3"
              data-testid="iris-messages"
            >
              {messages.length === 0 && (
                <div className="space-y-4">
                  <div className="text-sm text-muted-foreground">
                    Hi{user?.name ? `, ${user.name.split(" ")[0]}` : ""} — I&apos;m <span className="font-semibold text-foreground">IRIS</span>. Ask me anything about your SOC KPIs. I&apos;m reading the live snapshot for <span className="font-semibold text-foreground">{tenant?.name || "All Tenants"}</span>.
                  </div>
                  <div className="space-y-2">
                    <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold">
                      Suggested prompts
                    </div>
                    {(status?.suggestions || []).slice(0, 5).map((s) => (
                      <button
                        key={s}
                        onClick={() => send(s)}
                        data-testid={`iris-suggestion-${s.slice(0, 20).toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}
                        className="w-full text-left px-3 py-2 rounded-lg border border-border bg-background hover:bg-accent hover:border-primary/40 transition-colors text-sm"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((m, i) => (
                <div
                  key={i}
                  className={cn(
                    "flex",
                    m.role === "user" ? "justify-end" : "justify-start",
                  )}
                >
                  <div
                    className={cn(
                      "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed shadow-sm",
                      m.role === "user"
                        ? "bg-primary text-primary-foreground rounded-br-sm"
                        : "bg-muted/60 border border-border rounded-bl-sm",
                    )}
                    data-testid={`iris-msg-${m.role}-${i}`}
                  >
                    {m.content}
                    {m.role === "assistant" && m.source && (
                      <div className="mt-1.5 flex items-center gap-1 text-[9px] uppercase tracking-[0.2em] opacity-60">
                        {m.source === "hf-llm" ? (
                          <><Cpu className="h-2.5 w-2.5" /> HF LLM Reasoning</>
                        ) : m.source === "error" ? (
                          <span className="text-rose-500">error</span>
                        ) : (
                          <><ShieldCheck className="h-2.5 w-2.5" /> KPI Lookup</>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {sending && (
                <div className="flex justify-start">
                  <div className="max-w-[85%] rounded-2xl px-3.5 py-2.5 bg-muted/60 border border-border rounded-bl-sm">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      IRIS is reasoning…
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Composer */}
            <form
              onSubmit={(e) => { e.preventDefault(); send(); }}
              className="border-t border-border p-3 bg-background"
              data-testid="iris-composer"
            >
              <div className="flex items-end gap-2">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                  disabled={sending}
                  placeholder="Ask about MTTR, MITRE coverage, threat actors, playbooks…"
                  rows={1}
                  className={cn(
                    "flex-1 resize-none rounded-lg border border-border bg-background",
                    "px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/50",
                    "max-h-24 min-h-[38px]",
                  )}
                  data-testid="iris-input"
                />
                <Button
                  type="submit"
                  size="icon"
                  disabled={!input.trim() || sending}
                  data-testid="iris-send-btn"
                  className="h-[38px] w-[38px] shrink-0"
                >
                  {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </Button>
              </div>
              <div className="mt-1.5 text-[10px] text-muted-foreground text-center">
                IRIS reads only this tenant&apos;s KPI snapshot · answers may reference MITRE ATT&amp;CK
              </div>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
