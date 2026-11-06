import { useCallback, useState } from "react";

import Cursor from "./components/Cursor.jsx";
import Sphere from "./components/Sphere.jsx";
import Splash from "./components/Splash.jsx";
import "./App.css";

export default function App() {
  const [data, setData] = useState(null);

  // Stable function, so the sphere is not rebuilt on every render.
  const pick = useCallback((destination) => {
    console.log("Picked", destination.name); // the next step opens the destination from here
  }, []);

  return (
    <>
      <Cursor />
      {data ? <Sphere destinations={data.destinations} onPick={pick} /> : <Splash onDone={setData} />}
    </>
  );
}