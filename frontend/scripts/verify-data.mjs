/**
 * Verifies that every quantity in src/data/run.ts matches the repository
 * artifact it claims to come from. The landing page's argument is that its
 * numbers are real; this is how that claim stays true as the repo moves.
 *
 *   node scripts/verify-data.mjs
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, '../..')

const results = JSON.parse(readFileSync(resolve(repo, 'data/eval/results.json'), 'utf8'))
const golden = JSON.parse(readFileSync(resolve(repo, 'data/eval/golden_incidents.json'), 'utf8'))
const ts = readFileSync(resolve(here, '../src/data/run.ts'), 'utf8')

const problems = []
const checked = []

function has(needle, what) {
  if (ts.includes(needle)) checked.push(what)
  else problems.push(`${what}: expected \`${needle}\` in run.ts`)
}

// ── Aggregates ───────────────────────────────────────────────────────────
has(`totalIncidents: ${results.total_incidents}`, 'RUN.totalIncidents')
has(`passedIncidents: ${results.passed_incidents}`, 'RUN.passedIncidents')
has(`passRate: ${results.pass_rate}`, 'RUN.passRate')
has(`avgBlastRadius: ${results.average_blast_radius_accuracy}`, 'RUN.avgBlastRadius')
has(`avgRootCause: ${results.average_root_cause_score}`, 'RUN.avgRootCause')
has(`avgFaithfulness: ${results.average_faithfulness_score}`, 'RUN.avgFaithfulness')
has(`totalLatencyMs: ${results.total_latency_ms}`, 'RUN.totalLatencyMs')

// total_tokens was recorded as 0 for every specimen — the counter was never
// wired. The page must report it unread, never print a zero as a measurement.
if (results.total_tokens === 0 && !ts.includes('totalTokens: null')) {
  problems.push('RUN.totalTokens: results.json recorded 0; run.ts must carry null, not 0')
} else {
  checked.push('RUN.totalTokens is null (unread, not zero)')
}

// ── Per specimen ─────────────────────────────────────────────────────────
const goldenById = new Map(golden.map((g) => [g.incident_id, g]))

for (const r of results.results) {
  const g = goldenById.get(r.incident_id)
  if (!g) {
    problems.push(`${r.incident_id}: present in results.json but not in golden_incidents.json`)
    continue
  }

  const block = sliceBlock(r.incident_id)
  if (!block) {
    problems.push(`${r.incident_id}: no matching specimen block in run.ts`)
    continue
  }

  const field = (needle, what) => {
    if (block.includes(needle)) checked.push(`${r.incident_id} ${what}`)
    else problems.push(`${r.incident_id} ${what}: expected \`${needle}\``)
  }

  field(`service: '${r.service_id}'`, 'service')
  field(`confidence: ${r.confidence_score}`, 'confidence')
  field(`latencyMs: ${r.latency_ms}`, 'latencyMs')
  field(`toolLatencyMs: ${r.total_tool_latency_ms}`, 'toolLatencyMs')
  field(`calls: ${r.total_tool_calls}`, 'calls')
  field(`failedCalls: ${r.failed_tool_calls}`, 'failedCalls')
  field(`overlap: ${r.root_cause_overlap_score}`, 'overlap')
  field(`faithfulness: ${r.faithfulness_score}`, 'faithfulness')
  field(`blastRadius: ${r.blast_radius_accuracy}`, 'blastRadius')
  field(`passed: ${r.passed_evaluation}`, 'passed')

  // Alert text and label are quoted prose — compare with quotes normalised and
  // line wrapping collapsed, since Prettier may fold long strings.
  const flat = block.replace(/\s+/g, ' ')
  for (const [value, what] of [
    [g.alert_message, 'alert'],
    [g.expected_root_cause, 'label'],
  ]) {
    if (flat.includes(value)) checked.push(`${r.incident_id} ${what}`)
    else problems.push(`${r.incident_id} ${what}: run.ts text does not match golden set\n    want: ${value}`)
  }

  field(`difficulty: '${g.difficulty}'`, 'difficulty')
  for (const t of g.tags) field(`'${t}'`, `tag ${t}`)
  for (const s of g.expected_blast_radius) field(`'${s}'`, `blast member ${s}`)
}

function sliceBlock(id) {
  const start = ts.indexOf(`id: '${id}'`)
  if (start === -1) return null
  const end = ts.indexOf('\n  },', start)
  return end === -1 ? ts.slice(start) : ts.slice(start, end)
}

// ── Report ───────────────────────────────────────────────────────────────
if (problems.length) {
  console.error(`\n  ${problems.length} data mismatch(es) against the repository:\n`)
  for (const p of problems) console.error(`  ✗ ${p}`)
  console.error(`\n  ${checked.length} value(s) verified.\n`)
  process.exit(1)
}

console.log(`\n  ${checked.length} values verified against data/eval/*.json — no drift.\n`)
