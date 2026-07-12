import React, { useCallback, useEffect, useState } from 'react';
import { Users, CheckCircle, XCircle, Spinner, Warning } from '@phosphor-icons/react';
import { adminListUsers, adminApproveUser, adminRejectUser } from '../services/auth';

/**
 * Admin Users panel — list users with role/status, Approve / Reject
 * actions. Visible only when the logged-in user has role === 'admin'.
 */
function StatusBadge({ status }) {
  const cls = {
    pending:  'bg-yellow-500/10 border-yellow-500/40 text-yellow-300',
    approved: 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300',
    rejected: 'bg-red-500/10 border-red-500/40 text-red-300',
  }[status] || 'bg-zinc-500/10 border-zinc-500/40 text-zinc-300';
  return (
    <span
      data-testid={`admin-status-${status}`}
      className={`text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded border ${cls}`}
    >
      {status}
    </span>
  );
}

export default function AdminUsers() {
  const [users, setUsers] = useState([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [actioningId, setActioningId] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await adminListUsers(statusFilter || undefined);
      setUsers(res.users || []);
    } catch (e) {
      setError(e.message || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  const approve = async (id) => {
    setActioningId(id); setError(null);
    try {
      await adminApproveUser(id);
      await load();
    } catch (e) { setError(e.message); }
    finally { setActioningId(null); }
  };
  const reject = async (id) => {
    setActioningId(id); setError(null);
    try {
      await adminRejectUser(id);
      await load();
    } catch (e) { setError(e.message); }
    finally { setActioningId(null); }
  };

  return (
    <div className="space-y-4" data-testid="admin-users">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="font-heading text-xl font-bold text-zinc-100 flex items-center gap-2">
            <Users size={20} className="text-accent-primary" weight="bold" />
            User Management
          </h2>
          <p className="text-xs text-zinc-500 mt-1 max-w-3xl">
            Approve or reject signups. Only approved users can log in and access the system.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            data-testid="admin-status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-[#0B0F14] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:border-accent-primary/40"
          >
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
          <button
            data-testid="admin-refresh-btn"
            onClick={load}
            className="text-xs font-semibold px-3 py-1.5 rounded border border-zinc-700 bg-zinc-800/60 hover:bg-zinc-800 text-zinc-200"
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div
          data-testid="admin-error"
          className="flex items-start gap-2 rounded border border-red-500/30 bg-red-500/10 text-red-300 text-xs px-3 py-2"
        >
          <Warning size={14} className="mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <div
        className="rounded-md border border-zinc-800 bg-[#121821] overflow-hidden"
        data-testid="admin-users-table"
      >
        <div className="px-3 py-2 bg-zinc-900/60 text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
          Users ({users.length})
        </div>
        <table className="w-full text-xs">
          <thead className="text-[9px] font-mono uppercase tracking-[0.2em] text-zinc-500">
            <tr>
              <th className="text-left px-3 py-2">Email</th>
              <th className="text-left px-3 py-2">Role</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-left px-3 py-2">Created</th>
              <th className="text-right px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {loading && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-zinc-500 font-mono text-xs">
                  <Spinner size={16} className="inline animate-spin mr-2" /> Loading…
                </td>
              </tr>
            )}
            {!loading && users.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-zinc-500 font-mono text-xs">
                  No users match the current filter.
                </td>
              </tr>
            )}
            {!loading && users.map((u) => {
              const isAdmin = u.role === 'admin';
              const busy = actioningId === u.user_id;
              return (
                <tr
                  key={u.user_id}
                  data-testid={`admin-user-${u.user_id}`}
                  className="hover:bg-zinc-900/40 transition-colors"
                >
                  <td className="px-3 py-2 font-mono text-zinc-200">{u.email}</td>
                  <td className="px-3 py-2">
                    <span className={`text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded border ${
                      isAdmin
                        ? 'bg-accent-primary/10 border-accent-primary/40 text-accent-primary'
                        : 'bg-zinc-500/10 border-zinc-500/40 text-zinc-400'
                    }`}>
                      {u.role}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge status={u.status} />
                  </td>
                  <td className="px-3 py-2 font-mono text-[10px] text-zinc-500">
                    {u.created_at ? new Date(u.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <div className="inline-flex items-center gap-2">
                      <button
                        data-testid={`admin-approve-${u.user_id}`}
                        disabled={isAdmin || busy || u.status === 'approved'}
                        onClick={() => approve(u.user_id)}
                        className="text-[11px] font-semibold px-2 py-1 rounded border border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1"
                      >
                        {busy ? <Spinner size={12} className="animate-spin" /> : <CheckCircle size={12} weight="bold" />}
                        Approve
                      </button>
                      <button
                        data-testid={`admin-reject-${u.user_id}`}
                        disabled={isAdmin || busy || u.status === 'rejected'}
                        onClick={() => reject(u.user_id)}
                        className="text-[11px] font-semibold px-2 py-1 rounded border border-red-500/40 bg-red-500/10 hover:bg-red-500/20 text-red-300 disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1"
                      >
                        {busy ? <Spinner size={12} className="animate-spin" /> : <XCircle size={12} weight="bold" />}
                        Reject
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
