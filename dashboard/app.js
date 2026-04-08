const { useEffect, useState } = React;

function formatTemperature(value) {
  return value === null || value === undefined ? "N/A" : `${value.toFixed(1)} C`;
}

function formatMillis(value) {
  return `${Number(value || 0).toFixed(2)} ms`;
}

function formatRejectionsByReason(rejections) {
  const entries = Object.entries(rejections || {});
  if (!entries.length) {
    return "None";
  }
  return entries.map(([reason, count]) => `${reason}: ${count}`).join(" | ");
}

function DashboardApp() {
  const [data, setData] = useState({
    stats: { total_packets: 0, info: 0, warning: 0, critical: 0 },
    performance: {
      active_nodes: 0,
      offline_nodes: 0,
      packets_per_second: 0,
      average_delay_ms: 0,
      max_delay_ms: 0,
      rejected_packets: 0,
      worst_packet_loss_percent: 0,
      rejections_by_reason: {},
    },
    nodes: [],
    recent_events: [],
    generated_at: null,
  });
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadDashboard() {
      try {
        const response = await fetch("/api/dashboard", { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const payload = await response.json();
        if (active) {
          setData(payload);
          setError("");
        }
      } catch (err) {
        if (active) {
          setError(`Dashboard refresh failed: ${err.message}`);
        }
      }
    }

    loadDashboard();
    const timer = setInterval(loadDashboard, 2000);

    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <main className="shell">
      <section className="hero">
        <span className="eyebrow">Network Event Monitoring System</span>
        <h1>Live UDP Monitoring Dashboard</h1>
        <p>
          A live view of node health, anomaly severity, event throughput, delay,
          packet loss, and server-side rejection handling.
        </p>
        <div className="meta">
          <span className="meta-chip">Transport: UDP</span>
          <span className="meta-chip">Security: HMAC-SHA256</span>
          <span className="meta-chip">
            Last Refresh: {data.generated_at || "Waiting for packets"}
          </span>
        </div>
      </section>

      <section className="summary-grid">
        <article className="card">
          <div className="card-label">Tracked Nodes</div>
          <div className="card-value">{data.nodes.length}</div>
        </article>
        <article className="card">
          <div className="card-label">Total Packets</div>
          <div className="card-value">{data.stats.total_packets}</div>
        </article>
        <article className="card">
          <div className="card-label">Info Events</div>
          <div className="card-value">{data.stats.info}</div>
        </article>
        <article className="card">
          <div className="card-label">Warnings</div>
          <div className="card-value">{data.stats.warning}</div>
        </article>
        <article className="card">
          <div className="card-label">Critical Alerts</div>
          <div className="card-value">{data.stats.critical}</div>
        </article>
      </section>

      <section className="performance-grid">
        <article className="card performance-card accent-card">
          <div className="card-label">Active Nodes</div>
          <div className="card-value">{data.performance.active_nodes}</div>
          <div className="card-note">
            Offline nodes: {data.performance.offline_nodes}
          </div>
        </article>
        <article className="card performance-card">
          <div className="card-label">Packets / Sec</div>
          <div className="card-value">{data.performance.packets_per_second}</div>
          <div className="card-note">
            Rolling window: 10 seconds
          </div>
        </article>
        <article className="card performance-card">
          <div className="card-label">Avg Delay</div>
          <div className="card-value">
            {formatMillis(data.performance.average_delay_ms)}
          </div>
          <div className="card-note">
            Max: {formatMillis(data.performance.max_delay_ms)}
          </div>
        </article>
        <article className="card performance-card warn-card">
          <div className="card-label">Rejected Packets</div>
          <div className="card-value">{data.performance.rejected_packets}</div>
          <div className="card-note">
            Worst loss: {data.performance.worst_packet_loss_percent}%
          </div>
        </article>
      </section>

      <section className="two-column-layout">
        <section className="nodes-panel">
          <h2 className="section-title">Node Status</h2>
          <div className="node-grid">
            {data.nodes.length === 0 ? (
              <div className="empty-state">
                No packets received yet. Start one or more clients to populate the dashboard.
              </div>
            ) : (
              data.nodes.map((node) => (
                <article
                  key={node.node}
                  className={`node-card ${node.is_online ? "" : "offline-node"}`}
                >
                  <div className="node-header">
                    <div>
                      <h2 className="node-name">{node.node}</h2>
                      <div className="node-subtitle">
                        {node.source_ip}:{node.source_port} | Seq {node.seq}
                      </div>
                    </div>
                    <div className="badge-stack">
                      <span
                        className={`severity-badge ${node.severity.toLowerCase()}`}
                      >
                        {node.severity}
                      </span>
                      <span className={`status-badge ${node.is_online ? "online" : "offline"}`}>
                        {node.is_online ? "Online" : "Offline"}
                      </span>
                    </div>
                  </div>

                  <div className="metric-grid">
                    <div className="metric">
                      <div className="metric-label">CPU</div>
                      <div className="metric-value">{node.cpu}%</div>
                    </div>
                    <div className="metric">
                      <div className="metric-label">Memory</div>
                      <div className="metric-value">{node.memory}%</div>
                    </div>
                    <div className="metric">
                      <div className="metric-label">Latency</div>
                      <div className="metric-value">{node.latency} ms</div>
                    </div>
                    <div className="metric">
                      <div className="metric-label">Temperature</div>
                      <div className="metric-value">{formatTemperature(node.temperature)}</div>
                    </div>
                    <div className="metric">
                      <div className="metric-label">Delay</div>
                      <div className="metric-value">{formatMillis(node.delay_ms)}</div>
                    </div>
                    <div className="metric">
                      <div className="metric-label">Packet Loss</div>
                      <div className="metric-value">{node.packet_loss}%</div>
                    </div>
                    <div className="metric">
                      <div className="metric-label">Packets Seen</div>
                      <div className="metric-value">{node.total_packets}</div>
                    </div>
                    <div className="metric">
                      <div className="metric-label">Last Seen</div>
                      <div className="metric-value small-metric">
                        {node.last_seen_age_seconds}s ago
                      </div>
                    </div>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>

        <aside className="help-panel">
          <h2 className="section-title">Performance Readout</h2>
          
          <ul>
            <li>Active/offline counts help show node liveness under abrupt stops.</li>
            <li>Delay uses the packet&apos;s send timestamp and server receive time.</li>
            <li>Worst packet loss highlights the most affected node in the current run.</li>
            <li>Rejected packet counts prove malformed traffic is handled safely.</li>
          </ul>
          <div className="rejection-box">
            <div className="card-label">Rejection Breakdown</div>
            <div className="card-note">
              {formatRejectionsByReason(data.performance.rejections_by_reason)}
            </div>
          </div>
        </aside>
      </section>

      <section className="events-section">
        <section className="event-feed">
          <h2 className="section-title">Live Event Feed</h2>
          {error ? <div className="empty-state">{error}</div> : null}
          <div className="event-list">
            {data.recent_events.length === 0 ? (
              <div className="empty-state">
                Recent packets will appear here once the server receives events.
              </div>
            ) : (
              data.recent_events.map((event) => (
                <article
                  key={`${event.node}-${event.seq}-${event.timestamp}`}
                  className="event-row"
                >
                  <div className="event-main">
                    <div className="event-node">{event.node}</div>
                    <div className="event-time">{event.timestamp}</div>
                    <div className="event-extra">
                      {event.source_ip}:{event.source_port} {event.status_change || ""}
                    </div>
                  </div>
                  <div className="event-metrics">
                    <div className={`severity-badge ${event.severity.toLowerCase()}`}>
                      {event.severity}
                    </div>
                    <div className="event-extra">
                      CPU {event.cpu}% | MEM {event.memory}% | LAT {event.latency} ms
                    </div>
                    <div className="event-extra">
                      Delay {formatMillis(event.delay_ms)} | Loss {event.packet_loss}%
                    </div>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>
      </section>
    </main>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<DashboardApp />);
