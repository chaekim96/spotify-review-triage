import { db, handle } from "../lib/db.js";
export default (req, res) => handle(res, async () => {
  const id = String(req.query.id || "");
  const [r] = await db()`select review_id, topic, intent, sentiment, severity, entities, evidence_quote, needs_review,
                                label_config, cache_source_id, issue_id from records where review_id = ${id}`;
  return r || { error: "not found" };
});
