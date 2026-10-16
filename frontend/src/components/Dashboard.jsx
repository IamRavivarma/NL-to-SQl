import { FileText, Gauge, Layers, MessageSquare, Zap } from "lucide-react";
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
import { formatSeconds } from "../lib/format";
import { getStats } from "../services/api";

// Validated with the dataviz palette checker (light surface): both series pass CVD and contrast checks.
const SERIES = { primary: "#4f46e5", secondary: "#d97706" };
const AXIS = { fontSize: 12, fill: "#5c6378" };
const GRID = "#e3e6ed";
const TOOLTIP = {
  contentStyle: { borderRadius: 10, border: "1px solid #e3e6ed", fontSize: 13, color: "#171a2c" },
  cursor: { fill: "#eef0ff" },
};

function StatCard({ icon: Icon, label, value, hint }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="flex items-center gap-2 text-sm text-muted">
        <Icon className="size-4 text-accent" aria-hidden="true" />
        {label}
      </div>
      <p className="tabular mt-2 text-[1.75rem] font-semibold leading-none tracking-tight">{value}</p>
      {hint && <p className="mt-1.5 text-xs text-muted">{hint}</p>}
    </div>
  );
}

function ChartCard({ title, description, children, empty }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-5">
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-0.5 text-sm text-muted">{description}</p>
      {empty ? (
        <p className="mt-4 grid h-56 place-items-center rounded-lg bg-canvas text-sm text-muted">
          Ask a few questions to see this chart.
        </p>
      ) : (
        <div className="mt-4 h-56">
          <ResponsiveContainer width="100%" height="100%">
            {children}
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getStats().then(setStats).catch((err) => setError(err.message));
  }, []);

  if (error) {
    return (
      <p role="alert" className="m-6 rounded-lg bg-red-50 px-4 py-2 text-sm text-red-700">
        Couldn't load the dashboard: {error}
      </p>
    );
  }
  if (!stats) return <p className="p-6 text-sm text-muted">Loading dashboard…</p>;

  const { totals } = stats;
  const perQuestion = stats.per_question.map((q, i) => ({ ...q, label: `Q${i + 1}` }));
  const noAnswers = perQuestion.length === 0;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-6 px-6 pb-10 pt-6">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">How fast are the answers?</h2>
          <p className="mt-1 text-muted">Every answer is timed, from the moment you ask to the last word.</p>
        </div>

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <StatCard icon={FileText} label="Documents" value={totals.documents} />
          <StatCard icon={Layers} label="Chunks" value={totals.chunks} />
          <StatCard icon={MessageSquare} label="Questions" value={totals.questions} />
          <StatCard
            icon={Zap}
            label="First word"
            value={formatSeconds(totals.avg_ttft_ms)}
            hint="Average wait before text appears"
          />
          <StatCard
            icon={Gauge}
            label="Output speed"
            value={totals.avg_tokens_per_sec == null ? "—" : `${Math.round(totals.avg_tokens_per_sec)} tok/s`}
            hint="Average tokens per second"
          />
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <ChartCard
            title="Response time per question"
            description="Milliseconds until the first word, and until the answer finished."
            empty={noAnswers}
          >
            <LineChart data={perQuestion} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} />
              <Tooltip {...TOOLTIP} cursor={{ stroke: GRID }} />
              <Legend iconType="plainline" wrapperStyle={{ fontSize: 13, color: "#5c6378" }} />
              <Line isAnimationActive={false} type="monotone" dataKey="ttft_ms" name="First word" stroke={SERIES.secondary} strokeWidth={2} dot={{ r: 4 }} />
              <Line isAnimationActive={false} type="monotone" dataKey="total_ms" name="Finished" stroke={SERIES.primary} strokeWidth={2} dot={{ r: 4 }} />
            </LineChart>
          </ChartCard>

          <ChartCard title="Output speed per question" description="Tokens generated per second." empty={noAnswers}>
            <BarChart data={perQuestion} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} />
              <Tooltip {...TOOLTIP} />
              <Bar isAnimationActive={false} dataKey="tokens_per_sec" name="Tokens/sec" fill={SERIES.primary} radius={[4, 4, 0, 0]} maxBarSize={40} />
            </BarChart>
          </ChartCard>

          <ChartCard
            title="Questions per day"
            description="How often the assistant was asked something."
            empty={stats.questions_per_day.length === 0}
          >
            <BarChart data={stats.questions_per_day} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="date" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
              <YAxis allowDecimals={false} tick={AXIS} tickLine={false} axisLine={false} />
              <Tooltip {...TOOLTIP} />
              <Bar isAnimationActive={false} dataKey="count" name="Questions" fill={SERIES.primary} radius={[4, 4, 0, 0]} maxBarSize={40} />
            </BarChart>
          </ChartCard>

          <ChartCard
            title="Chunks per document"
            description="How many searchable pieces each upload was split into."
            empty={stats.chunks_per_document.length === 0}
          >
            <BarChart data={stats.chunks_per_document} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
              <CartesianGrid stroke={GRID} horizontal={false} />
              <XAxis type="number" allowDecimals={false} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
              <YAxis type="category" dataKey="filename" width={120} tick={AXIS} tickLine={false} axisLine={false} />
              <Tooltip {...TOOLTIP} />
              <Bar isAnimationActive={false} dataKey="chunks" name="Chunks" fill={SERIES.primary} radius={[0, 4, 4, 0]} maxBarSize={28} />
            </BarChart>
          </ChartCard>
        </div>
      </div>
    </div>
  );
}
