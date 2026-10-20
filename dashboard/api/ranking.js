import { db, handle } from "../lib/db.js";
export default (req, res) => handle(res, async () => {
  const s = db();
  return s`select r.rank, r.issue_id, i.name, i.topic, i.area, r.complaint_count, r.severity_sum, r.mean_severity, r.priority_score
           from ranking r join issues i using (issue_id) order by r.rank`;
});
