// Railway infrastructure for Thalace Shops: the API and the web app, deployed
// from main. Variables are listed by name with preserve(): their values are
// set on each service in Railway and never written to source.
// Steps and what each variable holds: docs/deploy-railway.md.
import { defineRailway, github, preserve, project, service } from "railway/iac";

const repo = "calebomondi/thalace-shops";

export default defineRailway(() => {
  // FastAPI + the shop agents + the payment watcher. Exactly one replica,
  // always on: the watcher and payout queue run inside its process.
  const api = service("api", {
    source: github(repo, { branch: "main", rootDirectory: "/backend" }),
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile", watchPatterns: ["backend/**"] },
    // Migrations run before each new version starts; a failed one stops the deploy.
    preDeploy: "alembic upgrade head",
    healthcheck: "/api/v1/health",
    healthcheckTimeout: 120,
    deploy: { restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 5 },
    env: {
      ADMIN_BOOTSTRAP_EMAILS: preserve(),
      ALLOWED_ORIGINS: preserve(),
      BRIGHTDATA_API_KEY: preserve(),
      CLIENT_IP_HEADER: preserve(),
      COMPOSIO_API_KEY: preserve(),
      COMPOSIO_AUTH_CONFIGS: preserve(),
      DASHSCOPE_API_KEY: preserve(),
      DASHSCOPE_BASE_URL: preserve(),
      DATABASE_URL: preserve(),
      ENVIRONMENT: preserve(),
      EXA_API_KEY: preserve(),
      FIRECRAWL_API_KEY: preserve(),
      FRONTEND_BASE_URL: preserve(),
      KRA_PIN_CHECKER_CONS_KEY: preserve(),
      KRA_PIN_CHECKER_CONS_SECRET: preserve(),
      KRA_TAXPAYER_OBLIGATIONS_CONS_KEY: preserve(),
      KRA_TAXPAYER_OBLIGATIONS_CONS_SECRET: preserve(),
      KRA_TAX_COMP_CERT_CHECKER_CONS_KEY: preserve(),
      KRA_TAX_COMP_CERT_CHECKER_CONS_SECRET: preserve(),
      LOG_FORMAT: preserve(),
      NEAR_AI_CLOUD_API_KEY: preserve(),
      NEAR_INTENTS_1CLICK_JWT: preserve(),
      NEAR_INTENTS_AGENT_API_KEY: preserve(),
      NEAR_INTENTS_AGENT_API_URL: preserve(),
      NEAR_MAINNET_PLATFORM_TREASURY_WALLET_ADDRESS: preserve(),
      NEAR_MAINNET_WALLET_ADDRESS: preserve(),
      OPENROUTER_API_KEY: preserve(),
      PORT: preserve(),
      RESEND_API_KEY: preserve(),
      SHOP_GRANT_KEY: preserve(),
      SUPABASE_ANON_KEY: preserve(),
      SUPABASE_BASE_URL: preserve(),
      SUPABASE_DB_CONN_STR: preserve(),
      SUPABASE_SECRET_KEY: preserve(),
      TAVILY_API_KEY: preserve(),
    },
  });

  // The web app at shops.thalace.com, served by Caddy, which forwards /api and
  // /mcp to the API over the private network (API_UPSTREAM).
  const app = service("app", {
    source: github(repo, { branch: "main", rootDirectory: "/frontend" }),
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile", watchPatterns: ["frontend/**"] },
    healthcheck: "/",
    deploy: { restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 5 },
    domains: ["shops.thalace.com"],
    env: {
      API_UPSTREAM: preserve(),
      VITE_SUPABASE_ANON_KEY: preserve(),
      VITE_SUPABASE_URL: preserve(),
    },
  });

  return project("perpetual-imagination", { resources: [api, app] });
});
