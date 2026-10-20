import { db, handle } from "../lib/db.js";
export default (req, res) => handle(res, async () => {
  const id = String(req.query.id || "");
  const s = db();
  const [issue] = await s`select i.*, r.rank, r.complaint_count, r.severity_sum, r.mean_severity, r.priority_score
                          from issues i left join ranking r using (issue_id) where issue_id = ${id}`;
  if (!issue) return { error: "not found" };
  const claims = await s`select claim_id, metric, value from claims where issue_id = ${id} order by claim_id`;
  const reviews = await s`select review_id, intent, severity, sentiment, evidence_quote, cache_source_id from records
                          where issue_id = ${id} and cache_source_id is null order by severity desc, review_id limit 25`;
  return { issue, claims, reviews };
});
