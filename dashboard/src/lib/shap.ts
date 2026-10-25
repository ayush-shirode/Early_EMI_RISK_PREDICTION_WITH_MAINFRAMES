import type { Explanation } from './types';

export interface ShapFeature {
  featureName: string;
  featureKey: string;
  rawValue: string;
  shapValue: number;          // contribution in risk points (probability x 100)
  direction: 'increase' | 'decrease';
  impact: 'high' | 'medium' | 'low';
  explanation: string;
}

export interface ShapResult {
  baselineScore: number;      // average predicted risk over the background sample
  finalScore: number;
  features: ShapFeature[];
  otherFeatures: number;      // combined contribution of the features not listed
  featureCount: number;
  modelVersion: string;
  computedAt: string;
}

/** Map the backend's SHAP explanation (probability space) onto the chart's 0-100 point scale. */
export function toShapResult(e: Explanation): ShapResult {
  return {
    baselineScore: Math.round(e.base * 1000) / 10,
    finalScore: Math.round(e.probability * 100),
    features: e.features.map(f => {
      const pts = f.shap * 100;
      return {
        featureName: f.label,
        featureKey: f.key,
        rawValue: f.display,
        shapValue: Math.round(pts * 10) / 10,
        direction: pts > 0 ? 'increase' : 'decrease',
        impact: Math.abs(pts) >= 8 ? 'high' : Math.abs(pts) >= 3 ? 'medium' : 'low',
        explanation: f.phrase.charAt(0).toUpperCase() + f.phrase.slice(1) + '.',
      };
    }),
    otherFeatures: Math.round(e.otherFeaturesShap * 1000) / 10,
    featureCount: e.featureCount,
    modelVersion: e.modelVersion,
    computedAt: e.computedAt,
  };
}
