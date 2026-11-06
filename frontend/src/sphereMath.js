// Geometry for the photo sphere. Pure functions, no DOM, so they are easy to reason about.

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

// Spread n points evenly over a sphere (a Fibonacci sphere).
export function fibonacciSphere(n) {
  const points = [];
  for (let i = 0; i < n; i++) {
    const y = n === 1 ? 0 : 1 - (i / (n - 1)) * 2;
    const rad = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = i * GOLDEN_ANGLE;
    const x = Math.cos(theta) * rad;
    const z = Math.sin(theta) * rad;
    points.push({
      x,
      y,
      z,
      lat: (Math.asin(y) * 180) / Math.PI,
      lon: (Math.atan2(x, z) * 180) / Math.PI,
    });
  }
  return points;
}

// Sphere radius from the shorter side of the screen.
export function sphereRadius(width, height) {
  const hr = width <= 380 ? 0.38 : width <= 640 ? 0.42 : 0.46;
  const wr = width <= 380 ? 0.48 : width <= 640 ? 0.52 : 0.58;
  const floor = width <= 380 ? 108 : width <= 640 ? 120 : 155;
  return Math.max(floor, Math.min(480, height * hr, width * wr));
}

// Card width from the radius.
export function cardWidth(width, radius) {
  const scale = width <= 380 ? 0.44 : width <= 640 ? 0.46 : 0.47;
  return Math.round(Math.max(72, radius * scale));
}

// Perspective in pixels, smaller on small screens so the sphere stays dramatic.
export function perspective(width) {
  if (width <= 380) return 620;
  if (width <= 640) return 760;
  if (width <= 900) return 920;
  return 1150;
}

// Rotate a unit vector by yaw then pitch (in degrees) and return its depth, from -1 (back) to 1 (front).
export function depthOf(point, yawDeg, pitchDeg) {
  const yaw = (yawDeg * Math.PI) / 180;
  const pitch = (pitchDeg * Math.PI) / 180;

  const x1 = point.x * Math.cos(yaw) + point.z * Math.sin(yaw);
  const z1 = -point.x * Math.sin(yaw) + point.z * Math.cos(yaw);

  const y2 = -point.y * Math.cos(pitch) - z1 * Math.sin(pitch);
  const z2 = -point.y * Math.sin(pitch) + z1 * Math.cos(pitch);

  return { depth: z2, x: x1, y: y2 };
}

// Region to hue, so each part of India has its own colour.
const REGION_HUE = {
  North: 24,
  Himalaya: 200,
  West: 340,
  Central: 42,
  East: 150,
  South: 168,
  Islands: 186,
  "North-East": 128,
};

export function hueFor(region) {
  return REGION_HUE[region] ?? 30;
}