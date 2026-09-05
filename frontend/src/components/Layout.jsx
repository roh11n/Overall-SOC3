import { NavLink, useLocation } from "react-router-dom";
import {
  Activity, Shield, Users, Radar, Target, Cog, Upload, Sun, Moon, LogOut, Menu, Settings, GitCompare,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useTheme } from "@/contexts/ThemeContext";
import { useAuth } from "@/contexts/AuthContext";
import { useState } from "react";
import UploadModal from "@/components/UploadModal";
import TenantSelector from "@/components/TenantSelector";
import IrisCopilot from "@/components/IrisCopilot";

const NAV = [
  { to: "/", label: "Executive Overview", icon: Activity, testid: "nav-executive" },
  { to: "/soc-manager", label: "SOC Manager", icon: Shield, testid: "nav-soc-manager" },
  { to: "/client", label: "Client / Stakeholder", icon: Users, testid: "nav-client" },
  { to: "/detection", label: "Detection Engineering", icon: Radar, testid: "nav-detection" },
  { to: "/threat-intel", label: "Threat Intelligence", icon: Target, testid: "nav-threat-intel" },
  { to: "/soar", label: "SOAR / Automation", icon: Cog, testid: "nav-soar" },
  { to: "/comparison", label: "Comparison", icon: GitCompare, testid: "nav-comparison" },
  { to: "/settings", label: "Settings", icon: Settings, testid: "nav-settings" },
];

const ROLE_LABEL = {
  admin: "Admin",
  soc_manager: "SOC Manager",
  client: "Client Executive",
  detection_engineer: "Detection Engineer",
  ti_analyst: "TI Analyst",
  automation_engineer: "Automation Engineer",
};

export default function Layout({ children }) {
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();
  const location = useLocation();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const current = NAV.find((n) => n.to === location.pathname);

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      {/* Sidebar */}
      <aside
        className={cn(
          "fixed z-40 md:static w-64 h-full border-r border-border/60 bg-card/60 backdrop-blur-xl flex-col",
          "transition-transform duration-300 md:translate-x-0",
          mobileOpen ? "translate-x-0 flex" : "-translate-x-full md:flex hidden",
        )}
        data-testid="app-sidebar"
      >
        <div className="h-16 px-6 flex items-center border-b border-border/60">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-md bg-primary/15 border border-primary/40 grid place-items-center">
              <Shield className="h-4 w-4 text-primary" />
            </div>
            <div>
              <div className="text-sm font-bold tracking-tight leading-none" style={{ fontFamily: "var(--font-heading)" }}>
                MSSP SOC
              </div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground mt-1">
                KPI Console
              </div>
            </div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto p-3 space-y-1">
          <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold">
            Personas
          </div>
          {NAV.map(({ to, label, icon: Icon, testid }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setMobileOpen(false)}
              data-testid={testid}
              className={({ isActive }) =>
                cn(
                  "group flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors duration-150",
                  "hover:bg-accent hover:text-accent-foreground",
                  isActive
                    ? "bg-accent text-accent-foreground persona-bar font-semibold"
                    : "text-muted-foreground",
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="truncate">{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-border/60">
          <div className="rounded-md border border-border/60 p-3 bg-muted/30">
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold">
              Data Sources
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              <Badge variant="outline" className="text-[10px]">QRadar</Badge>
              <Badge variant="outline" className="text-[10px]">XSOAR</Badge>
              <Badge variant="outline" className="text-[10px]">TI/SharePoint</Badge>
            </div>
          </div>
        </div>
      </aside>

      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-background/70 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <header
          className="sticky top-0 z-20 h-16 flex items-center justify-between px-4 md:px-8 border-b border-border/60 bg-background/80 backdrop-blur-md"
          data-testid="app-header"
        >
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              onClick={() => setMobileOpen((v) => !v)}
              data-testid="mobile-menu-toggle"
            >
              <Menu className="h-5 w-5" />
            </Button>
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-bold">
                Dashboard
              </div>
              <div className="text-lg font-semibold tracking-tight leading-tight" data-testid="current-page-title">
                {current?.label || "Executive Overview"}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <TenantSelector />
            <Button
              variant="outline"
              size="sm"
              onClick={() => setUploadOpen(true)}
              data-testid="header-upload-btn"
              className="gap-2"
            >
              <Upload className="h-4 w-4" />
              <span className="hidden sm:inline">Upload Data</span>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={toggle}
              data-testid="theme-toggle"
              aria-label="Toggle theme"
            >
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-2 rounded-full pl-1 pr-3 py-1 hover:bg-accent transition-colors" data-testid="user-menu-trigger">
                  <Avatar className="h-8 w-8">
                    <AvatarImage
                      src="https://images.unsplash.com/photo-1581841064838-a470c740e8ee?crop=entropy&cs=srgb&fm=jpg&w=100"
                      alt={user?.name}
                    />
                    <AvatarFallback>{user?.name?.[0] || "U"}</AvatarFallback>
                  </Avatar>
                  <div className="hidden md:block text-left">
                    <div className="text-xs font-medium leading-none">{user?.name}</div>
                    <div className="text-[10px] text-muted-foreground mt-1">{ROLE_LABEL[user?.role] || user?.role}</div>
                  </div>
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel>
                  <div className="text-xs font-medium">{user?.name}</div>
                  <div className="text-[10px] text-muted-foreground mt-0.5">{user?.email}</div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem>
                  <Badge variant="secondary" className="text-[10px]">
                    {ROLE_LABEL[user?.role] || user?.role}
                  </Badge>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout} data-testid="logout-btn">
                  <LogOut className="h-3.5 w-3.5 mr-2" /> Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto" data-testid="main-content">
          {children}
        </main>
      </div>

      <UploadModal open={uploadOpen} onOpenChange={setUploadOpen} />
      <IrisCopilot />
    </div>
  );
}
