const CARD_VERSION = "rc1";
const DEFAULT_PREFIX = "trading_212";
const DEFAULT_TIMEFRAMES = ["1D", "1W", "1M", "3M", "YTD", "1Y", "ALL"];
const SUMMARY_KEYS = {
  account_value: "account_value",
  cash: "cash",
  free_funds: "free_funds",
  invested: "invested",
  holdings_value: "holdings_value",
  open_positions: "open_positions",
  result: "result",
  result_percent: "result_percent",
  daily_gain_loss: "daily_gain_loss",
  daily_gain_loss_percent: "daily_gain_loss_percent",
  account_change: "account_change",
  account_change_percent: "account_change_percent",
  largest_position: "largest_position",
  largest_position_value: "largest_position_value",
  largest_position_percentage: "largest_position_percentage",
  top_5_position_concentration_percentage: "top_5_position_concentration_percentage",
  positions_in_profit: "positions_in_profit",
  positions_in_loss: "positions_in_loss",
  total_unrealised_result: "total_unrealised_result",
  best_position: "best_position",
  best_position_result: "best_position_result",
  worst_position: "worst_position",
  worst_position_result: "worst_position_result",
  pies_count: "pies_count",
  total_pies_value: "total_pies_value",
  total_pies_value_including_cash: "total_pies_value_including_cash",
  total_pies_cash: "total_pies_cash",
  total_pies_result: "total_pies_result",
  largest_pie: "largest_pie",
  largest_pie_value: "largest_pie_value",
  last_update: "last_update",
  top_daily_mover: "top_daily_mover",
  bottom_daily_mover: "bottom_daily_mover",
  biggest_daily_gain_value: "biggest_daily_gain_value",
  biggest_daily_loss_value: "biggest_daily_loss_value",
};

const TICKER_BRANDS = {
  AAPL: { bg: "linear-gradient(135deg, #d6dbe8 0%, #f5f6fa 100%)", fg: "#0a0e19", mark: "A" },
  AMD: { bg: "linear-gradient(135deg, #00d17f 0%, #005c42 100%)", fg: "#08140f", mark: "A" },
  AMZN: { bg: "linear-gradient(135deg, #ffb347 0%, #ff7a18 100%)", fg: "#1a0f02", mark: "a" },
  GOOGL: { bg: "linear-gradient(135deg, #4a90ff 0%, #33d1ff 100%)", fg: "#07101b", mark: "G" },
  LVMH: { bg: "linear-gradient(135deg, #f2f2f2 0%, #bcbcbc 100%)", fg: "#111111", mark: "L" },
  META: { bg: "linear-gradient(135deg, #00d2ff 0%, #3a7bfd 100%)", fg: "#07101b", mark: "M" },
  MSFT: { bg: "linear-gradient(135deg, #2dd4bf 0%, #2563eb 100%)", fg: "#07111d", mark: "■" },
  NFLX: { bg: "linear-gradient(135deg, #ff3b3b 0%, #7f1010 100%)", fg: "#150606", mark: "N" },
  NVDA: { bg: "linear-gradient(135deg, #7ce11b 0%, #0b6f38 100%)", fg: "#071107", mark: "N" },
  TSLA: { bg: "linear-gradient(135deg, #ff5f5f 0%, #611818 100%)", fg: "#1c0808", mark: "T" },
};

class Trading212PortfolioCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("div");
  }

  static getStubConfig() {
    return {
      entity_prefix: DEFAULT_PREFIX,
      title: "Trading 212 Portfolio",
      subtitle: "Read-only Home Assistant card concept",
      timeframe: "1Y",
      live_label: "LIVE",
      readonly_label: "Read-only",
    };
  }

  setConfig(config) {
    if (!config) {
      throw new Error("Trading 212 card configuration is required");
    }
    this._config = {
      title: "Trading 212 Portfolio",
      subtitle: "Read-only Home Assistant card concept",
      entity_prefix: DEFAULT_PREFIX,
      timeframe: "1Y",
      live_label: "LIVE",
      readonly_label: "Read-only",
      ...config,
    };
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this.shadowRoot) {
      this._render();
    }
  }

  getCardSize() {
    return 11;
  }

  _render() {
    if (!this.shadowRoot) {
      return;
    }

    if (!this._hass) {
      this.shadowRoot.innerHTML = `<ha-card>${this._style()}<div class="shell loading">Waiting for Home Assistant...</div></ha-card>`;
      return;
    }

    const stateMap = this._resolveEntities();
    const snapshot = this._buildSnapshot(stateMap);
    this._snapshot = snapshot;

    this.shadowRoot.innerHTML = `
      ${this._style()}
      <ha-card class="card-shell">
        <section class="shell">
          <div class="glow glow-a"></div>
          <div class="glow glow-b"></div>
          <header class="header">
            <div class="brand">
              <div class="brand-mark" aria-hidden="true">${this._brandMark()}</div>
              <div class="brand-copy">
                <h1>${escapeHtml(this._config.title)}</h1>
                <p>${escapeHtml(this._config.subtitle)}</p>
              </div>
            </div>
            <div class="meta-strip">
              <span class="meta-chip"><span class="meta-dot"></span>${escapeHtml(this._config.live_label)}</span>
              <span class="meta-mini">${escapeHtml(snapshot.lastUpdateLabel)}</span>
              <span class="meta-mini">${escapeHtml(this._config.readonly_label)}</span>
            </div>
          </header>
          <div class="account-strip">
            ${this._renderCompactMetric("Cash", snapshot.cash, snapshot.currency)}
            ${this._renderCompactMetric("Free funds", snapshot.freeFunds, snapshot.currency)}
            ${this._renderCompactMetric("Holdings value", snapshot.holdingsValue, snapshot.currency)}
            ${this._renderCompactMetric("Open positions", snapshot.openPositions)}
            ${this._renderCompactMetric("Result", snapshot.result, snapshot.currency, snapshot.resultPercent)}
            ${snapshot.dailyMarketAvailable
              ? this._renderCompactMetric("Daily market P/L", snapshot.dailyResult, snapshot.currency, snapshot.dailyResultPercent)
              : this._renderCompactStatus("Daily market P/L", "Awaiting holdings baseline")}
            <div class="account-strip-meta">${escapeHtml(snapshot.lastUpdateLabel)}</div>
          </div>

          <div class="layout">
            <aside class="pies-column">
              ${this._renderPiesPanel(snapshot)}
            </aside>

            <section class="hero-panel">
              <div class="hero-topline">${this._renderHeroLogo()}</div>
              <div class="hero-value-wrap">
                <div class="eyebrow">Account value</div>
                <div class="hero-value">${formatMoney(snapshot.accountValue, snapshot.currency)}</div>
              </div>
              <div class="hero-chart">
                <svg viewBox="0 0 1000 260" preserveAspectRatio="none" aria-hidden="true">
                  <defs>
                    <linearGradient id="hero-fill" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0%" stop-color="rgba(48,255,184,0.62)"></stop>
                      <stop offset="100%" stop-color="rgba(48,255,184,0.02)"></stop>
                    </linearGradient>
                    <filter id="hero-glow">
                      <feGaussianBlur stdDeviation="6" result="colored"></feGaussianBlur>
                      <feMerge>
                        <feMergeNode in="colored"></feMergeNode>
                        <feMergeNode in="SourceGraphic"></feMergeNode>
                      </feMerge>
                    </filter>
                  </defs>
                  <path class="hero-backdrop" d="${snapshot.heroBackdropPath}"></path>
                  <path class="hero-area" d="${snapshot.heroAreaPath}"></path>
                  <path class="hero-line" d="${snapshot.heroLinePath}"></path>
                  <circle class="hero-dot" cx="${snapshot.heroDot.x}" cy="${snapshot.heroDot.y}" r="6"></circle>
                </svg>
                <div class="hero-chart-note">${escapeHtml(snapshot.heroChartNote)}</div>
              </div>
            </section>

            <aside class="allocation-column">
              <section class="panel ring-panel">
                <div class="panel-title">Top Holdings</div>
                ${snapshot.allocationAvailable ? `
                  <div class="ring-wrap">
                    <div class="ring-chart" style="background:${snapshot.ringBackground}">
                      <div class="ring-core">
                        <span class="ring-core-label">${escapeHtml(snapshot.ringCenterLabel)}</span>
                        <strong>${escapeHtml(snapshot.ringCenterValue)}</strong>
                      </div>
                    </div>
                    <div class="ring-legend">${this._renderLegend(snapshot.legendItems)}</div>
                  </div>
                ` : `
                  <div class="allocation-empty">
                    <div class="allocation-empty-ring">
                      <span>Holdings</span>
                      <strong>Unavailable</strong>
                    </div>
                    <div class="allocation-empty-copy">
                      <strong>Top holdings mix unavailable from current entities</strong>
                      <span>The card will render real holdings percentages when per-position values are exposed.</span>
                    </div>
                  </div>
                `}
              </section>

              <section class="panel concentration-panel">
                <div class="panel-title">Concentration</div>
                <div class="concentration-copy">
                  <span>Top 5 holdings</span>
                  <strong>${formatPercent(snapshot.topFiveConcentration)}</strong>
                </div>
                <div class="concentration-track">
                  <div class="concentration-fill" style="width:${clampPercent(snapshot.topFiveConcentration)}%"></div>
                </div>
              </section>
            </aside>

            <section class="movers-grid">
              <section class="panel movers-panel positive">
                ${this._renderMoversSection("Top 5 movers", snapshot.topMovers, true, snapshot.currency)}
              </section>
              <section class="panel movers-panel negative">
                ${this._renderMoversSection("Bottom 5 movers", snapshot.bottomMovers, false, snapshot.currency)}
              </section>
            </section>

            <section class="performance-panel panel">
                <div class="performance-head">
                <div class="performance-head-copy">
                  <div class="panel-title">Portfolio performance</div>
                  <div class="panel-note">${escapeHtml(snapshot.performanceNote)}</div>
                </div>
                <div class="timeframes">
                  ${DEFAULT_TIMEFRAMES.map((item) => `
                    <button class="timeframe ${item === this._config.timeframe ? "active" : ""}" type="button">${escapeHtml(item)}</button>
                  `).join("")}
                </div>
              </div>

              <div class="performance-body">
                <div class="performance-chart">
                  <div class="performance-tooltip" hidden></div>
                  <svg viewBox="0 0 1180 300" preserveAspectRatio="none" aria-hidden="true">
                    <defs>
                      <linearGradient id="perf-fill" x1="0" x2="0" y1="0" y2="1">
                        <stop offset="0%" stop-color="rgba(42,255,180,0.50)"></stop>
                        <stop offset="100%" stop-color="rgba(42,255,180,0.02)"></stop>
                      </linearGradient>
                      <filter id="perf-glow">
                        <feGaussianBlur stdDeviation="5" result="colored"></feGaussianBlur>
                        <feMerge>
                          <feMergeNode in="colored"></feMergeNode>
                          <feMergeNode in="SourceGraphic"></feMergeNode>
                        </feMerge>
                      </feMerge>
                    </defs>
                    ${this._renderGridLines()}
                    <path class="perf-backdrop" d="${snapshot.performanceBackdropPath}"></path>
                    <path class="perf-area" d="${snapshot.performanceAreaPath}"></path>
                    <path class="perf-line" d="${snapshot.performanceLinePath}"></path>
                    <circle class="perf-dot" cx="${snapshot.performanceDot.x}" cy="${snapshot.performanceDot.y}" r="5"></circle>
                  </svg>
                  <div class="axis-row">${snapshot.performanceAxis.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
                </div>
                <aside class="performance-side">
                  <div class="side-metric">
                    <span>${escapeHtml(snapshot.performanceChangeLabel)}</span>
                    <strong>${formatMoney(snapshot.performanceChange, snapshot.currency)}</strong>
                    <em>${formatPercent(snapshot.performanceChangePercent)}</em>
                  </div>
                  <div class="side-metric">
                    <span>Trend high</span>
                    <strong>${formatMoney(snapshot.performanceHigh, snapshot.currency)}</strong>
                  </div>
                  <div class="side-metric">
                    <span>Trend low</span>
                    <strong>${formatMoney(snapshot.performanceLow, snapshot.currency)}</strong>
                  </div>
                </aside>
              </div>
            </section>
          </div>
        </section>
      </ha-card>
    `;
    this._bindInteractiveUi();
  }

  _resolveEntities() {
    const states = this._hass.states || {};
    const resolved = {};
    for (const [key, suffix] of Object.entries(SUMMARY_KEYS)) {
      resolved[key] = this._findEntity(key, suffix, states);
    }
    resolved.positionEntities = this._findPositionEntities(states);
    return resolved;
  }

  _findEntity(key, suffix, states) {
    const config = this._config || {};
    const entities = config.entities || {};
    const explicit = entities[key] || config[key];
    if (explicit && states[explicit]) {
      return states[explicit];
    }

    const prefix = config.entity_prefix || DEFAULT_PREFIX;
    const exact = `sensor.${prefix}_${suffix}`;
    if (states[exact]) {
      return states[exact];
    }

    const candidates = Object.values(states).filter((stateObj) => {
      const id = stateObj.entity_id || "";
      return id.startsWith("sensor.") && id.includes(prefix) && id.endsWith(`_${suffix}`);
    });
    return candidates[0] || null;
  }

  _findPositionEntities(states) {
    const config = this._config || {};
    const prefix = config.entity_prefix || DEFAULT_PREFIX;
    return Object.values(states)
      .filter((stateObj) => {
        const id = stateObj.entity_id || "";
        return id.startsWith("sensor.") && id.includes(prefix) && id.includes("_position_");
      })
      .sort((left, right) => {
        const leftValue = numericState(left);
        const rightValue = numericState(right);
        return rightValue - leftValue;
      });
  }

  _buildSnapshot(stateMap) {
    const accountValueState = stateMap.account_value;
    const currency = firstDefined(
      accountValueState?.attributes?.unit_of_measurement,
      stateMap.cash?.attributes?.unit_of_measurement,
      stateMap.result?.attributes?.unit_of_measurement,
      "GBP",
    );
    const accountValue = numericState(accountValueState);
    const cash = numericState(stateMap.cash);
    const freeFunds = numericState(stateMap.free_funds);
    const invested = numericState(stateMap.invested);
    const holdingsValue = numericState(stateMap.holdings_value);
    const openPositions = numericState(stateMap.open_positions);
    const result = numericState(stateMap.result);
    const resultPercent = numericState(stateMap.result_percent);
    const dailyResult = numericState(stateMap.daily_gain_loss);
    const dailyResultPercent = numericState(stateMap.daily_gain_loss_percent);
    const dailyMarketAvailable = stateMap.daily_gain_loss?.attributes?.available !== false
      && dailyResult !== null;
    const accountChange = numericState(stateMap.account_change);
    const accountChangePercent = numericState(stateMap.account_change_percent);
    const totalUnrealisedResult = numericState(stateMap.total_unrealised_result);
    const piesCount = numericState(stateMap.pies_count);
    const totalPiesValue = numericState(stateMap.total_pies_value);
    const totalPiesTotalValueIncludingCash = numericState(stateMap.total_pies_value_including_cash);
    const totalPiesCash = numericState(stateMap.total_pies_cash);
    const totalPiesResult = numericState(stateMap.total_pies_result);
    const topFiveConcentration = numericState(stateMap.top_5_position_concentration_percentage);
    const lastUpdateRaw = stateMap.last_update?.state;
    const lastUpdateLabel = formatRelative(lastUpdateRaw);
    const pieSummary = this._buildPieSummary(stateMap, currency);

    const richPositions = this._normalizePositionEntities(stateMap.positionEntities);
    const moverCandidates = dedupeMovers(this._buildMoverCandidates(stateMap, currency));
    const topMovers = moverCandidates
      .filter((item) => (item.changePercent ?? -999) >= 0)
      .sort((a, b) => (b.changePercent ?? -999) - (a.changePercent ?? -999))
      .slice(0, 5);
    const bottomMovers = moverCandidates
      .filter((item) => (item.changePercent ?? 999) < 0)
      .sort((a, b) => (a.changePercent ?? 999) - (b.changePercent ?? 999))
      .slice(0, 5);

    const allocationEntries = richPositions
      .filter((item) => (item.currentValue ?? 0) > 0)
      .slice()
      .sort((a, b) => (b.currentValue ?? 0) - (a.currentValue ?? 0))
      .slice(0, 6);
    const allocationTotal = allocationEntries.reduce((sum, item) => sum + Math.max(item.currentValue || 0, 0), 0);
    const legendItems = allocationEntries
      .map((item, index) => ({
        label: item.ticker || item.label,
        value: allocationTotal > 0 ? ((Math.max(item.currentValue || 0, 0) / allocationTotal) * 100) : 0,
        tone: item.tone || toneForIndex(index),
      }))
      .filter((item) => item.value > 0);
    const allocationAvailable = legendItems.length >= 2 && legendItems.some((item) => item.value > 0.5);
    const ringBackground = allocationAvailable ? buildConicGradient(legendItems) : null;

    const heroSeries = buildSeries(
      `${accountValue}:${result}:${dailyResult}:${topMovers.map((item) => item.ticker).join(",")}`,
      46,
      accountValue || holdingsValue || 100000,
      Math.abs(dailyResult || result || 1500),
      0.08,
      {
        floorRatio: 0.42,
        wobble: 1.45,
        noise: 0.16,
        pulse: 0.22,
      },
    );
    const performanceSeries = buildSeries(
      `${accountValue}:${holdingsValue}:${topFiveConcentration}:${bottomMovers.map((item) => item.ticker).join(",")}`,
      90,
      holdingsValue || accountValue || 100000,
      Math.abs(result || 3500),
      0.2,
      {
        floorRatio: 0.48,
        wobble: 1.15,
        noise: 0.08,
        pulse: 0.12,
      },
    );
    const heroPaths = buildChartPaths(heroSeries, 1000, 260, 26);
    const perfPaths = buildChartPaths(performanceSeries, 1180, 300, 32);
    const heroBackdropSeries = buildSeries(
      `backdrop:${accountValue}:${dailyResult}:${topFiveConcentration}`,
      22,
      accountValue || 100000,
      Math.abs(dailyResult || 1200),
      0.02,
      {
        floorRatio: 0.48,
        wobble: 0.85,
        noise: 0.04,
        pulse: 0.08,
      },
    );
    const heroBackdropPath = buildBackdropPath(heroBackdropSeries, 1000, 260, 26, 0.55);
    const performanceBackdropSeries = buildSeries(
      `perfback:${accountValue}:${holdingsValue}:${result}`,
      26,
      holdingsValue || accountValue || 100000,
      Math.abs(result || 3200),
      0.06,
      {
        floorRatio: 0.5,
        wobble: 0.78,
        noise: 0.03,
        pulse: 0.06,
      },
    );
    const performanceBackdropPath = buildBackdropPath(performanceBackdropSeries, 1180, 300, 32, 0.45);

    const performanceHigh = Math.max(...performanceSeries);
    const performanceLow = Math.min(...performanceSeries);
    const performanceChange = accountChange ?? result ?? 0;
    const performanceChangePercent = accountChangePercent ?? resultPercent ?? 0;
    const performanceChangeLabel = accountChange !== null ? "Account change" : "Unrealised P/L";

    const ringCenterLabel = "Largest 6";
    const ringCenterValue = allocationAvailable ? formatPercent(legendItems.reduce((sum, item) => sum + item.value, 0)) : "—";
    const heroChartNote = "Decorative trend backdrop";
    const performancePoints = buildTooltipPoints(
      performanceSeries,
      ["Jun ’23", "Jul ’23", "Aug ’23", "Sep ’23", "Oct ’23", "Nov ’23", "Dec ’23", "Jan ’24", "Feb ’24", "Mar ’24", "Apr ’24", "May ’24"],
      currency,
    );
    const performanceNote = "Decorative fallback trend based on current read-only account snapshot";

    return {
      currency,
      accountValue,
      cash,
      freeFunds,
      invested,
      holdingsValue,
      openPositions,
      result,
      resultPercent,
      dailyResult,
      dailyResultPercent,
      dailyMarketAvailable,
      accountChange,
      accountChangePercent,
      totalUnrealisedResult,
      piesCount,
      totalPiesValue,
      totalPiesTotalValueIncludingCash,
      totalPiesCash,
      totalPiesResult,
      pieSummary,
      topFiveConcentration,
      lastUpdateLabel,
      topMovers,
      bottomMovers,
      allocationAvailable,
      legendItems,
      ringBackground,
      ringCenterLabel,
      ringCenterValue,
      heroBackdropPath,
      heroLinePath: heroPaths.line,
      heroAreaPath: heroPaths.area,
      heroDot: heroPaths.dot,
      heroChartNote,
      performanceBackdropPath,
      performanceLinePath: perfPaths.line,
      performanceAreaPath: perfPaths.area,
      performanceDot: perfPaths.dot,
      performanceAxis: ["Jun ’23", "Jul ’23", "Aug ’23", "Sep ’23", "Oct ’23", "Nov ’23", "Dec ’23", "Jan ’24", "Feb ’24", "Mar ’24", "Apr ’24", "May ’24"],
      performancePoints,
      performanceNote,
      performanceIsFallback: true,
      performanceHigh,
      performanceLow,
      performanceChange,
      performanceChangePercent,
      performanceChangeLabel,
    };
  }

  _buildPieSummary(stateMap, currency) {
    const totalValueState = stateMap.total_pies_value;
    const totalValueIncludingCashState = stateMap.total_pies_value_including_cash;
    const largestPieState = stateMap.largest_pie;
    const attrs = largestPieState?.attributes || {};
    const pieSummaryAttrs = totalValueState?.attributes || totalValueIncludingCashState?.attributes || {};
    const pies = Array.isArray(pieSummaryAttrs.pies) ? pieSummaryAttrs.pies : [];
    const pieCount = pies.length || numericState(stateMap.pies_count);
    const totalValue = numericState(stateMap.total_pies_value);
    const totalValueIncludingCash = numericState(stateMap.total_pies_value_including_cash);
    const totalCash = numericState(stateMap.total_pies_cash);
    const totalResult = numericState(stateMap.total_pies_result);
    const largestPieLabel = textOrNull(largestPieState?.state);
    const largestPieValue = numericState(stateMap.largest_pie_value) ?? numericValue(attrs.holding_value) ?? numericValue(attrs.value);
    const largestPieTotalValueIncludingCash = numericValue(attrs.total_value_including_cash);
    const largestPieCash = numericValue(attrs.cash);
    const largestPieResult = numericValue(attrs.result);
    const pieCurrency = textOrNull(attrs.currency) || currency;

    const hasSummary = pieCount !== null || totalValue !== null || totalValueIncludingCash !== null || largestPieLabel !== null || pies.length > 0;
    const ringSegments = [
      largestPieValue && totalValue && largestPieValue > 0 && totalValue > 0
        ? { label: largestPieLabel || "Largest pie", value: Math.min(100, (largestPieValue / totalValue) * 100), tone: "#2de2c0" }
        : null,
      totalCash && totalValueIncludingCash && totalCash > 0 && totalValueIncludingCash > 0
        ? { label: "Pie cash", value: Math.min(100, (totalCash / totalValueIncludingCash) * 100), tone: "#2aa8ff" }
        : null,
      totalResult !== null && totalValue && totalValue > 0
        ? { label: "Result", value: Math.min(100, Math.abs(totalResult / totalValue) * 100), tone: totalResult >= 0 ? "#7e6bff" : "#ff5264" }
        : null,
    ].filter(Boolean);

    const rows = pies.length
      ? pies
        .map((pie) => normalizePieRow(pie, pieCurrency))
        .filter(Boolean)
        .slice(0, 5)
      : [];
    if (!rows.length && largestPieLabel) {
      rows.push({
        label: largestPieLabel,
        sublabel: largestPieResult !== null ? formatSignedMoney(largestPieResult, pieCurrency) : "Largest pie",
        valueLabel: largestPieValue !== null ? formatMoney(largestPieValue, pieCurrency) : "—",
        percent: largestPieValue && totalValue ? Math.min(100, (largestPieValue / totalValue) * 100) : null,
      });
    }
    if (!rows.length && totalValue !== null) {
      rows.push({
        label: "All pies holdings",
        sublabel: pieCount !== null ? `${pieCount} pie${pieCount === 1 ? "" : "s"}` : "Summary",
        valueLabel: formatMoney(totalValue, pieCurrency),
        percent: 100,
      });
    }
    if (!rows.length && totalCash !== null) {
      rows.push({
        label: "Pies cash",
        sublabel: largestPieCash !== null ? formatMoney(largestPieCash, pieCurrency) : "Available cash",
        valueLabel: formatMoney(totalCash, pieCurrency),
        percent: totalValueIncludingCash ? Math.min(100, (totalCash / totalValueIncludingCash) * 100) : null,
      });
    }
    if (!rows.length && totalValueIncludingCash !== null) {
      rows.push({
        label: "All pies incl. cash",
        sublabel: largestPieTotalValueIncludingCash !== null ? formatMoney(largestPieTotalValueIncludingCash, pieCurrency) : "Total value",
        valueLabel: formatMoney(totalValueIncludingCash, pieCurrency),
        percent: null,
      });
    }

    return {
      available: hasSummary,
      ringSegments,
      ringBackground: ringSegments.length ? buildConicGradient(ringSegments) : "conic-gradient(rgba(52, 89, 145, 0.42) 0 100%)",
      ringCenterLabel: pieCount !== null ? `${pieCount} pie${pieCount === 1 ? "" : "s"}` : "Pies",
      ringCenterValue: totalValueIncludingCash !== null ? formatMoney(totalValueIncludingCash, pieCurrency) : "Unavailable",
      rows: rows.slice(0, 5),
      fallbackTitle: "Pies data unavailable",
      fallbackCopy: "Enable read-only pies summary when available.",
    };
  }

  _normalizePositionEntities(positionStates) {
    return (positionStates || [])
      .map((stateObj, index) => {
        const attrs = stateObj.attributes || {};
        const ticker = textOrNull(attrs.ticker) || textOrNull(stateObj.entity_id?.split("_").pop());
        const label = textOrNull(attrs.name) || ticker || `Holding ${index + 1}`;
        const value = numericValue(attrs.current_value) ?? numericState(stateObj);
        const result = numericValue(attrs.result);
        const resultPercent = numericValue(attrs.result_percent);
        return {
          entityId: stateObj.entity_id,
          label,
          ticker,
          company: textOrNull(attrs.name) || ticker || "Unlabelled instrument",
          currentValue: value,
          result,
          resultPercent,
          quantity: numericValue(attrs.quantity),
          currentPrice: numericValue(attrs.current_price),
          averagePrice: numericValue(attrs.average_price),
          tone: result !== null && result < 0 ? "#ff4e63" : "#3dffb0",
        };
      })
      .filter((item) => item.ticker || item.label);
  }

  _buildMoverCandidates(stateMap, currency) {
    const summaryCandidates = [
      normalizeMoverSensor(stateMap.top_daily_mover, currency, "#3dffb0"),
      normalizeMoverSensor(stateMap.biggest_daily_gain_value, currency, "#3dffb0"),
      normalizeMoverSensor(stateMap.bottom_daily_mover, currency, "#ff4e63"),
      normalizeMoverSensor(stateMap.biggest_daily_loss_value, currency, "#ff4e63"),
    ];
    return dedupeByTicker(summaryCandidates.filter(Boolean));
  }

  _renderMetricTile(label, value, icon, unit, secondaryValue = null) {
    const negative = typeof value === "number" && value < 0;
    return `
      <div class="metric-tile ${negative ? "negative" : ""}">
        <div class="metric-icon ${icon}">${iconMarkup(icon)}</div>
        <div class="metric-body">
          <span class="metric-label">${escapeHtml(label)}</span>
          <strong class="metric-value">${formatPrimary(value, unit)}</strong>
          ${secondaryValue !== null && secondaryValue !== undefined ? `<em class="metric-secondary ${negative ? "negative" : "positive"}">${formatPercent(secondaryValue)}</em>` : ""}
        </div>
      </div>
    `;
  }

  _renderCompactMetric(label, value, unit, secondaryValue = null) {
    const negative = typeof value === "number" && value < 0;
    return `
      <div class="compact-metric ${negative ? "negative" : ""}">
        <span class="compact-label">${escapeHtml(label)}</span>
        <strong class="compact-value">${formatPrimary(value, unit)}</strong>
        ${secondaryValue !== null && secondaryValue !== undefined ? `<em class="compact-secondary ${negative ? "negative" : "positive"}">${formatPercent(secondaryValue)}</em>` : ""}
      </div>
    `;
  }

  _renderCompactStatus(label, message) {
    return `
      <div class="compact-metric">
        <span class="compact-label">${escapeHtml(label)}</span>
        <strong class="compact-value compact-value-muted">${escapeHtml(message)}</strong>
      </div>
    `;
  }

  _renderHeroLogo() {
    return `
      <div class="hero-logo">
        <span class="hero-symbol">${this._brandMark()}</span>
        <span class="hero-word">Trading 212</span>
      </div>
    `;
  }

  _renderHeroStat(label, value, unit, percent = null) {
    const negative = typeof value === "number" && value < 0;
    return `
      <div class="hero-stat">
        <span>${escapeHtml(label)}</span>
        <strong class="${negative ? "negative" : "positive"}">${formatPrimary(value, unit)}</strong>
        ${percent !== null && percent !== undefined ? `<em class="${negative ? "negative" : "positive"}">${formatPercent(percent)}</em>` : ""}
      </div>
    `;
  }

  _renderLegend(items) {
    return items
      .map((item) => `
        <div class="legend-item">
          <span class="legend-dot" style="background:${item.tone}"></span>
          <span class="legend-label">${escapeHtml(item.label)}</span>
          <strong>${formatPercent(item.value)}</strong>
        </div>
      `)
      .join("");
  }

  _renderPiesPanel(snapshot) {
    const pieSummary = snapshot.pieSummary;
    if (!pieSummary.available) {
      return `
        <section class="panel pies-panel pies-fallback">
          <div class="panel-title">Pies</div>
          <div class="pies-fallback-ring">
            <span>Pies</span>
            <strong>Unavailable</strong>
          </div>
          <div class="pies-fallback-copy">
            <strong>${escapeHtml(pieSummary.fallbackTitle)}</strong>
            <span>${escapeHtml(pieSummary.fallbackCopy)}</span>
          </div>
        </section>
      `;
    }

    return `
      <section class="panel pies-panel">
        <div class="panel-title">Pies</div>
        <div class="pies-top">
          <div class="pies-ring" style="background:${pieSummary.ringBackground}">
            <div class="pies-ring-core">
              <span>${escapeHtml(pieSummary.ringCenterLabel)}</span>
              <strong>${escapeHtml(pieSummary.ringCenterValue)}</strong>
            </div>
          </div>
          <div class="pies-mini-stats">
            <div><span>Holdings</span><strong>${formatMoney(snapshot.totalPiesValue, snapshot.currency)}</strong></div>
            <div><span>Total incl. cash</span><strong>${formatMoney(snapshot.totalPiesTotalValueIncludingCash, snapshot.currency)}</strong></div>
            <div><span>Cash</span><strong>${formatMoney(snapshot.totalPiesCash, snapshot.currency)}</strong></div>
            <div><span>Result</span><strong class="${(snapshot.totalPiesResult ?? 0) < 0 ? "negative" : "positive"}">${formatSignedMoney(snapshot.totalPiesResult, snapshot.currency)}</strong></div>
          </div>
        </div>
        <div class="pies-list-head">
          <span>Top pies</span>
          <span>Holding value</span>
        </div>
        <div class="pies-list">
          ${pieSummary.rows.length ? pieSummary.rows.map((row) => this._renderPieRow(row)).join("") : '<div class="pies-empty">Per-pie ranking detail is not available from current entities.</div>'}
        </div>
      </section>
    `;
  }

  _renderPieRow(row) {
    return `
      <div class="pie-row">
        <div class="pie-row-copy">
          <strong>${escapeHtml(row.label)}</strong>
          <span>${escapeHtml(row.sublabel)}</span>
        </div>
        <div class="pie-row-value">
          <strong>${escapeHtml(row.valueLabel)}</strong>
          ${row.percent !== null && row.percent !== undefined ? `<em>${formatPercent(row.percent)}</em>` : ""}
        </div>
      </div>
    `;
  }

  _renderMoversSection(title, items, positive, currency) {
    if (!items.length) {
      return `
        <div class="movers-head">
          <div class="panel-title">${escapeHtml(title)}</div>
          <div class="movers-columns">
            <span>Daily %</span>
            <span>Daily £</span>
          </div>
        </div>
        <div class="movers-empty">Daily movers unavailable until market P/L data is available.</div>
      `;
    }
    return `
      <div class="movers-head">
        <div class="panel-title">${escapeHtml(title)}</div>
        <div class="movers-columns">
          <span>Daily %</span>
          <span>Daily £</span>
        </div>
      </div>
      <div class="movers-list">
        ${items.map((item, index) => this._renderMoverRow(item, index, positive, currency)).join("")}
      </div>
    `;
  }

  _renderMoverRow(item, index, positive, currency) {
    const spark = buildMiniSparkline(item.sparkSeed, positive ? 1 : -1);
    const tone = item.tone || (positive ? "#3dffb0" : "#ff4e63");
    return `
      <div class="mover-row ${item.placeholder ? "placeholder" : ""}">
        <span class="mover-rank">${index + 1}</span>
        <span class="mover-logo" style="${logoStyle(item.ticker)}">${logoMark(item.ticker)}</span>
        <div class="mover-copy">
          <strong>${escapeHtml(item.ticker || item.label || "—")}</strong>
          <span>${escapeHtml(item.company || "Awaiting richer position detail")}</span>
        </div>
        <svg class="mover-spark" viewBox="0 0 120 36" preserveAspectRatio="none" aria-hidden="true">
          <path d="${spark}" stroke="${tone}" fill="none" stroke-width="2.4" stroke-linecap="round"></path>
        </svg>
        <span class="mover-change ${positive ? "positive" : "negative"}">${item.changePercent !== null && item.changePercent !== undefined ? formatSignedPercent(item.changePercent) : "—"}</span>
        <span class="mover-value ${positive ? "positive" : "negative"}">${item.changeValue !== null && item.changeValue !== undefined ? formatSignedMoney(item.changeValue, currency) : "—"}</span>
      </div>
    `;
  }

  _renderGridLines() {
    const lines = [];
    for (let index = 0; index < 5; index += 1) {
      const y = 34 + index * 56;
      lines.push(`<line x1="0" y1="${y}" x2="1180" y2="${y}" class="grid-line"></line>`);
    }
    return lines.join("");
  }

  _brandMark() {
    return `<svg viewBox="0 0 72 72" aria-hidden="true"><defs><linearGradient id="mark-grad" x1="0" x2="1" y1="0" y2="1"><stop offset="0%" stop-color="#25b7ff"></stop><stop offset="100%" stop-color="#0ae0cf"></stop></linearGradient></defs><path fill="url(#mark-grad)" d="M11 58 27.5 14h17L61 58H47.3l-4-11.2H29.6L25.8 58H11Zm21.8-21.3h7.1L36.4 24.8l-3.6 11.9Z"></path></svg>`;
  }

  _bindInteractiveUi() {
    const chart = this.shadowRoot?.querySelector(".performance-chart");
    const tooltip = this.shadowRoot?.querySelector(".performance-tooltip");
    const points = this._snapshot?.performancePoints || [];
    if (!chart || !tooltip || !points.length) {
      return;
    }

    const handleLeave = () => {
      tooltip.hidden = true;
    };
    const handleMove = (event) => {
      const rect = chart.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
      const index = Math.min(points.length - 1, Math.max(0, Math.round(ratio * (points.length - 1))));
      const point = points[index];
      const left = Math.max(12, Math.min(rect.width - 144, (event.clientX - rect.left) + 12));
      const top = Math.max(8, Math.min(rect.height - 70, (event.clientY - rect.top) - 52));
      tooltip.innerHTML = `
        <strong>${escapeHtml(point.label)}</strong>
        <span>${escapeHtml(point.valueLabel)}</span>
        <em>${escapeHtml(point.changeLabel)}</em>
        <small>${escapeHtml(point.note)}</small>
      `;
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
      tooltip.hidden = false;
    };

    chart.onmousemove = handleMove;
    chart.onmouseleave = handleLeave;
  }

  _style() {
    return `
      <style>
        :host {
          --t212-bg: radial-gradient(circle at 18% 18%, rgba(15, 90, 168, 0.22), transparent 28%), radial-gradient(circle at 80% 0%, rgba(33, 255, 202, 0.10), transparent 30%), linear-gradient(180deg, #020816 0%, #060d1d 48%, #030813 100%);
          --t212-panel: linear-gradient(180deg, rgba(7, 17, 34, 0.92) 0%, rgba(3, 11, 24, 0.90) 100%);
          --t212-panel-soft: linear-gradient(180deg, rgba(7, 17, 34, 0.76) 0%, rgba(3, 11, 24, 0.72) 100%);
          --t212-glow: rgba(61, 255, 176, 0.16);
          --t212-edge: rgba(65, 128, 255, 0.30);
          --t212-border: rgba(104, 184, 255, 0.20);
          --t212-text: #f2f7ff;
          --t212-muted: #8ea1bb;
          --t212-soft: #5f728f;
          --t212-positive: #39ffb1;
          --t212-negative: #ff5264;
          --t212-yellow: #f9d74d;
          --t212-cyan: #1ddfff;
          --t212-radius: 24px;
          display: block;
          color: var(--t212-text);
        }

        ha-card.card-shell {
          background: transparent;
          border: none;
          box-shadow: none;
          overflow: visible;
        }

        .shell {
          position: relative;
          overflow: hidden;
          border-radius: 28px;
          border: 1px solid rgba(91, 152, 255, 0.36);
          background: var(--t212-bg);
          box-shadow:
            0 0 0 1px rgba(89, 184, 255, 0.12) inset,
            0 0 28px rgba(20, 100, 255, 0.16),
            0 0 84px rgba(17, 104, 255, 0.08),
            0 20px 44px rgba(0, 0, 0, 0.46);
          padding: 16px 16px 14px;
          min-height: 720px;
        }

        .glow {
          position: absolute;
          inset: auto;
          pointer-events: none;
          filter: blur(30px);
          opacity: 0.7;
        }

        .glow-a {
          top: -80px;
          right: -40px;
          width: 220px;
          height: 220px;
          background: rgba(43, 166, 255, 0.20);
        }

        .glow-b {
          left: 34%;
          top: 160px;
          width: 260px;
          height: 200px;
          background: rgba(61, 255, 176, 0.11);
        }

        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          margin-bottom: 6px;
        }

        .brand {
          display: flex;
          align-items: center;
          gap: 14px;
          min-width: 0;
        }

        .brand-mark {
          width: 52px;
          height: 52px;
          display: grid;
          place-items: center;
          border-radius: 14px;
          background: rgba(9, 20, 41, 0.66);
          box-shadow: 0 0 0 1px rgba(67, 170, 255, 0.12) inset;
        }

        .brand-mark svg,
        .hero-symbol svg {
          width: 36px;
          height: 36px;
          display: block;
        }

        .brand-copy h1 {
          margin: 0;
          font: 700 18px/1.1 "Segoe UI", "Trebuchet MS", sans-serif;
          letter-spacing: 0;
        }

        .brand-copy p {
          margin: 4px 0 0;
          color: var(--t212-muted);
          font: 500 11px/1.2 "Segoe UI", sans-serif;
        }

        .meta-strip {
          display: flex;
          align-items: center;
          gap: 10px;
          flex-wrap: wrap;
          justify-content: flex-end;
        }

        .meta-chip,
        .meta-mini {
          border-radius: 999px;
          border: 1px solid rgba(120, 168, 255, 0.18);
          background: rgba(6, 15, 28, 0.72);
          color: #d6e4fb;
          padding: 6px 12px;
          font: 600 11px/1 "Segoe UI", sans-serif;
          display: inline-flex;
          align-items: center;
          gap: 7px;
        }

        .meta-mini {
          border: none;
          background: transparent;
          padding: 0 2px;
          color: var(--t212-muted);
          font-weight: 500;
        }

        .meta-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--t212-positive);
          box-shadow: 0 0 10px rgba(57, 255, 177, 0.85);
        }

        .account-strip {
          display: grid;
          grid-template-columns: repeat(6, minmax(0, 1fr)) auto;
          gap: 6px;
          align-items: center;
          margin-bottom: 8px;
        }

        .account-strip-meta {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          color: rgba(188, 210, 233, 0.56);
          font: 500 10px/1 "Segoe UI", sans-serif;
          letter-spacing: 0.04em;
          white-space: nowrap;
          padding: 0 2px;
        }

        .layout {
          display: grid;
          grid-template-columns: 200px minmax(500px, 1fr) 340px;
          grid-template-rows: auto auto 1fr;
          gap: 9px;
          align-items: stretch;
        }

        .pies-column {
          grid-column: 1;
          grid-row: 1 / span 2;
        }

        .panel,
        .hero-panel {
          position: relative;
          overflow: hidden;
          border-radius: 20px;
          border: 1px solid var(--t212-border);
          background: var(--t212-panel-soft);
          box-shadow:
            0 0 0 1px rgba(255, 255, 255, 0.02) inset,
            0 16px 34px rgba(0, 0, 0, 0.28);
          backdrop-filter: blur(18px);
        }

        .pies-panel {
          min-height: 100%;
          display: grid;
          grid-template-rows: auto auto auto 1fr;
          gap: 10px;
          padding: 12px 12px 10px;
        }

        .pies-top {
          display: grid;
          gap: 10px;
        }

        .pies-ring {
          width: 122px;
          height: 122px;
          margin: 0 auto;
          border-radius: 50%;
          display: grid;
          place-items: center;
          box-shadow: 0 0 26px rgba(42, 210, 255, 0.10);
        }

        .pies-ring-core {
          width: 74px;
          height: 74px;
          border-radius: 50%;
          background: rgba(5, 15, 28, 0.95);
          display: grid;
          place-items: center;
          text-align: center;
          padding: 10px;
          box-shadow: 0 0 0 1px rgba(126, 180, 255, 0.16) inset;
        }

        .pies-ring-core span,
        .pies-fallback-ring span {
          color: var(--t212-muted);
          font: 600 9px/1.1 "Segoe UI", sans-serif;
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }

        .pies-ring-core strong,
        .pies-fallback-ring strong {
          display: block;
          margin-top: 5px;
          font: 800 13px/1.15 "Segoe UI", sans-serif;
        }

        .pies-mini-stats {
          display: grid;
          gap: 7px;
        }

        .pies-mini-stats div {
          display: grid;
          gap: 3px;
          padding: 8px 9px;
          border-radius: 12px;
          background: rgba(10, 20, 37, 0.76);
          border: 1px solid rgba(103, 140, 196, 0.12);
        }

        .pies-mini-stats span {
          color: var(--t212-muted);
          font: 600 10px/1 "Segoe UI", sans-serif;
          text-transform: uppercase;
          letter-spacing: 0.06em;
        }

        .pies-mini-stats strong {
          font: 700 13px/1.15 "Segoe UI", sans-serif;
        }

        .pies-list-head {
          display: flex;
          justify-content: space-between;
          gap: 8px;
          color: #b8c8dc;
          font: 600 10px/1 "Segoe UI", sans-serif;
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }

        .pies-list {
          display: grid;
          gap: 6px;
          align-content: start;
        }

        .pies-empty {
          color: var(--t212-muted);
          font: 500 11px/1.35 "Segoe UI", sans-serif;
          padding-top: 4px;
        }

        .pie-row {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 10px;
          align-items: center;
          padding: 7px 0;
          border-top: 1px solid rgba(95, 128, 164, 0.16);
        }

        .pie-row:first-child {
          border-top: none;
          padding-top: 0;
        }

        .pie-row-copy,
        .pie-row-value {
          display: grid;
          gap: 2px;
          min-width: 0;
        }

        .pie-row-copy strong,
        .pie-row-copy span {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .pie-row-copy strong {
          font: 700 12px/1.15 "Segoe UI", sans-serif;
        }

        .pie-row-copy span,
        .pie-row-value em {
          color: var(--t212-muted);
          font: 500 11px/1.1 "Segoe UI", sans-serif;
          font-style: normal;
        }

        .pie-row-value {
          text-align: right;
        }

        .pie-row-value strong {
          font: 700 12px/1.1 "Segoe UI", sans-serif;
        }

        .pies-fallback {
          display: grid;
          align-content: start;
          gap: 14px;
        }

        .pies-fallback-ring {
          width: 122px;
          height: 122px;
          margin: 0 auto;
          border-radius: 50%;
          display: grid;
          place-items: center;
          text-align: center;
          background:
            radial-gradient(circle at 50% 50%, rgba(7, 18, 32, 0.96) 0 40px, transparent 41px),
            conic-gradient(rgba(74, 99, 137, 0.22) 0 100%);
          border: 1px solid rgba(118, 154, 212, 0.16);
          box-shadow: inset 0 0 0 12px rgba(26, 40, 66, 0.38);
        }

        .pies-fallback-copy {
          display: grid;
          gap: 6px;
          text-align: center;
        }

        .pies-fallback-copy strong {
          font: 700 13px/1.3 "Segoe UI", sans-serif;
          color: #edf5ff;
        }

        .pies-fallback-copy span {
          color: var(--t212-muted);
          font: 500 11px/1.35 "Segoe UI", sans-serif;
        }

        .hero-panel {
          grid-column: 2;
          grid-row: 1;
          min-height: 300px;
          background:
            radial-gradient(circle at 50% 14%, rgba(36, 255, 205, 0.08), transparent 35%),
            radial-gradient(circle at 14% 74%, rgba(26, 162, 255, 0.12), transparent 28%),
            linear-gradient(180deg, rgba(3, 22, 35, 0.95) 0%, rgba(5, 18, 31, 0.92) 100%);
          padding: 16px 16px 12px;
          border-color: rgba(66, 224, 180, 0.42);
          box-shadow:
            0 0 0 1px rgba(255, 255, 255, 0.02) inset,
            0 0 36px rgba(31, 255, 191, 0.09),
            0 16px 34px rgba(0, 0, 0, 0.34);
        }

        .hero-topline {
          display: flex;
          justify-content: center;
          margin-top: 1px;
        }

        .compact-metric {
          min-width: 0;
          padding: 3px 5px 2px;
          border-radius: 0;
          background: transparent;
          border: none;
          box-shadow: none;
        }

        .compact-label {
          display: block;
          color: #c5d3e7;
          font: 600 8px/1 "Segoe UI", sans-serif;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .compact-value {
          display: block;
          margin-top: 3px;
          font: 700 11px/1.05 "Segoe UI", sans-serif;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .compact-value-muted {
          color: var(--t212-muted);
          font-size: 10px;
        }

        .compact-secondary {
          display: block;
          margin-top: 2px;
          font: 600 9px/1 "Segoe UI", sans-serif;
          font-style: normal;
        }

        .hero-logo {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          font: 800 24px/1 "Segoe UI", sans-serif;
          text-transform: uppercase;
          letter-spacing: 0.06em;
        }

        .hero-symbol {
          display: grid;
          place-items: center;
          width: 34px;
          height: 34px;
        }

        .hero-value-wrap {
          text-align: center;
          margin-top: 14px;
        }

        .eyebrow {
          color: #d3e4f4;
          text-transform: uppercase;
          letter-spacing: 0.14em;
          font: 600 12px/1.1 "Segoe UI", sans-serif;
        }

        .hero-value {
          margin-top: 6px;
          font: 800 clamp(52px, 5.6vw, 88px)/0.95 "Segoe UI", sans-serif;
          letter-spacing: 0;
          text-shadow: 0 0 16px rgba(255, 255, 255, 0.08);
        }

        .positive {
          color: var(--t212-positive);
        }

        .negative {
          color: var(--t212-negative);
        }

        .hero-chart {
          position: absolute;
          left: 14px;
          right: 14px;
          bottom: 12px;
          height: 108px;
        }

        .hero-chart svg,
        .performance-chart svg {
          width: 100%;
          height: 100%;
          display: block;
        }

        .hero-area {
          fill: url(#hero-fill);
          opacity: 0.78;
        }

        .hero-backdrop {
          fill: none;
          stroke: rgba(125, 255, 203, 0.18);
          stroke-width: 1.8;
          stroke-linecap: round;
          stroke-dasharray: 3 10;
        }

        .hero-line {
          fill: none;
          stroke: #72ffc2;
          stroke-width: 3.2;
          stroke-linecap: round;
          filter: url(#hero-glow);
        }

        .hero-dot {
          fill: #b7ffe2;
          filter: url(#hero-glow);
        }

        .hero-chart-note {
          position: absolute;
          left: 8px;
          bottom: -2px;
          color: rgba(188, 210, 233, 0.48);
          font: 500 9px/1 "Segoe UI", sans-serif;
          letter-spacing: 0.06em;
          text-transform: uppercase;
        }

        .allocation-column {
          grid-column: 3;
          grid-row: 1;
          display: grid;
          grid-template-rows: 1fr auto;
          gap: 9px;
        }

        .panel {
          padding: 12px 14px;
        }

        .panel-title {
          color: #eef6ff;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          font: 700 12px/1.1 "Segoe UI", sans-serif;
        }

        .ring-wrap {
          display: grid;
          grid-template-columns: 148px 1fr;
          gap: 10px;
          align-items: center;
          margin-top: 10px;
        }

        .ring-chart {
          width: 140px;
          height: 140px;
          border-radius: 50%;
          display: grid;
          place-items: center;
          box-shadow: 0 0 24px rgba(18, 161, 255, 0.12);
        }

        .ring-core {
          width: 82px;
          height: 82px;
          border-radius: 50%;
          background: rgba(5, 15, 28, 0.95);
          display: grid;
          place-items: center;
          text-align: center;
          box-shadow: 0 0 0 1px rgba(126, 180, 255, 0.16) inset;
        }

        .ring-core-label {
          color: var(--t212-muted);
          font: 600 10px/1 "Segoe UI", sans-serif;
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }

        .ring-core strong {
          font: 800 14px/1.05 "Segoe UI", sans-serif;
        }

        .ring-legend {
          display: grid;
          gap: 6px;
        }

        .legend-item {
          display: grid;
          grid-template-columns: 10px 1fr auto;
          gap: 8px;
          align-items: center;
          color: #d8e3f2;
          font: 500 12px/1.2 "Segoe UI", sans-serif;
        }

        .allocation-empty {
          margin-top: 10px;
          display: grid;
          grid-template-columns: 136px 1fr;
          gap: 14px;
          align-items: center;
        }

        .allocation-empty-ring {
          width: 128px;
          height: 128px;
          border-radius: 50%;
          display: grid;
          place-items: center;
          text-align: center;
          background:
            radial-gradient(circle at 50% 50%, rgba(7, 18, 32, 0.96) 0 42px, transparent 43px),
            conic-gradient(rgba(74, 99, 137, 0.22) 0 100%);
          border: 1px solid rgba(118, 154, 212, 0.16);
          box-shadow: inset 0 0 0 12px rgba(26, 40, 66, 0.38);
        }

        .allocation-empty-ring span {
          display: block;
          color: var(--t212-muted);
          font: 600 10px/1 "Segoe UI", sans-serif;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }

        .allocation-empty-ring strong {
          display: block;
          margin-top: 6px;
          font: 800 15px/1.05 "Segoe UI", sans-serif;
        }

        .allocation-empty-copy {
          display: grid;
          gap: 6px;
        }

        .allocation-empty-copy strong {
          font: 700 13px/1.3 "Segoe UI", sans-serif;
          color: #edf5ff;
        }

        .allocation-empty-copy span {
          color: var(--t212-muted);
          font: 500 11px/1.35 "Segoe UI", sans-serif;
        }

        .legend-item strong {
          font-weight: 700;
        }

        .legend-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          box-shadow: 0 0 12px currentColor;
        }

        .concentration-panel {
          padding-top: 12px;
        }

        .concentration-copy {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          margin-top: 8px;
          color: #dce7f8;
          font: 500 13px/1.2 "Segoe UI", sans-serif;
        }

        .concentration-copy strong {
          color: var(--t212-positive);
          font: 800 24px/1 "Segoe UI", sans-serif;
        }

        .concentration-track {
          margin-top: 10px;
          height: 12px;
          border-radius: 999px;
          background: rgba(19, 30, 49, 0.9);
          overflow: hidden;
          box-shadow: 0 0 0 1px rgba(117, 165, 255, 0.12) inset;
        }

        .concentration-fill {
          height: 100%;
          border-radius: inherit;
          background: linear-gradient(90deg, #00e4cf 0%, #31ff9d 100%);
          box-shadow: 0 0 18px rgba(52, 255, 171, 0.28);
        }

        .movers-grid {
          grid-column: 2 / span 2;
          grid-row: 2;
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 9px;
        }

        .movers-head {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 16px;
        }

        .movers-columns {
          display: grid;
          grid-template-columns: 80px 80px;
          gap: 16px;
          color: #b2c2d7;
          font: 600 11px/1 "Segoe UI", sans-serif;
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }

        .movers-list {
          margin-top: 8px;
          display: grid;
          gap: 4px;
        }

        .movers-empty {
          margin-top: 12px;
          color: var(--t212-muted);
          font: 500 12px/1.3 "Segoe UI", sans-serif;
        }

        .mover-row {
          display: grid;
          grid-template-columns: 28px 32px minmax(0, 1fr) 94px 82px 94px;
          gap: 10px;
          align-items: center;
          min-height: 38px;
          border-top: 1px solid rgba(95, 128, 164, 0.16);
          padding-top: 6px;
        }

        .mover-row:first-child {
          border-top: none;
          padding-top: 0;
        }

        .mover-row.placeholder {
          opacity: 0.54;
        }

        .mover-rank {
          width: 24px;
          height: 24px;
          border-radius: 50%;
          display: grid;
          place-items: center;
          background: rgba(18, 31, 49, 0.92);
          color: #dde9f9;
          font: 700 11px/1 "Segoe UI", sans-serif;
        }

        .mover-logo {
          width: 28px;
          height: 28px;
          border-radius: 8px;
          display: grid;
          place-items: center;
          font: 800 13px/1 "Segoe UI", sans-serif;
          box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08) inset;
        }

        .mover-copy {
          min-width: 0;
          display: grid;
          gap: 2px;
        }

        .mover-copy strong,
        .mover-copy span {
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .mover-copy strong {
          font: 700 13px/1.05 "Segoe UI", sans-serif;
        }

        .mover-copy span {
          color: var(--t212-muted);
          font: 500 12px/1.05 "Segoe UI", sans-serif;
        }

        .mover-spark {
          width: 94px;
          height: 28px;
          opacity: 0.95;
        }

        .mover-change,
        .mover-value {
          text-align: right;
          font: 700 14px/1 "Segoe UI", sans-serif;
        }

        .performance-panel {
          grid-column: 1 / span 3;
          grid-row: 3;
          min-height: 176px;
          padding: 11px 13px 9px;
        }

        .performance-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          flex-wrap: wrap;
        }

        .performance-head-copy {
          display: grid;
          gap: 4px;
        }

        .panel-note {
          color: rgba(188, 210, 233, 0.52);
          font: 500 10px/1.2 "Segoe UI", sans-serif;
          letter-spacing: 0.04em;
        }

        .timeframes {
          display: inline-grid;
          grid-auto-flow: column;
          gap: 8px;
          align-items: center;
        }

        .timeframe {
          border: 1px solid rgba(120, 170, 255, 0.12);
          background: rgba(9, 17, 31, 0.74);
          color: #cad7eb;
          border-radius: 8px;
          padding: 6px 12px;
          font: 700 12px/1 "Segoe UI", sans-serif;
        }

        .timeframe.active {
          color: #04111f;
          background: linear-gradient(180deg, #5ce0ff 0%, #2db7ff 100%);
          box-shadow: 0 0 18px rgba(78, 211, 255, 0.26);
        }

        .performance-body {
          margin-top: 10px;
          display: grid;
          grid-template-columns: minmax(0, 1fr) 160px;
          gap: 12px;
          align-items: stretch;
        }

        .performance-chart {
          min-height: 136px;
          padding-bottom: 10px;
          position: relative;
        }

        .grid-line {
          stroke: rgba(105, 131, 163, 0.22);
          stroke-width: 1;
        }

        .perf-area {
          fill: url(#perf-fill);
          opacity: 0.72;
        }

        .perf-backdrop {
          fill: none;
          stroke: rgba(124, 255, 203, 0.12);
          stroke-width: 1.6;
          stroke-linecap: round;
          stroke-dasharray: 3 8;
        }

        .perf-line {
          fill: none;
          stroke: #7affc8;
          stroke-width: 2.8;
          stroke-linecap: round;
          filter: url(#perf-glow);
        }

        .perf-dot {
          fill: #c2ffe6;
        }

        .axis-row {
          display: flex;
          justify-content: space-between;
          gap: 10px;
          color: #90a5c3;
          font: 500 11px/1 "Segoe UI", sans-serif;
          margin-top: 6px;
          padding: 0 2px 2px;
        }

        .performance-tooltip {
          position: absolute;
          z-index: 3;
          width: 132px;
          padding: 8px 9px;
          border-radius: 12px;
          background: rgba(4, 13, 25, 0.94);
          border: 1px solid rgba(96, 147, 214, 0.20);
          box-shadow: 0 10px 24px rgba(0, 0, 0, 0.42);
          pointer-events: none;
          backdrop-filter: blur(16px);
        }

        .performance-tooltip strong,
        .performance-tooltip span,
        .performance-tooltip em,
        .performance-tooltip small {
          display: block;
        }

        .performance-tooltip strong {
          font: 700 11px/1.1 "Segoe UI", sans-serif;
        }

        .performance-tooltip span {
          margin-top: 5px;
          font: 700 12px/1.15 "Segoe UI", sans-serif;
          color: #eff7ff;
        }

        .performance-tooltip em {
          margin-top: 4px;
          font: 600 10px/1 "Segoe UI", sans-serif;
          color: var(--t212-positive);
          font-style: normal;
        }

        .performance-tooltip small {
          margin-top: 6px;
          color: var(--t212-muted);
          font: 500 9px/1.2 "Segoe UI", sans-serif;
        }

        .performance-side {
          border-radius: 16px;
          background: rgba(8, 16, 29, 0.84);
          border: 1px solid rgba(116, 170, 255, 0.12);
          padding: 12px 12px 8px;
          display: grid;
          gap: 8px;
        }

        .side-metric {
          padding-bottom: 8px;
          border-bottom: 1px solid rgba(103, 128, 160, 0.18);
        }

        .side-metric:last-child {
          border-bottom: none;
          padding-bottom: 0;
        }

        .side-metric span {
          display: block;
          color: #93a9c6;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          font: 600 11px/1.1 "Segoe UI", sans-serif;
        }

        .side-metric strong {
          display: block;
          margin-top: 6px;
          font: 700 15px/1.05 "Segoe UI", sans-serif;
        }

        .side-metric em {
          display: block;
          margin-top: 6px;
          color: var(--t212-positive);
          font: 700 12px/1 "Segoe UI", sans-serif;
          font-style: normal;
        }

        .loading {
          min-height: 320px;
          display: grid;
          place-items: center;
        }

        @media (max-width: 1480px) {
          .layout {
            grid-template-columns: 188px minmax(400px, 1fr) 316px;
          }

          .hero-value {
            font-size: clamp(48px, 5.2vw, 80px);
          }

          .account-strip {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }

          .ring-wrap {
            grid-template-columns: 132px 1fr;
          }

          .ring-chart {
            width: 124px;
            height: 124px;
          }
        }

        @media (max-width: 1220px) {
          .layout {
            grid-template-columns: 1fr;
            grid-template-rows: auto;
          }

          .pies-column,
          .hero-panel,
          .allocation-column,
          .movers-grid,
          .performance-panel {
            grid-column: auto;
            grid-row: auto;
          }

          .allocation-column,
          .movers-grid,
          .performance-body {
            grid-template-columns: 1fr;
          }

          .performance-side {
            grid-template-columns: repeat(3, minmax(0, 1fr));
            align-items: start;
          }
        }

        @media (max-width: 860px) {
          .shell {
            padding: 14px;
            min-height: 0;
          }

          .header,
          .performance-head {
            align-items: flex-start;
            flex-direction: column;
          }

          .hero-panel {
            min-height: 360px;
          }

          .account-strip {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }

          .account-strip-meta {
            justify-content: flex-start;
            padding-left: 5px;
          }

          .ring-wrap,
          .performance-body {
            grid-template-columns: 1fr;
          }

          .allocation-empty {
            grid-template-columns: 1fr;
          }

          .mover-row {
            grid-template-columns: 24px 28px minmax(0, 1fr) 66px 70px 82px;
            gap: 8px;
          }

          .axis-row {
            overflow-x: auto;
            white-space: nowrap;
          }
        }
      </style>
    `;
  }
}

function firstDefined(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== "") {
      return value;
    }
  }
  return null;
}

function numericState(stateObj) {
  return numericValue(stateObj?.state);
}

function numericValue(value) {
  if (value === undefined || value === null || value === "" || value === "unknown" || value === "unavailable") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function textOrNull(value) {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function formatMoney(value, currency = "GBP") {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatSignedMoney(value, currency = "GBP") {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatMoney(value, currency)}`;
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return `${value.toFixed(1)}%`;
}

function formatSignedPercent(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}%`;
}

function formatPrimary(value, unit) {
  if (unit === "GBP" || unit === "USD" || unit === "EUR") {
    return formatMoney(value, unit);
  }
  if (typeof unit === "string" && unit.length === 3 && unit === unit.toUpperCase()) {
    return formatMoney(value, unit);
  }
  if (unit === "%") {
    return formatPercent(value);
  }
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  if (unit) {
    return `${new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 }).format(value)} ${unit}`;
  }
  return new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 }).format(value);
}

function formatRelative(value) {
  if (!value || value === "unknown" || value === "unavailable") {
    return "Last update: unavailable";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return `Last update: ${value}`;
  }
  const diffMs = Date.now() - parsed.getTime();
  const diffMinutes = Math.max(0, Math.round(diffMs / 60000));
  if (diffMinutes < 1) {
    return "Last update: just now";
  }
  if (diffMinutes < 60) {
    return `Last update: ${diffMinutes} min ago`;
  }
  const diffHours = Math.round(diffMinutes / 60);
  return `Last update: ${diffHours}h ago`;
}

function clampPercent(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, value));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function buildSeries(seedText, length, baseline, amplitude, drift, options = {}) {
  const seed = seededNumber(seedText);
  const values = [];
  const floorRatio = options.floorRatio ?? 0.58;
  const wobble = options.wobble ?? 1;
  const noise = options.noise ?? 0.1;
  const pulse = options.pulse ?? 0.18;
  let current = baseline * floorRatio;
  for (let index = 0; index < length; index += 1) {
    const sinA = Math.sin((index / (3.4 + seed)) + seed * 3.1) * amplitude * 0.032 * wobble;
    const sinB = Math.sin((index / (7.4 + seed * 2)) + seed * 5.9) * amplitude * 0.045 * wobble;
    const sinC = Math.cos((index / (2.1 + seed * 0.8)) + seed * 1.7) * amplitude * 0.017 * wobble;
    const trend = baseline * drift / Math.max(length - 1, 1);
    const jitter = ((seededNumber(`${seedText}:${index}`) - 0.5) * amplitude * noise);
    const pulseLift = index > length * 0.72 ? amplitude * pulse * Math.sin(((index - length * 0.72) / length) * Math.PI) : 0;
    current += sinA + sinB + sinC + trend + jitter + pulseLift;
    values.push(Math.max(current, baseline * Math.max(0.18, floorRatio * 0.58)));
  }
  return values;
}

function buildChartPaths(values, width, height, bottomPad) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const coords = values.map((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = height - bottomPad - ((value - min) / range) * (height - bottomPad - 18);
    return { x, y };
  });
  const line = coords.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ");
  const last = coords[coords.length - 1];
  const first = coords[0];
  const area = `${line} L ${last.x.toFixed(2)} ${(height - bottomPad + 8).toFixed(2)} L ${first.x.toFixed(2)} ${(height - bottomPad + 8).toFixed(2)} Z`;
  return { line, area, dot: last };
}

function buildMiniSparkline(seedText, direction) {
  const values = buildSeries(seedText, 18, 100, 18, 0.01 * direction, {
    floorRatio: 0.52,
    wobble: 1.25,
    noise: 0.08,
    pulse: 0.04,
  });
  const { line } = buildChartPaths(values, 120, 36, 6);
  return line;
}

function buildBackdropPath(values, width, height, bottomPad, opacityScale = 0.5) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const coords = values.map((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = height - bottomPad - ((value - min) / range) * (height - bottomPad - 24) * opacityScale;
    return { x, y };
  });
  return coords.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ");
}

function buildTooltipPoints(values, axisLabels, currency) {
  const first = values[0] ?? 0;
  return values.map((value, index) => {
    const axisIndex = Math.min(axisLabels.length - 1, Math.round((index / Math.max(values.length - 1, 1)) * (axisLabels.length - 1)));
    const change = value - first;
    return {
      label: axisLabels[axisIndex] || `Point ${index + 1}`,
      valueLabel: formatMoney(value, currency),
      changeLabel: formatSignedMoney(change, currency),
      note: "Decorative fallback trend",
    };
  });
}

function seededNumber(value) {
  let hash = 0;
  for (let index = 0; index < String(value).length; index += 1) {
    hash = ((hash << 5) - hash + String(value).charCodeAt(index)) | 0;
  }
  return Math.abs(hash % 1000) / 1000;
}

function buildConicGradient(items) {
  let current = 0;
  const stops = [];
  for (const item of items) {
    const start = current;
    current += clampPercent(item.value);
    stops.push(`${item.tone} ${start}% ${Math.min(current, 100)}%`);
  }
  if (!stops.length) {
    return "conic-gradient(#2de2c0 0 64%, rgba(40,57,86,0.55) 64% 100%)";
  }
  if (current < 100) {
    stops.push(`rgba(40,57,86,0.55) ${current}% 100%`);
  }
  return `conic-gradient(${stops.join(", ")})`;
}

function fallbackLegend(topFiveConcentration) {
  const tech = clampPercent(topFiveConcentration || 59.1);
  return [
    { label: "Equities", value: tech, tone: "#2de2c0" },
    { label: "Cash", value: Math.max(8, 100 - tech), tone: "#4f74ff" },
  ];
}

function normalizeMoverSensor(stateObj, currency, tone) {
  if (!stateObj || !stateObj.attributes) {
    return null;
  }
  const attrs = stateObj.attributes;
  const ticker = textOrNull(attrs.ticker);
  const company = textOrNull(attrs.name) || ticker;
  const label = textOrNull(stateObj.state);
  return {
    label: label || ticker || company || "Pending",
    ticker,
    company,
    changePercent: numericValue(attrs.change_percent),
    changeValue: numericValue(attrs.change_value),
    tone,
    sparkSeed: `${ticker}:${attrs.change_percent}:${attrs.change_value}`,
  };
}

function normalizePieRow(pie, currency) {
  if (!pie || typeof pie !== "object") {
    return null;
  }
  const label = textOrNull(pie.state) || textOrNull(pie.name) || textOrNull(pie.pie_id);
  if (!label) {
    return null;
  }
  const topSlice = Array.isArray(pie.top_slices) ? pie.top_slices[0] : null;
  const topSliceTicker = textOrNull(topSlice?.ticker);
  const topSliceShare = numericValue(topSlice?.current_share_percent);
  const pieCurrency = textOrNull(pie.currency) || currency;
  const holdingValue = numericValue(pie.holding_value) ?? numericValue(pie.value);
  return {
    label,
    sublabel:
      topSliceTicker && topSliceShare !== null
        ? `${topSliceTicker} · ${formatPercent(topSliceShare)}`
        : (numericValue(pie.result) !== null ? formatSignedMoney(numericValue(pie.result), pieCurrency) : "Pie summary"),
    valueLabel: formatMoney(holdingValue, pieCurrency),
    percent: numericValue(pie.result_percent),
  };
}

function normalizePositionSummary(labelState, resultState, currency, tone) {
  if (!labelState) {
    return null;
  }
  const attrs = labelState.attributes || resultState?.attributes || {};
  const ticker = textOrNull(attrs.ticker) || textOrNull(labelState.state);
  const company = textOrNull(attrs.name) || ticker;
  return {
    label: textOrNull(labelState.state) || ticker || company || "Pending",
    ticker,
    company,
    changePercent: numericValue(attrs.result_percent),
    changeValue: numericState(resultState) ?? numericValue(attrs.result),
    tone,
    sparkSeed: `${ticker}:${attrs.result_percent}:${resultState?.state}`,
  };
}

function dedupeByTicker(items) {
  const seen = new Set();
  const output = [];
  for (const item of items) {
    const key = item.ticker || item.label;
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    output.push(item);
  }
  return output;
}

function dedupeMovers(items) {
  const bestByKey = new Map();
  for (const item of items) {
    const key = moverKey(item);
    if (!key) {
      continue;
    }
    const existing = bestByKey.get(key);
    if (!existing || moverScore(item) > moverScore(existing)) {
      bestByKey.set(key, item);
    }
  }
  return Array.from(bestByKey.values());
}

function moverKey(item) {
  return textOrNull(item.ticker)
    || textOrNull(item.instrumentCode)
    || textOrNull(item.shortName)
    || textOrNull(item.company)
    || textOrNull(item.label);
}

function moverScore(item) {
  return Math.abs(item.changePercent ?? 0) * 1000 + Math.abs(item.changeValue ?? 0);
}

function buildPlaceholderMover(index, positive) {
  return {
    label: positive ? "Awaiting data" : "Awaiting data",
    ticker: `--${index + 1}`,
    company: positive ? "Enable richer position detail for full ranking" : "Enable richer position detail for full ranking",
    changePercent: null,
    changeValue: null,
    tone: positive ? "#3dffb0" : "#ff4e63",
    sparkSeed: `placeholder:${index}:${positive}`,
    placeholder: true,
  };
}

function toneForIndex(index) {
  return ["#2de2c0", "#2aa8ff", "#944cff", "#f4c93d", "#ff8a1c", "#8d95ab"][index % 6];
}

function brandToken(ticker) {
  if (!ticker) {
    return null;
  }
  return TICKER_BRANDS[ticker.toUpperCase()] || null;
}

function logoStyle(ticker) {
  const brand = brandToken(ticker);
  if (!brand) {
    return "background:linear-gradient(135deg,#13304f 0%,#0a1627 100%);color:#dceaff;";
  }
  return `background:${brand.bg};color:${brand.fg};`;
}

function logoMark(ticker) {
  const brand = brandToken(ticker);
  if (brand) {
    return escapeHtml(brand.mark);
  }
  const token = textOrNull(ticker);
  return escapeHtml(token ? token.slice(0, 2).toUpperCase() : "•");
}

function iconMarkup(icon) {
  const icons = {
    vault: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M3 7.5 12 4l9 3.5V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5Zm9 1a3 3 0 1 0 0 6 3 3 0 0 0 0-6Zm0 1.6a1.4 1.4 0 1 1 0 2.8 1.4 1.4 0 0 1 0-2.8Z"/></svg>',
    stack: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 4c4.97 0 9 1.79 9 4s-4.03 4-9 4-9-1.79-9-4 4.03-4 9-4Zm-9 8v4c0 2.21 4.03 4 9 4s9-1.79 9-4v-4c-1.97 1.38-5.33 2.2-9 2.2S4.97 13.38 3 12Zm0-2.8V10c0 2.21 4.03 4 9 4s9-1.79 9-4V9.2c-1.97 1.38-5.33 2.2-9 2.2s-7.03-.82-9-2.2Z"/></svg>',
    pie: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M11 2v9H2A10 10 0 0 1 11 2Zm2 0a10 10 0 1 1-10 11h10V2Z"/></svg>',
    briefcase: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M9 4h6a2 2 0 0 1 2 2v2h3a2 2 0 0 1 2 2v8a3 3 0 0 1-3 3H5a3 3 0 0 1-3-3v-8a2 2 0 0 1 2-2h3V6a2 2 0 0 1 2-2Zm0 4h6V6H9v2Z"/></svg>',
    trend: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="m4 18 6-6 4 4 6-9 1.5 1L14.3 19 10 14.7 5.5 19.2 4 18Zm13-12h5v5h-2V9.4l-3.8 3.8-1.4-1.4L18.6 8H17V6Z"/></svg>',
    bars: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M3 21V10h3v11H3Zm5 0V4h3v17H8Zm5 0v-7h3v7h-3Zm5 0V8h3v13h-3Z"/></svg>',
  };
  return icons[icon] || icons.vault;
}

if (!customElements.get("trading212-portfolio-card")) {
  customElements.define("trading212-portfolio-card", Trading212PortfolioCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "trading212-portfolio-card")) {
  window.customCards.push({
    type: "trading212-portfolio-card",
    name: "Trading 212 Portfolio",
    description: "Bespoke glossy Trading 212 dashboard card",
  });
}
