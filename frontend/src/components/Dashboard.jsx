import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getStats } from "../services/api";

function StatCard({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function ChartCard({ title, children, empty }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-700">{title}</h3>
      {empty ? (
        <p className="flex h-56 items-center justify-center text-sm text-slate-400">No data yet</p>
      ) : (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            {children}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getStats().then(setStats).catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="p-6 text-sm text-red-600">{error}</p>;
  if (!stats) return <p className="p-6 text-sm text-slate-500">Loading dashboard…</p>;

  const { totals } = stats;
  const perQuestion = stats.per_question.map((q, i) => ({ ...q, label: `Q${i + 1}` }));

  return (
    <div className="h-full space-y-4 overflow-y-auto p-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Documents" value={totals.documents} />
        <StatCard label="Chunks" value={totals.chunks} />
        <StatCard label="Questions" value={totals.questions} />
        <StatCard
          label="Avg speed"
          value={totals.avg_tokens_per_sec == null ? "—" : `${Math.round(totals.avg_tokens_per_sec)} tok/s`}
        />
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ChartCard title="Response time per question (ms)" empty={perQuestion.length === 0}>
          <LineChart data={perQuestion}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="label" fontSize={12} />
            <YAxis fontSize={12} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="ttft_ms" name="First token" stroke="#f59e0b" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="total_ms" name="Total" stroke="#4f46e5" strokeWidth={2} dot={false} />
          </LineChart>
        </ChartCard>
        <ChartCard title="Output speed per question (tokens/sec)" empty={perQuestion.length === 0}>
          <BarChart data={perQuestion}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="label" fontSize={12} />
            <YAxis fontSize={12} />
            <Tooltip />
            <Bar dataKey="tokens_per_sec" name="tokens/sec" fill="#f59e0b" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartCard>
        <ChartCard title="Questions per day" empty={stats.questions_per_day.length === 0}>
          <BarChart data={stats.questions_per_day}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" fontSize={12} />
            <YAxis allowDecimals={false} fontSize={12} />
            <Tooltip />
            <Bar dataKey="count" name="Questions" fill="#4f46e5" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartCard>
        <ChartCard title="Chunks per document" empty={stats.chunks_per_document.length === 0}>
          <BarChart data={stats.chunks_per_document} layout="vertical" margin={{ left: 24 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis type="number" allowDecimals={false} fontSize={12} />
            <YAxis type="category" dataKey="filename" width={120} fontSize={12} />
            <Tooltip />
            <Bar dataKey="chunks" name="Chunks" fill="#10b981" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ChartCard>
      </div>
    </div>
  );
}
