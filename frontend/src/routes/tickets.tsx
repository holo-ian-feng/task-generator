import { createFileRoute, Link } from '@tanstack/react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { supabase } from '@/data/supabase';

export const Route = createFileRoute('/tickets')({
  component: TicketsPage,
});

function TicketsPage() {
  const qc = useQueryClient();
  const [teamFilter, setTeamFilter] = useState('');

  const { data: teams = [] } = useQuery({
    queryKey: ['teams'],
    queryFn: async () => {
      const { data } = await supabase.from('teams').select('id, name').order('name');
      return data ?? [];
    },
  });

  const { data: tickets = [], isLoading } = useQuery({
    queryKey: ['tickets', teamFilter],
    queryFn: async () => {
      let q = supabase
        .from('tickets')
        .select('id, title, description, assignee_name, due_date, status, topic, transcript_job_id, team_members(name), teams(name), created_at')
        .order('created_at', { ascending: false });
      if (teamFilter) q = q.eq('team_id', teamFilter);
      const { data, error } = await q;
      if (error) throw error;
      return data ?? [];
    },
  });

  const toggleStatus = useMutation({
    mutationFn: async ({ id, current }: { id: string; current: string }) => {
      const next = current === 'open' ? 'done' : 'open';
      const { error } = await supabase.from('tickets').update({ status: next }).eq('id', id);
      if (error) throw error;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tickets'] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Tickets</h1>
        <select
          value={teamFilter}
          onChange={e => setTeamFilter(e.target.value)}
          className="px-3 py-2 border rounded-md text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All teams</option>
          {(teams as any[]).map(t => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (tickets as any[]).length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No tickets yet. Submit a transcript to generate some.
        </p>
      ) : (
        <div className="border rounded-lg overflow-hidden bg-card">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 border-b">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium">Topic</th>
                <th className="text-left px-4 py-2.5 font-medium">Title</th>
                <th className="text-left px-4 py-2.5 font-medium">Description</th>
                <th className="text-left px-4 py-2.5 font-medium">Assignee</th>
                <th className="text-left px-4 py-2.5 font-medium">Due Date</th>
                <th className="text-left px-4 py-2.5 font-medium">Status</th>
                <th className="text-left px-4 py-2.5 font-medium">Source</th>
              </tr>
            </thead>
            <tbody>
              {(tickets as any[]).map(ticket => (
                <tr key={ticket.id} className="border-t hover:bg-muted/20">
                  <td className="px-4 py-3">
                    {ticket.topic ? (
                      <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700">
                        {ticket.topic}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-4 py-3 font-medium">{ticket.title}</td>
                  <td className="px-4 py-3 text-muted-foreground max-w-xs">
                    <span className="line-clamp-2">{ticket.description ?? '—'}</span>
                  </td>
                  <td className="px-4 py-3">
                    {ticket.team_members?.name ?? ticket.assignee_name ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{ticket.due_date ?? '—'}</td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => toggleStatus.mutate({ id: ticket.id, current: ticket.status })}
                      className={`px-2.5 py-0.5 rounded-full text-xs font-medium transition-colors ${
                        ticket.status === 'done'
                          ? 'bg-green-100 text-green-700 hover:bg-green-200'
                          : 'bg-blue-100 text-blue-700 hover:bg-blue-200'
                      }`}
                    >
                      {ticket.status}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    {ticket.transcript_job_id ? (
                      <Link
                        to="/transcripts/$jobId"
                        params={{ jobId: ticket.transcript_job_id }}
                        className="text-xs text-primary hover:underline"
                      >
                        Transcript →
                      </Link>
                    ) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
