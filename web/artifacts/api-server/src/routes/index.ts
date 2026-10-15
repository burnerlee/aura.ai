import { Router, type IRouter } from "express";
import healthRouter from "./health";
import proxyRouter from "./proxy";

const router: IRouter = Router();

router.use(healthRouter);
// Catch-all: forward remaining /api/* to Python FastAPI
router.use(proxyRouter);

export default router;
