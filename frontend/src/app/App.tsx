import { Navigate, Route, Routes } from "react-router-dom";
import { ConsoleShell } from "../shell/ConsoleShell";
import { PortfolioBacktestPage } from "../features/backtests/PortfolioBacktestPage";
import { DailyPlanPage } from "../features/daily/DailyPlanPage";
import { PaperTradingPage } from "../features/paper/PaperTradingPage";
import { PaperTemplatesPage } from "../features/paperTemplates/PaperTemplatesPage";
import { StockPoolsPage } from "../features/stockPools/StockPoolsPage";
import { SingleStockPage } from "../features/singleStock/SingleStockPage";
import { SectorResearchPage } from "../features/sectors/SectorResearchPage";
import { SystemRunPage } from "../features/systemRun/SystemRunPage";
import { UserManagementPage } from "../features/users/UserManagementPage";
import { LegacyFrame } from "../features/legacy/LegacyFrame";
import { PlaceholderPage } from "../features/placeholders/PlaceholderPage";
import { HealthPage } from "../features/system/HealthPage";
import { routes } from "../navigation/menu";

const appText = {
  notFoundTitle: "\u9875\u9762\u672a\u627e\u5230",
  system: "\u7cfb\u7edf",
  notFoundDescription: "\u5f53\u524d\u8def\u7531\u6ca1\u6709\u5bf9\u5e94\u7684\u63a7\u5236\u53f0\u9875\u9762\uff0c\u8bf7\u4ece\u5de6\u4fa7\u5bfc\u822a\u91cd\u65b0\u8fdb\u5165\u3002"
};

export function App() {
  return (
    <ConsoleShell>
      <Routes>
        <Route path="/" element={<Navigate to="/backtests/portfolio" replace />} />
        {routes.map((route) => {
          if (route.path === "/system/health") {
            return <Route key={route.path} path={route.path} element={<HealthPage />} />;
          }

          if (route.path === "/system/admin") {
            return <Route key={route.path} path={route.path} element={<SystemRunPage />} />;
          }

          if (route.path === "/system/users") {
            return <Route key={route.path} path={route.path} element={<UserManagementPage />} />;
          }

          if (route.path === "/backtests/portfolio") {
            return <Route key={route.path} path={route.path} element={<PortfolioBacktestPage />} />;
          }

          if (route.path === "/backtests/single-stock") {
            return <Route key={route.path} path={route.path} element={<SingleStockPage />} />;
          }

          if (route.path === "/research/sectors") {
            return <Route key={route.path} path={route.path} element={<SectorResearchPage />} />;
          }

          if (route.path === "/trading/daily-plan") {
            return <Route key={route.path} path={route.path} element={<DailyPlanPage />} />;
          }

          if (route.path === "/trading/paper") {
            return <Route key={route.path} path={route.path} element={<PaperTradingPage />} />;
          }

          if (route.path === "/portfolio/paper-templates") {
            return <Route key={route.path} path={route.path} element={<PaperTemplatesPage />} />;
          }

          if (route.path === "/portfolio/stock-pools") {
            return <Route key={route.path} path={route.path} element={<StockPoolsPage />} />;
          }

          return (
            <Route
              key={route.path}
              path={route.path}
              element={
                route.legacyPath ? (
                  <LegacyFrame
                    title={route.label}
                    eyebrow={route.groupLabel}
                    description={route.description}
                    legacyPath={route.legacyPath}
                  />
                ) : (
                  <PlaceholderPage title={route.label} eyebrow={route.groupLabel} description={route.description} />
                )
              }
            />
          );
        })}
        <Route
          path="*"
          element={
            <PlaceholderPage
              title={appText.notFoundTitle}
              eyebrow={appText.system}
              description={appText.notFoundDescription}
            />
          }
        />
      </Routes>
    </ConsoleShell>
  );
}
