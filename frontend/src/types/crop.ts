export interface CropCoordinates {
  left: number;   // pixels in original image space
  top: number;
  width: number;
  height: number;
}

export interface CropState {
  imageId: string;
  coordinates: CropCoordinates;
  rotation: number;       // 0, 90, 180, 270
  flipH: boolean;
  flipV: boolean;
  targetBucket: [number, number];  // [width, height] of assigned bucket
  included: boolean;       // true = in dataset, false = excluded
}

export type BucketSize = 512 | 768 | 1024;

export interface BucketOption {
  width: number;
  height: number;
  label: string;    // e.g. "512x768 (2:3)"
  aspectRatio: number;
}

/**
 * Mirror of klippbok/config/model_profiles.py generate_buckets().
 * Step size 64, min 256, max = baseResolution * 2, max aspect ratio 2.0.
 * Generates both portrait and landscape orientations.
 */
export function generateBuckets(
  baseResolution: BucketSize,
  allowNonSquare: boolean,
): [number, number][] {
  const pixelBudget = baseResolution * baseResolution;
  const step = 64;
  const min = 256;
  const max = baseResolution * 2;
  const seen = new Set<string>();
  const result: [number, number][] = [];

  for (let w = min; w <= max; w += step) {
    const h = Math.floor(Math.floor(pixelBudget / w) / step) * step;
    const clampedH = Math.min(h, max);
    if (clampedH < min) continue;

    const ratio = Math.max(w, clampedH) / Math.min(w, clampedH);
    if (ratio > 2.0) continue;

    if (allowNonSquare || w === clampedH) {
      const key = `${w}x${clampedH}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push([w, clampedH]);
      }
      if (w !== clampedH) {
        const key2 = `${clampedH}x${w}`;
        if (!seen.has(key2)) {
          seen.add(key2);
          result.push([clampedH, w]);
        }
      }
    }
  }

  return result.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
}

/**
 * Mirror of klippbok/image/bucket.py assign_to_bucket().
 * Returns the bucket with the smallest absolute aspect ratio difference.
 */
export function snapToNearestBucket(
  width: number,
  height: number,
  buckets: [number, number][],
): [number, number] {
  const ar = width / height;
  return buckets.reduce((best, b) => {
    const diff = Math.abs(b[0] / b[1] - ar);
    const bestDiff = Math.abs(best[0] / best[1] - ar);
    return diff < bestDiff ? b : best;
  });
}

/**
 * Returns true if either image dimension is smaller than the target bucket dimension,
 * meaning the image would need to be upscaled to fill the bucket.
 */
export function needsUpscale(
  imageW: number,
  imageH: number,
  bucketW: number,
  bucketH: number,
): boolean {
  return imageW < bucketW || imageH < bucketH;
}
