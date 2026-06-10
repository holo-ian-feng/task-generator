/**
 * Root Route - App Shell
 */

import { useState } from 'react';
import { createRootRoute, Outlet, Link, useLocation, redirect, useNavigate } from '@tanstack/react-router';
import { TanStackRouterDevtools } from '@tanstack/router-devtools';
import { cn } from '@/lib/utils';
import { Home, Users, FileText, Ticket, Workflow, LogOut } from 'lucide-react';
import { supabase } from '@/data/supabase';

export const Route = createRootRoute({
  beforeLoad: async ({ location }) => {
    if (location.pathname === '/login') return;
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) throw redirect({ to: '/login' });
  },
  component: RootComponent,
});

function RootComponent() {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
      {import.meta.env.DEV && (
        <TanStackRouterDevtools position="bottom-right" />
      )}
    </div>
  );
}

function Header() {
  const navigate = useNavigate();
  const [email, setEmail] = useState<string | null>(null);

  useState(() => {
    supabase.auth.getUser().then(({ data }) => setEmail(data.user?.email ?? null));
  });

  async function handleSignOut() {
    await supabase.auth.signOut();
    navigate({ to: '/login' });
  }

  return (
    <header className="h-16 border-b bg-card flex items-center justify-between px-6">
      <h1 className="text-xl font-semibold">Transcript Tickets</h1>
      <div className="flex items-center gap-4">
        {email && <span className="text-sm text-muted-foreground">{email}</span>}
        <button
          onClick={handleSignOut}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </header>
  );
}

function Sidebar() {
  const location = useLocation();

  const links = [
    { to: '/', label: 'Dashboard', icon: Home, exact: true },
    { to: '/teams', label: 'Teams', icon: Users, exact: false },
    { to: '/transcripts', label: 'Transcripts', icon: FileText, exact: false },
    { to: '/tickets', label: 'Tickets', icon: Ticket, exact: false },
    { to: '/workflows', label: 'Task Flows', icon: Workflow, exact: false },
  ];

  return (
    <aside className="w-56 border-r bg-card min-h-[calc(100vh-4rem)]">
      <nav className="p-3 space-y-1">
        {links.map(({ to, label, icon: Icon, exact }) => {
          const isActive = exact
            ? location.pathname === to
            : location.pathname.startsWith(to);
          return (
            <Link
              key={to}
              to={to}
              className={cn(
                'flex items-center gap-3 px-3 py-2 rounded-lg transition-colors text-sm',
                isActive ? 'bg-primary text-primary-foreground' : 'hover:bg-muted',
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
