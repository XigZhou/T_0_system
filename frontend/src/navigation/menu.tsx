import type { ReactNode } from "react";
import {
  BarChart2,
  BookOpen,
  Briefcase,
  Database,
  FlaskConical,
  HeartPulse,
  Layers,
  ListFilter,
  Settings,
  ShieldCheck,
  TrendingUp,
  Users
} from "lucide-react";

export type ConsoleRoute = {
  path: string;
  label: string;
  groupLabel: string;
  description: string;
  legacyPath?: string;
  adminOnly?: boolean;
};

export type NavItem = ConsoleRoute & {
  icon: ReactNode;
};

export type NavGroup = {
  id: string;
  label: string;
  items: NavItem[];
};

export const navGroups: NavGroup[] = [
  {
    id: "research",
    label: "\u7814\u7a76",
    items: [
      {
        path: "/research/sectors",
        label: "\u677f\u5757\u7814\u7a76",
        groupLabel: "\u7814\u7a76",
        description: "\u627f\u8f7d\u65e7\u7248\u677f\u5757\u7814\u7a76\u9875\u9762\uff0c\u5148\u4fdd\u7559\u539f\u8868\u5355\u3001\u56fe\u8868\u548c API \u884c\u4e3a\u3002",
        legacyPath: "/sector",
        icon: <BarChart2 size={15} />
      }
    ]
  },
  {
    id: "market-data",
    label: "\u6570\u636e\u884c\u60c5",
    items: [
      {
        path: "/market-data",
        label: "\u6570\u636e\u884c\u60c5",
        groupLabel: "\u6570\u636e\u884c\u60c5",
        description: "\u53ea\u8bfb\u67e5\u770b\u5f53\u524d\u7cfb\u7edf\u5df2\u6709\u7684\u56e0\u5b50\u5e93\u548c\u80a1\u7968\u65e5\u7ebf\u6570\u636e\u3002",
        icon: <Database size={15} />
      }
    ]
  },
  {
    id: "backtests",
    label: "\u56de\u6d4b",
    items: [
      {
        path: "/backtests/portfolio",
        label: "\u7ec4\u5408\u56de\u6d4b",
        groupLabel: "\u56de\u6d4b",
        description: "\u627f\u8f7d\u65e7\u7248\u7ec4\u5408\u56de\u6d4b\u9875\u9762\uff0c\u4fdd\u7559\u8d26\u6237\u56de\u6d4b\u3001\u4fe1\u53f7\u8d28\u91cf\u6a21\u5f0f\u3001\u5bfc\u51fa\u548c\u7ed3\u679c\u8868\u683c\u3002",
        legacyPath: "/",
        icon: <TrendingUp size={15} />
      },
      {
        path: "/backtests/single-stock",
        label: "\u5355\u80a1\u56de\u6d4b",
        groupLabel: "\u56de\u6d4b",
        description: "\u627f\u8f7d\u65e7\u7248\u5355\u80a1\u56de\u6d4b\u9875\u9762\uff0c\u5148\u4fdd\u7559\u80a1\u7968\u8f93\u5165\u3001\u56de\u6d4b\u8868\u683c\u548c\u539f API \u884c\u4e3a\u3002",
        legacyPath: "/single",
        icon: <FlaskConical size={15} />
      }
    ]
  },
  {
    id: "trading",
    label: "\u4ea4\u6613",
    items: [
      {
        path: "/trading/daily-plan",
        label: "\u6bcf\u65e5\u6536\u76d8\u9009\u80a1",
        groupLabel: "\u4ea4\u6613",
        description: "\u627f\u8f7d\u65e7\u7248\u6bcf\u65e5\u6536\u76d8\u9009\u80a1\u9875\u9762\uff0c\u5148\u4fdd\u7559\u6536\u76d8\u8ba1\u5212\u3001\u5356\u51fa\u63d0\u9192\u548c\u6301\u4ed3\u590d\u6838\u3002",
        legacyPath: "/daily",
        icon: <ListFilter size={15} />
      },
      {
        path: "/trading/paper",
        label: "\u591a\u8d26\u6237\u6a21\u62df\u4ea4\u6613",
        groupLabel: "\u4ea4\u6613",
        description: "\u627f\u8f7d\u65e7\u7248\u591a\u8d26\u6237\u6a21\u62df\u4ea4\u6613\u9875\u9762\uff0c\u5148\u4fdd\u7559\u8d26\u672c\u8bfb\u53d6\u3001\u8ba2\u5355\u751f\u6210\u3001\u6267\u884c\u548c\u4f30\u503c\u5237\u65b0\u3002",
        legacyPath: "/paper",
        icon: <BookOpen size={15} />
      }
    ]
  },
  {
    id: "portfolio",
    label: "\u7ec4\u5408",
    items: [
      {
        path: "/portfolio/stock-pools",
        label: "\u80a1\u7968\u6c60\u6a21\u677f",
        groupLabel: "\u7ec4\u5408",
        description: "\u627f\u8f7d\u65e7\u7248\u80a1\u7968\u6c60\u6a21\u677f\u9875\u9762\uff0c\u5148\u4fdd\u7559\u6a21\u677f\u7ef4\u62a4\u3001\u4ee3\u7801\u6821\u9a8c\u548c\u6570\u636e\u5237\u65b0\u5165\u53e3\u3002",
        legacyPath: "/stock-pools",
        icon: <Layers size={15} />
      },
      {
        path: "/portfolio/paper-templates",
        label: "\u6a21\u62df\u8d26\u6237\u6a21\u677f",
        groupLabel: "\u7ec4\u5408",
        description: "\u627f\u8f7d\u65e7\u7248\u6a21\u62df\u8d26\u6237\u6a21\u677f\u9875\u9762\uff0c\u5148\u4fdd\u7559\u8d26\u6237\u53c2\u6570\u3001\u8d44\u91d1\u3001\u4ea4\u6613\u6210\u672c\u548c\u8d26\u672c\u8def\u5f84\u7ef4\u62a4\u3002",
        legacyPath: "/paper/templates",
        icon: <Briefcase size={15} />
      }
    ]
  },
  {
    id: "system",
    label: "\u7cfb\u7edf",
    items: [
      {
        path: "/system/admin",
        label: "\u7cfb\u7edf\u7ef4\u62a4",
        groupLabel: "\u7cfb\u7edf",
        description: "\u627f\u8f7d\u65e7\u7248\u7cfb\u7edf\u7ba1\u7406\u5458\u9875\u9762\uff0c\u4fdd\u7559\u65e5\u7ebf\u91c7\u96c6\u3001\u6307\u6807\u8ba1\u7b97\u3001\u4e3b\u80a1\u7968\u6c60\u548c\u4efb\u52a1\u65e5\u5fd7\u3002",
        legacyPath: "/admin",
        adminOnly: true,
        icon: <Settings size={15} />
      },
      {
        path: "/system/users",
        label: "\u7528\u6237\u7ba1\u7406",
        groupLabel: "\u7cfb\u7edf",
        description: "\u627f\u8f7d\u65e7\u7248\u7528\u6237\u7ba1\u7406\u9875\u9762\uff0c\u5148\u4fdd\u7559\u7528\u6237\u72b6\u6001\u548c\u5bc6\u7801\u91cd\u7f6e\u7b49\u7ba1\u7406\u5458\u529f\u80fd\u3002",
        legacyPath: "/users",
        adminOnly: true,
        icon: <Users size={15} />
      },
      {
        path: "/system/health",
        label: "\u5065\u5eb7\u68c0\u67e5",
        groupLabel: "\u7cfb\u7edf",
        description: "\u68c0\u67e5 FastAPI \u670d\u52a1\u5065\u5eb7\u72b6\u6001\uff0c\u8c03\u7528 /health\u3002",
        legacyPath: "/health",
        icon: <ShieldCheck size={15} />
      }
    ]
  }
];

export const routes: ConsoleRoute[] = navGroups.flatMap((group) =>
  group.items.map(({ icon: _icon, ...item }) => item)
);

export function findRoute(pathname: string): ConsoleRoute | undefined {
  return routes.find((route) => route.path === pathname);
}

export function LogoMark() {
  return <HeartPulse size={15} />;
}
