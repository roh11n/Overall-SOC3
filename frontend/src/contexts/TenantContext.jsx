import { createContext, useContext, useEffect, useState } from "react";
import api from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";

const TenantContext = createContext(null);

export function TenantProvider({ children }) {
  const { user } = useAuth();
  const [tenants, setTenants] = useState([]);
  const [tenantId, setTenantId] = useState(() => localStorage.getItem("mssp_tenant") || "all");
  const [loading, setLoading] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    if (!user) {
      setTenants([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    api.get("/tenants")
      .then((res) => setTenants(res.data))
      .catch(() => setTenants([]))
      .finally(() => setLoading(false));
  }, [user, refreshTick]);

  const setTenant = (id) => {
    localStorage.setItem("mssp_tenant", id);
    setTenantId(id);
  };

  const refresh = () => setRefreshTick((t) => t + 1);

  const tenant = tenants.find((t) => t.id === tenantId) || tenants[0] || null;

  return (
    <TenantContext.Provider value={{ tenants, tenant, tenantId, setTenant, loading, refresh }}>
      {children}
    </TenantContext.Provider>
  );
}

export function useTenant() {
  return useContext(TenantContext);
}
