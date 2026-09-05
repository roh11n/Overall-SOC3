import { createContext, useContext, useEffect, useState } from "react";
import api from "@/api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const cached = localStorage.getItem("mssp_user");
    return cached ? JSON.parse(cached) : null;
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("mssp_token");
    if (!token) {
      setLoading(false);
      return;
    }
    api.get("/auth/me")
      .then((res) => {
        setUser(res.data);
        localStorage.setItem("mssp_user", JSON.stringify(res.data));
      })
      .catch(() => {
        localStorage.removeItem("mssp_token");
        localStorage.removeItem("mssp_user");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("mssp_token", data.access_token);
    const u = { id: data.id, email: data.email, name: data.name, role: data.role };
    localStorage.setItem("mssp_user", JSON.stringify(u));
    setUser(u);
    return u;
  };

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch (_) {}
    localStorage.removeItem("mssp_token");
    localStorage.removeItem("mssp_user");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
