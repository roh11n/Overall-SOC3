import { useState } from "react";
import { Download, Mail, FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import api, { API } from "@/api/client";
import EmailModal from "@/components/EmailModal";
import { useTenant } from "@/contexts/TenantContext";

export default function ExportActions({ period }) {
  const [busy, setBusy] = useState(false);
  const [emailOpen, setEmailOpen] = useState(false);
  const { tenantId, tenant } = useTenant();

  const downloadPptx = async () => {
    setBusy(true);
    try {
      const token = localStorage.getItem("mssp_token");
      const res = await fetch(
        `${API}/export/pptx?period=${period}&tenant_id=${tenantId || "all"}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!res.ok) throw new Error(`Status ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `MSSP_SOC_${tenantId}_${period}_${new Date().toISOString().slice(0, 10)}.pptx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("PPTX report downloaded");
    } catch (e) {
      toast.error(`Export failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={downloadPptx}
          disabled={busy}
          className="gap-2"
          data-testid="export-pptx-btn"
        >
          <FileDown className="h-4 w-4" />
          <span className="hidden sm:inline">{busy ? "Exporting…" : "Export PPTX"}</span>
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setEmailOpen(true)}
          className="gap-2"
          data-testid="email-report-btn"
        >
          <Mail className="h-4 w-4" />
          <span className="hidden sm:inline">Email Report</span>
        </Button>
      </div>
      <EmailModal open={emailOpen} onOpenChange={setEmailOpen} period={period} tenant={tenant} />
    </>
  );
}
