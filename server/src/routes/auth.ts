import bcrypt from "bcryptjs";
import { Router } from "express";
import { pool } from "../db";
import { signToken } from "../auth";
import { logEvent } from "../events";

export const authRouter = Router();

authRouter.post("/register", async (req, res) => {
  const { username, email, password, legalExpertise } = req.body ?? {};

  if (!username || !email || !password) {
    return res.status(400).json({ error: "username, email, and password are required" });
  }
  if (legalExpertise && !["law", "non_law"].includes(legalExpertise)) {
    return res.status(400).json({ error: "legalExpertise must be 'law' or 'non_law'" });
  }

  try {
    const passwordHash = await bcrypt.hash(password, 10);
    const result = await pool.query(
      `INSERT INTO users (username, email, password_hash, legal_expertise)
       VALUES ($1, $2, $3, $4)
       RETURNING user_id, username, email, legal_expertise, created_at`,
      [username, email, passwordHash, legalExpertise ?? null]
    );
    const user = result.rows[0];
    const token = signToken({ userId: user.user_id, username: user.username });

    req.user = { userId: user.user_id, username: user.username };
    await logEvent(req, "user_registered", { page: "register" });

    res.status(201).json({ token, user });
  } catch (err: any) {
    if (err.code === "23505") {
      // unique_violation on username or email
      return res.status(409).json({ error: "username or email already exists" });
    }
    console.error("register failed:", err);
    res.status(500).json({ error: "registration failed" });
  }
});

authRouter.post("/login", async (req, res) => {
  const { username, password } = req.body ?? {};
  if (!username || !password) {
    return res.status(400).json({ error: "username and password are required" });
  }

  try {
    const result = await pool.query(
      `SELECT user_id, username, email, password_hash, legal_expertise, created_at
       FROM users WHERE username = $1`,
      [username]
    );
    const user = result.rows[0];
    if (!user || !(await bcrypt.compare(password, user.password_hash))) {
      return res.status(401).json({ error: "invalid username or password" });
    }

    const token = signToken({ userId: user.user_id, username: user.username });
    delete user.password_hash;

    req.user = { userId: user.user_id, username: user.username };
    await logEvent(req, "user_login", { page: "login" });

    res.json({ token, user });
  } catch (err) {
    console.error("login failed:", err);
    res.status(500).json({ error: "login failed" });
  }
});
