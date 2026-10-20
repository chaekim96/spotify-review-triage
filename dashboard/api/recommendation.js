import { db, handle } from "../lib/db.js";
export default (req, res) => handle(res, async () => {
  const s = db();
  const [rec] = await s`select * from recommendations order by id desc limit 1`;
  const ids = rec ? rec.cited_claim_ids : [];
  const claims = ids.length ? await s`select claim_id, issue_id, metric, value from claims where claim_id in ${s(ids)} order by claim_id` : [];
  return { recommendation: rec || null, cited_claims: claims };
});
