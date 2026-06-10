import { createFileRoute, Link } from '@tanstack/react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { supabase } from '@/data/supabase';
import { Send, RefreshCw } from 'lucide-react';

export const Route = createFileRoute('/transcripts')({
  component: TranscriptsPage,
});

const STATUS_STYLE: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-700',
  processing: 'bg-yellow-100 text-yellow-700',
  complete: 'bg-green-100 text-green-700',
  error: 'bg-red-100 text-red-700',
};

function TranscriptsPage() {
  const qc = useQueryClient();
  const [selectedTeam, setSelectedTeam] = useState('');
  const [transcript, setTranscript] = useState('');

  const { data: teams = [] } = useQuery({
    queryKey: ['teams'],
    queryFn: async () => {
      const { data, error } = await supabase.from('teams').select('id, name').order('name');
      if (error) throw error;
      return data;
    },
  });

  const { data: jobs = [] } = useQuery({
    queryKey: ['transcript-jobs'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('transcript_jobs')
        .select('id, status, error_msg, created_at, teams(name), tickets(count)')
        .order('created_at', { ascending: false })
        .limit(20);
      if (error) throw error;
      return data ?? [];
    },
    refetchInterval: (query) => {
      const data = query.state.data ?? [];
      const hasActive = (data as any[]).some(
        j => j.status === 'pending' || j.status === 'processing',
      );
      return hasActive ? 4000 : false;
    },
  });

  const submit = useMutation({
    mutationFn: async () => {
      const { data: { user } } = await supabase.auth.getUser();
      const { error } = await supabase.from('transcript_jobs').insert({
        team_id: selectedTeam,
        transcript: transcript.trim(),
        submitted_by: user?.id,
      });
      if (error) throw error;
    },
    onSuccess: () => {
      setTranscript('');
      qc.invalidateQueries({ queryKey: ['transcript-jobs'] });
    },
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Transcripts</h1>

      <div className="bg-card border rounded-lg p-5 space-y-4">
        <h2 className="font-medium">Submit Meeting Transcript</h2>

        <select
          value={selectedTeam}
          onChange={e => setSelectedTeam(e.target.value)}
          className="w-full px-3 py-2 border rounded-md text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">Select a team…</option>
          {(teams as any[]).map(t => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>

        <textarea
          value={transcript}
          onChange={e => setTranscript(e.target.value)}
          placeholder="Paste your meeting transcript here…"
          rows={10}
          className="w-full px-3 py-2 border rounded-md text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring resize-none font-mono"
        />

        {submit.isError && (
          <p className="text-sm text-destructive">{String(submit.error)}</p>
        )}

        <button
          onClick={() => submit.mutate()}
          disabled={!selectedTeam || !transcript.trim() || submit.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
        >
          <Send className="h-4 w-4" />
          {submit.isPending ? 'Submitting…' : 'Process Transcript'}
        </button>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Job History</h2>
          <button
            onClick={() => qc.invalidateQueries({ queryKey: ['transcript-jobs'] })}
            className="text-muted-foreground hover:text-foreground transition-colors"
            title="Refresh"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>

        {(jobs as any[]).length === 0 ? (
          <p className="text-sm text-muted-foreground">No jobs yet.</p>
        ) : (
          <div className="border rounded-lg overflow-hidden bg-card">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 border-b">
                <tr>
                  <th className="text-left px-4 py-2.5 font-medium">Team</th>
                  <th className="text-left px-4 py-2.5 font-medium">Status</th>
                  <th className="text-left px-4 py-2.5 font-medium">Tickets</th>
                  <th className="text-left px-4 py-2.5 font-medium">Submitted</th>
                  <th className="px-4 py-2.5"></th>
                </tr>
              </thead>
              <tbody>
                {(jobs as any[]).map(job => {
                  const ticketCount = job.tickets?.[0]?.count ?? 0;
                  return (
                    <tr key={job.id} className="border-t hover:bg-muted/20">
                      <td className="px-4 py-3">{job.teams?.name ?? '—'}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLE[job.status] ?? ''}`}>
                          {job.status}
                        </span>
                        {job.status === 'error' && job.error_msg && (
                          <span className="ml-2 text-xs text-destructive">{job.error_msg}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {ticketCount > 0 ? ticketCount : '—'}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {new Date(job.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          to="/transcripts/$jobId"
                          params={{ jobId: job.id }}
                          className="text-xs text-primary hover:underline"
                        >
                          View →
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
