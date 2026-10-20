import { db, handle } from "../lib/db.js";
export default (req, res) => handle(res, async () => {
  const s = db();
  const rows = await s`select key, value from run_summary`;
  const areas = await s`select * from area_aggregates order by severity_sum desc`;
  return { summary: Object.fromEntries(rows.map(r => [r.key, r.value])), areas };
});
