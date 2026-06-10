import { createFileRoute, Link } from '@tanstack/react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { supabase } from '@/data/supabase';

export const Route = createFileRoute('/workflows')({
  component: WorkflowsPage,
});

const STEP_STATUS_STYLE: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-600',
  in_progress: 'bg-yellow-100 text-yellow-700',
  done: 'bg-green-100 text-green-700',
};

const STEP_STATUS_NEXT: Record<string, string> = {
  pending: 'in_progress',
  in_progress: 'done',
  done: 'pending',
};

function WorkflowsPage() {
  const qc = useQueryClient();
  const [teamFilter, setTeamFilter] = useState('');

  const { data: teams = [] } = useQuery({
    queryKey: ['teams'],
    queryFn: async () => {
      const { data } = await supabase.from('teams').select('id, name').order('name');
      return data ?? [];
    },
  });

  const { data: flows = [], isLoading } = useQuery({
    queryKey: ['task-flows', teamFilter],
    queryFn: async () => {
      let q = supabase
        .from('task_flows')
        .select(`
          id, title, topic, created_at, transcript_job_id,
          teams(name),
          task_flow_steps(id, title, description, step_order, assignee_name, due_date, status)
        `)
        .order('created_at', { ascending: false });
      if (teamFilter) q = q.eq('team_id', teamFilter);
      const { data, error } = await q;
      if (error) throw error;
      return (data ?? []).map((f: any) => ({
        ...f,
        task_flow_steps: [...(f.task_flow_steps ?? [])].sort(
          (a: any, b: any) => a.step_order - b.step_order,
        ),
      }));
    },
  });

  const advanceStep = useMutation({
    mutationFn: async ({ id, current }: { id: string; current: string }) => {
      const next = STEP_STATUS_NEXT[current] ?? 'pending';
      const { error } = await supabase.from('task_flow_steps').update({ status: next }).eq('id', id);
      if (error) throw error;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['task-flows'] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Task Flows</h1>
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
      ) : (flows as any[]).length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No task flows yet. Submit a transcript with sequential tasks (e.g. "first do X, then Y") to generate one.
        </p>
      ) : (
        <div className="space-y-4">
          {(flows as any[]).map(flow => (
            <div key={flow.id} className="border rounded-lg bg-card overflow-hidden">
              <div className="px-5 py-3 border-b bg-muted/50 flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2">
                  {flow.topic && (
                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700">
                      {flow.topic}
                    </span>
                  )}
                  <span className="font-medium">{flow.title}</span>
                  <span className="text-xs text-muted-foreground">
                    {flow.teams?.name} · {new Date(flow.created_at).toLocaleDateString()}
                  </span>
                </div>
                {flow.transcript_job_id && (
                  <Link
                    to="/transcripts/$jobId"
                    params={{ jobId: flow.transcript_job_id }}
                    className="text-xs text-primary hover:underline"
                  >
                    View transcript →
                  </Link>
                )}
              </div>

              <div className="p-5 overflow-x-auto">
                <div className="flex items-start gap-1 min-w-max">
                  {(flow.task_flow_steps as any[]).map((step: any, i: number) => (
                    <div key={step.id} className="flex items-start gap-1">
                      <div className="w-44 border rounded-lg p-3 space-y-2 bg-background">
                        <div className="flex items-start justify-between gap-1">
                          <span className="text-sm font-medium leading-snug">{step.title}</span>
                          <span className="text-xs text-muted-foreground flex-shrink-0">#{step.step_order}</span>
                        </div>
                        {step.description && (
                          <p className="text-xs text-muted-foreground line-clamp-2">{step.description}</p>
                        )}
                        <div className="space-y-1 text-xs text-muted-foreground">
                          {step.assignee_name && <p>👤 {step.assignee_name}</p>}
                          {step.due_date && <p>📅 {step.due_date}</p>}
                        </div>
                        <button
                          onClick={() => advanceStep.mutate({ id: step.id, current: step.status })}
                          className={`w-full px-2 py-0.5 rounded-full text-xs font-medium transition-colors ${STEP_STATUS_STYLE[step.status] ?? ''}`}
                        >
                          {step.status.replace('_', ' ')}
                        </button>
                      </div>
                      {i < (flow.task_flow_steps as any[]).length - 1 && (
                        <ChevronRight className="h-5 w-5 mt-4 text-muted-foreground flex-shrink-0" />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
