import { useEffect, useMemo, useRef, useState } from 'react';
import type { ChangeEvent, MouseEvent } from 'react';
import { pythonApi } from '../api/pythonApi';
import type { DataFitResponse } from '../types/contracts';

interface PointRow {
  id: string;
  x: string;
  y: string;
}

interface FitRecord {
  id: string;
  fitType: 'Polynomial' | 'Exponential' | 'Logarithmic' | 'Sine';
  degree: number;
  response: DataFitResponse;
}

interface ChartBounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

export function DataFittingPage() {
  const chartSvgRef = useRef<SVGSVGElement | null>(null);
  const [points, setPoints] = useState<PointRow[]>([
    { id: crypto.randomUUID(), x: '1', y: '2' },
    { id: crypto.randomUUID(), x: '2', y: '4' },
    { id: crypto.randomUUID(), x: '3', y: '8' },
    { id: crypto.randomUUID(), x: '4', y: '16' },
  ]);
  const [fitType, setFitType] = useState<'Polynomial' | 'Exponential' | 'Logarithmic' | 'Sine'>('Exponential');
  const [degree, setDegree] = useState(2);
  const [chartTitle, setChartTitle] = useState('拟合结果');
  const [xLabel, setXLabel] = useState('X');
  const [yLabel, setYLabel] = useState('Y');
  const [tickCount, setTickCount] = useState(6);
  const [showGrid, setShowGrid] = useState(true);
  const [result, setResult] = useState<DataFitResponse | null>(null);
  const [records, setRecords] = useState<FitRecord[]>([]);
  const [zoomBounds, setZoomBounds] = useState<ChartBounds | null>(null);
  const [hoverPoint, setHoverPoint] = useState<{ px: number; py: number; x: number; y: number } | null>(null);
  const [status, setStatus] = useState('');

  const parsed = useMemo(() => {
    const data = points
      .map((item) => ({
        x: Number(item.x),
        y: Number(item.y),
      }))
      .filter((item) => Number.isFinite(item.x) && Number.isFinite(item.y));
    return {
      xData: data.map((item) => item.x),
      yData: data.map((item) => item.y),
    };
  }, [points]);

  function updatePoint(id: string, key: 'x' | 'y', value: string) {
    setPoints((prev) => prev.map((item) => (item.id === id ? { ...item, [key]: value } : item)));
  }

  function addPoint() {
    setPoints((prev) => [...prev, { id: crypto.randomUUID(), x: '', y: '' }]);
  }

  function removePoint(id: string) {
    setPoints((prev) => prev.filter((item) => item.id !== id));
  }

  function clearPoints() {
    setPoints([{ id: crypto.randomUUID(), x: '', y: '' }]);
    setResult(null);
    setZoomBounds(null);
    setStatus('已清空数据');
  }

  async function importCsv(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    const text = await file.text();
    const rows = text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const parsedRows: PointRow[] = [];
    for (const row of rows) {
      const parts = row.split(/[,\s]+/).filter(Boolean);
      if (parts.length < 2) {
        continue;
      }
      const x = Number(parts[0]);
      const y = Number(parts[1]);
      if (Number.isFinite(x) && Number.isFinite(y)) {
        parsedRows.push({ id: crypto.randomUUID(), x: String(x), y: String(y) });
      }
    }
    if (parsedRows.length === 0) {
      setStatus('导入失败：未读取到有效的两列数值数据');
      return;
    }
    setPoints(parsedRows);
    setStatus(`已导入 ${parsedRows.length} 行数据`);
  }

  async function runFit() {
    if (parsed.xData.length < 2 || parsed.xData.length !== parsed.yData.length) {
      setStatus('请至少提供两行有效数据，且 X/Y 数量一致');
      return;
    }
    try {
      const resp = await pythonApi.fitData({
        x_data: parsed.xData,
        y_data: parsed.yData,
        fit_type: fitType,
        degree,
      });
      setResult(resp);
      setStatus(resp.status === 'success' ? '拟合完成' : resp.message ?? '拟合失败');
      setZoomBounds(null);
      setRecords((prev) => [
        {
          id: crypto.randomUUID(),
          fitType,
          degree,
          response: resp,
        },
        ...prev,
      ]);
    } catch (error) {
      setStatus((error as Error).message);
    }
  }

  const chartModel = useMemo(() => {
    const x = parsed.xData;
    const y = parsed.yData;
    if (x.length === 0 || y.length === 0) {
      return null;
    }
    const fitX = result?.x_fit ?? [];
    const fitY = result?.y_fit ?? [];
    const allX = [...x, ...fitX];
    const allY = [...y, ...fitY];
    const baseMinX = Math.min(...allX);
    const baseMaxX = Math.max(...allX);
    const baseMinY = Math.min(...allY);
    const baseMaxY = Math.max(...allY);
    const width = 720;
    const height = 300;
    const padding = 36;
    const minX = zoomBounds?.minX ?? baseMinX;
    const maxX = zoomBounds?.maxX ?? baseMaxX;
    const minY = zoomBounds?.minY ?? baseMinY;
    const maxY = zoomBounds?.maxY ?? baseMaxY;
    const safeMaxX = maxX === minX ? minX + 1 : maxX;
    const safeMaxY = maxY === minY ? minY + 1 : maxY;
    const xSpan = safeMaxX - minX;
    const ySpan = safeMaxY - minY;
    const toPx = (vx: number, vy: number) => ({
      x: padding + ((vx - minX) / (safeMaxX - minX)) * (width - padding * 2),
      y: height - padding - ((vy - minY) / (safeMaxY - minY)) * (height - padding * 2),
    });
    const toData = (px: number, py: number) => ({
      x: minX + ((px - padding) / (width - padding * 2)) * xSpan,
      y: minY + ((height - padding - py) / (height - padding * 2)) * ySpan,
    });
    return {
      width,
      height,
      padding,
      minX,
      maxX: safeMaxX,
      minY,
      maxY: safeMaxY,
      baseMinX,
      baseMaxX,
      baseMinY,
      baseMaxY,
      toPx,
      toData,
    };
  }, [parsed.xData, parsed.yData, result?.x_fit, result?.y_fit, zoomBounds]);

  function formatPoints(xs: number[], ys: number[]) {
    if (!chartModel || xs.length !== ys.length) {
      return '';
    }
    return xs
      .map((vx, index) => {
        const p = chartModel.toPx(vx, ys[index]);
        return `${p.x},${p.y}`;
      })
      .join(' ');
  }

  function formatAxisValue(value: number, span: number) {
    if (!Number.isFinite(value)) {
      return '-';
    }
    if (span >= 100) {
      return value.toFixed(1);
    }
    if (span >= 1) {
      return value.toFixed(2);
    }
    return value.toFixed(4);
  }

  function resetZoom() {
    setZoomBounds(null);
  }

  useEffect(() => {
    const svgEl = chartSvgRef.current;
    if (!svgEl || !chartModel) {
      return;
    }
    const onNativeWheel = (event: globalThis.WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      const rect = svgEl.getBoundingClientRect();
      const px = event.clientX - rect.left;
      const py = event.clientY - rect.top;
      if (px < chartModel.padding || px > chartModel.width - chartModel.padding) {
        return;
      }
      if (py < chartModel.padding || py > chartModel.height - chartModel.padding) {
        return;
      }
      const cursorData = chartModel.toData(px, py);
      const factor = event.deltaY < 0 ? 0.88 : 1.14;
      const nextMinX = cursorData.x - (cursorData.x - chartModel.minX) * factor;
      const nextMaxX = cursorData.x + (chartModel.maxX - cursorData.x) * factor;
      const nextMinY = cursorData.y - (cursorData.y - chartModel.minY) * factor;
      const nextMaxY = cursorData.y + (chartModel.maxY - cursorData.y) * factor;
      const minSpanX = Math.max((chartModel.baseMaxX - chartModel.baseMinX) * 0.01, 0.0001);
      const minSpanY = Math.max((chartModel.baseMaxY - chartModel.baseMinY) * 0.01, 0.0001);
      if (nextMaxX - nextMinX < minSpanX || nextMaxY - nextMinY < minSpanY) {
        return;
      }
      setZoomBounds({
        minX: nextMinX,
        maxX: nextMaxX,
        minY: nextMinY,
        maxY: nextMaxY,
      });
    };
    svgEl.addEventListener('wheel', onNativeWheel, { passive: false });
    return () => svgEl.removeEventListener('wheel', onNativeWheel);
  }, [chartModel]);

  function handleChartMouseMove(event: MouseEvent<SVGSVGElement>) {
    if (!chartModel) {
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    if (px < chartModel.padding || px > chartModel.width - chartModel.padding) {
      setHoverPoint(null);
      return;
    }
    if (py < chartModel.padding || py > chartModel.height - chartModel.padding) {
      setHoverPoint(null);
      return;
    }
    const dataPoint = chartModel.toData(px, py);
    setHoverPoint({ px, py, x: dataPoint.x, y: dataPoint.y });
  }

  function exportResultJson() {
    if (!result) {
      setStatus('暂无可导出的拟合结果');
      return;
    }
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `fit-result-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function exportPointsCsv() {
    if (parsed.xData.length === 0) {
      setStatus('暂无可导出的数据点');
      return;
    }
    const rows = ['x,y', ...parsed.xData.map((x, i) => `${x},${parsed.yData[i]}`)];
    const blob = new Blob([rows.join('\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `fit-points-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function applySampleData(kind: 'exp' | 'poly' | 'sin') {
    const next: PointRow[] = [];
    if (kind === 'exp') {
      for (let i = 1; i <= 8; i += 1) {
        next.push({ id: crypto.randomUUID(), x: String(i), y: String(Math.round(1.6 ** i * 10) / 10) });
      }
      setFitType('Exponential');
      setDegree(2);
    } else if (kind === 'poly') {
      for (let i = -4; i <= 4; i += 1) {
        next.push({ id: crypto.randomUUID(), x: String(i), y: String(i * i - 2 * i + 1) });
      }
      setFitType('Polynomial');
      setDegree(2);
    } else {
      for (let i = 0; i <= 12; i += 1) {
        const x = (i * Math.PI) / 6;
        next.push({ id: crypto.randomUUID(), x: x.toFixed(3), y: Math.sin(x).toFixed(3) });
      }
      setFitType('Sine');
      setDegree(2);
    }
    setPoints(next);
    setResult(null);
    setZoomBounds(null);
    setStatus('已载入示例数据');
  }

  return (
    <section className="fit-legacy-page">
      <div className="fit-page-wrap">
        <div className="fit-container">
          <h2 className="fit-section-title">数据输入</h2>
          <section className="fit-section-card">
        <div className="row">
          <button className="btn" onClick={addPoint}>
            添加行
          </button>
          <button className="btn secondary" onClick={clearPoints}>
            清空数据
          </button>
          <label className="btn secondary" style={{ display: 'inline-flex', alignItems: 'center' }}>
            导入 CSV/TXT
            <input type="file" accept=".csv,.txt" style={{ display: 'none' }} onChange={importCsv} />
          </label>
          <button className="btn secondary" onClick={() => applySampleData('exp')}>
            示例数据-指数
          </button>
          <button className="btn secondary" onClick={() => applySampleData('poly')}>
            示例数据-多项式
          </button>
          <button className="btn secondary" onClick={() => applySampleData('sin')}>
            示例数据-正弦
          </button>
        </div>
            <div className="fit-table-wrap">
              <table className="fit-table">
                <thead>
                  <tr>
                    <th>X</th>
                    <th>Y</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {points.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <input value={item.x} onChange={(e) => updatePoint(item.id, 'x', e.target.value)} />
                      </td>
                      <td>
                        <input value={item.y} onChange={(e) => updatePoint(item.id, 'y', e.target.value)} />
                      </td>
                      <td>
                        <button className="btn secondary" onClick={() => removePoint(item.id)}>
                          删除
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <h2 className="fit-section-title">拟合设置</h2>
          <section className="fit-section-card">
            <div className="row">
              <label className="field">
                拟合类型
                <select value={fitType} onChange={(e) => setFitType(e.target.value as typeof fitType)}>
                  <option value="Polynomial">Polynomial</option>
                  <option value="Exponential">Exponential</option>
                  <option value="Logarithmic">Logarithmic</option>
                  <option value="Sine">Sine</option>
                </select>
              </label>
              <label className="field">
                Degree
                <input type="number" value={degree} onChange={(e) => setDegree(Number(e.target.value))} />
              </label>
              <div className="field">
                <span>执行</span>
                <button className="btn" onClick={runFit}>
                  运行拟合
                </button>
              </div>
              <div className="field">
                <span>导出</span>
                <button className="btn secondary" onClick={exportResultJson}>
                  导出结果 JSON
                </button>
              </div>
              <div className="field">
                <span>导出</span>
                <button className="btn secondary" onClick={exportPointsCsv}>
                  导出数据 CSV
                </button>
              </div>
            </div>
            <p className="status">{status}</p>
          </section>

          <h2 className="fit-section-title">数据图表</h2>
          <section className="fit-section-card">
            <h3>{chartTitle}</h3>
            {chartModel ? (
              <div className="fit-chart-wrap">
                <div className="fit-chart-container">
                  <svg
                    ref={chartSvgRef}
                    width={chartModel.width}
                    height={chartModel.height}
                    className="fit-chart"
                    onMouseMove={handleChartMouseMove}
                    onMouseLeave={() => setHoverPoint(null)}
                  >
                  {showGrid
                    ? Array.from({ length: Math.max(3, tickCount) }).map((_, i, arr) => {
                        const rate = i / (arr.length - 1);
                        const y = chartModel.padding + rate * (chartModel.height - chartModel.padding * 2);
                        return <line key={`grid-${i}`} x1={chartModel.padding} y1={y} x2={chartModel.width - chartModel.padding} y2={y} className="fit-grid" />;
                      })
                    : null}
                  {Array.from({ length: Math.max(3, tickCount) }).map((_, i, arr) => {
                    const rate = i / (arr.length - 1);
                    const x = chartModel.padding + rate * (chartModel.width - chartModel.padding * 2);
                    const y = chartModel.height - chartModel.padding;
                    const value = chartModel.minX + rate * (chartModel.maxX - chartModel.minX);
                    return (
                      <g key={`x-tick-${i}`}>
                        <line x1={x} y1={y} x2={x} y2={y + 6} className="fit-axis-tick" />
                        <text x={x} y={y + 18} textAnchor="middle" className="fit-axis-label">
                          {formatAxisValue(value, chartModel.maxX - chartModel.minX)}
                        </text>
                      </g>
                    );
                  })}
                  {Array.from({ length: Math.max(3, tickCount) }).map((_, i, arr) => {
                    const rate = i / (arr.length - 1);
                    const x = chartModel.padding;
                    const y = chartModel.height - chartModel.padding - rate * (chartModel.height - chartModel.padding * 2);
                    const value = chartModel.minY + rate * (chartModel.maxY - chartModel.minY);
                    return (
                      <g key={`y-tick-${i}`}>
                        <line x1={x - 6} y1={y} x2={x} y2={y} className="fit-axis-tick" />
                        <text x={x - 10} y={y + 4} textAnchor="end" className="fit-axis-label">
                          {formatAxisValue(value, chartModel.maxY - chartModel.minY)}
                        </text>
                      </g>
                    );
                  })}
                  <line
                    x1={chartModel.padding}
                    y1={chartModel.height - chartModel.padding}
                    x2={chartModel.width - chartModel.padding}
                    y2={chartModel.height - chartModel.padding}
                    className="fit-axis"
                  />
                  <line
                    x1={chartModel.padding}
                    y1={chartModel.padding}
                    x2={chartModel.padding}
                    y2={chartModel.height - chartModel.padding}
                    className="fit-axis"
                  />
                  <polyline points={formatPoints(parsed.xData, parsed.yData)} className="fit-line-source" />
                  {result?.status === 'success' && result.x_fit && result.y_fit ? (
                    <polyline points={formatPoints(result.x_fit, result.y_fit)} className="fit-line-model" />
                  ) : null}
                  {parsed.xData.map((x, i) => {
                    const p = chartModel.toPx(x, parsed.yData[i]);
                    return <circle key={`pt-${i}`} cx={p.x} cy={p.y} r={3} className="fit-point" />;
                  })}
                  </svg>
                  {hoverPoint ? (
                    <div className="fit-tooltip" style={{ left: hoverPoint.px + 14, top: hoverPoint.py + 12 }}>
                      ({hoverPoint.x.toFixed(3)}, {hoverPoint.y.toFixed(3)})
                    </div>
                  ) : null}
                </div>
                <div className="fit-chart-meta">
                  <span>{xLabel}: [{chartModel.minX.toFixed(2)}, {chartModel.maxX.toFixed(2)}]</span>
                  <span>{yLabel}: [{chartModel.minY.toFixed(2)}, {chartModel.maxY.toFixed(2)}]</span>
                  <span>滚轮缩放：以鼠标位置为中心</span>
                </div>
              </div>
            ) : (
              <p className="status">暂无可绘制数据</p>
            )}
          </section>

          <h2 className="fit-section-title">拟合参数</h2>
          <section className="fit-section-card">
            {result?.status === 'success' ? (
              <div className="app-list">
                <div className="app-item">
                  <span>拟合函数</span>
                  <strong>{result.fit_func || '-'}</strong>
                </div>
                <div className="app-item">
                  <span>R²</span>
                  <strong>{result.r_squared ?? '-'}</strong>
                </div>
                <div className="app-item">
                  <span>系数参数</span>
                  <strong>{(result.coeffs ?? []).join(', ') || '-'}</strong>
                </div>
              </div>
            ) : (
              <p className="status">暂无成功拟合参数</p>
            )}
          </section>

          <h2 className="fit-section-title">拟合结果历史</h2>
          <section className="fit-section-card">
            {records.length === 0 ? (
              <p className="status">暂无历史结果</p>
            ) : (
              <div className="app-list">
                {records.map((record) => (
                  <div className="app-item" key={record.id}>
                    <div>
                      <strong>{record.fitType}</strong> | degree={record.degree} | R²={record.response.r_squared ?? '-'}
                    </div>
                    <button className="btn secondary" onClick={() => setRecords((prev) => prev.filter((item) => item.id !== record.id))}>
                      删除
                    </button>
                  </div>
                ))}
              </div>
            )}
            <pre className="mono status">{JSON.stringify(result, null, 2)}</pre>
          </section>
        </div>
        <aside className="fit-params-bar">
          <div className="param-title">图表参数</div>
          <div className="param-row">
            <label>图表名称</label>
            <input value={chartTitle} onChange={(e) => setChartTitle(e.target.value)} />
          </div>
          <div className="param-row">
            <label>X 轴名称</label>
            <input value={xLabel} onChange={(e) => setXLabel(e.target.value)} />
          </div>
          <div className="param-row">
            <label>Y 轴名称</label>
            <input value={yLabel} onChange={(e) => setYLabel(e.target.value)} />
          </div>
          <div className="param-row">
            <label>刻度数量</label>
            <input type="number" min={3} max={12} value={tickCount} onChange={(e) => setTickCount(Number(e.target.value))} />
          </div>
          <label className="param-row checkbox-row">
            <input type="checkbox" checked={showGrid} onChange={(e) => setShowGrid(e.target.checked)} />
            显示网格
          </label>
          <div className="param-row">
            <button type="button" className="btn secondary" onClick={resetZoom}>
              重置缩放
            </button>
          </div>
          <p className="status">图表设置会实时生效</p>
        </aside>
      </div>
    </section>
  );
}
