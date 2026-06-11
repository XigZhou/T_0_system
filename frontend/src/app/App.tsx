import { Fragment, type ReactNode } from "react";
import { Route, Routes } from "react-router-dom";
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
import { MarketDataPage } from "../features/marketData/MarketDataPage";
import { PlaceholderPage } from "../features/placeholders/PlaceholderPage";
import { HealthPage } from "../features/system/HealthPage";
import { routes } from "../navigation/menu";

const appText = {
  notFoundTitle: "\u9875\u9762\u672a\u627e\u5230",
  system: "\u7cfb\u7edf",
  notFoundDescription: "\u5f53\u524d\u8def\u7531\u6ca1\u6709\u5bf9\u5e94\u7684\u63a7\u5236\u53f0\u9875\u9762\uff0c\u8bf7\u4ece\u5de6\u4fa7\u5bfc\u822a\u91cd\u65b0\u8fdb\u5165\u3002"
};

function pageForRoute(route: (typeof routes)[number]): ReactNode {
  if (route.path === "/system/health") return <HealthPage />;
  if (route.path === "/system/admin") return <SystemRunPage />;
  if (route.path === "/system/users") return <UserManagementPage />;
  if (route.path === "/backtests/portfolio") return <PortfolioBacktestPage />;
  if (route.path === "/backtests/single-stock") return <SingleStockPage />;
  if (route.path === "/research/sectors") return <SectorResearchPage />;
  if (route.path === "/market-data/factors") return <MarketDataPage view="factors" />;
  if (route.path === "/market-data/stocks") return <MarketDataPage view="stocks" />;
  if (route.path === "/trading/daily-plan") return <DailyPlanPage />;
  if (route.path === "/trading/paper") return <PaperTradingPage />;
  if (route.path === "/portfolio/paper-templates") return <PaperTemplatesPage />;
  if (route.path === "/portfolio/stock-pools") return <StockPoolsPage />;
  return <PlaceholderPage title={route.label} eyebrow={route.groupLabel} description={route.description} />;
}

export function App() {
  return (
    <ConsoleShell>
      <Routes>
        {routes.map((route) => {
          const element = pageForRoute(route);
          return (
            <Fragment key={route.path}>
              <Route path={route.path} element={element} />
              {route.aliases?.map((alias) => <Route key={alias} path={alias} element={element} />)}
            </Fragment>
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
