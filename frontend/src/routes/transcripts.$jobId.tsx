import { createFileRoute, Link } from '@tanstack/react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { ArrowLeft, ExternalLink, ChevronRight } from 'lucide-react';
import { supabase } from '@/data/supabase';

export const Route = createFileRoute('/transcripts/$jobId')({
  component: TranscriptDetailPage,
});

const STATUS_STYLE: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-700',
  processing: 'bg-yellow-100 text-yellow-700',
  complete: 'bg-green-100 text-green-700',
  error: 'bg-red-100 text-red-700',
};

function TranscriptDetailPage() {
  const { jobId } = Route.useParams();
  const qc = useQueryClient();
  const [showFull, setShowFull] = useState(false);

  const { data: job, isLoading } = useQuery({
    queryKey: ['transcript-job', jobId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('transcript_jobs')
        .select('id, status, error_msg, transcript, created_at, teams(name)')
        .eq('id', jobId)
        .single();
      if (error) throw error;
      return data;
    },
    refetchInterval: (query) => {
      const s = (query.state.data as any)?.status;
      return s === 'pending' || s === 'processing' ? 3000 : false;
    },
  });

  const { data: taskFlows = [] } = useQuery({
    queryKey: ['job-task-flows', jobId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('task_flows')
        .select(`id, title, topic, task_flow_steps(id, title, description, step_order, assignee_name, due_date, status)`)
        .eq('transcript_job_id', jobId)
        .order('created_at', { ascending: true });
      if (error) throw error;
      return (data ?? []).map((f: any) => ({
        ...f,
        task_flow_steps: [...(f.task_flow_steps ?? [])].sort((a: any, b: any) => a.step_order - b.step_order),
      }));
    },
    refetchInterval: (query) => (!query.state.data || query.state.data.length === 0 ? 4000 : false),
  });

  const advanceStep = useMutation({
    mutationFn: async ({ id, current }: { id: string; current: string }) => {
      const next = current === 'pending' ? 'in_progress' : current === 'in_progress' ? 'done' : 'pending';
      const { error } = await supabase.from('task_flow_steps').update({ status: next }).eq('id', id);
      if (error) throw error;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['job-task-flows', jobId] }),
  });

  const { data: tickets = [] } = useQuery({
    queryKey: ['job-tickets', jobId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('tickets')
        .select('id, title, description, assignee_name, due_date, status, topic, created_at')
        .eq('transcript_job_id', jobId)
        .order('topic', { ascending: true })
        .order('created_at', { ascending: true });
      if (error) throw error;
      return data ?? [];
    },
    refetchInterval: (query) => {
      const hasTickets = (query.state.data ?? []).length > 0;
      return hasTickets ? false : 4000;
    },
  });

  const toggleStatus = useMutation({
    mutationFn: async ({ id, current }: { id: string; current: string }) => {
      const next = current === 'open' ? 'done' : 'open';
      const { error } = await supabase.from('tickets').update({ status: next }).eq('id', id);
      if (error) throw error;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['job-tickets', jobId] });
      qc.invalidateQueries({ queryKey: ['tickets'] });
    },
  });

  const byTopic = (tickets as any[]).reduce<Record<string, any[]>>((acc, t) => {
    const key = t.topic ?? 'General';
    (acc[key] ??= []).push(t);
    return acc;
  }, {});

  const temporalUrl = `http://localhost:8080/namespaces/default/workflows?query=WorkflowId%3D%22transcript-${jobId}%22`;

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (!job) return <p className="text-sm text-destructive">Job not found.</p>;

  const jobAny = job as any;
  const text: string = jobAny.transcript ?? '';
  const isTruncated = text.length > 400;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/transcripts" className="text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <h1 className="text-2xl font-semibold">Transcript Detail</h1>
      </div>

      {/* Job metadata */}
      <div className="bg-card border rounded-lg p-5 space-y-4">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">
              Team: <span className="text-foreground font-medium">{jobAny.teams?.name ?? '—'}</span>
              <span className="mx-2">·</span>
              Submitted: <span className="text-foreground">{new Date(jobAny.created_at).toLocaleString()}</span>
            </p>
            {jobAny.status === 'error' && jobAny.error_msg && (
              <p className="text-xs text-destructive">{jobAny.error_msg}</p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${STATUS_STYLE[jobAny.status] ?? ''}`}>
              {jobAny.status}
            </span>
            <a
              href={temporalUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs border rounded-md hover:bg-muted transition-colors"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              View in Temporal
            </a>
          </div>
        </div>

        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1.5 uppercase tracking-wide">Transcript</p>
          <p className="text-sm font-mono whitespace-pre-wrap text-muted-foreground leading-relaxed bg-muted/30 rounded p-3">
            {showFull || !isTruncated ? text : text.slice(0, 400) + '…'}
          </p>
          {isTruncated && (
            <button
              onClick={() => setShowFull(v => !v)}
              className="text-xs text-primary hover:underline mt-1.5"
            >
              {showFull ? 'Show less' : 'Show full transcript'}
            </button>
          )}
        </div>
      </div>

      {/* Task Flows */}
      {(taskFlows as any[]).length > 0 && (
        <div className="space-y-3">
          <h2 className="font-medium">Task Flows
            <span className="ml-2 text-sm text-muted-foreground font-normal">
              {(taskFlows as any[]).length} flow{(taskFlows as any[]).length !== 1 ? 's' : ''}
            </span>
          </h2>
          {(taskFlows as any[]).map((flow: any) => (
            <div key={flow.id} className="border rounded-lg bg-card overflow-hidden">
              <div className="px-4 py-2.5 bg-muted/50 border-b flex items-center gap-2">
                {flow.topic && (
                  <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700">{flow.topic}</span>
                )}
                <span className="font-medium text-sm">{flow.title}</span>
              </div>
              <div className="p-4 overflow-x-auto">
                <div className="flex items-start gap-1 min-w-max">
                  {(flow.task_flow_steps as any[]).map((step: any, i: number) => (
                    <div key={step.id} className="flex items-start gap-1">
                      <div className="w-40 border rounded-lg p-3 space-y-2 bg-background">
                        <div className="flex items-start justify-between gap-1">
                          <span className="text-sm font-medium leading-snug">{step.title}</span>
                          <span className="text-xs text-muted-foreground flex-shrink-0">#{step.step_order}</span>
                        </div>
                        {step.description && (
                          <p className="text-xs text-muted-foreground line-clamp-2">{step.description}</p>
                        )}
                        <div className="space-y-0.5 text-xs text-muted-foreground">
                          {step.assignee_name && <p>👤 {step.assignee_name}</p>}
                          {step.due_date && <p>📅 {step.due_date}</p>}
                        </div>
                        <button
                          onClick={() => advanceStep.mutate({ id: step.id, current: step.status })}
                          className={`w-full px-2 py-0.5 rounded-full text-xs font-medium transition-colors ${
                            step.status === 'done' ? 'bg-green-100 text-green-700' :
                            step.status === 'in_progress' ? 'bg-yellow-100 text-yellow-700' :
                            'bg-gray-100 text-gray-600'
                          }`}
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

      {/* Topics & tickets */}
      <div className="space-y-3">
        <h2 className="font-medium">
          Topics &amp; Tickets
          {(tickets as any[]).length > 0 && (
            <span className="ml-2 text-sm text-muted-foreground font-normal">
              {Object.keys(byTopic).length} topic{Object.keys(byTopic).length !== 1 ? 's' : ''}
              {' · '}
              {(tickets as any[]).length} ticket{(tickets as any[]).length !== 1 ? 's' : ''}
            </span>
          )}
        </h2>

        {jobAny.status !== 'complete' && (tickets as any[]).length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {jobAny.status === 'error'
              ? 'Workflow failed — no tickets were generated.'
              : 'Processing… tickets will appear here once the workflow completes.'}
          </p>
        ) : Object.keys(byTopic).length === 0 ? (
          <p className="text-sm text-muted-foreground">No tickets generated.</p>
        ) : (
          Object.entries(byTopic).map(([topic, topicTickets]) => (
            <div key={topic} className="border rounded-lg overflow-hidden bg-card">
              <div className="px-4 py-2.5 bg-muted/50 border-b flex items-center gap-2">
                <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700">
                  {topic}
                </span>
                <span className="text-xs text-muted-foreground">
                  {topicTickets.length} ticket{topicTickets.length !== 1 ? 's' : ''}
                </span>
              </div>
              <table className="w-full text-sm">
                <thead className="border-b">
                  <tr>
                    <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Title</th>
                    <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Description</th>
                    <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Assignee</th>
                    <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Due Date</th>
                    <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(topicTickets as any[]).map((ticket: any) => (
                    <tr key={ticket.id} className="border-t hover:bg-muted/20">
                      <td className="px-4 py-3 font-medium">{ticket.title}</td>
                      <td className="px-4 py-3 text-muted-foreground max-w-xs">
                        <span className="line-clamp-2">{ticket.description ?? '—'}</span>
                      </td>
                      <td className="px-4 py-3">{ticket.assignee_name ?? '—'}</td>
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
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
