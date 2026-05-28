interface StatCardProps {
  label: string;
  value: number | string;
  sub?: string;
  color?: "default" | "yellow" | "green" | "red" | "orange";
}

const COLOR_MAP = {
  default: "text-gray-900",
  yellow: "text-yellow-600",
  green: "text-green-600",
  red: "text-red-600",
  orange: "text-orange-600",
};

export default function StatCard({ label, value, sub, color = "default" }: StatCardProps) {
  return (
    <div className="card px-5 py-4">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{label}</p>
      <p className={`mt-1 text-3xl font-bold tabular-nums ${COLOR_MAP[color]}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-400">{sub}</p>}
    </div>
  );
}
