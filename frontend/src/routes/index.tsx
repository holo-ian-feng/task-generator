import { createFileRoute, Link } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { supabase } from '@/data/supabase';
import { Users, FileText, Ticket, ArrowRight } from 'lucide-react';

export const Route = createFileRoute('/')({
  component: Dashboard,
});

function Dashboard() {
  const { data: teams = [] } = useQuery({
    queryKey: ['teams'],
    queryFn: async () => {
      const { data } = await supabase.from('teams').select('id, name');
      return data ?? [];
    },
  });

  const { data: jobs = [] } = useQuery({
    queryKey: ['transcript-jobs'],
    queryFn: async () => {
      const { data } = await supabase
        .from('transcript_jobs')
        .select('id, status, created_at, teams(name)')
        .order('created_at', { ascending: false })
        .limit(5);
      return data ?? [];
    },
  });

  const { data: ticketCount = 0 } = useQuery({
    queryKey: ['ticket-count'],
    queryFn: async () => {
      const { count } = await supabase.from('tickets').select('id', { count: 'exact', head: true });
      return count ?? 0;
    },
  });

  const STATUS_STYLE: Record<string, string> = {
    pending: 'bg-gray-100 text-gray-700',
    processing: 'bg-yellow-100 text-yellow-700',
    complete: 'bg-green-100 text-green-700',
    error: 'bg-red-100 text-red-700',
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-muted-foreground text-sm">Meeting transcript → ticket pipeline</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <StatCard title="Teams" value={teams.length} icon={<Users className="h-5 w-5" />} to="/teams" />
        <StatCard title="Transcripts" value={jobs.length} icon={<FileText className="h-5 w-5" />} to="/transcripts" />
        <StatCard title="Tickets" value={ticketCount} icon={<Ticket className="h-5 w-5" />} to="/tickets" />
      </div>

      {teams.length === 0 ? (
        <div className="bg-card border rounded-lg p-8 text-center space-y-3">
          <p className="text-muted-foreground">Start by creating a team and adding members.</p>
          <Link
            to="/teams"
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90"
          >
            Create your first team <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      ) : (
        <div className="bg-card border rounded-lg p-8 text-center space-y-3">
          <p className="text-muted-foreground">Ready to process a meeting transcript.</p>
          <Link
            to="/transcripts"
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90"
          >
            New Transcript <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      )}

      {jobs.length > 0 && (
        <div className="space-y-2">
          <h2 className="font-medium">Recent Transcripts</h2>
          <div className="border rounded-lg divide-y bg-card">
            {jobs.map((job: any) => (
              <div key={job.id} className="flex items-center justify-between px-4 py-3">
                <span className="text-sm">{job.teams?.name ?? '—'}</span>
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLE[job.status] ?? ''}`}>
                  {job.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ title, value, icon, to }: { title: string; value: number; icon: React.ReactNode; to: string }) {
  return (
    <Link to={to} className="bg-card border rounded-lg p-4 hover:bg-muted/30 transition-colors block">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-muted-foreground">{title}</span>
        <span className="text-muted-foreground">{icon}</span>
      </div>
      <p className="text-2xl font-semibold">{value}</p>
    </Link>
  );
}
