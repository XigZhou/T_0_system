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
  aliases?: string[];
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
        aliases: ["/sector"],
        label: "\u677f\u5757\u7814\u7a76",
        groupLabel: "\u7814\u7a76",
        description: "\u67e5\u770b\u677f\u5757\u7814\u7a76\u770b\u677f\u3001\u4e3b\u9898\u6392\u540d\u3001\u5f3a\u52bf\u677f\u5757\u3001\u4e2a\u80a1\u66b4\u9732\u548c\u5f02\u5e38\u65e5\u5fd7\u3002",
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
        aliases: ["/", "/static/console", "/static/console/"],
        label: "\u7ec4\u5408\u56de\u6d4b",
        groupLabel: "\u56de\u6d4b",
        description: "\u8fd0\u884c\u7ec4\u5408\u56de\u6d4b\u548c\u4fe1\u53f7\u8d28\u91cf\u8bc4\u4f30\uff0c\u67e5\u770b\u66f2\u7ebf\u3001\u4ea4\u6613\u6d41\u6c34\u3001\u6301\u4ed3\u3001\u8bca\u65ad\u4e0e\u5bfc\u51fa\u7ed3\u679c\u3002",
        icon: <TrendingUp size={15} />
      },
      {
        path: "/backtests/single-stock",
        aliases: ["/single"],
        label: "\u5355\u80a1\u56de\u6d4b",
        groupLabel: "\u56de\u6d4b",
        description: "\u5bf9\u5355\u53ea\u80a1\u7968\u9a8c\u8bc1\u4e70\u5165\u6761\u4ef6\u3001\u5356\u51fa\u6761\u4ef6\u3001\u6301\u6709\u5929\u6570\u3001\u6536\u76ca\u548c\u4ea4\u6613\u660e\u7ec6\u3002",
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
        aliases: ["/daily"],
        label: "\u6bcf\u65e5\u6536\u76d8\u9009\u80a1",
        groupLabel: "\u4ea4\u6613",
        description: "\u57fa\u4e8e\u6536\u76d8\u4fe1\u53f7\u751f\u6210\u6b21\u65e5\u5019\u9009\u3001\u4e70\u5165\u8ba1\u5212\u3001\u5356\u51fa\u63d0\u9192\u548c\u6301\u4ed3\u590d\u6838\u3002",
        icon: <ListFilter size={15} />
      },
      {
        path: "/trading/paper",
        aliases: ["/paper"],
        label: "\u591a\u8d26\u6237\u6a21\u62df\u4ea4\u6613",
        groupLabel: "\u4ea4\u6613",
        description: "\u7ba1\u7406\u591a\u8d26\u6237\u6a21\u62df\u4ea4\u6613\u8d26\u672c\uff0c\u6267\u884c\u8ba2\u5355\u751f\u6210\u3001\u5f00\u76d8\u6210\u4ea4\u3001\u6536\u76d8\u4f30\u503c\u548c\u5237\u65b0\u3002",
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
        aliases: ["/stock-pools"],
        label: "\u80a1\u7968\u6c60\u6a21\u677f",
        groupLabel: "\u7ec4\u5408",
        description: "\u7ef4\u62a4\u5f53\u524d\u7528\u6237\u80a1\u7968\u6c60\u6a21\u677f\uff0c\u6821\u9a8c\u80a1\u7968\u6e05\u5355\u5e76\u89e6\u53d1\u6570\u636e\u5237\u65b0\u5165\u53e3\u3002",
        icon: <Layers size={15} />
      },
      {
        path: "/portfolio/paper-templates",
        aliases: ["/paper/templates"],
        label: "\u6a21\u62df\u8d26\u6237\u6a21\u677f",
        groupLabel: "\u7ec4\u5408",
        description: "\u7ef4\u62a4\u6a21\u62df\u8d26\u6237\u6a21\u677f\u53c2\u6570\u3001\u8d44\u91d1\u3001\u4ea4\u6613\u6210\u672c\u3001\u80a1\u7968\u6c60\u548c\u8d26\u672c\u914d\u7f6e\u3002",
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
        aliases: ["/admin"],
        label: "\u7cfb\u7edf\u7ef4\u62a4",
        groupLabel: "\u7cfb\u7edf",
        description: "\u7ba1\u7406\u5458\u7ef4\u62a4\u65e5\u7ebf\u91c7\u96c6\u3001\u6307\u6807\u8ba1\u7b97\u3001\u4e3b\u80a1\u7968\u6c60\u3001\u8c03\u5ea6\u8bb0\u5f55\u548c\u5b89\u5168\u91cd\u8dd1\u3002",
        adminOnly: true,
        icon: <Settings size={15} />
      },
      {
        path: "/system/users",
        aliases: ["/users"],
        label: "\u7528\u6237\u7ba1\u7406",
        groupLabel: "\u7cfb\u7edf",
        description: "\u7ba1\u7406\u5458\u67e5\u770b\u7528\u6237\u3001\u542f\u505c\u8d26\u53f7\u5e76\u91cd\u7f6e\u666e\u901a\u7528\u6237\u5bc6\u7801\u3002",
        adminOnly: true,
        icon: <Users size={15} />
      },
      {
        path: "/system/health",
        label: "\u5065\u5eb7\u68c0\u67e5",
        groupLabel: "\u7cfb\u7edf",
        description: "\u68c0\u67e5 FastAPI \u670d\u52a1\u5065\u5eb7\u72b6\u6001\uff0c\u8c03\u7528 /health\u3002",
        icon: <ShieldCheck size={15} />
      }
    ]
  }
];

export const routes: ConsoleRoute[] = navGroups.flatMap((group) =>
  group.items.map(({ icon: _icon, ...item }) => item)
);

export function findRoute(pathname: string): ConsoleRoute | undefined {
  return routes.find((route) => route.path === pathname || route.aliases?.includes(pathname));
}

export function LogoMark() {
  return <HeartPulse size={15} />;
}
