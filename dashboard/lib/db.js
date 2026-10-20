// Read-only Postgres access for the API. The connection string lives only in the Vercel env (DATABASE_URL);
// the browser never sees it, and no model is ever called from here.
import postgres from "postgres";

let sql;
export function db() {
  if (!sql) sql = postgres(process.env.POSTGRES_URL || process.env.DATABASE_URL, { ssl: "require", max: 1, prepare: false, idle_timeout: 5 });
  return sql;
}

export function send(res, body, status = 200) {
  res.setHeader("Cache-Control", "s-maxage=300, stale-while-revalidate=3600");
  res.status(status).json(body);
}

export async function handle(res, fn) {
  try { send(res, await fn()); }
  catch (e) { console.error(e); send(res, { error: "database error" }, 500); }
}
