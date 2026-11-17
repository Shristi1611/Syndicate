// The camera of the Earth video's last frame, and the maths to draw things exactly where the video
// shows them. The video was rendered looking straight down at 82 degrees east, 22 degrees north.
export const FRAME = 1080; // the video is a 1080 x 1080 square
export const LON0 = 82;
export const LAT0 = 22;
export const RADIUS = 0.455 * FRAME; // how big the globe is in the last frame, in pixels

const rad = (degrees) => (degrees * Math.PI) / 180;
const SIN_P0 = Math.sin(rad(LAT0));
const COS_P0 = Math.cos(rad(LAT0));

// Where a place on Earth lands in the 1080 x 1080 frame.
export function project(lon, lat) {
  const l = rad(lon - LON0);
  const p = rad(lat);
  const x = Math.cos(p) * Math.sin(l);
  const y = COS_P0 * Math.sin(p) - SIN_P0 * Math.cos(p) * Math.cos(l);
  const facingUs = SIN_P0 * Math.sin(p) + COS_P0 * Math.cos(p) * Math.cos(l) > 0;
  return { x: FRAME / 2 + RADIUS * x, y: FRAME / 2 - RADIUS * y, visible: facingUs };
}

// A GeoJSON polygon, or several, as one SVG path in frame coordinates.
export function geometryToPath(geometry) {
  const polygons = geometry.type === "MultiPolygon" ? geometry.coordinates : [geometry.coordinates];
  let d = "";
  for (const polygon of polygons) {
    for (const ring of polygon) {
      let started = false;
      for (const [lon, lat] of ring) {
        const point = project(lon, lat);
        if (!point.visible) continue; // the far side of the planet is not drawn
        d += `${started ? "L" : "M"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
        started = true;
      }
      if (started) d += "Z";
    }
  }
  return d;
}

// How far to zoom, and where to centre, so that a shape fills most of the screen.
export function fitView(geometry, heightShare = 0.8, widthShare = 0.68) {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  const polygons = geometry.type === "MultiPolygon" ? geometry.coordinates : [geometry.coordinates];
  for (const polygon of polygons) {
    for (const ring of polygon) {
      for (const [lon, lat] of ring) {
        const { x, y, visible } = project(lon, lat);
        if (!visible) continue;
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minY = Math.min(minY, y);
        maxY = Math.max(maxY, y);
      }
    }
  }
  const width = maxX - minX;
  const height = maxY - minY;
  return {
    cx: (minX + maxX) / 2,
    cy: (minY + maxY) / 2,
    k: Math.min((heightShare * FRAME) / height, (widthShare * FRAME) / width),
    width,
    height,
  };
}