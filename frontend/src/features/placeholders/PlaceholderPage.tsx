type PlaceholderPageProps = {
  title: string;
  eyebrow: string;
  description: string;
};

const placeholderMetrics = [
  ["接口状态", "待接入"],
  ["数据来源", "沿用后端"],
  ["结果口径", "不变"],
  ["数据库", "不修改"]
];

export function PlaceholderPage({ title, eyebrow, description }: PlaceholderPageProps) {
  return (
    <div className="placeholder-page">
      <div className="page-header">
        <div>
          <p className="page-eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
        </div>
      </div>

      <section className="run-surface">
        <div className="run-copy">
          <p className="surface-label">控制台壳层已就绪</p>
          <p>{description}</p>
        </div>
        <button className="primary-button" type="button" disabled>
          等待接入
        </button>
      </section>

      <section className="metric-strip" aria-label="当前实施状态">
        {placeholderMetrics.map(([label, value]) => (
          <div className="metric-tile" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </section>

      <section className="workbench-grid">
        <div className="workbench-panel">
          <div className="panel-header">
            <h2>本阶段范围</h2>
          </div>
          <ul className="scope-list">
            <li>建立 React 控制台壳层和中文导航。</li>
            <li>使用 BrowserRouter 支持干净页面路径。</li>
            <li>保留 /single、/daily 等兼容短路径，统一进入新控制台。</li>
            <li>后续逐页迁移表单、图表、表格和 API 调用。</li>
          </ul>
        </div>

        <div className="workbench-panel">
          <div className="panel-header">
            <h2>后端影响</h2>
          </div>
          <div className="status-table-wrap">
            <table>
              <tbody>
                <tr>
                  <th>API</th>
                  <td>不修改</td>
                </tr>
                <tr>
                  <th>回测结果</th>
                  <td>不影响</td>
                </tr>
                <tr>
                  <th>数据库结构</th>
                  <td>不修改</td>
                </tr>
                <tr>
                  <th>兼容短路径</th>
                  <td>保留</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
