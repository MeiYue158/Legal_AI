import cors from "cors";
import "dotenv/config";
import express from "express";
import { authRouter } from "./routes/auth";
import { feedbackRouter } from "./routes/feedback";
import { historyRouter } from "./routes/history";
import { legalAnalysisRouter } from "./routes/legalAnalysis";

const app = express();

app.use(cors({ origin: process.env.CORS_ORIGIN ?? "http://localhost:5173" }));
app.use(express.json());

app.get("/health", (_req, res) => res.json({ status: "ok" }));

app.use("/auth", authRouter);
app.use("/legal-analysis", legalAnalysisRouter);
app.use("/feedback", feedbackRouter);
app.use("/history", historyRouter);

const port = Number(process.env.PORT ?? 4000);
app.listen(port, () => {
  console.log(`Product backend listening on http://localhost:${port}`);
});
