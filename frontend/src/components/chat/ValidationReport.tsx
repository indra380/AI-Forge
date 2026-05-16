interface ValidationRuleResult {
  rule: string;
  field: string;
  extracted?: unknown;
  expected?: unknown;
  operator: string;
  passed: boolean;
  reason?: string;
}

interface ValidationReportProps {
  rule_name?: string;
  extracted?: Record<string, unknown>;
  results: ValidationRuleResult[];
  passed: boolean;
  violation_count?: number;
  summary?: string;
}

export function ValidationReport({
  rule_name,
  results,
  passed,
  summary,
}: ValidationReportProps) {
  const total = results.length;
  const passing = results.filter((r) => r.passed).length;
  const failing = total - passing;

  return (
    <div className="my-3 w-full max-w-lg rounded-2xl border border-slate-200 bg-white shadow-sm">
      {/* Header */}
      <div
        className={`flex items-center gap-3 rounded-t-2xl px-4 py-3 ${
          passed ? "bg-emerald-50" : "bg-rose-50"
        }`}
      >
        <span className="text-xl">{passed ? "✅" : "❌"}</span>
        <div className="flex-1">
          <div className="font-semibold text-slate-800">
            {rule_name ?? "Validation Report"}
          </div>
          <div className="text-xs text-slate-500">
            {passing}/{total} rules passed
            {failing > 0 && ` · ${failing} violation${failing > 1 ? "s" : ""}`}
          </div>
        </div>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-bold ${
            passed
              ? "bg-emerald-100 text-emerald-700"
              : "bg-rose-100 text-rose-700"
          }`}
        >
          {passed ? "PASS" : "FAIL"}
        </span>
      </div>

      {/* Rules list */}
      {results.length > 0 && (
        <div className="divide-y divide-slate-100 px-4">
          {results.map((r, idx) => (
            <div key={idx} className="flex items-start gap-3 py-2.5">
              <span className="mt-0.5 text-sm">
                {r.passed ? "✅" : "❌"}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-slate-700 truncate">
                  {r.rule}
                </div>
                {!r.passed && (
                  <div className="mt-0.5 text-xs text-rose-600">
                    {r.reason
                      ? r.reason
                      : `Found: ${JSON.stringify(r.extracted)} · Expected ${r.operator} ${JSON.stringify(r.expected)}`}
                  </div>
                )}
                {r.passed && r.extracted !== undefined && (
                  <div className="mt-0.5 text-xs text-slate-400">
                    Extracted: {JSON.stringify(r.extracted)}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Summary */}
      {summary && (
        <div className="rounded-b-2xl border-t border-slate-100 bg-slate-50 px-4 py-2 text-xs text-slate-500">
          {summary}
        </div>
      )}
    </div>
  );
}
