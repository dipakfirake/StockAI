import {
  ISeriesPrimitive,
  ISeriesPrimitivePaneRenderer,
  ISeriesPrimitivePaneView,
  SeriesAttachedParameter,
  Time,
} from 'lightweight-charts';

// Points for drawing
export interface Point {
  time: Time;
  price: number;
}

export class LineRenderer implements ISeriesPrimitivePaneRenderer {
  _p1: { x: number; y: number } | null = null;
  _p2: { x: number; y: number } | null = null;

  constructor(p1: { x: number; y: number } | null, p2: { x: number; y: number } | null) {
    this._p1 = p1;
    this._p2 = p2;
  }

  draw(target: any) {
    if (!this._p1 || !this._p2) return;
    
    target.useBitmapCoordinateSpace((scope: any) => {
      const ctx = scope.context;
      const x1 = Math.round(this._p1!.x * scope.horizontalPixelRatio);
      const y1 = Math.round(this._p1!.y * scope.verticalPixelRatio);
      const x2 = Math.round(this._p2!.x * scope.horizontalPixelRatio);
      const y2 = Math.round(this._p2!.y * scope.verticalPixelRatio);

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.strokeStyle = '#3b82f6';
      // Scale line width too
      ctx.lineWidth = Math.max(2 * scope.horizontalPixelRatio, 2);
      ctx.stroke();
      ctx.restore();
    });
  }
}

export class LineView implements ISeriesPrimitivePaneView {
  _source: TrendlinePrimitive;

  constructor(source: TrendlinePrimitive) {
    this._source = source;
  }

  zOrder(): 'normal' | 'top' | 'bottom' {
    return 'top';
  }

  renderer(): ISeriesPrimitivePaneRenderer | null {
    const p1 = this._source._p1;
    const p2 = this._source._p2;
    
    if (!p1 || !p2 || !this._source.chart || !this._source.series) return null;

    const timeScale = this._source.chart.timeScale();
    const x1 = timeScale.timeToCoordinate(p1.time);
    const x2 = timeScale.timeToCoordinate(p2.time);
    const y1 = this._source.series.priceToCoordinate(p1.price);
    const y2 = this._source.series.priceToCoordinate(p2.price);

    if (x1 === null || x2 === null || y1 === null || y2 === null) return null;

    return new LineRenderer({ x: x1, y: y1 }, { x: x2, y: y2 });
  }
}

export class TrendlinePrimitive implements ISeriesPrimitive {
  _p1: Point | null = null;
  _p2: Point | null = null;
  chart: any = null;
  series: any = null;
  _view: LineView;

  constructor(p1: Point, p2: Point) {
    this._p1 = p1;
    this._p2 = p2;
    this._view = new LineView(this);
  }

  attached(param: SeriesAttachedParameter<Time>) {
    this.chart = param.chart;
    this.series = param.series;
    this.requestUpdate();
  }

  detached() {
    this.chart = null;
    this.series = null;
  }

  paneViews() {
    return [this._view];
  }

  updateAllViews() {}

  updatePoints(p1: Point | null, p2: Point | null) {
    if (p1) this._p1 = p1;
    if (p2) this._p2 = p2;
    this.requestUpdate();
  }

  requestUpdate() {
    if (this.chart) {
      this.chart.timeScale().applyOptions({}); // forces a redraw
    }
  }
}
