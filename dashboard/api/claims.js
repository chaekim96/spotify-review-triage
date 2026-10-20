import { db, handle } from "../lib/db.js";
export default (req, res) => handle(res, async () => db()`select claim_id, issue_id, metric, value from claims order by claim_id`);
