import { createFileRoute } from '@tanstack/react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { supabase } from '@/data/supabase';
import { Plus, ChevronDown, ChevronRight, Trash2 } from 'lucide-react';

export const Route = createFileRoute('/teams')({
  component: TeamsPage,
});

function TeamsPage() {
  const qc = useQueryClient();
  const [newTeamName, setNewTeamName] = useState('');
  const [expandedTeam, setExpandedTeam] = useState<string | null>(null);
  const [memberForm, setMemberForm] = useState({ name: '', email: '', role: '' });

  const { data: teams = [], isLoading } = useQuery({
    queryKey: ['teams'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('teams')
        .select('id, name, created_at')
        .order('created_at', { ascending: false });
      if (error) throw error;
      return data;
    },
  });

  const { data: members = [] } = useQuery({
    queryKey: ['team-members', expandedTeam],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('team_members')
        .select('id, name, email, role')
        .eq('team_id', expandedTeam!)
        .order('created_at');
      if (error) throw error;
      return data;
    },
    enabled: !!expandedTeam,
  });

  const createTeam = useMutation({
    mutationFn: async (name: string) => {
      const { data: { user } } = await supabase.auth.getUser();
      const { error } = await supabase.from('teams').insert({ name, created_by: user?.id });
      if (error) throw error;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['teams'] });
      setNewTeamName('');
    },
  });

  const addMember = useMutation({
    mutationFn: async ({ teamId, member }: { teamId: string; member: typeof memberForm }) => {
      const { error } = await supabase.from('team_members').insert({ team_id: teamId, ...member });
      if (error) throw error;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['team-members', expandedTeam] });
      setMemberForm({ name: '', email: '', role: '' });
    },
  });

  const deleteMember = useMutation({
    mutationFn: async (id: string) => {
      const { error } = await supabase.from('team_members').delete().eq('id', id);
      if (error) throw error;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team-members', expandedTeam] }),
  });

  const handleCreateTeam = () => {
    if (newTeamName.trim()) createTeam.mutate(newTeamName.trim());
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Teams</h1>

      <div className="bg-card border rounded-lg p-4 flex gap-3">
        <input
          value={newTeamName}
          onChange={e => setNewTeamName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleCreateTeam()}
          placeholder="New team name…"
          className="flex-1 px-3 py-2 border rounded-md text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <button
          onClick={handleCreateTeam}
          disabled={!newTeamName.trim() || createTeam.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
        >
          <Plus className="h-4 w-4" />
          Create Team
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : teams.length === 0 ? (
        <p className="text-sm text-muted-foreground">No teams yet. Create one above.</p>
      ) : (
        <div className="space-y-3">
          {teams.map((team: any) => (
            <div key={team.id} className="bg-card border rounded-lg overflow-hidden">
              <button
                className="w-full flex items-center justify-between p-4 hover:bg-muted/50 transition-colors text-left"
                onClick={() => setExpandedTeam(expandedTeam === team.id ? null : team.id)}
              >
                <span className="font-medium">{team.name}</span>
                {expandedTeam === team.id
                  ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
              </button>

              {expandedTeam === team.id && (
                <div className="border-t p-4 space-y-4">
                  {members.length > 0 && (
                    <div className="space-y-1.5">
                      {members.map((m: any) => (
                        <div key={m.id} className="flex items-center justify-between py-2 px-3 bg-muted/30 rounded-md">
                          <div className="flex items-center gap-3 text-sm">
                            <span className="font-medium">{m.name}</span>
                            {m.role && <span className="text-muted-foreground">({m.role})</span>}
                            {m.email && <span className="text-muted-foreground">{m.email}</span>}
                          </div>
                          <button
                            onClick={() => deleteMember.mutate(m.id)}
                            className="text-muted-foreground hover:text-destructive transition-colors"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="space-y-2">
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Add Member</p>
                    <div className="grid grid-cols-3 gap-2">
                      <input
                        value={memberForm.name}
                        onChange={e => setMemberForm(f => ({ ...f, name: e.target.value }))}
                        placeholder="Name *"
                        className="px-3 py-2 border rounded-md text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                      />
                      <input
                        value={memberForm.role}
                        onChange={e => setMemberForm(f => ({ ...f, role: e.target.value }))}
                        placeholder="Role"
                        className="px-3 py-2 border rounded-md text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                      />
                      <input
                        value={memberForm.email}
                        onChange={e => setMemberForm(f => ({ ...f, email: e.target.value }))}
                        placeholder="Email"
                        className="px-3 py-2 border rounded-md text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                      />
                    </div>
                    {addMember.isError && (
                      <p className="text-xs text-destructive">{String(addMember.error)}</p>
                    )}
                    <button
                      onClick={() =>
                        memberForm.name.trim() &&
                        addMember.mutate({ teamId: team.id, member: memberForm })
                      }
                      disabled={!memberForm.name.trim() || addMember.isPending}
                      className="flex items-center gap-2 px-3 py-1.5 bg-primary text-primary-foreground rounded-md text-sm hover:bg-primary/90 disabled:opacity-50"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      Add Member
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
