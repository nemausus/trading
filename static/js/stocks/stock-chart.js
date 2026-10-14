/**
 * stock-chart.js
 * ~~~~~~~~~~~~~~
 * TradingView Lightweight Charts (v5) integration.
 * Manages candlestick series, volume histogram, SMA 50/200 overlays,
 * RSI 14 pane with 30/70 reference lines, synchronized crosshair,
 * live hover tooltips, and responsive resizing.
 */

import { calculateSMA, calculateRSI } from './indicators.js';
import { formatVolume } from '../utils.js';

// Keep in sync with .stock-chart-wrapper min-height in stocks.css
const CHART_HEIGHT = 380;
// Empty bars kept to the right of the last candle. Lightweight Charts' default
// of 12 left a visible blank strip next to the price scale on narrow charts.
const RIGHT_OFFSET_BARS = 2;
const SECONDS_PER_DAY = 86400;

export class StockChart {
    /**
     * @param {HTMLElement} containerElement - Element the chart canvas mounts into.
     * @param {HTMLElement|null} tooltipElement - Element for the live OHLCV legend.
     */
    constructor(containerElement, tooltipElement = null) {
        this.container = containerElement;
        this.tooltip = tooltipElement;

        this.chart = null;
        this.candlestickSeries = null;
        this.volumeSeries = null;
        this.sma50Series = null;
        this.sma200Series = null;
        this.rsiSeries = null;

        this.currentCandles = [];
        this.latestCandle = null;

        this.indicatorState = {
            sma50: true,
            sma200: true,
            volume: true,
            rsi: true,
        };

        this.cachedIndicators = {
            sma50: [],
            sma200: [],
            rsi: [],
        };

        this.resizeObserver = null;
        this._initChart();
    }

    _initChart() {
        if (!window.LightweightCharts) {
            console.error("TradingView LightweightCharts library not loaded.");
            return;
        }

        const LC = window.LightweightCharts;

        // Container sizing
        const width = this.container.clientWidth || 800;
        const height = CHART_HEIGHT;

        this.chart = LC.createChart(this.container, {
            width: width,
            height: height,
            layout: {
                background: { type: 'solid', color: '#ffffff' },
                textColor: '#475569',
                fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                fontSize: 12,
                panes: {
                    separatorColor: '#e2e8f0',
                    separatorHoverColor: '#cbd5e1',
                    enableResize: true,
                },
            },
            grid: {
                vertLines: { color: '#f1f5f9' },
                horzLines: { color: '#f1f5f9' },
            },
            crosshair: {
                mode: LC.CrosshairMode.Normal,
                vertLine: {
                    color: '#94a3b8',
                    width: 1,
                    style: LC.LineStyle.Dashed,
                    labelBackgroundColor: '#334155',
                },
                horzLine: {
                    color: '#94a3b8',
                    width: 1,
                    style: LC.LineStyle.Dashed,
                    labelBackgroundColor: '#334155',
                },
            },
            timeScale: {
                borderColor: '#e2e8f0',
                timeVisible: false, // enabled in setData() for intraday candles
                secondsVisible: false,
                rightOffset: RIGHT_OFFSET_BARS,
            },
            rightPriceScale: {
                borderColor: '#e2e8f0',
                scaleMargins: {
                    top: 0.08,
                    bottom: 0.22, // leaves room for volume overlay in pane 0
                },
            },
        });

        // 1. Candlestick Price Series (Pane 0)
        this.candlestickSeries = this.chart.addSeries(LC.CandlestickSeries, {
            upColor: '#16a34a',
            downColor: '#dc2626',
            borderVisible: false,
            wickUpColor: '#16a34a',
            wickDownColor: '#dc2626',
            priceFormat: {
                type: 'price',
                precision: 2,
                minMove: 0.01,
            },
        }, 0);

        // 2. Volume Histogram (Pane 0 overlay at the bottom)
        this.volumeSeries = this.chart.addSeries(LC.HistogramSeries, {
            priceFormat: { type: 'volume' },
            priceScaleId: 'volume_scale',
            priceLineVisible: false,
            lastValueVisible: false,
        }, 0);

        this.chart.priceScale('volume_scale').applyOptions({
            scaleMargins: {
                top: 0.80, // Volume occupies bottom 20%
                bottom: 0.0,
            },
        });

        // 3. SMA Overlays (Pane 0)
        this.sma50Series = this.chart.addSeries(LC.LineSeries, {
            color: '#d97706', // Amber / Orange
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: false,
        }, 0);

        this.sma200Series = this.chart.addSeries(LC.LineSeries, {
            color: '#dc2626', // Red
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: false,
        }, 0);

        // 4. RSI (Pane 1)
        this._setupRSISeries();

        // 5. Crosshair live hover tooltip
        this._setupCrosshairHandler();

        // 6. Responsive resize observer
        this._setupResizeObserver();
    }

    /**
     * Remove the RSI series (and its pane) if present.
     */
    _removeRSISeries() {
        if (!this.rsiSeries) return;
        try {
            this.chart.removeSeries(this.rsiSeries);
        } catch (e) {
            // Ignore if already removed
        }
        this.rsiSeries = null;
    }

    _setupRSISeries() {
        if (!this.chart || !window.LightweightCharts) return;
        const LC = window.LightweightCharts;

        this._removeRSISeries();
        if (!this.indicatorState.rsi) {
            return;
        }

        this.rsiSeries = this.chart.addSeries(LC.LineSeries, {
            color: '#9333ea', // Purple
            lineWidth: 1.5,
            priceFormat: {
                type: 'custom',
                formatter: (val) => val != null ? val.toFixed(1) : '',
            },
            autoscaleInfoProvider: () => ({
                priceRange: {
                    minValue: 10,
                    maxValue: 90,
                },
            }),
        }, 1); // Pane index 1

        // Reference lines at 70 and 30
        this.rsiSeries.createPriceLine({
            price: 70,
            color: '#ef4444',
            lineWidth: 1,
            lineStyle: LC.LineStyle.Dashed,
            axisLabelVisible: true,
        });

        this.rsiSeries.createPriceLine({
            price: 30,
            color: '#10b981',
            lineWidth: 1,
            lineStyle: LC.LineStyle.Dashed,
            axisLabelVisible: true,
        });

        // Populate cached RSI if present
        if (this.cachedIndicators.rsi && this.cachedIndicators.rsi.length > 0) {
            this.rsiSeries.setData(this.cachedIndicators.rsi);
        }
    }

    _setupCrosshairHandler() {
        if (!this.chart) return;

        this.chart.subscribeCrosshairMove((param) => {
            if (!param || !param.time || !param.point) {
                this._renderDefaultLegend();
                return;
            }

            const candle = param.seriesData.get(this.candlestickSeries);
            const volumeData = this.volumeSeries ? param.seriesData.get(this.volumeSeries) : null;
            const sma50 = (this.indicatorState.sma50 && this.sma50Series) ? param.seriesData.get(this.sma50Series) : null;
            const sma200 = (this.indicatorState.sma200 && this.sma200Series) ? param.seriesData.get(this.sma200Series) : null;
            const rsi = (this.indicatorState.rsi && this.rsiSeries) ? param.seriesData.get(this.rsiSeries) : null;

            this._updateLegendDisplay({
                time: param.time,
                open: candle ? candle.open : null,
                high: candle ? candle.high : null,
                low: candle ? candle.low : null,
                close: candle ? candle.close : null,
                volume: volumeData ? volumeData.value : null,
                sma50: sma50 ? sma50.value : null,
                sma200: sma200 ? sma200.value : null,
                rsi: rsi ? rsi.value : null,
            });
        });
    }

    _setupResizeObserver() {
        if (!this.container || typeof ResizeObserver === 'undefined') return;

        this.resizeObserver = new ResizeObserver((entries) => {
            if (!entries || !entries.length) return;
            const width = Math.floor(entries[0].contentRect.width);
            if (width > 0 && this.chart) {
                this.chart.applyOptions({ width });
            }
        });

        this.resizeObserver.observe(this.container);
    }

    /**
     * Set new candlestick data and recalculate all indicators.
     *
     * @param {Array<Object>} candles - Array of normalized candles.
     */
    setData(candles) {
        if (!this.chart) {
            this._initChart();
        }
        if (!this.chart || !candles || !candles.length) {
            return;
        }

        this.currentCandles = candles;
        this.latestCandle = candles[candles.length - 1];

        // Show time-of-day on the axis only for intraday candles (daily bars would show e.g. "06:00")
        const isIntraday = candles.length > 1 && (candles[1].time - candles[0].time) < SECONDS_PER_DAY;
        this.isIntraday = isIntraday;
        this.chart.applyOptions({ timeScale: { timeVisible: isIntraday } });

        // Format candlestick data for Lightweight Charts
        const candleData = candles.map(c => ({
            time: c.time,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
        }));
        this.candlestickSeries.setData(candleData);

        // Format volume data with green/red bars
        const volumeData = candles.map(c => ({
            time: c.time,
            value: c.volume,
            color: c.close >= c.open ? 'rgba(22, 163, 74, 0.45)' : 'rgba(220, 38, 38, 0.45)',
        }));
        this.volumeSeries.setData(volumeData);

        // Calculate and cache indicators locally
        this.cachedIndicators.sma50 = calculateSMA(candles, 50);
        this.cachedIndicators.sma200 = calculateSMA(candles, 200);
        this.cachedIndicators.rsi = calculateRSI(candles, 14);

        // Apply data to indicator series
        this.sma50Series.setData(this.cachedIndicators.sma50);
        this.sma200Series.setData(this.cachedIndicators.sma200);

        if (this.rsiSeries) {
            this.rsiSeries.setData(this.cachedIndicators.rsi);
        }

        // Apply visibility states
        this._syncIndicatorVisibilities();

        // Fit content onto screen
        this.chart.timeScale().fitContent();

        // Update default legend display
        this._renderDefaultLegend();
    }

    /**
     * Toggle indicator visibility without making another API request.
     *
     * @param {string} name - 'sma50' | 'sma200' | 'volume' | 'rsi'.
     * @param {boolean} isVisible - Active state.
     */
    toggleIndicator(name, isVisible) {
        if (!(name in this.indicatorState)) return;
        this.indicatorState[name] = Boolean(isVisible);
        this._syncIndicatorVisibilities();
        this._renderDefaultLegend();
    }

    /**
     * Apply indicatorState to all series: overlays are shown/hidden,
     * the RSI series (own pane) is added/removed.
     */
    _syncIndicatorVisibilities() {
        const overlays = {
            sma50: this.sma50Series,
            sma200: this.sma200Series,
            volume: this.volumeSeries,
        };
        for (const [name, series] of Object.entries(overlays)) {
            if (series) series.applyOptions({ visible: this.indicatorState[name] });
        }
        if (!this.indicatorState.rsi) {
            this._removeRSISeries();
        } else if (!this.rsiSeries) {
            this._setupRSISeries();
        }
    }

    _formatTime(timeVal) {
        if (!timeVal) return '';
        const d = new Date(timeVal * 1000);
        if (this.isIntraday) {
            return d.toLocaleDateString('en-US', {
                timeZone: 'America/New_York',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                hour12: true,
            });
        }
        return d.toLocaleDateString('en-US', {
            timeZone: 'UTC',
            year: 'numeric',
            month: 'short',
            day: 'numeric',
        });
    }

    _formatNumber(num, decimals = 2) {
        if (num == null || isNaN(num)) return '—';
        return Number(num).toLocaleString('en-US', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals
        });
    }

    _renderDefaultLegend() {
        if (!this.latestCandle) {
            if (this.tooltip) this.tooltip.innerHTML = '';
            return;
        }

        const c = this.latestCandle;
        const latestSma50 = this.cachedIndicators.sma50.length ? this.cachedIndicators.sma50[this.cachedIndicators.sma50.length - 1].value : null;
        const latestSma200 = this.cachedIndicators.sma200.length ? this.cachedIndicators.sma200[this.cachedIndicators.sma200.length - 1].value : null;
        const latestRsi = this.cachedIndicators.rsi.length ? this.cachedIndicators.rsi[this.cachedIndicators.rsi.length - 1].value : null;

        this._updateLegendDisplay({
            time: c.time,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
            volume: c.volume,
            sma50: latestSma50,
            sma200: latestSma200,
            rsi: latestRsi,
        });
    }

    _updateLegendDisplay(data) {
        if (!this.tooltip) return;

        const dateStr = this._formatTime(data.time);
        const openStr = this._formatNumber(data.open);
        const highStr = this._formatNumber(data.high);
        const lowStr = this._formatNumber(data.low);
        const closeStr = this._formatNumber(data.close);
        const volStr = formatVolume(data.volume);

        let indicatorsHtml = '<div class="legend-indicators-group">';
        if (this.indicatorState.sma50 && data.sma50 != null) {
            indicatorsHtml += `<span class="legend-badge badge-sma50">SMA 50: ${data.sma50.toFixed(2)}</span>`;
        }
        if (this.indicatorState.sma200 && data.sma200 != null) {
            indicatorsHtml += `<span class="legend-badge badge-sma200">SMA 200: ${data.sma200.toFixed(2)}</span>`;
        }
        if (this.indicatorState.rsi && data.rsi != null) {
            const rsiVal = data.rsi.toFixed(1);
            const rsiColor = data.rsi >= 70 ? 'badge-rsi-high' : (data.rsi <= 30 ? 'badge-rsi-low' : 'badge-rsi');
            indicatorsHtml += `<span class="legend-badge ${rsiColor}">RSI 14: ${rsiVal}</span>`;
        }
        indicatorsHtml += '</div>';

        this.tooltip.innerHTML = `
            <div class="legend-line">
                <span class="legend-date">${dateStr}</span>
                <span class="legend-ohlc">O: <strong>${openStr}</strong></span>
                <span class="legend-ohlc">H: <strong>${highStr}</strong></span>
                <span class="legend-ohlc">L: <strong>${lowStr}</strong></span>
                <span class="legend-ohlc">C: <strong>${closeStr}</strong></span>
                ${this.indicatorState.volume ? `<span class="legend-vol">Vol: <strong>${volStr}</strong></span>` : ''}
            </div>
            ${indicatorsHtml}
        `;
    }

    /**
     * Trigger responsive resize and re-fit content.
     */
    resize() {
        if (!this.chart || !this.container) return;
        const width = this.container.clientWidth;
        if (width > 0) {
            this.chart.applyOptions({ width });
            this.chart.timeScale().fitContent();
        }
    }

    destroy() {
        if (this.resizeObserver) {
            this.resizeObserver.disconnect();
            this.resizeObserver = null;
        }
        if (this.chart) {
            this.chart.remove();
            this.chart = null;
        }
    }
}
