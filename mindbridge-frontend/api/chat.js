export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  // Every request to this function comes from Vercel's network, so the
  // backend would otherwise rate-limit "Vercel" instead of each visitor.
  // Vercel sets x-forwarded-for on the incoming request to the real
  // visitor IP — pass it through.
  const clientIp =
    (req.headers["x-forwarded-for"] || "").split(",")[0].trim() ||
    req.socket?.remoteAddress ||
    "unknown";

  try {
    const response = await fetch(
      `${process.env.BACKEND_URL}/api/v1/chat`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": process.env.API_KEY,
          "X-Forwarded-For": clientIp
        },
        body: JSON.stringify(req.body)
      }
    );

    const data = await response.json();
    return res.status(response.status).json(data);
  } catch (error) {
    return res.status(500).json({ error: "Internal server error" });
  }
}