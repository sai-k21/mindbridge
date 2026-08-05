export default async function handler(req, res) {
  if (req.method !== "GET") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { user_id, session_id } = req.query;
  const accessToken = req.headers["x-access-token"];

  if (!user_id) {
    return res.status(400).json({ error: "user_id required" });
  }

  if (!accessToken) {
    return res.status(400).json({ error: "access_token required" });
  }

  const url = new URL(`${process.env.BACKEND_URL}/api/v1/history/${encodeURIComponent(user_id)}`);
  if (session_id) url.searchParams.set("session_id", session_id);
  url.searchParams.set("limit", "200");

  try {
    const response = await fetch(url.toString(), {
      method: "GET",
      headers: {
        "X-API-Key": process.env.API_KEY,
        "X-Access-Token": accessToken
      }
    });

    const data = await response.json();
    return res.status(response.status).json(data);
  } catch (error) {
    return res.status(500).json({ error: "Internal server error" });
  }
}